# ArcVault Triage

ArcVault Triage accepts customer requests from Email, Web Form, and Support Portal sources, responds
quickly, and processes accepted events through a controlled LangGraph workflow. An LLM classifies the
request and extracts facts; Pydantic validates the model output; deterministic Python policies retain
final authority over routing and escalation.

The project supports live Groq and Ollama providers, an explicitly selected deterministic demo
provider, durable SQLite business records, atomic JSONL queue projections, optional outbound webhook
delivery, and automatic local email intake through MailHog.

## Architecture

```text
Email -> MailHog SMTP -> MailHog watcher ----+
                                             |
Web Form / Support Portal -------------------+-> POST /webhooks/intake
                                                  -> authenticate and validate
                                                  -> atomically accept in SQLite
                                                  -> HTTP 202 + background processing
                                                  -> LangGraph normalize
                                                     -> analyze
                                                     -> validate
                                                     -> repair once if invalid
                                                     -> deterministic escalation policy
                                                     -> summarize
                                                     -> select destination
                                                  -> persist final record in SQLite
                                                  -> rewrite JSONL queue projections
                                                  -> optional outbound webhook
                                                  -> completed status
```

FastAPI owns authentication, transport validation, atomic idempotency, background-task registration,
and HTTP responses. LangGraph starts only after acceptance and owns semantic processing. SQLite is
the canonical business store; JSON and JSONL files are assessment-facing projections. See
[`docs/architecture.md`](docs/architecture.md) for conditional edges and production trade-offs.

## Requirements

- Python 3.11 through 3.14; verified locally with Python 3.14.3
- A Groq API key, a running local Ollama model, or explicit fake/demo mode
- MailHog when demonstrating automatic email intake

Create the environment and install the exact pinned dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Linux and macOS activation:

```bash
source .venv/bin/activate
```

## Configuration

Copy the example configuration and keep the real file untracked:

```powershell
Copy-Item .env.example .env
```

Never commit `.env` or expose its API keys and webhook secret.

| Variable | Meaning |
|---|---|
| `LLM_PROVIDER` | `groq`, `ollama`, or explicitly selected `fake` |
| `LLM_MODEL` | Model name understood by the selected provider |
| `GROQ_API_KEY` | Required when `LLM_PROVIDER=groq` |
| `OLLAMA_BASE_URL` | Ollama server, normally `http://localhost:11434` |
| `WEBHOOK_SECRET` | Shared secret required by `POST /webhooks/intake` |
| `DATABASE_URL` | Canonical SQLite URL, normally `sqlite:///./arcvault.db` |
| `OUTPUT_DIR` | Result and queue projection directory |
| `OUTBOUND_WEBHOOK_URL` | Optional receiver for completed records; may be empty |
| `OUTBOUND_TIMEOUT_SECONDS` | Timeout for each outbound delivery attempt |
| `OUTBOUND_MAX_ATTEMPTS` | Maximum outbound attempts, including the first attempt |
| `MAIL_TRIGGER` | `disabled` or `mailhog` |
| `MAILHOG_API_URL` | MailHog HTTP API, normally `http://127.0.0.1:8025` |
| `MAILHOG_SMTP_HOST` | MailHog SMTP host, normally `127.0.0.1` |
| `MAILHOG_SMTP_PORT` | MailHog SMTP port, normally `1025` |
| `MAILHOG_RECIPIENT` | Address searched and forwarded by the watcher |
| `MAILHOG_POLL_INTERVAL_SECONDS` | Delay between MailHog polls |
| `MAILHOG_REQUEST_TIMEOUT_SECONDS` | MailHog and intake HTTP timeout |
| `MAILHOG_INTAKE_URL` | ArcVault authenticated intake URL |

A typical live Groq and MailHog configuration is:

```env
LLM_PROVIDER=groq
LLM_MODEL=openai/gpt-oss-20b
GROQ_API_KEY=your-real-groq-key
WEBHOOK_SECRET=replace-with-a-long-random-secret
DATABASE_URL=sqlite:///./arcvault.db
OUTPUT_DIR=outputs
OUTBOUND_WEBHOOK_URL=
OUTBOUND_TIMEOUT_SECONDS=5
OUTBOUND_MAX_ATTEMPTS=3
MAIL_TRIGGER=mailhog
MAILHOG_API_URL=http://127.0.0.1:8025
MAILHOG_SMTP_HOST=127.0.0.1
MAILHOG_SMTP_PORT=1025
MAILHOG_RECIPIENT=triage@arcvault.local
MAILHOG_POLL_INTERVAL_SECONDS=2
MAILHOG_REQUEST_TIMEOUT_SECONDS=5
MAILHOG_INTAKE_URL=http://127.0.0.1:8000/webhooks/intake
```

