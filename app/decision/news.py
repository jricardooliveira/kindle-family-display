"""Deterministic news deduplication and small category-balanced selection."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

from app.collectors.rss import _canonical_url, _title_key
from app.contracts import NewsItem

_MAX_AGE = timedelta(hours=48)
_MAX_FUTURE = timedelta(minutes=5)
_CATEGORIES = ("national", "portugal", "world")
# How many recent stories a rotation window cycles through.
ROTATION_POOL = 8


def parse_window(value: str) -> tuple[time, time]:
    """Parse a local "HH:MM-HH:MM" period that starts before it ends."""
    try:
        start_text, end_text = value.split("-")
        start, end = time.fromisoformat(start_text.strip()), time.fromisoformat(end_text.strip())
    except ValueError as exc:
        raise ValueError("news rotation windows must look like 07:30-08:30") from exc
    if start >= end:
        raise ValueError("news rotation windows must start before they end")
    return start, end


def rotation_offset(local_now: datetime, windows: list[str], step_minutes: int) -> int | None:
    """Return how many steps into an active rotation window `local_now` is, if any."""
    current = local_now.time()
    for window in windows:
        start, end = parse_window(window)
        if start <= current < end:
            elapsed = (current.hour - start.hour) * 60 + current.minute - start.minute
            return elapsed // max(1, step_minutes)
    return None


def rotate(news: list[NewsItem], offset: int, count: int) -> list[NewsItem]:
    """Pick `count` consecutive stories starting `offset` places into the list, wrapping."""
    if not news:
        return []
    return [news[(offset + index) % len(news)] for index in range(min(count, len(news)))]


def select_news(news: list[NewsItem], *, now: datetime, max_items: int = 2) -> list[NewsItem]:
    """Return fresh, deduplicated headlines, balancing the configured categories."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if isinstance(max_items, bool) or not isinstance(max_items, int) or max_items < 0:
        raise ValueError("max_items must be a non-negative integer")
    if max_items == 0:
        return []
    current = now.astimezone(UTC)
    candidates = sorted(news, key=lambda item: (-item.published_at.timestamp(), item.id))
    unique: list[NewsItem] = []
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    seen_urls: set[str] = set()
    for item in candidates:
        published_at = item.published_at.astimezone(UTC)
        if not current - _MAX_AGE <= published_at <= current + _MAX_FUTURE:
            continue
        title = _title_key(item.title)
        url = _canonical_url(item.url)
        if item.id in seen_ids or title in seen_titles or (url is not None and url in seen_urls):
            continue
        seen_ids.add(item.id)
        seen_titles.add(title)
        if url is not None:
            seen_urls.add(url)
        unique.append(item)

    grouped = {
        category: [item for item in unique if item.category == category] for category in _CATEGORIES
    }
    categories = sorted(
        (category for category, items in grouped.items() if items),
        key=lambda category: (-grouped[category][0].published_at.timestamp(), category),
    )
    selected: list[NewsItem] = []
    positions = {category: 0 for category in categories}
    while len(selected) < max_items and any(
        positions[category] < len(grouped[category]) for category in categories
    ):
        for category in categories:
            position = positions[category]
            if position < len(grouped[category]) and len(selected) < max_items:
                selected.append(grouped[category][position])
                positions[category] += 1
    return selected
