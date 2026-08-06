# ArcVault Triage

ArcVault Triage is an event-driven take-home assessment that accepts customer requests, acknowledges
them quickly, and processes them through a controlled LangGraph workflow. An LLM classifies and
extracts facts; Pydantic validates its output; deterministic Python policies retain final control over
routing and escalation.

## Architecture

```text
POST /webhooks/intake
  -> authenticate + validate + atomically accept in SQLite
  -> HTTP 202 + FastAPI BackgroundTasks
  -> LangGraph normalize -> analyze -> validate -> repair once if needed
  -> deterministic policy -> summary -> explicit queue branch
  -> persist final record -> JSONL queue projection -> optional outbound webhook
  -> completed / completed_with_delivery_failure
```

FastAPI is only the secure transport boundary. LangGraph starts after the event is stored as
`accepted`. SQLite is canonical; JSON and JSONL files are assessment-facing projections. See
[`docs/architecture.md`](docs/architecture.md) for the full design and production trade-offs.

## Requirements and setup

- Python 3.11 through 3.14 (verified with Python 3.14.3)
- A Groq API key, a running local Ollama model, or explicit fake/demo mode

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env`; real `.env` files are ignored. Important settings are:

| Variable | Meaning |
|---|---|
| `LLM_PROVIDER` | `groq`, `ollama`, or explicitly selected `fake` |
| `LLM_MODEL` | Provider model name |
| `GROQ_API_KEY` | Required for Groq |
| `OLLAMA_BASE_URL` | Local Ollama server, default `http://localhost:11434` |
| `WEBHOOK_SECRET` | Shared inbound secret |
| `DATABASE_URL` | Local `sqlite:///...` URL |
| `OUTPUT_DIR` | Queue/result output root |
| `OUTBOUND_WEBHOOK_URL` | Optional completed-record receiver |
| `MAIL_TRIGGER` | `disabled` or `mailhog` for the separate email watcher |
| `MAILHOG_API_URL` | MailHog HTTP API, normally `http://127.0.0.1:8025` |
| `MAILHOG_RECIPIENT` | Address the watcher searches for and forwards |
| `MAILHOG_INTAKE_URL` | Existing ArcVault intake webhook URL |

For Groq, set `LLM_PROVIDER=groq`, a supported `LLM_MODEL`, and `GROQ_API_KEY`. For Ollama, pull a
structured-output-capable model, set `LLM_PROVIDER=ollama`, set its model name, and ensure the local
server is reachable. `LLM_PROVIDER=fake` is deterministic assessment/demo behavior and records are
clearly labeled; it is never selected silently.

## Run the API

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

If the configured live provider lacks credentials, the API still starts safely; processing exhausts
the single repair and sends the event to Human Review with `model_output_invalid`. Configure a live
provider or explicitly select `fake` before demonstrating semantic classification.

Submit an event:

```bash
curl -X POST http://localhost:8000/webhooks/intake \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: change-me" \
  -d '{
    "event_id": "demo-001",
    "source": "Email",
    "message": "Several users cannot load the dashboard."
  }'
```

The initial response is `202 Accepted`. Query current status and the eventual record with:

```bash
curl http://localhost:8000/requests/demo-001
curl http://localhost:8000/health
python scripts/send_test_webhook.py --secret change-me
```

Submitting `demo-001` again returns `200` with `duplicate: true` and does not start a second graph.

## Automatic email intake with MailHog

MailHog is a local SMTP test server with an HTTP API. It requires no API key. Run it with Docker:

```powershell
docker run -d --name mailhog -p 1025:1025 -p 8025:8025 mailhog/mailhog
```

Set these values in the untracked `.env` file:

```env
MAIL_TRIGGER=mailhog
MAILHOG_API_URL=http://127.0.0.1:8025
MAILHOG_SMTP_HOST=127.0.0.1
MAILHOG_SMTP_PORT=1025
MAILHOG_RECIPIENT=triage@arcvault.local
MAILHOG_POLL_INTERVAL_SECONDS=2
MAILHOG_REQUEST_TIMEOUT_SECONDS=5
MAILHOG_INTAKE_URL=http://127.0.0.1:8000/webhooks/intake
```

Keep the API running, then start the separate adapter in another terminal:

```powershell
python scripts\watch_mailhog.py
```

Send a representative customer email through MailHog SMTP:

```powershell
python scripts\send_test_email.py
```

The watcher searches MailHog by recipient, parses MIME text while ignoring attachments, derives a
stable event ID from `Message-ID`, and calls the authenticated FastAPI webhook. Repeated polls or
watcher restarts are safe because the API's SQLite idempotency key prevents a second graph run. Use
`python scripts\watch_mailhog.py --once` for a single diagnostic poll. The MailHog UI is available at
`http://127.0.0.1:8025`.

## Run the assessment samples

Use a configured live model:

```bash
python scripts/run_samples.py
```

Without live configuration, the command exits with guidance. The explicit offline demonstration is:

```bash
python scripts/run_samples.py --demo
```

It uses fresh temporary SQLite state, runs all five inputs through the same compiled graph used by
the API, prints a result table, and atomically writes:

- `outputs/triage_results.json` — five schema-valid structured records
- `outputs/queues/*.jsonl` — one projection per destination

The checked-in assessment outputs were intentionally regenerated in demo mode and contain
`analysis_provider: "fake"` and `analysis_model: "deterministic-demo"`.

## Test and quality commands

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
python scripts/run_samples.py --demo
```

Tests use temporary databases/output directories, fake providers, and mocked HTTP clients. They need
no internet access or API key. Outbound tests prove that the durable record exists before delivery,
successful delivery is recorded, and failure is bounded without losing the result.

## Assessment limitations

- `BackgroundTasks` is not durable; a process crash after acceptance can strand work.
- The in-memory LangGraph checkpointer is inspectable but not restart-safe. SQLite business records
  remain durable.
- The MailHog adapter polls its local API; production email intake would use a durable provider event
  or push subscription rather than a process-local seen set.
- SQLite and process-local file locking target a single local assessment instance.
- Monetary and broad-impact matching is intentionally conservative and English-focused.
- Groq and Ollama adapters follow their current structured-output APIs but were not live-tested
  without credentials/a local model.

At production scale, use a durable broker and workers, PostgreSQL, a transactional outbox,
dead-letter handling, replica-safe idempotency, stronger authentication/rate limiting, sensitive-data
controls, structured logs/traces, prompt/model versioning, evaluations, cost/latency monitoring, and a
real Human Review interface.