For Ollama, pull a structured-output-capable model, set `LLM_PROVIDER=ollama`, set `LLM_MODEL` to
the pulled model, and ensure `OLLAMA_BASE_URL` is reachable. `LLM_PROVIDER=fake` is deterministic
assessment behavior and is never selected silently; its records are labeled `fake` and
`deterministic-demo`.

Leaving `OUTBOUND_WEBHOOK_URL` empty is valid. Triage still completes and the record contains
`outbound_delivery_status: "not_configured"`. Do not point the outbound URL back to ArcVault's intake
endpoint.

## Complete live email pipeline on Windows

The live demonstration uses three long-running processes: MailHog, the ArcVault API, and the MailHog
watcher. Keep all three running while testing.

### 1. Install the standalone MailHog executable

Docker is not required. Download the official Windows AMD64 release once:

```powershell
$mailhogDirectory = Join-Path $env:LOCALAPPDATA "ArcVault\MailHog"
New-Item -ItemType Directory -Force -Path $mailhogDirectory
Invoke-WebRequest `
  -Uri "https://github.com/mailhog/MailHog/releases/download/v1.0.1/MailHog_windows_amd64.exe" `
  -OutFile (Join-Path $mailhogDirectory "MailHog.exe")
Unblock-File (Join-Path $mailhogDirectory "MailHog.exe")
```

Alternatively, if Docker is already installed:

```powershell
docker run --rm -p 1025:1025 -p 8025:8025 mailhog/mailhog
```

Use either the standalone executable or Docker, not both.

### 2. Start MailHog with persistent email storage

MailHog defaults to in-memory storage, which loses all inbox messages when the process stops. Start
the standalone executable with its `maildir` backend so new messages survive restarts:

```powershell
$mailhogExe = Join-Path $env:LOCALAPPDATA "ArcVault\MailHog\MailHog.exe"
$mailhogData = Join-Path $env:LOCALAPPDATA "ArcVault\MailHogData"
New-Item -ItemType Directory -Force -Path $mailhogData
& $mailhogExe "-storage=maildir" "-maildir-path=$mailhogData"
```

Keep that terminal open. The inbox is available at <http://127.0.0.1:8025>. Always use the same
storage arguments; double-clicking the executable returns to in-memory mode. Previously lost
in-memory messages cannot be migrated into `maildir`.

### 3. Start the ArcVault API

In a second terminal, from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Verify the API and open its interactive documentation:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

- Health: <http://127.0.0.1:8000/health>
- OpenAPI UI: <http://127.0.0.1:8000/docs>

### 4. Start the automatic MailHog watcher

In a third terminal:

```powershell
.\.venv\Scripts\python.exe scripts\watch_mailhog.py
```

The watcher searches MailHog's API by `MAILHOG_RECIPIENT`, parses MIME content, prefers plain text,
falls back to HTML text, ignores attachments, and caps the forwarded message at 10,000 characters.
It derives a stable ArcVault event ID from the email `Message-ID` and calls the existing authenticated
FastAPI webhook. Failed forwards are retried on later polls. Repeated polls and watcher restarts are
safe because SQLite idempotency prevents a second graph run for the same event ID.

Run one diagnostic poll and exit with:

```powershell
.\.venv\Scripts\python.exe scripts\watch_mailhog.py --once
```

Successful output resembles:

```text
fetched=1 forwarded=1 skipped=0 failed=0
Forwarded MailHog message id=... event_id=mailhog-...
```

### 5. Send a test customer email

In a fourth terminal:

```powershell
.\.venv\Scripts\python.exe scripts\send_test_email.py
```

Send custom content with:

```powershell
.\.venv\Scripts\python.exe scripts\send_test_email.py `
  --subject "Production dashboard outage" `
  --message "The dashboard is down for all users since 2pm EST."
```

The message first appears in MailHog. The watcher then logs its derived `event_id` and submits it to
ArcVault. Copy that ID and retrieve the completed record:

```powershell
$eventId = "mailhog-replace-with-the-id-from-the-watcher"
Invoke-RestMethod "http://127.0.0.1:8000/requests/$eventId" |
  ConvertTo-Json -Depth 10
```

The response exposes processing status, category, priority, confidence, extracted identifiers,
escalation reasons, summary, original and final destination, delivery status, and provider/model
labels. `202 Accepted` from intake means background processing started; poll the GET endpoint until
the status becomes `completed`, `completed_with_delivery_failure`, or `failed`.

