from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.factory import create_app
from app.llm.fake import FakeLLMProvider


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        llm_provider="fake",
        llm_model="deterministic-demo",
        webhook_secret="test-secret",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        output_dir=tmp_path / "outputs",
        outbound_webhook_url=None,
    )


@pytest.fixture
def app(settings: Settings):
    return create_app(settings, provider=FakeLLMProvider())


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def payload() -> dict[str, str]:
    return {
        "event_id": "evt-001",
        "source": "Email",
        "message": "I keep getting a 403 error at arcvault.io/user/jsmith.",
    }


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-Webhook-Secret": "test-secret"}
