from __future__ import annotations

from functools import partial
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.integrations.outbound_webhook import OutboundWebhook
from app.llm.base import LLMProvider
from app.nodes.analyze import analyze_request, repair_analysis, validate_analysis, validation_route
from app.nodes.initialize import initialize_state
from app.nodes.normalize import normalize_request
from app.nodes.persist import deliver_outbound_webhook, mark_complete, persist_result
from app.nodes.route import (
    apply_policy,
    destination_route,
    force_escalation,
    human_review,
    select_destination,
    standard_queue,
)
from app.nodes.summarize import generate_summary
from app.outputs import OutputWriter
from app.repositories.events import EventsRepository
from app.repositories.records import RecordsRepository
from app.state import TriageState


def compile_graph(
    *,
    provider: LLMProvider,
    events: EventsRepository,
    records: RecordsRepository,
    writer: OutputWriter,
    outbound: OutboundWebhook,
    prompts_dir: Path | None = None,
):
    prompt_root = prompts_dir or Path(__file__).parent / "prompts"
    triage_prompt = (prompt_root / "triage_system.txt").read_text(encoding="utf-8")
    summary_prompt = (prompt_root / "summary_system.txt").read_text(encoding="utf-8")

    builder = StateGraph(TriageState)
    builder.add_node("initialize_state", initialize_state)
    builder.add_node("normalize_request", normalize_request)
    builder.add_node(
        "analyze_request", partial(analyze_request, provider=provider, triage_prompt=triage_prompt)
    )
    builder.add_node("validate_analysis", validate_analysis)
    builder.add_node(
        "repair_analysis", partial(repair_analysis, provider=provider, triage_prompt=triage_prompt)
    )
    builder.add_node("force_escalation", force_escalation)
    builder.add_node("apply_policy", apply_policy)
    builder.add_node(
        "generate_summary",
        partial(generate_summary, provider=provider, summary_prompt=summary_prompt),
    )
    builder.add_node("select_destination", select_destination)
    builder.add_node("human_review", human_review)
    builder.add_node("standard_queue", standard_queue)
    builder.add_node(
        "persist_result", partial(persist_result, records=records, events=events, writer=writer)
    )
    builder.add_node(
        "deliver_outbound_webhook",
        partial(deliver_outbound_webhook, records=records, outbound=outbound),
    )
    builder.add_node(
        "mark_complete", partial(mark_complete, records=records, events=events, writer=writer)
    )

    builder.add_edge(START, "initialize_state")
    builder.add_edge("initialize_state", "normalize_request")
    builder.add_edge("normalize_request", "analyze_request")
    builder.add_edge("analyze_request", "validate_analysis")
    builder.add_conditional_edges(
        "validate_analysis",
        validation_route,
        {"valid": "apply_policy", "repair": "repair_analysis", "invalid": "force_escalation"},
    )
    builder.add_edge("repair_analysis", "validate_analysis")
    builder.add_edge("apply_policy", "generate_summary")
    builder.add_edge("force_escalation", "generate_summary")
    builder.add_edge("generate_summary", "select_destination")
    builder.add_conditional_edges(
        "select_destination",
        destination_route,
        {"human_review": "human_review", "standard_queue": "standard_queue"},
    )
    builder.add_edge("human_review", "persist_result")
    builder.add_edge("standard_queue", "persist_result")
    builder.add_edge("persist_result", "deliver_outbound_webhook")
    builder.add_edge("deliver_outbound_webhook", "mark_complete")
    builder.add_edge("mark_complete", END)
    return builder.compile(checkpointer=InMemorySaver())
