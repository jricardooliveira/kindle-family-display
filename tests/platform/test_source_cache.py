import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.storage.sources import SourceCache

NOW = datetime(2026, 10, 4, 7, 30, tzinfo=UTC)
SOURCES = [
    {"id": "calendar-a", "kind": "ics", "fingerprint": "hash-a"},
    {"id": "weather-a", "kind": "weather", "fingerprint": "hash-weather"},
]


def database_url(path: Path) -> str:
    return f"sqlite:///{path}"


def required_row(cache: SourceCache, source_id: str) -> dict[str, Any]:
    row = cache.get(source_id)
    assert row is not None
    return row


def test_success_survives_restart_with_utc_timestamps(tmp_path):
    db_url = database_url(tmp_path / "dashboard.db")
    cache = SourceCache(db_url)
    cache.sync(SOURCES)
    cache.success("calendar-a", {"events": [{"id": "e-1"}]}, NOW)
    first = cache.get("calendar-a")
    cache.close()

    reopened = SourceCache(db_url)
    row = required_row(reopened, "calendar-a")
    assert row == first
    assert row["data"] == {"events": [{"id": "e-1"}]}
    assert row["last_attempt_at"] == "2026-10-04T07:30:00+00:00"
    assert row["last_success_at"] == "2026-10-04T07:30:00+00:00"
    assert row["last_error"] is None
    reopened.close()


def test_failure_retains_last_good_data_and_success_timestamp(tmp_path):
    cache = SourceCache(database_url(tmp_path / "dashboard.db"))
    cache.sync(SOURCES)
    cache.success("calendar-a", {"events": [{"id": "e-1"}]}, NOW)

    cache.failure("calendar-a", "timeout", NOW + timedelta(minutes=5))
    row = required_row(cache, "calendar-a")

    assert row["data"] == {"events": [{"id": "e-1"}]}
    assert row["last_success_at"] == "2026-10-04T07:30:00+00:00"
    assert row["last_attempt_at"] == "2026-10-04T07:35:00+00:00"
    assert row["last_error"] == "timeout"
    cache.close()


def test_success_with_empty_data_clears_old_cached_facts(tmp_path):
    cache = SourceCache(database_url(tmp_path / "dashboard.db"))
    cache.sync(SOURCES)
    cache.success("calendar-a", {"events": [{"id": "e-1"}]}, NOW)
    cache.success("calendar-a", {"events": []}, NOW + timedelta(hours=1))

    row = required_row(cache, "calendar-a")
    assert row["data"] == {"events": []}
    assert row["last_attempt_at"] == "2026-10-04T08:30:00+00:00"
    assert row["last_success_at"] == row["last_attempt_at"]
    cache.close()


def test_sync_preserves_unchanged_sources_resets_changed_sources_and_removes_deleted(tmp_path):
    cache = SourceCache(database_url(tmp_path / "dashboard.db"))
    cache.sync(SOURCES)
    cache.success("calendar-a", {"events": [{"id": "e-1"}]}, NOW)
    cache.failure("weather-a", "dns_failed", NOW)

    cache.sync(
        [
            {"id": "calendar-a", "kind": "ics", "fingerprint": "hash-a"},
            {"id": "weather-a", "kind": "weather", "fingerprint": "hash-new"},
        ]
    )
    assert required_row(cache, "calendar-a")["data"] == {"events": [{"id": "e-1"}]}
    changed = required_row(cache, "weather-a")
    assert changed["data"] is None
    assert changed["last_attempt_at"] is None
    assert changed["last_success_at"] is None
    assert changed["last_error"] is None

    cache.sync([SOURCES[0]])
    assert cache.get("weather-a") is None
    assert [row["id"] for row in cache.records()] == ["calendar-a"]
    cache.close()


def test_sources_fail_independently_and_unknown_errors_are_sanitized(tmp_path):
    cache = SourceCache(database_url(tmp_path / "dashboard.db"))
    cache.sync(SOURCES)
    cache.success("calendar-a", {"events": [{"id": "e-1"}]}, NOW)

    cache.failure("weather-a", "https://secret.example/api?token=private", NOW)

    assert required_row(cache, "calendar-a")["last_error"] is None
    assert required_row(cache, "weather-a")["last_error"] == "source_error"
    assert "secret.example" not in str(cache.records())
    cache.close()


def test_success_rejects_nan_and_oversized_data_atomically(tmp_path):
    cache = SourceCache(database_url(tmp_path / "dashboard.db"))
    cache.sync(SOURCES)
    cache.success("calendar-a", {"events": [{"id": "e-1"}]}, NOW)
    before = required_row(cache, "calendar-a")

    with pytest.raises(ValueError):
        cache.success("calendar-a", {"value": float("nan")}, NOW + timedelta(minutes=1))
    with pytest.raises(ValueError, match="1 MiB"):
        cache.success("calendar-a", {"value": "x" * (1024 * 1024)}, NOW + timedelta(minutes=2))

    assert cache.get("calendar-a") == before
    cache.close()


def test_invalid_cached_json_is_reported_without_returning_raw_data(tmp_path):
    path = tmp_path / "dashboard.db"
    cache = SourceCache(database_url(path))
    cache.sync(SOURCES)
    cache.success("calendar-a", {"events": [{"id": "e-1"}]}, NOW)
    cache.close()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE source_cache SET data_json = ? WHERE source_id = ?",
            ("{private invalid", "calendar-a"),
        )

    reopened = SourceCache(database_url(path))
    row = required_row(reopened, "calendar-a")
    assert row["data"] is None
    assert row["last_error"] == "invalid_cache"
    assert row["last_success_at"] == "2026-10-04T07:30:00+00:00"
    assert "private invalid" not in str(row)
    reopened.close()


def test_sync_rejects_duplicate_ids_without_partial_changes(tmp_path):
    cache = SourceCache(database_url(tmp_path / "dashboard.db"))
    cache.sync(SOURCES)
    before = cache.records()

    with pytest.raises(ValueError):
        cache.sync([SOURCES[0], SOURCES[0]])

    assert cache.records() == before
    cache.close()
