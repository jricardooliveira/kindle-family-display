from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.contracts.models import DisplayContext, DisplayDecision, DisplayItem
from app.decision.rules import select_items, validate_decision

LISBON = ZoneInfo("Europe/Lisbon")
NOW = datetime(2026, 10, 4, 7, 30, tzinfo=LISBON)


def make_item(item_id, kind, priority, *, severity="ordinary", protected=False):
    return DisplayItem(
        id=item_id,
        kind=kind,
        title=item_id,
        priority=priority,
        occurred_at=NOW + timedelta(minutes=priority),
        severity=severity,
        is_protected=protected,
    )


def context(items, protected_ids=()):
    return DisplayContext(
        generated_at=NOW,
        timezone="Europe/Lisbon",
        mode="family",
        items=items,
        protected_alert_ids=list(protected_ids),
    )


def test_select_items_keeps_critical_alerts_separate_and_ranks_ordinary_items():
    critical = make_item("critical", "alert", 1, severity="critical")
    weather = make_item("weather", "weather", 90)
    family = make_item("family", "calendar", 20)
    news = make_item("news", "news", 100)
    result = select_items(context([news, family, critical, weather]), "news-weather")

    assert result.protected_alert_ids == ["critical"]
    assert result.item_ids == ["weather", "news"]
    assert len(result.item_ids) <= 3


def test_select_items_caps_news_and_is_deterministic():
    items = [make_item(f"news-{i}", "news", i) for i in range(5)]
    first = select_items(context(items), "news-weather")
    second = select_items(context(list(reversed(items))), "news-weather")

    assert first.item_ids == second.item_ids
    assert len(first.item_ids) == 2


def test_select_items_places_family_content_before_ambient_content():
    items = [
        make_item("verse", "verse", 100),
        make_item("fact", "fact", 100),
        make_item("photo", "photo", 100),
        make_item("family", "calendar", 1),
    ]
    result = select_items(context(items), "family")

    assert result.item_ids == ["family", "fact", "photo"]


def test_family_screen_excludes_ordinary_weather_and_news():
    items = [
        make_item("weather", "weather", 100),
        make_item("news", "news", 100),
        make_item("family", "countdown", 1),
    ]
    result = select_items(context(items), "family")

    assert result.item_ids == ["family"]


def test_select_items_orders_critical_before_disruption_alerts():
    alerts = [
        make_item("protected-ordinary", "alert", 100, protected=True),
        make_item("disruption", "alert", 100, severity="disruption", protected=True),
        make_item("critical", "alert", 1, severity="critical"),
    ]
    result = select_items(context(alerts), "news-weather")

    assert result.protected_alert_ids == ["critical", "disruption", "protected-ordinary"]


def test_select_items_does_not_choose_news_qr_from_an_item_id_prefix():
    result = select_items(context([make_item("news-story-1", "news", 10)]), "news-weather")

    assert result.layout == "hero"


def test_select_items_filters_items_by_screen_and_protected_alerts_ignore_cap():
    alerts = [make_item(f"alert-{i}", "alert", i, protected=True) for i in range(5)]
    family = make_item("family", "calendar", 50)
    news = make_item("news", "news", 100)
    result = select_items(context([*alerts, family, news]), "calendar")

    assert set(result.protected_alert_ids) == {f"alert-{i}" for i in range(5)}
    assert result.item_ids == ["family"]


def test_validate_decision_rejects_unknown_ids_and_removed_protected_alerts():
    protected = make_item("urgent", "alert", 100, severity="critical")
    ctx = context([protected, make_item("event", "calendar", 50)])

    unknown = DisplayDecision(
        layout="hero",
        item_ids=["missing"],
        protected_alert_ids=["urgent"],
        reason="unknown item",
        generated_at=NOW,
        provider="ai",
    )
    with pytest.raises(ValueError, match="unknown"):
        validate_decision(unknown, ctx)

    removed = DisplayDecision(
        layout="hero",
        item_ids=["event"],
        protected_alert_ids=[],
        reason="removed protected alert",
        generated_at=NOW,
        provider="ai",
    )
    with pytest.raises(ValueError, match="protected"):
        validate_decision(removed, ctx)


