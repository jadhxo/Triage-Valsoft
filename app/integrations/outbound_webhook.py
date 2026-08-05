from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from app.repositories.records import RecordsRepository
from app.schemas import FinalTriageRecord


class HTTPClient(Protocol):
    def post(self, url: str, *, json: object, timeout: float) -> httpx.Response: ...


@dataclass(frozen=True)
class DeliveryResult:
    status: str
    attempts: int


class OutboundWebhook:
    def __init__(
        self,
        *,
        repository: RecordsRepository,
        url: str | None,
        timeout_seconds: float,
        max_attempts: int,
        client: HTTPClient | None = None,
    ) -> None:
        self.repository = repository
        self.url = url
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.client = client or httpx.Client()

    def deliver(self, record: FinalTriageRecord) -> DeliveryResult:
        if not self.url:
            return DeliveryResult("not_configured", 0)

        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.client.post(
                    self.url,
                    json=record.model_dump(mode="json"),
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                self.repository.record_delivery_attempt(
                    event_id=record.event_id,
                    attempt_number=attempt,
                    success=True,
                    status_code=response.status_code,
                    error=None,
                )
                return DeliveryResult("delivered", attempt)
            except httpx.HTTPError as exc:
                status_code = (
                    exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                )
                self.repository.record_delivery_attempt(
                    event_id=record.event_id,
                    attempt_number=attempt,
                    success=False,
                    status_code=status_code,
                    error=str(exc),
                )
        return DeliveryResult("failed", self.max_attempts)
