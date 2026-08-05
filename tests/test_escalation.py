from decimal import Decimal

import pytest

from app.policies.escalation import evaluate_escalation, extract_billing_discrepancy
from app.schemas import Category


def decide(**overrides):
    values = {
        "category": Category.BUG_REPORT,
        "confidence": 0.9,
        "message": "One customer reports an issue.",
    }
    values.update(overrides)
    return evaluate_escalation(**values)


def test_confidence_boundary():
    assert "low_confidence" in decide(confidence=0.69).reasons
    assert "low_confidence" not in decide(confidence=0.70).reasons


def test_incident_and_multiple_users_accumulate():
    result = decide(
        category=Category.INCIDENT_OUTAGE,
        message="The dashboard is down. Multiple users affected.",
    )
    assert result.reasons == ["incident_or_outage", "multiple_users_affected"]


@pytest.mark.parametrize(
    ("message", "expected", "escalates"),
    [
        ("Billing discrepancy is $600.", Decimal("600"), True),
        ("Billing discrepancy is $500.", Decimal("500"), False),
        (
            "Invoice #8821 shows a charge of $1,240 but our contract rate is $980/month.",
            Decimal("260"),
            False,
        ),
    ],
)
def test_billing_threshold(message, expected, escalates):
    result = decide(category=Category.BILLING_ISSUE, message=message)
    assert result.billing_discrepancy == expected
    assert ("billing_discrepancy_over_500" in result.reasons) is escalates


def test_ambiguous_amount_has_no_calculated_discrepancy():
    assert extract_billing_discrepancy("The invoice contains $700.") is None


def test_invalid_model_output_escalates():
    result = decide(category=None, confidence=None, model_output_invalid=True, unsafe_to_route=True)
    assert result.reasons == ["model_output_invalid", "unsafe_to_route"]
