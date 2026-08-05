# ArcVault Triage Contributor Guide

## Layout

- `app/`: FastAPI transport, LangGraph workflow, policies, providers, persistence, integrations.
- `data/`: assessment inputs.
- `scripts/`: runnable webhook and batch demonstrations.
- `tests/`: offline unit and integration tests.
- `docs/`: architecture and prompt rationale.
- `outputs/`: intentionally generated assessment results and queue projections.

## Commands

- Setup: `python -m venv .venv` then `python -m pip install -r requirements.txt`
- Tests: `python -m pytest`
- Lint: `python -m ruff check .`
- Format check: `python -m ruff format --check .`

## Architectural boundaries

FastAPI owns HTTP authentication, transport validation, idempotent acceptance, background-task
registration, and responses. LangGraph starts only after acceptance and owns semantic processing.
SQLite is canonical. Persist the final record before queue projection and outbound delivery.

Routing and escalation must remain deterministic Python policies. Never delegate final business
decisions, retry counts, persistence, or delivery behavior to an LLM.

## Definition of done

Changes are complete when offline tests, Ruff checks, the demo batch, and documented commands pass;
outputs validate against the final schema; retries are bounded; duplicate events are not reprocessed;
and no secret, local database, or cache is tracked.
