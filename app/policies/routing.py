from app.schemas import Category

ROUTING_TABLE: dict[Category, str] = {
    Category.BUG_REPORT: "Engineering",
    Category.FEATURE_REQUEST: "Product",
    Category.BILLING_ISSUE: "Billing",
    Category.TECHNICAL_QUESTION: "Technical Support",
    Category.INCIDENT_OUTAGE: "Engineering - Incident Response",
}


def destination_for(category: Category) -> str:
    return ROUTING_TABLE[category]
