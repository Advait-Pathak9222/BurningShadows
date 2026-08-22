from __future__ import annotations

import sqlite3
from pathlib import Path

from controlplane.ledger.hash_chain import GENESIS_HASH, record_hash
from controlplane.ledger.records import canonical_record
from controlplane.models import DecisionTrace


class LedgerStore:
    """Append and verify hash-chained decision records in SQLite."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._create_schema()

    def append(self, trace: DecisionTrace) -> str:
        record = canonical_record(trace)
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT record_hash FROM decisions ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            previous = str(row[0]) if row else GENESIS_HASH
            digest = record_hash(previous, record)
            connection.execute(
                """
                INSERT INTO decisions(event_id, record_json, previous_hash, record_hash)
                VALUES (?, ?, ?, ?)
                """,
                (trace.interaction_id, record, previous, digest),
            )
            connection.commit()
        return digest

    def verify(self) -> tuple[bool, int]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                "SELECT record_json, previous_hash, record_hash FROM decisions ORDER BY sequence"
            ).fetchall()
        expected_previous = GENESIS_HASH
        for index, (record, previous, digest) in enumerate(rows, start=1):
            if previous != expected_previous or digest != record_hash(previous, record):
                return False, index
            expected_previous = str(digest)
        return True, len(rows)

    def records(self, limit: int = 100) -> list[dict[str, str | int]]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                """
                SELECT sequence, event_id, record_json, previous_hash, record_hash
                FROM decisions ORDER BY sequence DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "sequence": int(row[0]),
                "event_id": str(row[1]),
                "record_json": str(row[2]),
                "previous_hash": str(row[3]),
                "record_hash": str(row[4]),
            }
            for row in rows
        ]

    def _create_schema(self) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    record_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.commit()
