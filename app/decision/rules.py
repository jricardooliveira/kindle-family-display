"""Deterministic screen candidate selection and decision validation."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.contracts.models import DisplayContext, DisplayDecision, DisplayItem, DisplayLayout, Screen

_SCREEN_KINDS: dict[Screen, set[str]] = {
    "news-weather": {"alert", "weather", "news"},
    "family": {"alert", "calendar", "countdown", "verse", "fact", "photo", "local_event"},
    "calendar": {"alert", "calendar"},
    "news": {"alert", "news"},
    "nearby": {"alert", "local_event"},
    "photo": {"alert", "photo"},
}
_KIND_RANK = {
    "calendar": 1,
    "countdown": 1,
    "weather": 2,
    "news": 3,
    "alert": 4,
    "verse": 4,
    "fact": 4,
    "photo": 4,
    "local_event": 4,
}


def _protected_ids(context: DisplayContext) -> set[str]:
    return set(context.protected_alert_ids) | {
        item.id for item in context.items if item.is_protected or item.severity == "critical"
    }


def _sort_key(item: DisplayItem) -> tuple[int, int, int, str]:
    severity_rank = {"critical": 0, "disruption": 1, "ordinary": 2}[item.severity]
    return (severity_rank, _KIND_RANK.get(item.kind, 4), -item.priority, item.id)


def _is_weekend(context: DisplayContext) -> bool:
    """Nearby events are offered from Friday afternoon until Sunday night."""
    local = context.generated_at.astimezone(ZoneInfo(context.timezone))
    return local.weekday() >= 5 or (local.weekday() == 4 and local.hour >= 15)


def _order_time(item: DisplayItem, context: DisplayContext) -> datetime:
    if item.kind == "calendar":
        return item.occurred_at
    if item.kind == "local_event":
        # Soonest first; long-running events already under way come after fresh ones.
        if item.occurred_at < context.generated_at - timedelta(hours=12):
            return context.generated_at + timedelta(days=30)
        return item.occurred_at
    return context.generated_at


def _night_candidates(context: DisplayContext, candidates: list[DisplayItem]) -> list[DisplayItem]:
    """At night only the first event of the coming morning's day matters."""
    zone = ZoneInfo(context.timezone)
    local = context.generated_at.astimezone(zone)
    day = local.date() + timedelta(days=1 if local.hour >= 12 else 0)
    events = [
        item
        for item in candidates
        if item.kind == "calendar" and item.occurred_at.astimezone(zone).date() == day
    ]
    events.sort(key=lambda item: (item.occurred_at, item.id))
    if events:
        return events[:1]
    return [item for item in candidates if item.kind not in ("calendar", "countdown")]


def _layout_for(
    screen: Screen, protected_ids: list[str], selected: list[DisplayItem]
) -> DisplayLayout:
    ordinary_ids = [item.id for item in selected]
    if screen == "news-weather" and protected_ids:
        return DisplayLayout.WEATHER_ALERT
    if screen == "family" and selected and selected[0].kind in ("verse", "fact"):
        return DisplayLayout.QUOTE
    if screen == "family" and selected and selected[0].kind == "local_event":
        return DisplayLayout.NEARBY
    if len(ordinary_ids) >= 3:
        return DisplayLayout.THREE_ITEMS
    if len(ordinary_ids) >= 2:
        return DisplayLayout.HERO_SECONDARY
    return DisplayLayout.HERO


def select_items(context: DisplayContext, screen: Screen) -> DisplayDecision:
    """Select up to three ordinary candidates while retaining every protected alert."""
    if screen not in _SCREEN_KINDS:
        raise ValueError(f"unknown screen: {screen}")
    protected = _protected_ids(context)
    weekend = _is_weekend(context)
    items_by_id = {item.id: item for item in context.items}
    protected_ids = sorted(
        protected,
        key=lambda item_id: (
            _sort_key(items_by_id[item_id]),
            item_id,
        ),
    )
    candidates = [
        item
        for item in context.items
        if item.id not in protected
        and item.kind in _SCREEN_KINDS[screen]
        and not (
            screen == "family"
            and item.kind == "calendar"
            and (item.ends_at or item.occurred_at) <= context.generated_at
        )
        and not (screen == "family" and item.kind == "local_event" and not weekend)
    ]
    candidates.sort(
        key=lambda item: (
            _sort_key(item)[:3],
            _order_time(item, context),
            item.distance_km or 0.0,
            item.id,
        )
    )
    if screen == "family" and context.night:
        candidates = _night_candidates(context, candidates)
    selected: list[DisplayItem] = []
    news_count = 0
    for item in candidates:
        if item.kind == "news" and screen == "news-weather":
            if news_count >= 2:
                continue
            news_count += 1
        selected.append(item)
        if len(selected) == 3:
            break
    item_ids = [item.id for item in selected]
    return DisplayDecision(
        layout=_layout_for(screen, protected_ids, selected),
        item_ids=item_ids,
        protected_alert_ids=protected_ids,
        reason=f"Rules selected candidates for the {screen} screen",
        generated_at=context.generated_at,
        provider="rules",
    )


def validate_decision(decision: DisplayDecision, context: DisplayContext) -> DisplayDecision:
    """Reject decisions that reference unknown items or drop protected alerts."""
    known_ids = {item.id for item in context.items}
    unknown_ids = (set(decision.item_ids) | set(decision.protected_alert_ids)) - known_ids
    if unknown_ids:
        raise ValueError(f"decision contains unknown item ids: {', '.join(sorted(unknown_ids))}")

    expected_protected = _protected_ids(context)
    actual_protected = set(decision.protected_alert_ids)
    missing_protected = expected_protected - actual_protected
    if missing_protected:
        raise ValueError("decision omits protected alerts: " + ", ".join(sorted(missing_protected)))
    extra_protected = actual_protected - expected_protected
    if extra_protected:
        raise ValueError(
            "decision contains unprotected alert ids: " + ", ".join(sorted(extra_protected))
        )

    ordinary_ids = set(decision.item_ids)
    if ordinary_ids & expected_protected:
        raise ValueError("protected alerts must be listed separately from ordinary item_ids")
    return decision
