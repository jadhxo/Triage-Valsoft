import json

from fastapi.testclient import TestClient

from app.factory import create_app
from app.llm.fake import FakeLLMProvider


class CountingProvider(FakeLLMProvider):
    def __init__(self):
        self.analysis_calls = 0

    def analyze(self, message, system_prompt):
        self.analysis_calls += 1
        return super().analyze(message, system_prompt)


def test_duplicate_does_not_reprocess_or_duplicate_queue(settings, payload, auth_headers):
    provider = CountingProvider()
    app = create_app(settings, provider=provider)
    with TestClient(app) as client:
        first = client.post("/webhooks/intake", json=payload, headers=auth_headers)
        second = client.post("/webhooks/intake", json=payload, headers=auth_headers)

    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["status"] == "completed"
    assert provider.analysis_calls == 1
    queue_path = settings.output_dir / "queues" / "engineering.jsonl"
    lines = [json.loads(line) for line in queue_path.read_text().splitlines() if line]
    assert [line["event_id"] for line in lines] == ["evt-001"]