def test_validate_decision_allows_protected_ids_beyond_ordinary_item_limit():
    alerts = [make_item(f"alert-{i}", "alert", 100, protected=True) for i in range(5)]
    ctx = context(alerts + [make_item(f"event-{i}", "calendar", i) for i in range(4)])
    valid = DisplayDecision(
        layout="three_items",
        item_ids=["event-0", "event-1", "event-2"],
        protected_alert_ids=[f"alert-{i}" for i in range(5)],
        reason="retain all alerts",
        generated_at=NOW,
        provider="ai",
    )

    assert validate_decision(valid, ctx) == valid


def test_family_prefers_next_calendar_event_and_ignores_finished_events():
    from datetime import timedelta

    from app.contracts.models import DisplayItem

    context = DisplayContext(
        generated_at=NOW,
        timezone="Europe/Lisbon",
        demo=False,
        items=[
            DisplayItem(
                id=name,
                kind="calendar",
                title=name,
                occurred_at=NOW + timedelta(hours=start),
                ends_at=NOW + timedelta(hours=start + 1),
            )
            for name, start in [("z-next", 1), ("a-later", 5), ("finished", -4)]
        ],
    )
    decision = select_items(context, "family")
    assert decision.item_ids == ["z-next", "a-later"]


def test_night_family_screen_keeps_only_the_first_event_of_the_coming_morning():
    evening = datetime(2026, 10, 4, 22, 0, tzinfo=LISBON)

    def event(item_id, when):
        return DisplayItem(id=item_id, kind="calendar", title=item_id, occurred_at=when)

    items = [
        event("tonight", evening + timedelta(minutes=30)),
        event("tomorrow-late", evening + timedelta(hours=20)),
        event("tomorrow-early", evening + timedelta(hours=10)),
        DisplayItem(id="fact", kind="fact", title="fact", occurred_at=evening),
    ]
    night = DisplayContext(generated_at=evening, timezone="Europe/Lisbon", items=items, night=True)

    assert select_items(night, "family").item_ids == ["tomorrow-early"]
    quiet = night.model_copy(update={"items": [items[0], items[3]]})
    assert select_items(quiet, "family").item_ids == ["fact"]
    day = night.model_copy(update={"night": False})
    assert select_items(day, "family").item_ids[0] == "tonight"


def test_night_period_may_cross_midnight():
    from datetime import time

    from app.decision.periods import in_period, parse_period

    assert in_period("21:30-06:30", time(23, 0))
    assert in_period("21:30-06:30", time(5, 0))
    assert not in_period("21:30-06:30", time(12, 0))
    assert in_period("07:30-08:30", time(8, 0))
    with pytest.raises(ValueError):
        parse_period("night")


def test_weekend_nearby_events_put_fresh_ones_before_long_running_exhibitions():
    saturday = datetime(2026, 10, 10, 10, 0, tzinfo=LISBON)

    def nearby(item_id, when):
        return DisplayItem(
            id=item_id, kind="local_event", title=item_id, occurred_at=when, priority=2
        )

    items = [
        nearby("exhibition", saturday - timedelta(days=40)),
        nearby("tonight", saturday + timedelta(hours=11)),
        nearby("sunday", saturday + timedelta(days=1)),
        DisplayItem(id="fact", kind="fact", title="fact", occurred_at=saturday),
    ]
    weekend = DisplayContext(generated_at=saturday, timezone="Europe/Lisbon", items=items)

    result = select_items(weekend, "family")

    assert result.item_ids == ["tonight", "sunday", "exhibition"]
    assert result.layout == "nearby"
    weekday = weekend.model_copy(update={"generated_at": saturday - timedelta(days=3)})
    assert select_items(weekday, "family").item_ids == ["fact"]
