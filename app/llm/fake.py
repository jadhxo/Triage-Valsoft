from __future__ import annotations

import re
from typing import Any

from app.schemas import Category, Identifiers, LLMAnalysis, Priority, SummaryOutput, UrgencySignal


def _identifiers(message: str) -> Identifiers:
    lower = message.lower()
    urls = re.findall(r"(?:https?://)?(?:[\w-]+\.)+[a-z]{2,}/[^\s,.]+", message, re.IGNORECASE)
    error_codes = re.findall(r"\b(?:[45]\d{2}|[A-Z][A-Z0-9_-]*\d[A-Z0-9_-]*)\b", message)
    invoice_numbers = re.findall(r"invoice\s*#?\s*([A-Z0-9-]+)", message, re.IGNORECASE)
    amounts = re.findall(r"\$\s*([0-9][0-9,]*(?:\.\d{1,2})?)", message)
    timestamps = re.findall(
        r"\b(?:around\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)(?:\s+[A-Z]{2,4})?\b",
        message,
        re.IGNORECASE,
    )
    auth = [
        provider
        for provider in ("Okta", "Auth0", "Azure AD", "Google")
        if provider.lower() in lower
    ]
    return Identifiers(
        account_urls=urls,
        invoice_numbers=invoice_numbers,
        error_codes=error_codes,
        amounts=[value.replace(",", "") for value in amounts],
        timestamps=timestamps,
        auth_providers=auth,
    )


class FakeLLMProvider:
    provider_name = "fake"
    model_name = "deterministic-demo"

    def analyze(self, message: str, system_prompt: str) -> dict[str, Any]:
        del system_prompt
        lower = message.lower()
        identifiers = _identifiers(message)
        if any(term in lower for term in ("stopped loading", "down for everyone", "outage")):
            category = Category.INCIDENT_OUTAGE
            priority = Priority.HIGH
            urgency = UrgencySignal.HIGH
            issue = "The dashboard is unavailable and is affecting multiple users."
            confidence = 0.97
        elif "invoice" in lower or "charge" in lower or "billing" in lower:
            category = Category.BILLING_ISSUE
            priority = Priority.MEDIUM
            urgency = UrgencySignal.MODERATE
            issue = "The customer reports an invoice charge that differs from the contract rate."
            confidence = 0.98
        elif any(term in lower for term in ("feature", "we'd love", "would save us")):
            category = Category.FEATURE_REQUEST
            priority = Priority.LOW
            urgency = UrgencySignal.LOW
            issue = "The customer requests bulk export for audit logs."
            confidence = 0.96
        elif any(term in lower for term in ("how", "is there a way", "set up", "sso")):
            category = Category.TECHNICAL_QUESTION
            priority = Priority.MEDIUM
            urgency = UrgencySignal.NONE
            issue = "The customer asks how to configure SSO with an authentication provider."
            confidence = 0.94
        else:
            category = Category.BUG_REPORT
            priority = Priority.MEDIUM
            urgency = UrgencySignal.MODERATE
            issue = "The customer cannot log in because the application returns an error."
            confidence = 0.95

        return LLMAnalysis(
            category=category,
            priority=priority,
            confidence=confidence,
            core_issue=issue,
            identifiers=identifiers,
            urgency_signal=urgency,
        ).model_dump(mode="json")

    def repair(
        self,
        message: str,
        candidate: Any,
        validation_errors: list[str],
        system_prompt: str,
    ) -> dict[str, Any]:
        del candidate, validation_errors
        return self.analyze(message, system_prompt)

    def summarize(self, validated_context: dict[str, Any], system_prompt: str) -> dict[str, str]:
        del system_prompt
        team = validated_context["final_destination"]
        issue = validated_context["core_issue"]
        priority = validated_context["priority"]
        escalation = (
            " Human Review is required." if validated_context["escalation_required"] else ""
        )
        return SummaryOutput(
            summary=f"For {team}: {issue} Priority is {priority}.{escalation}"
        ).model_dump()
