from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import dataclass
from email import policy
from email.message import Message
from email.parser import BytesParser
from html.parser import HTMLParser
from typing import Any, Protocol

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class MailHogHTTPClient(Protocol):
    def get(self, url: str, *, params: dict[str, object], timeout: float) -> httpx.Response: ...


class IntakeHTTPClient(Protocol):
    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: object,
        timeout: float,
    ) -> httpx.Response: ...


@dataclass(frozen=True)
class MailHogEmail:
    mailhog_id: str
    event_id: str
    message: str
    received_at: str | None


@dataclass(frozen=True)
class PollResult:
    fetched: int
    forwarded: int
    skipped: int
    failed: int


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return " ".join(self.parts)


def _case_insensitive(mapping: object, name: str) -> Any:
    if not isinstance(mapping, dict):
        return None
    wanted = name.casefold()
    for key, value in mapping.items():
        if str(key).casefold() == wanted:
            return value
    return None


def _first_header(headers: object, name: str) -> str | None:
    value = _case_insensitive(headers, name)
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _message_headers(message: dict[str, Any]) -> dict[str, Any]:
    content = _case_insensitive(message, "content")
    headers = _case_insensitive(content, "headers")
    if not isinstance(headers, dict):
        headers = _case_insensitive(message, "headers")
    return headers if isinstance(headers, dict) else {}


def _raw_email_bytes(message: dict[str, Any]) -> bytes:
    raw = _case_insensitive(message, "raw")
    raw_data = _case_insensitive(raw, "data")
    if isinstance(raw_data, str) and raw_data.strip():
        return raw_data.encode("utf-8", errors="replace")

    content = _case_insensitive(message, "content")
    headers = _message_headers(message)
    body = _case_insensitive(content, "body")
    if body is None:
        body = _case_insensitive(message, "body")
    lines: list[str] = []
    for name, values in headers.items():
        items = values if isinstance(values, list) else [values]
        lines.extend(f"{name}: {value}" for value in items if value is not None)
    lines.extend(("", str(body or "")))
    return "\r\n".join(lines).encode("utf-8", errors="replace")


def _plain_text(parsed: Message) -> str:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    parts = parsed.walk() if parsed.is_multipart() else [parsed]
    for part in parts:
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        try:
            content = part.get_content()
        except (LookupError, UnicodeError):
            payload = part.get_payload(decode=True) or b""
            content = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if not isinstance(content, str) or not content.strip():
            continue
        if content_type == "text/plain":
            plain_parts.append(content.strip())
        else:
            html_parts.append(content.strip())
    if plain_parts:
        return "\n\n".join(plain_parts)
    if html_parts:
        extractor = _HTMLTextExtractor()
        extractor.feed("\n".join(html_parts))
        return extractor.text()
    return ""


def _recipient_addresses(message: dict[str, Any]) -> set[str]:
    addresses: set[str] = set()
    recipients = _case_insensitive(message, "to")
    if isinstance(recipients, list):
        for recipient in recipients:
            mailbox = _case_insensitive(recipient, "mailbox")
            domain = _case_insensitive(recipient, "domain")
            if mailbox and domain:
                addresses.add(f"{mailbox}@{domain}".casefold())
    to_header = _first_header(_message_headers(message), "to")
    if to_header:
        addresses.update(
            token.strip(" <>\t\r\n").casefold()
            for token in to_header.replace(",", " ").split()
            if "@" in token
        )
    return addresses


