from __future__ import annotations

import logging
from typing import Any

from app.repositories.events import EventsRepository
from app.repositories.records import RecordsRepository
from app.schemas import FinalTriageRecord, InboundWebhook

logger = logging.getLogger(__name__)


class TriageProcessor:
    def __init__(
        self,
        *,
        graph: Any,
        events: EventsRepository,
        records: RecordsRepository,
        provider_name: str,
        model_name: str,
    ) -> None:
        self.graph = graph
        self.events = events
        self.records = records
        self.provider_name = provider_name
        self.model_name = model_name

    def process_event(self, event_id: str) -> FinalTriageRecord | None:
        event = self.events.get(event_id)
        if event is None:
            raise KeyError(f"Unknown accepted event: {event_id}")
        payload = InboundWebhook.model_validate(event.payload)
        self.events.set_status(event_id, "processing")
        initial_state = {
            "event_id": event_id,
            "source": payload.source.value,
            "raw_message": payload.message,
            "received_at": payload.effective_received_at().isoformat(),
            "analysis_provider": self.provider_name,
            "analysis_model": self.model_name,
            "outbound_delivery_status": "pending",
        }
        try:
            self.graph.invoke(
                initial_state,
                config={"configurable": {"thread_id": event_id}},
            )
        except Exception as exc:
            logger.exception("Triage processing failed event_id=%s", event_id)
            self.events.set_status(event_id, "failed", f"{type(exc).__name__}: {exc}")
            return self.records.get(event_id)
        return self.records.get(event_id)
