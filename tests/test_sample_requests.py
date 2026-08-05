import json
from pathlib import Path

from app.llm.fake import FakeLLMProvider
from app.schemas import FinalTriageRecord, InboundWebhook
from app.services.container import build_services


def test_all_assessment_samples(settings):
    services = build_services(settings, provider=FakeLLMProvider())
    samples = json.loads(Path("data/sample_requests.json").read_text(encoding="utf-8"))
    for item in samples:
        payload = InboundWebhook.model_validate(item)
        services.events.accept(payload)
        services.processor.process_event(payload.event_id)

    records = {
        record.event_id: FinalTriageRecord.model_validate(record)
        for record in services.records.list_all()
    }
    assert len(records) == 5
    assert records["sample-001"].category.value == "Bug Report"
    assert records["sample-001"].final_destination == "Engineering"
    assert "403" in records["sample-001"].identifiers.error_codes
    assert records["sample-001"].identifiers.account_urls
    assert records["sample-002"].final_destination == "Product"
    assert "bulk export" in records["sample-002"].core_issue.lower()
    assert records["sample-003"].final_destination == "Billing"
    assert records["sample-003"].billing_discrepancy == "260"
    assert records["sample-003"].identifiers.invoice_numbers == ["8821"]
    assert records["sample-004"].final_destination == "Technical Support"
    assert records["sample-004"].identifiers.auth_providers == ["Okta"]
    assert records["sample-005"].priority.value == "High"
    assert records["sample-005"].original_destination == "Engineering - Incident Response"
    assert records["sample-005"].final_destination == "Human Review"
    assert set(records["sample-005"].escalation_reasons) >= {
        "incident_or_outage",
        "multiple_users_affected",
    }
    assert all(record.analysis_provider == "fake" for record in records.values())
