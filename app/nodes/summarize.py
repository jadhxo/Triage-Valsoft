from __future__ import annotations

from app.llm.base import LLMProvider
from app.schemas import SummaryOutput
from app.state import TriageState


def fallback_summary(state: TriageState) -> str:
    team = state.get("final_destination", "Human Review")
    issue = (
        state.get("core_issue") or "The request could not be safely classified from model output."
    )
    escalation = (
        f" Escalation is required: {', '.join(state.get('escalation_reasons', []))}."
        if state.get("escalation_required")
        else ""
    )
    return f"For {team}: {issue}{escalation}"


def generate_summary(
    state: TriageState, *, provider: LLMProvider, summary_prompt: str
) -> TriageState:
    if not state.get("analysis_valid"):
        return {"summary": fallback_summary(state)}
    context = {
        "category": state["category"],
        "priority": state["priority"],
        "core_issue": state["core_issue"],
        "identifiers": state["identifiers"],
        "urgency_signal": state["urgency_signal"],
        "original_destination": state["original_destination"],
        "final_destination": state["final_destination"],
        "escalation_required": state["escalation_required"],
        "escalation_reasons": state["escalation_reasons"],
    }
    try:
        result = SummaryOutput.model_validate(provider.summarize(context, summary_prompt))
        return {"summary": result.summary}
    except Exception:
        return {"summary": fallback_summary(state)}