## API contract

| Method and path | Behavior |
|---|---|
| `POST /webhooks/intake` | Authenticates, validates, and atomically accepts a new event |
| `GET /requests/{event_id}` | Returns status and the final record when available |
| `GET /health` | Returns a basic health indicator |

`POST /webhooks/intake` requires the `X-Webhook-Secret` header. A new event returns `202`; a repeated
event ID returns `200` with `duplicate: true` and never starts a second graph. Unknown request IDs
return `404`. Transport validation failures return `422`.

Accepted source values are exactly:

```text
Email
Web Form
Support Portal
```

IDs are trimmed and limited to 128 characters. Messages retain their unmodified raw value, must not
be blank, and are limited to 10,000 characters. `received_at` is optional, must be timezone-aware
when supplied, and otherwise defaults to UTC.

## Simulate all three sources

Email has a live MailHog adapter. Web Form and Support Portal represent systems that call the same
normalized intake webhook. They do not require separate pipeline implementations.

Load the configured webhook secret into the current PowerShell session without printing it:

```powershell
$secretLine = Get-Content .env |
  Where-Object { $_ -match '^\s*WEBHOOK_SECRET=' } |
  Select-Object -First 1
$webhookSecret = $secretLine.Substring($secretLine.IndexOf('=') + 1).Trim()
$headers = @{ "X-Webhook-Secret" = $webhookSecret }
```

### Web Form simulation

```powershell
$webFormId = "webform-$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
$webFormPayload = @{
  event_id = $webFormId
  source = "Web Form"
  message = "We'd love to see a bulk export feature for our audit logs. We're a compliance-heavy org and this would save us hours every month."
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/webhooks/intake" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $webFormPayload

Invoke-RestMethod "http://127.0.0.1:8000/requests/$webFormId" |
  ConvertTo-Json -Depth 10
```

### Support Portal simulation

```powershell
$supportId = "support-$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
$supportPayload = @{
  event_id = $supportId
  source = "Support Portal"
  message = 'Invoice #8821 shows a charge of $1,240 but our contract rate is $980/month. Can someone look into this?'
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/webhooks/intake" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $supportPayload

Invoke-RestMethod "http://127.0.0.1:8000/requests/$supportId" |
  ConvertTo-Json -Depth 10
```

Use a new `event_id` for each independent test. Reusing one deliberately tests idempotency and
returns the previously accepted record.

## Deterministic routing and Human Review

Normal category destinations are:

| Category | Original destination |
|---|---|
| Bug Report | Engineering |
| Feature Request | Product |
| Billing Issue | Billing |
| Technical Question | Technical Support |
| Incident/Outage | Engineering - Incident Response |

The model recommends semantic fields, but Python policies make every final escalation decision. All
rules are evaluated independently and stable reason codes accumulate. A request is sent to Human
Review when any of these conditions applies:

- confidence is strictly below `0.70`
- category is `Incident/Outage`
- tested wording indicates multiple users or broad impact
- a safely parsed billing discrepancy is strictly greater than `$500`
- routing is unsafe
- model output remains invalid after one repair attempt

`Human Review` is a queue destination, not a built-in user interface or notification service. In a
production system it would connect to a ticketing system, operations dashboard, Slack/on-call
workflow, or staffed review tool. Because every incident is escalated by policy,
`incident_response.jsonl` can remain empty: Incident Response is recorded as the original destination
while Human Review becomes the final destination.

## Persistence and generated files

MailHog, SQLite, and JSON files have different purposes and retention:

| Location | Purpose | Retention/read behavior |
|---|---|---|
| MailHog memory or configured maildir | Original test emails | Independent of ArcVault records |
| `arcvault.db` | Canonical accepted events, records, and delivery attempts | Durable; read by the API |
| `data/sample_requests.json` | Five supplied assessment inputs | Read only by the batch runner/tests |
| `outputs/triage_results.json` | Five batch results | Written only by `run_samples.py`; not live API state |
| `outputs/queues/*.jsonl` | One output projection per final destination | Rewritten atomically from SQLite; never canonical input |

Deleting or losing an email in MailHog does not delete its accepted ArcVault record. Similarly,
deleting an ArcVault record would not delete the source email. The API deliberately provides no
DELETE endpoint because accepted requests are treated as durable audit records; use a new event ID
for routine testing.

The queue files are:

```text
outputs/queues/engineering.jsonl
outputs/queues/incident_response.jsonl
outputs/queues/product.jsonl
outputs/queues/billing.jsonl
outputs/queues/technical_support.jsonl
outputs/queues/human_review.jsonl
```

