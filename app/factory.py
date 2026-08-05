from __future__ import annotations

from fastapi import FastAPI

from app.api.webhooks import create_router
from app.config import Settings, get_settings
from app.integrations.outbound_webhook import HTTPClient
from app.llm.base import LLMProvider
from app.services.container import build_services


def create_app(
    settings: Settings | None = None,
    *,
    provider: LLMProvider | None = None,
    http_client: HTTPClient | None = None,
) -> FastAPI:
    selected_settings = settings or get_settings()
    services = build_services(selected_settings, provider=provider, http_client=http_client)
    application = FastAPI(title="ArcVault Triage", version="1.0.0")
    application.state.services = services
    application.include_router(create_router(services))
    return application
