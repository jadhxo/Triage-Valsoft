from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas import InboundWebhook


def test_received_at_must_be_timezone_aware():
    with pytest.raises(ValidationError):
        InboundWebhook(
            event_id="evt",
            source="Email",
            message="message",
            received_at=datetime(2026, 8, 5, 12, 30),
        )


def test_raw_message_whitespace_is_preserved():
    payload = InboundWebhook(event_id="evt", source="Email", message="  customer message  ")
    assert payload.message == "  customer message  "
