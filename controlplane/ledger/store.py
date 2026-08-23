from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from controlplane.ledger.hash_chain import GENESIS_HASH, record_hash
from controlplane.ledger.records import canonical_record
from controlplane.models import DecisionTrace


class LedgerStore:
    """Append and verify hash-chained decision records in SQLite."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # One connection reused across threads, guarded by our own lock. Opening a
        # connection per append cost a full connect on the request path and left the
        # read-then-write below unserialised.
        self._connection = sqlite3.connect(path, check_same_thread=False, timeout=30.0)
        self._lock = threading.Lock()
        self._configure()
        self._create_schema()

    def append(self, trace: DecisionTrace) -> str:
        record = canonical_record(trace)
        with self._lock:
            # The previous hash is read and the new row written inside one write
            # transaction. Without IMMEDIATE the SELECT takes only a shared lock, so two
            # appends could read the same predecessor and fork the chain for good.
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT record_hash FROM decisions ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous = str(row[0]) if row else GENESIS_HASH
                digest = record_hash(previous, record)
                self._connection.execute(
                    """
                    INSERT INTO decisions(event_id, record_json, previous_hash, record_hash)
                    VALUES (?, ?, ?, ?)
                    """,
                    (trace.interaction_id, record, previous, digest),
                )
            except BaseException:
                self._connection.rollback()
                raise
            self._connection.commit()
        return digest

    def verify(self) -> tuple[bool, int]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT record_json, previous_hash, record_hash FROM decisions ORDER BY sequence"
            ).fetchall()
        expected_previous = GENESIS_HASH
        for index, (record, previous, digest) in enumerate(rows, start=1):
            if previous != expected_previous or digest != record_hash(previous, record):
                return False, index
            expected_previous = str(digest)
        return True, len(rows)

    def records(self, limit: int = 100) -> list[dict[str, str | int]]:
        with self._lock:
            rows = self._connection.execute(
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

    def reset(self) -> None:
        """Clear the chain in place; deleting the file would strand the open connection."""
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            self._connection.execute("DELETE FROM decisions")
            self._connection.execute(
                "DELETE FROM sqlite_sequence WHERE name = 'decisions'"
            )
            self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _configure(self) -> None:
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=NORMAL")
        self._connection.execute("PRAGMA busy_timeout=30000")

    def _create_schema(self) -> None:
        with self._lock:
            self._connection.execute(
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
            self._connection.commit()
