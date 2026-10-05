"""Parse nearby public events from schema.org JSON-LD embedded in listing pages."""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from app.contracts.models import NearbyEvent

_LD_BLOCK = re.compile(
    rb'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
_EVENT_ID = re.compile(r"/events/(\d+)")
_MAX_EVENTS = 100


def parse_events(payload: bytes, *, source_id: str, timezone: str) -> list[NearbyEvent]:
    """Return the events a listing page declares, ignoring anything malformed."""
    zone = ZoneInfo(timezone)
    events: dict[str, NearbyEvent] = {}
    blocks = _LD_BLOCK.findall(payload)
    if not blocks:
        raise ValueError("page has no structured event data")
    for block in blocks:
        try:
            document = json.loads(block.decode("utf-8", errors="replace"))
        except ValueError:
            continue
        for node in _nodes(document):
            event = _event(node, source_id, zone)
            if event is not None and len(events) < _MAX_EVENTS:
                events.setdefault(event.id, event)
    return sorted(events.values(), key=lambda event: (event.starts_at, event.id))


def _nodes(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return [node for entry in document for node in _nodes(entry)]
    if not isinstance(document, dict):
        return []
    graph = document.get("@graph")
    return _nodes(graph) if graph is not None else [document]


def _event(node: dict[str, Any], source_id: str, zone: ZoneInfo) -> NearbyEvent | None:
    kind = node.get("@type")
    if not isinstance(kind, str) or not (kind.endswith("Event") or kind == "Festival"):
        return None
    title = _text(node.get("name"))
    start = _moment(node.get("startDate"), zone)
    url = node.get("url")
    if not title or start is None or not isinstance(url, str):
        return None
    if not url.startswith(("https://", "http://")) or len(url) > 2000:
        return None
    end = _moment(node.get("endDate"), zone)
    location = node.get("location")
    venue = _text(location.get("name")) if isinstance(location, dict) else ""
    match = _EVENT_ID.search(url)
    key = match.group(1) if match else hashlib.sha256(url.encode()).hexdigest()[:16]
    try:
        return NearbyEvent(
            id=f"{source_id}:{key}",
            title=title[:160],
            starts_at=start[0],
            ends_at=end[0] if end is not None and end[0] > start[0] else None,
            all_day=start[1],
            venue=venue[:80] or None,
            url=url,
        )
    except ValueError:
        return None


def _text(value: Any) -> str:
    return " ".join(html.unescape(value).split()) if isinstance(value, str) else ""


def _moment(value: Any, zone: ZoneInfo) -> tuple[datetime, bool] | None:
    """Parse an ISO date or date-time; a bare date is an all-day local event."""
    if not isinstance(value, str):
        return None
    try:
        if "T" not in value:
            return datetime.combine(date.fromisoformat(value), time.min, zone), True
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return (moment if moment.tzinfo else moment.replace(tzinfo=zone)), False
