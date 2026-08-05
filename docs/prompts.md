# Prompt Design

Prompts live under `app/prompts/` and are loaded once when the graph is compiled. Runtime code supplies
the Pydantic JSON schema separately; local Pydantic validation remains mandatory even when a provider
offers constrained decoding.

## Triage system prompt

**Purpose.** Classify an ArcVault request, recommend priority/confidence, state the core issue, and
extract supported identifiers and urgency without making business-policy decisions.

**Structure.** It first establishes the B2B audit/security context, then enumerates the only five
categories and defines priority. It explicitly distinguishes category confidence from severity,
requests a one-sentence issue and evidence-bound identifiers, prohibits invented facts and routing,
and ends with the structured-output requirement.

**Trade-offs.** A compact prompt lowers tokens and latency and makes provider behavior easier to
compare. Explicit labels improve consistency but cannot cover every customer phrasing or industry
edge case.

**Risks.** Models can still misclassify ambiguous requests, over-extract identifiers, or express
overconfidence. Provider-specific JSON Schema support also varies. Pydantic validation, one repair,
low-confidence escalation, and deterministic policies contain these risks.

**With more time.** Add few-shot examples selected from a versioned evaluation dataset, prompt/model
version fields, adversarial and multilingual cases, calibrated confidence evaluation, and sensitive
identifier handling rules.

## Summary system prompt

**Purpose.** Turn already validated analysis and policy fields into a short internal handoff for the
receiving team.

**Structure.** It restricts the model to supplied fields, asks for two or three concise sentences,
requires issue/impact/context and escalation when relevant, and excludes invented or customer-facing
language. The output is a one-field Pydantic object.

**Trade-offs.** A separate call produces a clearer team-specific handoff but adds latency and cost.
Keeping it downstream of policy prevents the prose from influencing routing.

**Risks.** The summary can omit useful nuance, repeat structured fields awkwardly, or fail provider
validation. Any exception or invalid response falls back to deterministic text built solely from safe
state.

**With more time.** Evaluate usefulness with receiving teams, add destination-specific style guidance,
version and score summaries, and test whether a deterministic template is sufficient for low-complexity
requests.
