from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(str, Enum):
    EMAIL = "Email"
    WEB_FORM = "Web Form"
    SUPPORT_PORTAL = "Support Portal"


class Category(str, Enum):
    BUG_REPORT = "Bug Report"
    FEATURE_REQUEST = "Feature Request"
    BILLING_ISSUE = "Billing Issue"
    TECHNICAL_QUESTION = "Technical Question"
    INCIDENT_OUTAGE = "Incident/Outage"


class Priority(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class UrgencySignal(str, Enum):
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class Identifiers(StrictModel):
    account_ids: list[str] = Field(default_factory=list)
    account_urls: list[str] = Field(default_factory=list)
    invoice_numbers: list[str] = Field(default_factory=list)
    error_codes: list[str] = Field(default_factory=list)
    amounts: list[str] = Field(default_factory=list)
    timestamps: list[str] = Field(default_factory=list)
    auth_providers: list[str] = Field(default_factory=list)
    other: list[str] = Field(default_factory=list)


class InboundWebhook(StrictModel):
    event_id: str = Field(min_length=1, max_length=128)
    source: Source
    message: str = Field(min_length=1, max_length=10_000)
    received_at: datetime | None = None

    @field_validator("event_id")
    @classmethod
    def normalize_event_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @field_validator("message")
    @classmethod
    def reject_blank_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("received_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("received_at must include a timezone")
        return value

    def effective_received_at(self) -> datetime:
        return self.received_at or datetime.now(UTC)


class LLMAnalysis(StrictModel):
    category: Category
    priority: Priority
    confidence: float = Field(ge=0.0, le=1.0)
    core_issue: str = Field(min_length=1, max_length=500)
    identifiers: Identifiers
    urgency_signal: UrgencySignal

    @field_validator("core_issue")
    @classmethod
    def reject_blank_issue(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("core_issue must not be blank")
        return value.strip()


class SummaryOutput(StrictModel):
    summary: str = Field(min_length=1, max_length=1_000)


class FinalTriageRecord(StrictModel):
    event_id: str
    request_id: str
    source: Source
    raw_message: str
    normalized_message: str
    category: Category | None
    priority: Priority | None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    core_issue: str | None
    identifiers: Identifiers
    urgency_signal: UrgencySignal | None
    original_destination: str | None
    final_destination: str
    escalation_required: bool
    escalation_reasons: list[str]
    summary: str
    billing_discrepancy: str | None = None
    status: str
    received_at: datetime
    processing_started_at: datetime
    processing_completed_at: datetime | None
    outbound_delivery_status: str
    outbound_delivery_attempts: int = 0
    analysis_provider: str
    analysis_model: str
    error: str | None = None


class IntakeResponse(StrictModel):
    accepted: bool = True
    duplicate: bool
    event_id: str
    status: str


class RequestStatusResponse(StrictModel):
    event_id: str
    status: str
    error: str | None = None
    record: FinalTriageRecord | None = None


class HealthResponse(StrictModel):
    status: str = "ok"