def parse_mailhog_message(
    message: dict[str, Any], *, recipient: str, maximum_characters: int = 10_000
) -> MailHogEmail | None:
    if recipient.casefold() not in _recipient_addresses(message):
        return None

    mailhog_id = str(_case_insensitive(message, "id") or "").strip()
    parsed = BytesParser(policy=policy.default).parsebytes(_raw_email_bytes(message))
    headers = _message_headers(message)
    subject = str(parsed.get("Subject") or _first_header(headers, "subject") or "").strip()
    body = _plain_text(parsed).strip()
    if not body:
        content = _case_insensitive(message, "content")
        body = str(_case_insensitive(content, "body") or "").strip()
    if not body:
        return None

    intake_message = f"Subject: {subject}\n\n{body}" if subject else body
    if len(intake_message) > maximum_characters:
        suffix = "\n[truncated]"
        intake_message = intake_message[: maximum_characters - len(suffix)] + suffix

    message_id = str(parsed.get("Message-ID") or _first_header(headers, "message-id") or "").strip()
    stable_key = message_id or mailhog_id
    if not stable_key:
        stable_key = hashlib.sha256(_raw_email_bytes(message)).hexdigest()
    digest = hashlib.sha256(stable_key.encode("utf-8", errors="replace")).hexdigest()[:32]
    created = _case_insensitive(message, "created")
    return MailHogEmail(
        mailhog_id=mailhog_id or digest,
        event_id=f"mailhog-{digest}",
        message=intake_message,
        received_at=str(created).strip() if created else None,
    )


class MailHogWatcher:
    def __init__(
        self,
        settings: Settings,
        *,
        mailhog_client: MailHogHTTPClient | None = None,
        intake_client: IntakeHTTPClient | None = None,
    ) -> None:
        self.settings = settings
        self.mailhog_client = mailhog_client or httpx.Client()
        self.intake_client = intake_client or httpx.Client()
        self._seen: set[str] = set()

    def fetch_messages(self) -> list[dict[str, Any]]:
        response = self.mailhog_client.get(
            f"{self.settings.mailhog_api_url}/api/v2/search",
            params={
                "kind": "to",
                "query": self.settings.mailhog_recipient,
                "start": 0,
                "limit": 50,
            },
            timeout=self.settings.mailhog_request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        messages = _case_insensitive(payload, "items")
        if not isinstance(messages, list):
            messages = _case_insensitive(payload, "messages")
        if not isinstance(messages, list):
            raise ValueError("MailHog response does not contain an items list")
        return [message for message in messages if isinstance(message, dict)]

    def forward(self, email: MailHogEmail) -> None:
        payload: dict[str, object] = {
            "event_id": email.event_id,
            "source": "Email",
            "message": email.message,
        }
        if email.received_at:
            payload["received_at"] = email.received_at
        response = self.intake_client.post(
            self.settings.mailhog_intake_url,
            headers={"X-Webhook-Secret": self.settings.webhook_secret},
            json=payload,
            timeout=self.settings.mailhog_request_timeout_seconds,
        )
        response.raise_for_status()

    def poll_once(self) -> PollResult:
        messages = self.fetch_messages()
        forwarded = skipped = failed = 0
        for message in sorted(
            messages, key=lambda item: str(_case_insensitive(item, "created") or "")
        ):
            mailhog_id = str(_case_insensitive(message, "id") or "").strip()
            if mailhog_id and mailhog_id in self._seen:
                skipped += 1
                continue
            email = parse_mailhog_message(message, recipient=self.settings.mailhog_recipient)
            if email is None:
                skipped += 1
                if mailhog_id:
                    self._seen.add(mailhog_id)
                continue
            try:
                self.forward(email)
            except httpx.HTTPError:
                failed += 1
                logger.exception("Failed forwarding MailHog message id=%s", email.mailhog_id)
                continue
            self._seen.add(email.mailhog_id)
            forwarded += 1
            logger.info(
                "Forwarded MailHog message id=%s event_id=%s", email.mailhog_id, email.event_id
            )
        return PollResult(len(messages), forwarded, skipped, failed)

    def run_forever(self, stop_event: threading.Event | None = None) -> None:
        stopping = stop_event or threading.Event()
        while not stopping.is_set():
            try:
                result = self.poll_once()
                if result.forwarded or result.failed:
                    logger.info(
                        "MailHog poll fetched=%d forwarded=%d skipped=%d failed=%d",
                        result.fetched,
                        result.forwarded,
                        result.skipped,
                        result.failed,
                    )
            except (httpx.HTTPError, ValueError):
                logger.exception("MailHog polling failed; retrying after configured interval")
            stopping.wait(self.settings.mailhog_poll_interval_seconds)