## Optional outbound delivery

When `OUTBOUND_WEBHOOK_URL` is configured, ArcVault sends the persisted final record to that URL only
after SQLite persistence and queue projection succeed. HTTP delivery uses a bounded timeout and at
most `OUTBOUND_MAX_ATTEMPTS` total attempts, with every outcome recorded in SQLite. Exhausted delivery
updates the request to `completed_with_delivery_failure` without deleting its triage data.

When no receiver is available, keep:

```env
OUTBOUND_WEBHOOK_URL=
```

This is a complete and successful local pipeline configuration; the record simply reports
`outbound_delivery_status: "not_configured"`.

## Run the five assessment samples

The exact supplied Email, Web Form, and Support Portal inputs live in
[`data/sample_requests.json`](data/sample_requests.json).

Run them with the configured live provider:

```powershell
.\.venv\Scripts\python.exe scripts\run_samples.py
```

Without a valid live configuration, the command exits with guidance. Run the explicit offline demo
with:

```powershell
.\.venv\Scripts\python.exe scripts\run_samples.py --demo
```

The batch uses a fresh temporary SQLite assessment store, processes all five inputs through the same
compiled graph used by the API, prints a compact table, and atomically writes exactly five records to
`outputs/triage_results.json` plus the queue projections. Demo records are visibly labeled
`analysis_provider: "fake"` and `analysis_model: "deterministic-demo"`.

The batch and live API share the configured output directory. A later live API queue synchronization
therefore rewrites queue JSONL files from the live SQLite database; `triage_results.json` remains the
separate five-record batch artifact.

## Troubleshooting

- **MailHog UI is unavailable:** confirm MailHog is running and port `8025` is free.
- **SMTP test fails:** confirm MailHog is listening on `127.0.0.1:1025`.
- **Watcher cannot connect:** confirm `MAILHOG_API_URL=http://127.0.0.1:8025`.
- **Watcher exits with configuration guidance:** set `MAIL_TRIGGER=mailhog` and restart it.
- **Webhook returns `401`:** the watcher and API must read the same non-empty `WEBHOOK_SECRET`.
- **Webhook returns `202` but no final record yet:** processing is asynchronous; poll
  `GET /requests/{event_id}` and inspect the API log for provider errors.
- **Webhook returns duplicate `200`:** the event already exists in SQLite; use a new ID for a new run.
- **MailHog has fewer emails than queue records:** MailHog retention is independent; SQLite and JSONL
  retain completed business records after an email is deleted or an in-memory MailHog restart.
- **Old email disappears after restart:** it was received in memory mode. Restart with the documented
  maildir arguments and resend it; previously lost memory cannot be recovered.
- **Code changed while watcher was running:** restart the watcher because it does not use Uvicorn's
  auto-reload behavior.

## Test and quality commands

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe scripts\run_samples.py --demo
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "from app.main import app; print(app.title, app.version)"
```

Offline tests use temporary databases/output directories, deterministic or scripted providers, and
mocked HTTP clients. They require no internet connection or API key. The suite covers authentication,
validation, atomic idempotency, graph validation/repair paths, escalation boundaries, all source
samples, MailHog MIME parsing and forwarding, SQLite persistence, JSONL projection, outbound retries,
and persist-before-deliver ordering.

The live local flow has also been exercised successfully with MailHog, FastAPI, Groq
`openai/gpt-oss-20b`, LangGraph, SQLite, and Human Review queue projection.

## Assessment limitations and production evolution

- FastAPI `BackgroundTasks` is not durable; a process crash after acceptance can strand work.
- The in-memory LangGraph checkpointer is inspectable but not restart-safe. SQLite business records
  remain durable.
- The MailHog adapter polls a local development API and has a process-local seen set. Production email
  intake would use a durable provider push event, cursor, or subscription.
- Web Form and Support Portal are source-labelled webhook producers, not bundled vendor-specific user
  interfaces or connectors.
- SQLite and process-local output locking target a single local assessment instance.
- Monetary and broad-impact matching is intentionally conservative and English-focused.
- Human Review is represented as a durable record and queue projection, not a staffed review UI.

At production scale, use durable broker-backed workers, PostgreSQL, a transactional outbox,
dead-letter handling, replica-safe idempotency, signed provider callbacks, stronger authentication and
rate limiting, PII encryption and retention controls, structured logs/traces, prompt/model versioning,
evaluation datasets, cost/latency monitoring, and real ticketing and Human Review integrations.
