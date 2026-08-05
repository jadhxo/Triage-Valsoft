from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.schemas import Category

LOW_CONFIDENCE_THRESHOLD = 0.70
BILLING_ESCALATION_THRESHOLD = Decimal("500")

_BROAD_IMPACT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bmultiple\s+(?:customers?|users?|accounts?|teams?|organizations?|orgs?)\s+(?:are\s+)?affected\b",
        r"\ball\s+(?:customers?|users?|accounts?|teams?)\b",
        r"\bdown\s+for\s+everyone\b",
        r"\bcompany[- ]wide\b",
        r"\borganization[- ]wide\b",
    )
)
_MONEY = r"\$\s*([0-9][0-9,]*(?:\.\d{1,2})?)"
_EXPLICIT_DIFFERENCE = re.compile(
    rf"\b(?:difference|discrepancy|overcharge|overcharged)\b[^$\n]{{0,40}}{_MONEY}", re.IGNORECASE
)
_CHARGE = re.compile(
    rf"\b(?:invoice\s+amount|invoice|charge|charged|billed)\b[^$\n]{{0,40}}{_MONEY}", re.IGNORECASE
)
_CONTRACT = re.compile(
    rf"\b(?:contract\s+(?:amount|rate)|contract|agreed\s+(?:amount|rate)|rate)\b[^$\n]{{0,40}}{_MONEY}",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EscalationDecision:
    required: bool
    reasons: list[str]
    billing_discrepancy: Decimal | None


def _decimal(match: re.Match[str] | None) -> Decimal | None:
    if match is None:
        return None
    try:
        return Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None


def extract_billing_discrepancy(message: str) -> Decimal | None:
    explicit = _decimal(_EXPLICIT_DIFFERENCE.search(message))
    if explicit is not None:
        return explicit

    charge = _decimal(_CHARGE.search(message))
    contract = _decimal(_CONTRACT.search(message))
    if charge is None or contract is None:
        return None
    return abs(charge - contract)


def has_broad_impact(message: str) -> bool:
    return any(pattern.search(message) for pattern in _BROAD_IMPACT_PATTERNS)


def evaluate_escalation(
    *,
    category: Category | None,
    confidence: float | None,
    message: str,
    model_output_invalid: bool = False,
    unsafe_to_route: bool = False,
) -> EscalationDecision:
    reasons: list[str] = []
    discrepancy = (
        extract_billing_discrepancy(message) if category == Category.BILLING_ISSUE else None
    )

    if confidence is not None and confidence < LOW_CONFIDENCE_THRESHOLD:
        reasons.append("low_confidence")
    if category == Category.INCIDENT_OUTAGE:
        reasons.append("incident_or_outage")
    if has_broad_impact(message):
        reasons.append("multiple_users_affected")
    if discrepancy is not None and discrepancy > BILLING_ESCALATION_THRESHOLD:
        reasons.append("billing_discrepancy_over_500")
    if model_output_invalid:
        reasons.append("model_output_invalid")
    if unsafe_to_route:
        reasons.append("unsafe_to_route")

    return EscalationDecision(bool(reasons), reasons, discrepancy)
