from __future__ import annotations

from datetime import UTC, datetime

from app.integrations.outbound_webhook import OutboundWebhook
from app.outputs import OutputWriter
from app.repositories.events import EventsRepository
from app.repositories.records import RecordsRepository
from app.schemas import FinalTriageRecord
from app.state import TriageState


def record_from_state(state: TriageState) -> FinalTriageRecord:
    return FinalTriageRecord(
        event_id=state["event_id"],
        request_id=state["request_id"],
        source=state["source"],
        raw_message=state["raw_message"],
        normalized_message=state["normalized_message"],
        category=state.get("category"),
        priority=state.get("priority"),
        confidence=state.get("confidence"),
        core_issue=state.get("core_issue"),
        identifiers=state.get("identifiers", {}),
        urgency_signal=state.get("urgency_signal"),
        original_destination=state.get("original_destination"),
        final_destination=state["final_destination"],
        escalation_required=state["escalation_required"],
        escalation_reasons=state["escalation_reasons"],
        summary=state["summary"],
        billing_discrepancy=state.get("billing_discrepancy"),
        status="completed",
        received_at=state["received_at"],
        processing_started_at=state["processing_started_at"],
        processing_completed_at=datetime.now(UTC),
        outbound_delivery_status=(
            "pending" if state["outbound_delivery_status"] == "pending" else "not_configured"
        ),
        outbound_delivery_attempts=0,
        analysis_provider=state["analysis_provider"],
        analysis_model=state["analysis_model"],
        error=None,
    )


def persist_result(
    state: TriageState,
    *,
    records: RecordsRepository,
    events: EventsRepository,
    writer: OutputWriter,
) -> TriageState:
    record = record_from_state(state)
    records.save(record)
    events.set_status(record.event_id, "completed")
    writer.sync_queues(records)
    return {
        "processing_completed_at": record.processing_completed_at.isoformat(),
        "status": "completed",
    }


def deliver_outbound_webhook(
    state: TriageState,
    *,
    records: RecordsRepository,
    outbound: OutboundWebhook,
) -> TriageState:
    record = records.get(state["event_id"])
    if record is None:
        raise RuntimeError("Persisted record is unavailable before outbound delivery")
    result = outbound.deliver(record)
    return {
        "outbound_delivery_status": result.status,
        "outbound_delivery_attempts": result.attempts,
    }


def mark_complete(
    state: TriageState,
    *,
    records: RecordsRepository,
    events: EventsRepository,
    writer: OutputWriter,
) -> TriageState:
    delivery_status = state["outbound_delivery_status"]
    status = "completed_with_delivery_failure" if delivery_status == "failed" else "completed"
    updated = records.update_delivery(
        state["event_id"], delivery_status, state["outbound_delivery_attempts"], status
    )
    events.set_status(state["event_id"], status)
    writer.sync_queues(records)
    return {
        "status": status,
        "processing_completed_at": updated.processing_completed_at.isoformat(),
    }
