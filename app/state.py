from __future__ import annotations

from typing import Any, TypedDict


class TriageState(TypedDict, total=False):
    event_id: str
    request_id: str
    source: str
    raw_message: str
    normalized_message: str
    received_at: str
    processing_started_at: str
    processing_completed_at: str
    category: str | None
    priority: str | None
    confidence: float | None
    core_issue: str | None
    identifiers: dict[str, list[str]]
    urgency_signal: str | None
    original_destination: str | None
    final_destination: str
    escalation_required: bool
    escalation_reasons: list[str]
    summary: str
    billing_discrepancy: str | None
    analysis_candidate: Any
    analysis_valid: bool
    validation_errors: list[str]
    retry_count: int
    outbound_delivery_status: str
    outbound_delivery_attempts: int
    analysis_provider: str
    analysis_model: str
    error: str | None
    status: str
    selected_queue: str
