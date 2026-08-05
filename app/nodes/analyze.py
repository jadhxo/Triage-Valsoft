from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.llm.base import LLMProvider
from app.schemas import LLMAnalysis
from app.state import TriageState


def analyze_request(
    state: TriageState, *, provider: LLMProvider, triage_prompt: str
) -> TriageState:
    try:
        candidate = provider.analyze(state["normalized_message"], triage_prompt)
        return {"analysis_candidate": candidate}
    except Exception as exc:
        return {
            "analysis_candidate": None,
            "validation_errors": [f"provider_error: {type(exc).__name__}: {exc}"],
        }


def validate_analysis(state: TriageState) -> TriageState:
    try:
        analysis = LLMAnalysis.model_validate(state.get("analysis_candidate"))
    except ValidationError as exc:
        existing = state.get("validation_errors", [])
        return {
            "analysis_valid": False,
            "validation_errors": existing + [error["msg"] for error in exc.errors()],
        }
    return {
        "analysis_valid": True,
        "validation_errors": [],
        "category": analysis.category.value,
        "priority": analysis.priority.value,
        "confidence": analysis.confidence,
        "core_issue": analysis.core_issue,
        "identifiers": analysis.identifiers.model_dump(),
        "urgency_signal": analysis.urgency_signal.value,
    }


def repair_analysis(
    state: TriageState, *, provider: LLMProvider, triage_prompt: str
) -> TriageState:
    retry_count = state.get("retry_count", 0) + 1
    candidate: Any = state.get("analysis_candidate")
    try:
        repaired = provider.repair(
            state["normalized_message"],
            candidate,
            state.get("validation_errors", []),
            triage_prompt,
        )
        return {
            "analysis_candidate": repaired,
            "validation_errors": [],
            "retry_count": retry_count,
        }
    except Exception as exc:
        return {
            "analysis_candidate": None,
            "validation_errors": [f"provider_error: {type(exc).__name__}: {exc}"],
            "retry_count": retry_count,
        }


def validation_route(state: TriageState) -> str:
    if state.get("analysis_valid"):
        return "valid"
    if state.get("retry_count", 0) < 1:
        return "repair"
    return "invalid"
