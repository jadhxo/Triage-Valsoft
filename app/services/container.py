from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.graph import compile_graph
from app.integrations.outbound_webhook import HTTPClient, OutboundWebhook
from app.llm.base import LLMProvider
from app.llm.factory import create_provider_for_api
from app.outputs import OutputWriter
from app.repositories.database import Database
from app.repositories.events import EventsRepository
from app.repositories.records import RecordsRepository
from app.services.processor import TriageProcessor


@dataclass(frozen=True)
class Services:
    settings: Settings
    events: EventsRepository
    records: RecordsRepository
    writer: OutputWriter
    outbound: OutboundWebhook
    processor: TriageProcessor


def build_services(
    settings: Settings,
    *,
    provider: LLMProvider | None = None,
    http_client: HTTPClient | None = None,
) -> Services:
    database = Database(settings.database_path)
    database.initialize()
    events = EventsRepository(database)
    records = RecordsRepository(database)
    writer = OutputWriter(settings.output_dir)
    writer.initialize_queue_files()
    selected_provider = provider or create_provider_for_api(settings)
    outbound = OutboundWebhook(
        repository=records,
        url=settings.outbound_webhook_url,
        timeout_seconds=settings.outbound_timeout_seconds,
        max_attempts=settings.outbound_max_attempts,
        client=http_client,
    )
    graph = compile_graph(
        provider=selected_provider,
        events=events,
        records=records,
        writer=writer,
        outbound=outbound,
    )
    processor = TriageProcessor(
        graph=graph,
        events=events,
        records=records,
        provider_name=selected_provider.provider_name,
        model_name=selected_provider.model_name,
    )
    return Services(settings, events, records, writer, outbound, processor)
