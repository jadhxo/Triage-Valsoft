# ArcVault Triage Architecture

## System design and boundary

Webhooks provide event-driven, near-real-time triggers, while FastAPI acts as the secure ingestion
boundary. FastAPI validates and acknowledges each event before handing it to LangGraph for stateful
AI processing. LangGraph controls semantic analysis, validation and branching, while deterministic
Python policies retain control over routing and escalation. Results are persisted before outbound
webhook delivery so that downstream delivery failures cannot erase the triage decision.

FastAPI owns HTTP concerns: the shared-secret header, transport schema, atomic idempotency insert,
accepted event, background-task registration, and HTTP response. No graph node handles requests,
authentication, or response construction. A new request receives `202`; a duplicate returns its
existing status with `duplicate: true` and never registers another task.

For this assessment, Starlette runs the synchronous processor in its background-task thread pool.
Production would place the accepted event on a durable broker such as Redis/Celery, RabbitMQ, Kafka,
or a managed queue and acknowledge only after the enqueue transaction is safe.

## Workflow and state

`event_id` is the inbound idempotency key, correlation identifier, status lookup key, SQLite primary
key, and LangGraph `thread_id`. Typed `TriageState` exists for one graph run; an app-scoped
`InMemorySaver` makes node checkpoints inspectable. SQLite—not the checkpointer—is canonical durable
business state.

```text
START -> initialize_state -> normalize_request -> analyze_request -> validate_analysis
  valid -------------------------------> apply_policy
  invalid, retry_count=0 -> repair_analysis -> validate_analysis
  invalid, retry_count=1 --------------> force_escalation

apply_policy / force_escalation -> generate_summary -> select_destination
  -> human_review | standard_queue -> persist_result
  -> deliver_outbound_webhook -> mark_complete -> END
```

The raw message is never overwritten. Normalization collapses whitespace into a separate field.
Analysis and summary provider output are independently validated by Pydantic. The single repair node
increments `retry_count` before returning to validation, so the conditional edge cannot execute it
twice. Exhausted invalid output preserves transport data, leaves unsafe analysis fields null, adds
`model_output_invalid` and `unsafe_to_route`, chooses Human Review, and uses a deterministic summary.

## Deterministic decisions

The LLM recommends category/priority/confidence, extracts the issue and identifiers, interprets
urgency, and drafts the internal summary. It never selects a queue or decides escalation.

Routing is an exact table: bugs to Engineering, features to Product, billing to Billing, technical
questions to Technical Support, and incidents to Engineering - Incident Response. The table result is
always retained as `original_destination`; any escalation changes only `final_destination` to Human
Review.

Escalation collects every applicable stable reason: confidence below 0.70, incident/outage category,
unambiguous broad-user impact, billing discrepancy strictly above $500, exhausted invalid model
output, or an unsafe decision. Billing uses `Decimal`, preferring an explicitly labeled discrepancy;
otherwise it subtracts clearly labeled charge/invoice and contract/rate values. Thus $1,240 minus
$980 is $260 and does not cross the threshold. Ambiguous standalone amounts are not guessed.

## Persistence, outputs, and delivery

SQLite uses a short-lived connection per operation with foreign keys, busy timeout, and WAL. The
`events` table provides atomic acceptance/status/error storage; `triage_records` stores the validated
record; `delivery_attempts` records each HTTP outcome. The unique event primary key makes concurrent
duplicate acceptance safe.

`persist_result` stores a completed result before producing queue files or invoking outbound HTTP.
Queue JSONL files are deterministic, atomically replaced projections of canonical records rather than
blind appends; this prevents duplicate event lines. A process-local lock prevents competing writers
inside the assessment server.

Outbound delivery is skipped as `not_configured` when no URL exists. Otherwise HTTPX uses a five-second
timeout and at most three total attempts by default, recording each one. A success becomes `delivered`.
Exhausted failure becomes `failed` and changes the processing status to
`completed_with_delivery_failure`; the saved triage decision remains queryable.

## Reliability, latency, cost, and evolution

The design uses one classification call and one summary call on the normal path, minimizing latency
and token cost. Malformed analysis adds at most one call. Schema-constrained output reduces parse
failures, while local validation remains the trust boundary. The separate summary improves usefulness
but adds latency/cost; its deterministic fallback protects completion.

Production should replace background tasks and in-memory checkpoints with durable workers and
checkpointing; use PostgreSQL and a transactional outbox to atomically coordinate acceptance,
enqueueing, queue publication, and delivery. Add a dead-letter queue, lease/recovery for accepted or
processing events, replica-safe idempotency, signed webhooks, rate limiting, PII minimization and
encryption, structured event-ID logs and traces, prompt/model versioning, cost/latency dashboards,
evaluation datasets, configurable versioned policies, and a Human Review interface.

Phase 2 can add customer-history retrieval, duplicate-ticket detection, SLA calculation, multilingual
input, feedback-driven evaluation, ticketing integrations, and customer-specific routing without
moving business-policy authority into the model.
