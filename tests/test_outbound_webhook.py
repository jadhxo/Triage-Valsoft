from __future__ import annotations

import httpx

from app.llm.fake import FakeLLMProvider
from app.schemas import InboundWebhook
from app.services.container import build_services


class RecordingClient:
    def __init__(self, *, status_code: int, records=None):
        self.status_code = status_code
        self.calls = 0
        self.records = records
        self.persisted_before_delivery = False

    def post(self, url, *, json, timeout):
        del timeout
        self.calls += 1
        if self.records is not None:
            self.persisted_before_delivery = self.records.get(json["event_id"]) is not None
        request = httpx.Request("POST", url)
        return httpx.Response(self.status_code, request=request)


def run(settings, client=None):
    services = build_services(settings, provider=FakeLLMProvider(), http_client=client)
    payload = InboundWebhook(event_id="delivery-001", source="Email", message="A 403 error occurs.")
    services.events.accept(payload)
    return services, services.processor.process_event(payload.event_id)


def test_delivery_skipped_when_not_configured(settings):
    services, record = run(settings)
    assert record.outbound_delivery_status == "not_configured"
    assert services.records.count_delivery_attempts(record.event_id) == 0


def test_successful_delivery_and_persistence_order(settings):
    settings = settings.model_copy(update={"outbound_webhook_url": "https://example.test/hook"})
    services = build_services(settings, provider=FakeLLMProvider())
    client = RecordingClient(status_code=204, records=services.records)
    services.outbound.client = client
    payload = InboundWebhook(event_id="delivery-001", source="Email", message="A 403 error occurs.")
    services.events.accept(payload)
    record = services.processor.process_event(payload.event_id)
    assert record.outbound_delivery_status == "delivered"
    assert client.calls == 1
    assert client.persisted_before_delivery is True


def test_failure_is_bounded_and_record_remains(settings):
    settings = settings.model_copy(
        update={"outbound_webhook_url": "https://example.test/hook", "outbound_max_attempts": 2}
    )
    client = RecordingClient(status_code=503)
    services, record = run(settings, client)
    assert client.calls == 2
    assert record.status == "completed_with_delivery_failure"
    assert record.outbound_delivery_status == "failed"
    assert services.records.get(record.event_id) is not None
    assert services.records.count_delivery_attempts(record.event_id) == 2
