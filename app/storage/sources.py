"""Persistent normalized source facts and per-source refresh metadata."""

import json
import sqlite3
import threading
from datetime import UTC, datetime
from typing import Any

from app.storage.cache import database_path_from_url

_MAX_JSON_BYTES = 1024 * 1024
_SAFE_ERRORS = {
    "timeout",
    "dns_failed",
    "http_error",
    "blocked_url",
    "body_too_large",
    "redirect_blocked",
    "invalid_body",
    "invalid_payload",
    "invalid_cache",
}


class SourceCache:
    """Thread-safe SQLite cache for normalized collector output."""

    def __init__(self, database_url: str):
        database_path = database_path_from_url(database_url)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA busy_timeout = 5000")
        with self._lock:
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS source_cache (
                    source_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    data_json TEXT,
                    last_attempt_at TEXT,
                    last_success_at TEXT,
                    last_error TEXT
                )"""
            )
            self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def sync(self, sources: list[dict[str, str]]) -> None:
        """Keep exactly the configured sources, clearing cache on config changes."""
        configured: dict[str, tuple[str, str]] = {}
        for source in sources:
            if not isinstance(source, dict):
                raise TypeError("each source must contain id, kind, and fingerprint strings")
            source_id = source.get("id")
            kind = source.get("kind")
            fingerprint = source.get("fingerprint")
            if (
                not isinstance(source_id, str)
                or not source_id.strip()
                or not isinstance(kind, str)
                or not kind.strip()
                or not isinstance(fingerprint, str)
                or not fingerprint.strip()
            ):
                raise ValueError("each source must contain id, kind, and fingerprint strings")
            source_id = source_id.strip()
            if source_id in configured:
                raise ValueError("source ids must be unique")
            configured[source_id] = (kind.strip(), fingerprint)

        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                existing = {
                    row["source_id"]: dict(row)
                    for row in self._connection.execute("SELECT * FROM source_cache")
                }
                removed = set(existing) - set(configured)
                if removed:
                    self._connection.executemany(
                        "DELETE FROM source_cache WHERE source_id = ?",
                        [(source_id,) for source_id in removed],
                    )
                for source_id, (kind, fingerprint) in configured.items():
                    previous = existing.get(source_id)
                    if previous is None:
                        self._connection.execute(
                            "INSERT INTO source_cache (source_id, kind, fingerprint) "
                            "VALUES (?, ?, ?)",
                            (source_id, kind, fingerprint),
                        )
                    elif previous["kind"] != kind or previous["fingerprint"] != fingerprint:
                        self._connection.execute(
                            """UPDATE source_cache SET kind = ?, fingerprint = ?, data_json = NULL,
                                last_attempt_at = NULL, last_success_at = NULL, last_error = NULL
                                WHERE source_id = ?""",
                            (kind, fingerprint, source_id),
                        )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def get(self, source_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM source_cache WHERE source_id = ?", (source_id,)
            ).fetchone()
            return self._result(row) if row is not None else None

    def records(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM source_cache ORDER BY source_id"
            ).fetchall()
            return [self._result(row) for row in rows]

    def success(self, source_id: str, data: dict[str, Any], now: datetime) -> None:
        serialized = self._serialize_data(data)
        timestamp = self._timestamp(now)
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                cursor = self._connection.execute(
                    """UPDATE source_cache SET data_json = ?, last_attempt_at = ?,
                        last_success_at = ?, last_error = NULL WHERE source_id = ?""",
                    (serialized, timestamp, timestamp, source_id),
                )
                if cursor.rowcount != 1:
                    raise KeyError(source_id)
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def failure(self, source_id: str, code: str, now: datetime) -> None:
        timestamp = self._timestamp(now)
        safe_code = code if isinstance(code, str) and code in _SAFE_ERRORS else "source_error"
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                cursor = self._connection.execute(
                    "UPDATE source_cache SET last_attempt_at = ?, last_error = ? "
                    "WHERE source_id = ?",
                    (timestamp, safe_code, source_id),
                )
                if cursor.rowcount != 1:
                    raise KeyError(source_id)
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def _result(self, row: sqlite3.Row) -> dict[str, Any]:
        data: dict[str, Any] | None = None
        last_error = row["last_error"]
        serialized = row["data_json"]
        if serialized is not None:
            try:
                parsed = json.loads(serialized)
                if not isinstance(parsed, dict):
                    raise TypeError("cached source payload must be an object")
                data = parsed
            except (json.JSONDecodeError, TypeError, ValueError):
                self._connection.execute(
                    "UPDATE source_cache SET last_error = 'invalid_cache' WHERE source_id = ?",
                    (row["source_id"],),
                )
                self._connection.commit()
                last_error = "invalid_cache"
        return {
            "id": row["source_id"],
            "kind": row["kind"],
            "fingerprint": row["fingerprint"],
            "data": data,
            "last_attempt_at": row["last_attempt_at"],
            "last_success_at": row["last_success_at"],
            "last_error": last_error,
        }

    @staticmethod
    def _timestamp(now: datetime) -> str:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("cache timestamp must be timezone-aware")
        return now.astimezone(UTC).isoformat()

    @staticmethod
    def _serialize_data(data: dict[str, Any]) -> str:
        if not isinstance(data, dict):
            raise TypeError("source data must be a JSON object")
        try:
            serialized = json.dumps(
                data,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            raise ValueError("source data must contain strict JSON values") from None
        if len(serialized.encode("utf-8")) > _MAX_JSON_BYTES:
            raise ValueError("source data exceeds the 1 MiB limit")
        return serialized
