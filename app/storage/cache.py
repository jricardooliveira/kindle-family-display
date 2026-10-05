"""SQLite index for immutable, atomically replaced PNG cache files."""

import hashlib
import os
import re
import sqlite3
import threading
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

_OWNED_PNG = re.compile(r"^(news-weather|news|family|calendar|nearby|photo)-[0-9a-f]{32}\.png$")
_OWNED_TEMP = re.compile(r"^\.(news-weather|news|family|calendar|nearby|photo)-[0-9a-f]{32}\.tmp$")


def database_path_from_url(database_url: str) -> Path:
    """Return the local file path for a validated sqlite:/// URL."""
    path = Path(database_url[len("sqlite:///") :]).expanduser()
    return path if path.is_absolute() else Path.cwd() / path


class ScreenCache:
    def __init__(self, database_url: str, cache_dir: str | Path):
        self.database_path = database_path_from_url(database_url)
        self.cache_dir = Path(cache_dir).expanduser()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS screen_cache (
                    screen TEXT PRIMARY KEY,
                    image_file TEXT,
                    generated_at TEXT,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    timezone TEXT NOT NULL DEFAULT 'Europe/Lisbon',
                    rotation INTEGER NOT NULL DEFAULT 0,
                    byte_length INTEGER NOT NULL DEFAULT 0,
                    sha256 TEXT NOT NULL DEFAULT '',
                    last_error TEXT
                )"""
            )
            columns = {
                row["name"] for row in self._connection.execute("PRAGMA table_info(screen_cache)")
            }
            for column, declaration in {
                "timezone": "TEXT NOT NULL DEFAULT 'Europe/Lisbon'",
                "rotation": "INTEGER NOT NULL DEFAULT 0",
                "byte_length": "INTEGER NOT NULL DEFAULT 0",
                "sha256": "TEXT NOT NULL DEFAULT ''",
            }.items():
                if column not in columns:
                    self._connection.execute(
                        f"ALTER TABLE screen_cache ADD COLUMN {column} {declaration}"
                    )
            self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def invalidate(self) -> None:
        """Remove images whose source configuration is no longer applicable."""
        with self._lock:
            self._connection.execute("DELETE FROM screen_cache")
            self._connection.commit()
            self.cleanup_orphans()

    def configure(self, fingerprint: str) -> None:
        """Invalidate existing images when switching sources or demo/live mode."""
        with self._lock:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS display_configuration (id INTEGER PRIMARY KEY, fingerprint TEXT)"
            )
            row = self._connection.execute(
                "SELECT fingerprint FROM display_configuration WHERE id = 1"
            ).fetchone()
            if row is None or row["fingerprint"] != fingerprint:
                self.invalidate()
                self._connection.execute(
                    "INSERT OR REPLACE INTO display_configuration VALUES (1, ?)", (fingerprint,)
                )
                self._connection.commit()

    def record(self, screen: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM screen_cache WHERE screen = ?", (screen,)
            ).fetchone()
            return dict(row) if row else None

    def read(self, screen: str) -> tuple[bytes, dict[str, Any]] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM screen_cache WHERE screen = ?", (screen,)
            ).fetchone()
            if row is None or row["image_file"] is None:
                return None
            try:
                content = (self.cache_dir / row["image_file"]).read_bytes()
            except FileNotFoundError:
                return None
            if (
                len(content) != row["byte_length"]
                or hashlib.sha256(content).hexdigest() != row["sha256"]
            ):
                return None
            try:
                with Image.open(BytesIO(content)) as image:
                    if image.format != "PNG" or image.size != (row["width"], row["height"]):
                        return None
                    image.verify()
            except (OSError, SyntaxError, ValueError):
                return None
            return content, dict(row)

    def write(
        self,
        screen: str,
        content: bytes,
        generated_at: str,
        width: int,
        height: int,
        timezone: str,
        rotation: int,
    ) -> None:
        try:
            with Image.open(BytesIO(content)) as image:
                if image.format != "PNG" or image.size != (width, height):
                    raise ValueError("renderer returned a PNG with unexpected dimensions")
                image.verify()
        except Exception as exc:
            raise ValueError("renderer returned an invalid PNG") from exc
        token = uuid.uuid4().hex
        image_name = f"{screen}-{token}.png"
        temp_path = self.cache_dir / f".{screen}-{token}.tmp"
        image_path = self.cache_dir / image_name
        with self._lock:
            old_row = self._connection.execute(
                "SELECT image_file FROM screen_cache WHERE screen = ?", (screen,)
            ).fetchone()
            old_name = old_row["image_file"] if old_row else None
            try:
                with temp_path.open("wb") as image_file:
                    image_file.write(content)
                    image_file.flush()
                    os.fsync(image_file.fileno())
                os.replace(temp_path, image_path)
                self._connection.execute("BEGIN IMMEDIATE")
                self._connection.execute(
                    """INSERT INTO screen_cache
                        (screen, image_file, generated_at, width, height, timezone, rotation,
                         byte_length, sha256, last_error)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                        ON CONFLICT(screen) DO UPDATE SET
                            image_file = excluded.image_file,
                            generated_at = excluded.generated_at,
                            width = excluded.width,
                            height = excluded.height,
                            timezone = excluded.timezone,
                            rotation = excluded.rotation,
                            byte_length = excluded.byte_length,
                            sha256 = excluded.sha256,
                            last_error = NULL""",
                    (
                        screen,
                        image_name,
                        generated_at,
                        width,
                        height,
                        timezone,
                        rotation,
                        len(content),
                        hashlib.sha256(content).hexdigest(),
                    ),
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                image_path.unlink(missing_ok=True)
                raise
            finally:
                temp_path.unlink(missing_ok=True)
            if old_name and old_name != image_name and _OWNED_PNG.fullmatch(old_name):
                (self.cache_dir / old_name).unlink(missing_ok=True)

    def record_failure(self, screen: str, width: int, height: int) -> None:
        with self._lock:
            self._connection.execute(
                """INSERT INTO screen_cache
                    (screen, image_file, generated_at, width, height, last_error)
                    VALUES (?, NULL, NULL, ?, ?, 'render failed')
                    ON CONFLICT(screen) DO UPDATE SET last_error = 'render failed'""",
                (screen, width, height),
            )
            self._connection.commit()

    def cleanup_orphans(self) -> None:
        with self._lock:
            rows = self._connection.execute(
                "SELECT image_file FROM screen_cache WHERE image_file IS NOT NULL"
            ).fetchall()
            referenced = {row["image_file"] for row in rows}
            for path in self.cache_dir.iterdir():
                if (
                    _OWNED_PNG.fullmatch(path.name) and path.name not in referenced
                ) or _OWNED_TEMP.fullmatch(path.name):
                    path.unlink(missing_ok=True)

    def records(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM screen_cache ORDER BY screen").fetchall()
            return [dict(row) for row in rows]
