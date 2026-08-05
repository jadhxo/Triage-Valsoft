from __future__ import annotations

from datetime import UTC, datetime

from app.repositories.database import Database
from app.schemas import FinalTriageRecord


def _now() -> str:
    return datetime.now(UTC).isoformat()


class RecordsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save(self, record: FinalTriageRecord) -> None:
        now = _now()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO triage_records
                    (event_id, final_destination, status, record_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    final_destination = excluded.final_destination,
                    status = excluded.status,
                    record_json = excluded.record_json,
                    updated_at = excluded.updated_at
                """,
                (
                    record.event_id,
                    record.final_destination,
                    record.status,
                    record.model_dump_json(),
                    now,
                    now,
                ),
            )

    def get(self, event_id: str) -> FinalTriageRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM triage_records WHERE event_id = ?", (event_id,)
            ).fetchone()
        return FinalTriageRecord.model_validate_json(row["record_json"]) if row else None

    def list_all(self) -> list[FinalTriageRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM triage_records ORDER BY event_id"
            ).fetchall()
        return [FinalTriageRecord.model_validate_json(row["record_json"]) for row in rows]

    def list_by_destination(self, destination: str) -> list[FinalTriageRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT record_json FROM triage_records
                WHERE final_destination = ? ORDER BY event_id
                """,
                (destination,),
            ).fetchall()
        return [FinalTriageRecord.model_validate_json(row["record_json"]) for row in rows]

    def record_delivery_attempt(
        self,
        *,
        event_id: str,
        attempt_number: int,
        success: bool,
        status_code: int | None,
        error: str | None,
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO delivery_attempts
                    (event_id, attempt_number, attempted_at, success, status_code, error)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_id, attempt_number, _now(), int(success), status_code, error),
            )

    def count_delivery_attempts(self, event_id: str) -> int:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM delivery_attempts WHERE event_id = ?", (event_id,)
            ).fetchone()
        return int(row["count"])

    def update_delivery(
        self, event_id: str, delivery_status: str, attempts: int, processing_status: str
    ) -> FinalTriageRecord:
        record = self.get(event_id)
        if record is None:
            raise KeyError(f"No triage record for {event_id}")
        data = record.model_dump()
        data.update(
            outbound_delivery_status=delivery_status,
            outbound_delivery_attempts=attempts,
            status=processing_status,
            processing_completed_at=datetime.now(UTC),
        )
        updated = FinalTriageRecord.model_validate(data)
        self.save(updated)
        return updated
