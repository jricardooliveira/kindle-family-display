from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.collectors.events import parse_events
from app.collectors.pipeline import _nearby_items
from app.contracts.models import NearbyEvent

LISBON = ZoneInfo("Europe/Lisbon")


def page(*nodes: dict) -> bytes:
    graph = json.dumps({"@context": "https://schema.org", "@graph": list(nodes)})
    return f'<html><script type="application/ld+json">{graph}</script></html>'.encode()


def node(event_id: int, name: str, start: str, **extra) -> dict:
    return {
        "@type": "MusicEvent",
        "name": name,
        "url": f"https://example.com/pt/events/{event_id}/slug",
        "startDate": start,
        "location": {"@type": "Place", "name": "Auditório &amp; Jardim"},
        **extra,
    }


def test_parse_events_reads_json_ld_and_skips_malformed_entries() -> None:
    payload = page(
        node(2, "Concerto  de\nOutono", "2026-10-10T21:00:00+01:00"),
        node(1, "Feira", "2026-10-09", endDate="2026-10-11"),
        node(3, "Sem data", "amanhã"),
        node(4, "Ligação estranha", "2026-10-10", url="javascript:alert(1)"),
        {"@type": "Organization", "name": "Não é evento"},
    )

    events = parse_events(payload, source_id="vila", timezone="Europe/Lisbon")

    assert [(event.id, event.title, event.all_day) for event in events] == [
        ("vila:1", "Feira", True),
        ("vila:2", "Concerto de Outono", False),
    ]
    assert events[0].ends_at == datetime(2026, 10, 11, tzinfo=LISBON)
    assert events[1].venue == "Auditório & Jardim"
    with pytest.raises(ValueError):
        parse_events(b"<html>no data</html>", source_id="vila", timezone="Europe/Lisbon")


def test_nearby_items_keep_only_upcoming_events_until_sunday() -> None:
    saturday = datetime(2026, 10, 10, 10, 0, tzinfo=LISBON)

    def event(key: str, start: datetime, **extra) -> NearbyEvent:
        return NearbyEvent(
            id=key, title=key, starts_at=start, url=f"https://example.com/{key}", **extra
        )

    nearby = [
        (event("tonight", saturday.replace(hour=21)), 10.0),
        (event("earlier", saturday.replace(hour=7)), 10.0),
        (event("yesterday", saturday.replace(day=9), all_day=True), 0.0),
        (
            event(
                "festival", saturday.replace(day=9), ends_at=saturday.replace(day=11), all_day=True
            ),
            0.0,
        ),
        (event("sunday", saturday.replace(day=11, hour=16)), 0.0),
        (event("next-week", saturday.replace(day=14)), 0.0),
    ]

    items = _nearby_items(nearby, saturday)

    assert [item.title for item in items] == ["festival", "tonight", "sunday"]
    assert all(item.kind == "local_event" and item.url for item in items)
    assert items[1].distance_km == 10.0
