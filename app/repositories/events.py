from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from app.repositories.database import Database
from app.schemas import InboundWebhook


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class EventRow:
    event_id: str
    source: str
    payload: dict[str, object]
    status: str
    error: str | None


class EventsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def accept(self, payload: InboundWebhook) -> tuple[bool, EventRow]:
        now = utc_now_iso()
        serialized = payload.model_dump_json()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO events
                    (event_id, source, payload_json, status, accepted_at, updated_at)
                VALUES (?, ?, ?, 'accepted', ?, ?)
                """,
                (payload.event_id, payload.source.value, serialized, now, now),
            )
            created = cursor.rowcount == 1
            row = connection.execute(
                "SELECT event_id, source, payload_json, status, error FROM events WHERE event_id = ?",
                (payload.event_id,),
            ).fetchone()
        assert row is not None
        return created, self._map(row)

    def get(self, event_id: str) -> EventRow | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT event_id, source, payload_json, status, error FROM events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return self._map(row) if row else None

    def set_status(self, event_id: str, status: str, error: str | None = None) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE events SET status = ?, error = ?, updated_at = ? WHERE event_id = ?",
                (status, error, utc_now_iso(), event_id),
            )

    @staticmethod
    def _map(row: object) -> EventRow:
        return EventRow(
            event_id=row["event_id"],
            source=row["source"],
            payload=json.loads(row["payload_json"]),
            status=row["status"],
            error=row["error"],
        )
