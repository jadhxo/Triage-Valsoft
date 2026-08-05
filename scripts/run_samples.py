from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Settings  # noqa: E402
from app.llm.factory import create_provider  # noqa: E402
from app.llm.fake import FakeLLMProvider  # noqa: E402
from app.schemas import FinalTriageRecord, InboundWebhook  # noqa: E402
from app.services.container import build_services  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process the five ArcVault assessment samples")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use the deterministic fake provider and visibly label generated records",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_settings = Settings()
    if args.demo:
        provider = FakeLLMProvider()
        print("DEMO MODE: deterministic fake LLM output (not a live model evaluation)")
    else:
        try:
            provider = create_provider(base_settings)
        except RuntimeError as exc:
            print(f"Live provider is not configured: {exc}", file=sys.stderr)
            print("Configure .env or rerun with --demo.", file=sys.stderr)
            return 2

    sample_path = PROJECT_ROOT / "data" / "sample_requests.json"
    payloads = [
        InboundWebhook.model_validate(item)
        for item in json.loads(sample_path.read_text(encoding="utf-8"))
    ]
    output_dir = PROJECT_ROOT / base_settings.output_dir

    with tempfile.TemporaryDirectory(prefix="arcvault-samples-") as temp_dir:
        settings = base_settings.model_copy(
            update={
                "database_url": f"sqlite:///{Path(temp_dir) / 'samples.db'}",
                "output_dir": output_dir,
                "outbound_webhook_url": None,
            }
        )
        services = build_services(settings, provider=provider)
        for payload in payloads:
            created, _ = services.events.accept(payload)
            if not created:
                print(f"Duplicate sample in fresh state: {payload.event_id}", file=sys.stderr)
                return 1
            services.processor.process_event(payload.event_id)

        records = services.records.list_all()
        if len(records) != 5 or {record.event_id for record in records} != {
            payload.event_id for payload in payloads
        }:
            print("Batch did not produce exactly one record per sample", file=sys.stderr)
            return 1
        validated = [FinalTriageRecord.model_validate(record) for record in records]
        services.writer.write_results(validated)
        services.writer.sync_queues(services.records)

    print(f"{'EVENT':<12} {'CATEGORY':<22} {'PRIORITY':<9} DESTINATION")
    for record in validated:
        print(
            f"{record.event_id:<12} {(record.category.value if record.category else 'Unclassified'):<22} "
            f"{(record.priority.value if record.priority else 'N/A'):<9} {record.final_destination}"
        )
    print(f"Wrote {len(validated)} records to {output_dir / 'triage_results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
