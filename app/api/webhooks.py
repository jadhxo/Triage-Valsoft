from __future__ import annotations

import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Response, status

from app.schemas import (
    HealthResponse,
    InboundWebhook,
    IntakeResponse,
    RequestStatusResponse,
)
from app.services.container import Services


def create_router(services: Services) -> APIRouter:
    router = APIRouter()

    def authenticate_webhook(x_webhook_secret: str | None = Header(default=None)) -> None:
        supplied = x_webhook_secret or ""
        if not secrets.compare_digest(supplied, services.settings.webhook_secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook secret"
            )

    @router.post(
        "/webhooks/intake",
        response_model=IntakeResponse,
        responses={200: {"model": IntakeResponse}, 202: {"model": IntakeResponse}},
    )
    def ingest_webhook(
        payload: InboundWebhook,
        background_tasks: BackgroundTasks,
        response: Response,
        _authenticated: None = Depends(authenticate_webhook),
    ) -> IntakeResponse:
        created, event = services.events.accept(payload)
        if not created:
            response.status_code = status.HTTP_200_OK
            return IntakeResponse(duplicate=True, event_id=event.event_id, status=event.status)

        background_tasks.add_task(services.processor.process_event, event.event_id)
        response.status_code = status.HTTP_202_ACCEPTED
        return IntakeResponse(duplicate=False, event_id=event.event_id, status="accepted")

    @router.get("/requests/{event_id}", response_model=RequestStatusResponse)
    def request_status(event_id: str) -> RequestStatusResponse:
        event = services.events.get(event_id)
        if event is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
        return RequestStatusResponse(
            event_id=event.event_id,
            status=event.status,
            error=event.error,
            record=services.records.get(event_id),
        )

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    return router
