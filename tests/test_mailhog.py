from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.factory import create_app
from app.integrations.mailhog import MailHogWatcher, parse_mailhog_message
from app.llm.fake import FakeLLMProvider


def mailhog_message(*, body: str = "A 403 error prevents login.") -> dict:
    return {
        "ID": "mailhog-message-1",
        "From": {"Mailbox": "customer", "Domain": "example.com"},
        "To": [{"Mailbox": "triage", "Domain": "arcvault.local"}],
        "Content": {
            "Headers": {
                "Content-Type": ["text/plain; charset=utf-8"],
                "Message-ID": ["<customer-message-1@example.com>"],
                "Subject": ["Cannot sign in"],
                "To": ["triage@arcvault.local"],
            },
            "Body": body,
        },
        "Created": "2026-08-06T09:00:00Z",
    }


@pytest.fixture
def mailhog_settings() -> Settings:
    return Settings(
        _env_file=None,
        mail_trigger="mailhog",
        webhook_secret="mail-secret",
        mailhog_api_url="http://mailhog.test:8025/",
        mailhog_recipient="TRIAGE@arcvault.local",
        mailhog_intake_url="http://api.test:8000/webhooks/intake/",
    )


def test_parses_simple_message_and_derives_stable_event_id():
    first = parse_mailhog_message(mailhog_message(), recipient="triage@arcvault.local")
    second = parse_mailhog_message(mailhog_message(), recipient="triage@arcvault.local")
    assert first is not None
    assert first == second
    assert first.event_id.startswith("mailhog-")
    assert first.message == "Subject: Cannot sign in\n\nA 403 error prevents login."
    assert first.received_at == "2026-08-06T09:00:00Z"


def test_parses_multipart_mime_and_ignores_attachment():
    raw = """From: customer@example.com
To: triage@arcvault.local
Subject: Multipart request
Message-ID: <multipart@example.com>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary=arcvault

--arcvault
Content-Type: text/plain; charset=utf-8

The dashboard is down for everyone.
--arcvault
Content-Type: text/plain
Content-Disposition: attachment; filename=notes.txt

Do not classify this attachment.
--arcvault--
"""
    message = mailhog_message()
    message["Raw"] = {"Data": raw}
    parsed = parse_mailhog_message(message, recipient="triage@arcvault.local")
    assert parsed is not None
    assert "dashboard is down" in parsed.message
    assert "Do not classify" not in parsed.message


def test_html_fallback_and_transport_length_bound():
    message = mailhog_message()
    message["Content"]["Headers"]["Content-Type"] = ["text/html; charset=utf-8"]
    message["Content"]["Body"] = f"<p>{'x' * 200}</p>"
    parsed = parse_mailhog_message(
        message, recipient="triage@arcvault.local", maximum_characters=100
    )
    assert parsed is not None
    assert len(parsed.message) == 100
    assert parsed.message.endswith("[truncated]")


def test_wrong_recipient_or_blank_body_is_ignored():
    assert parse_mailhog_message(mailhog_message(), recipient="other@arcvault.local") is None
    assert (
        parse_mailhog_message(mailhog_message(body="   "), recipient="triage@arcvault.local")
        is None
    )


def test_poll_searches_recipient_forwards_once_and_skips_seen(mailhog_settings):
    forwarded_payloads: list[dict] = []

    def mailhog_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/search"
        assert request.url.params["kind"] == "to"
        assert request.url.params["query"] == "triage@arcvault.local"
        return httpx.Response(200, json={"total": 1, "items": [mailhog_message()]})

    def intake_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/webhooks/intake"
        assert request.headers["X-Webhook-Secret"] == "mail-secret"
        forwarded_payloads.append(json.loads(request.content))
        return httpx.Response(202, json={"accepted": True})

    with (
        httpx.Client(transport=httpx.MockTransport(mailhog_handler)) as mailhog_client,
        httpx.Client(transport=httpx.MockTransport(intake_handler)) as intake_client,
    ):
        watcher = MailHogWatcher(
            mailhog_settings, mailhog_client=mailhog_client, intake_client=intake_client
        )
        first = watcher.poll_once()
        second = watcher.poll_once()

    assert first.forwarded == 1
    assert second.skipped == 1
    assert len(forwarded_payloads) == 1
    assert forwarded_payloads[0]["source"] == "Email"
    assert forwarded_payloads[0]["received_at"] == "2026-08-06T09:00:00Z"


def test_failed_forward_is_retried_on_next_poll(mailhog_settings):
    attempts = 0

    def mailhog_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [mailhog_message()]})

    def intake_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503 if attempts == 1 else 202)

    with (
        httpx.Client(transport=httpx.MockTransport(mailhog_handler)) as mailhog_client,
        httpx.Client(transport=httpx.MockTransport(intake_handler)) as intake_client,
    ):
        watcher = MailHogWatcher(
            mailhog_settings, mailhog_client=mailhog_client, intake_client=intake_client
        )
        assert watcher.poll_once().failed == 1
        assert watcher.poll_once().forwarded == 1
    assert attempts == 2


def test_mailhog_message_runs_through_real_intake_and_graph(settings):
    configured = settings.model_copy(
        update={
            "mail_trigger": "mailhog",
            "mailhog_api_url": "http://mailhog.test:8025",
            "mailhog_recipient": "triage@arcvault.local",
            "mailhog_intake_url": "http://testserver/webhooks/intake",
        }
    )
    email = parse_mailhog_message(mailhog_message(), recipient=configured.mailhog_recipient)
    assert email is not None

    def mailhog_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"messages": [mailhog_message()]})

    class IntakeAdapter:
        def __init__(self, client: TestClient) -> None:
            self.client = client

        def post(self, url, *, headers, json, timeout):
            del timeout
            return self.client.post(url, headers=headers, json=json)

    app = create_app(configured, provider=FakeLLMProvider())
    with (
        httpx.Client(transport=httpx.MockTransport(mailhog_handler)) as mailhog_client,
        TestClient(app) as intake_client,
    ):
        result = MailHogWatcher(
            configured,
            mailhog_client=mailhog_client,
            intake_client=IntakeAdapter(intake_client),
        ).poll_once()
        status_response = intake_client.get(f"/requests/{email.event_id}")

    assert result.forwarded == 1
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["status"] == "completed"
    assert status["record"]["source"] == "Email"
    assert status["record"]["analysis_provider"] == "fake"


def test_mailhog_configuration_validation():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, mail_trigger="gmail")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, mailhog_api_url="mailhog:8025")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, mailhog_recipient="not-an-email")
