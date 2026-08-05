import pytest

from app.policies.routing import destination_for
from app.schemas import Category


@pytest.mark.parametrize(
    ("category", "destination"),
    [
        (Category.BUG_REPORT, "Engineering"),
        (Category.FEATURE_REQUEST, "Product"),
        (Category.BILLING_ISSUE, "Billing"),
        (Category.TECHNICAL_QUESTION, "Technical Support"),
        (Category.INCIDENT_OUTAGE, "Engineering - Incident Response"),
    ],
)
def test_routing_table(category, destination):
    assert destination_for(category) == destination
