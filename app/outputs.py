from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from app.repositories.records import RecordsRepository
from app.schemas import FinalTriageRecord

QUEUE_FILES = {
    "Engineering": "engineering.jsonl",
    "Engineering - Incident Response": "incident_response.jsonl",
    "Product": "product.jsonl",
    "Billing": "billing.jsonl",
    "Technical Support": "technical_support.jsonl",
    "Human Review": "human_review.jsonl",
}


class OutputWriter:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.queue_dir = output_dir / "queues"
        self._lock = threading.Lock()

    def initialize_queue_files(self) -> None:
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        for filename in QUEUE_FILES.values():
            path = self.queue_dir / filename
            if not path.exists():
                path.write_text("", encoding="utf-8")

    def sync_queues(self, repository: RecordsRepository) -> None:
        with self._lock:
            self.initialize_queue_files()
            for destination, filename in QUEUE_FILES.items():
                records = repository.list_by_destination(destination)
                content = "".join(
                    json.dumps(record.model_dump(mode="json"), sort_keys=True) + "\n"
                    for record in records
                )
                self._atomic_write(self.queue_dir / filename, content)

    def write_results(self, records: list[FinalTriageRecord]) -> None:
        content = (
            json.dumps(
                [record.model_dump(mode="json") for record in records], indent=2, sort_keys=True
            )
            + "\n"
        )
        with self._lock:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self._atomic_write(self.output_dir / "triage_results.json", content)

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
