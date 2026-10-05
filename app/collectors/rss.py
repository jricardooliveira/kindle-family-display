"""Pure RSS/Atom parsing for already-fetched feed payloads."""

from __future__ import annotations

import hashlib
import re
from calendar import timegm
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser  # type: ignore[import-untyped]

from app.collectors.text import plain_text
from app.contracts import NewsItem

_MAX_AGE = timedelta(hours=48)
_MAX_FUTURE = timedelta(minutes=5)
_TRACKING_PARAMETERS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
_SOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")


def parse_rss(
    payload: bytes,
    *,
    source_id: str,
    category: Literal["national", "portugal", "world"],
    now: datetime,
    max_items: int = 64,
) -> list[NewsItem]:
    """Parse a bounded RSS/Atom payload; never performs network requests."""
    if not isinstance(payload, bytes):
        raise TypeError("RSS payload must be bytes")
    if not source_id or not _SOURCE_ID_PATTERN.fullmatch(source_id):
        raise ValueError("source_id must be a short stable identifier")
    if category not in ("national", "portugal", "world"):
        raise ValueError("category must be 'national', 'portugal' or 'world'")
    current = _aware_utc(now)
    if isinstance(max_items, bool) or not isinstance(max_items, int) or max_items < 0:
        raise ValueError("max_items must be a non-negative integer")
    if not payload.strip():
        raise ValueError("empty RSS/Atom response")

    document = feedparser.parse(payload)
    if document.get("bozo"):
        raise ValueError("malformed RSS/Atom feed")
    version = document.get("version", "")
    if not isinstance(version, str) or not version.startswith(("rss", "atom")):
        raise ValueError("response is not a recognized RSS/Atom feed")

    entries = document.get("entries", [])
    if not isinstance(entries, list):
        raise TypeError("RSS/Atom entries must be a list")

    result: list[NewsItem] = []
    seen_links: set[str] = set()
    seen_titles: set[str] = set()
    for entry in entries[:max_items]:
        if not isinstance(entry, dict):
            continue
        title = plain_text(entry.get("title"), max_length=160)
        if not title:
            continue
        published_at = _published_at(entry)
        if published_at is None or not _is_fresh(published_at, current):
            continue
        summary = _summary(entry)
        normalized_title = _title_key(title)
        url = _canonical_url(entry.get("link"))
        if normalized_title in seen_titles or (url is not None and url in seen_links):
            continue
        seen_titles.add(normalized_title)
        if url is not None:
            seen_links.add(url)

        identity = _identity(entry, url, normalized_title, published_at)
        item_id = f"rss:{source_id}:{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:32]}"
        result.append(
            NewsItem(
                id=item_id,
                title=title,
                summary=summary or None,
                published_at=published_at,
                source=source_id,
                category=category,
                url=url,
            )
        )
        if len(result) == max_items:
            break
    return result


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)


def _published_at(entry: dict[str, Any]) -> datetime | None:
    parsed = entry.get("published_parsed")
    if parsed is not None:
        try:
            return datetime.fromtimestamp(timegm(parsed), tz=UTC)
        except (OverflowError, TypeError, ValueError):
            return None

    raw = entry.get("published") or entry.get("date")
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip()
    try:
        parsed_date = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed_date = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed_date.tzinfo is None or parsed_date.utcoffset() is None:
        return None
    return parsed_date.astimezone(UTC)


def _is_fresh(published_at: datetime, now: datetime) -> bool:
    return now - _MAX_AGE <= published_at <= now + _MAX_FUTURE


def _summary(entry: dict[str, Any]) -> str:
    content = entry.get("content")
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict) and first.get("value"):
            cleaned = plain_text(first["value"], max_length=280)
            if cleaned:
                return cleaned
    return plain_text(entry.get("summary"), max_length=280)


def _title_key(title: str) -> str:
    return " ".join(title.casefold().split())


def _identity(entry: dict[str, Any], url: str | None, title: str, published_at: datetime) -> str:
    guid = entry.get("id")
    if isinstance(guid, str) and guid.strip():
        return f"guid:{guid.strip()}"
    if url:
        return f"url:{url}"
    return f"title:{title}|published:{published_at.isoformat()}"


def _canonical_url(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        parsed = urlsplit(value.strip())
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if scheme not in {"http", "https"} or not hostname or parsed.username or parsed.password:
        return None
    if any(character.isspace() for character in parsed.netloc):
        return None
    try:
        host = hostname.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host if port is None or default_port else f"{host}:{port}"
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    query_pairs = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_") and key.casefold() not in _TRACKING_PARAMETERS
    ]
    query_pairs.sort()
    canonical = urlunsplit((scheme, netloc, path, urlencode(query_pairs), ""))
    return canonical[:2048] if canonical else None
