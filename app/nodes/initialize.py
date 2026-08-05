from __future__ import annotations

from datetime import UTC, datetime

from app.state import TriageState


def initialize_state(state: TriageState) -> TriageState:
    return {
        "request_id": state["event_id"],
        "processing_started_at": datetime.now(UTC).isoformat(),
        "retry_count": 0,
        "analysis_valid": False,
        "validation_errors": [],
        "identifiers": {},
        "escalation_required": False,
        "escalation_reasons": [],
        "outbound_delivery_status": "pending",
        "outbound_delivery_attempts": 0,
        "status": "processing",
        "error": None,
    }
