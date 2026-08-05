from __future__ import annotations

from collections import deque
from typing import Any

from app.llm.fake import FakeLLMProvider
from app.schemas import LLMAnalysis
from app.services.container import build_services


class ScriptedProvider(FakeLLMProvider):
    provider_name = "scripted"
    model_name = "test-model"

    def __init__(self, analyses: list[Any], *, summary_fails: bool = False):
        self.analyses = deque(analyses)
        self.repair_calls = 0
        self.summary_fails = summary_fails

    def analyze(self, message: str, system_prompt: str) -> Any:
        del message, system_prompt
        return self.analyses.popleft()

    def repair(self, message, candidate, validation_errors, system_prompt):
        del message, candidate, validation_errors, system_prompt
        self.repair_calls += 1
        return self.analyses.popleft()

    def summarize(self, validated_context, system_prompt):
        if self.summary_fails:
            raise RuntimeError("summary unavailable")
        return super().summarize(validated_context, system_prompt)


def valid_analysis(category: str = "Bug Report", confidence: float = 0.9) -> dict[str, Any]:
    return {
        "category": category,
        "priority": "High" if category == "Incident/Outage" else "Medium",
        "confidence": confidence,
        "core_issue": "A validated issue.",
        "identifiers": {},
        "urgency_signal": "high" if category == "Incident/Outage" else "moderate",
    }


def process(settings, provider, message="A customer reports a product bug."):
    services = build_services(settings, provider=provider)
    from app.schemas import InboundWebhook

    payload = InboundWebhook(event_id="graph-001", source="Email", message=message)
    services.events.accept(payload)
    record = services.processor.process_event(payload.event_id)
    return services, record


def history_nodes(services) -> set[str]:
    snapshots = services.processor.graph.get_state_history(
        {"configurable": {"thread_id": "graph-001"}}
    )
    nodes: set[str] = set()
    for snapshot in snapshots:
        nodes.update(snapshot.next)
    return nodes


def test_valid_analysis_uses_normal_path(settings):
    services, record = process(settings, ScriptedProvider([valid_analysis()]))
    assert record.final_destination == "Engineering"
    assert "repair_analysis" not in history_nodes(services)


def test_invalid_first_analysis_repairs_then_continues(settings):
    provider = ScriptedProvider([{"category": "wrong"}, valid_analysis()])
    services, record = process(settings, provider)
    assert provider.repair_calls == 1
    assert record.final_destination == "Engineering"
    assert "repair_analysis" in history_nodes(services)


def test_invalid_repair_forces_human_review_once(settings):
    provider = ScriptedProvider([{"bad": True}, {"still": "bad"}])
    services, record = process(settings, provider)
    assert provider.repair_calls == 1
    assert record.final_destination == "Human Review"
    assert "model_output_invalid" in record.escalation_reasons
    assert "force_escalation" in history_nodes(services)


def test_incident_reaches_human_review(settings):
    _, record = process(
        settings,
        ScriptedProvider([valid_analysis("Incident/Outage")]),
        "The dashboard is down for everyone.",
    )
    assert record.original_destination == "Engineering - Incident Response"
    assert record.final_destination == "Human Review"


def test_summary_failure_uses_deterministic_fallback(settings):
    _, record = process(settings, ScriptedProvider([valid_analysis()], summary_fails=True))
    assert record.summary.startswith("For Engineering:")


def test_llm_analysis_schema_rejects_invalid_candidate():
    try:
        LLMAnalysis.model_validate({"category": "not-real"})
    except Exception:
        pass
    else:
        raise AssertionError("Invalid structured output was accepted")
