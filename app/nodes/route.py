from __future__ import annotations

from app.policies.escalation import evaluate_escalation
from app.policies.routing import destination_for
from app.schemas import Category
from app.state import TriageState


def force_escalation(state: TriageState) -> TriageState:
    decision = evaluate_escalation(
        category=None,
        confidence=None,
        message=state["normalized_message"],
        model_output_invalid=True,
        unsafe_to_route=True,
    )
    return {
        "category": None,
        "priority": None,
        "confidence": None,
        "core_issue": None,
        "identifiers": {},
        "urgency_signal": None,
        "original_destination": None,
        "final_destination": "Human Review",
        "escalation_required": True,
        "escalation_reasons": decision.reasons,
        "billing_discrepancy": None,
    }


def apply_policy(state: TriageState) -> TriageState:
    category = Category(state["category"])
    original = destination_for(category)
    decision = evaluate_escalation(
        category=category,
        confidence=state.get("confidence"),
        message=state["normalized_message"],
    )
    return {
        "original_destination": original,
        "final_destination": "Human Review" if decision.required else original,
        "escalation_required": decision.required,
        "escalation_reasons": decision.reasons,
        "billing_discrepancy": (
            str(decision.billing_discrepancy) if decision.billing_discrepancy is not None else None
        ),
    }


def select_destination(state: TriageState) -> TriageState:
    return {"selected_queue": state["final_destination"]}


def destination_route(state: TriageState) -> str:
    return "human_review" if state["final_destination"] == "Human Review" else "standard_queue"


def human_review(state: TriageState) -> TriageState:
    return {"selected_queue": "Human Review"}


def standard_queue(state: TriageState) -> TriageState:
    return {"selected_queue": state["final_destination"]}
