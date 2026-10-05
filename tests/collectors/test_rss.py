from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import pytest

from app.collectors.rss import parse_rss
from app.contracts import NewsItem
from app.decision.news import select_news

FIXTURES = Path(__file__).parents[1] / "fixtures" / "rss"
NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)


def load_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def news_item(
    item_id: str,
    title: str,
    published_at: datetime,
    *,
    category: Literal["portugal", "world"] = "portugal",
    url: str | None = None,
) -> NewsItem:
    return NewsItem(
        id=item_id,
        title=title,
        summary=None,
        published_at=published_at,
        source="synthetic-feed",
        category=category,
        url=url,
    )


def test_parse_rss_sanitizes_html_and_keeps_fresh_dated_items() -> None:
    items = parse_rss(
        load_fixture("sample-rss.xml"),
        source_id="portugal-news",
        category="portugal",
        now=NOW,
    )

    assert [item.title for item in items] == [
        "Portugal anuncia novas medidas",
        "Mercados recuperam",
    ]
    assert items[0].summary == "A & B avançam. Mais detalhes."
    assert "\x7f" not in (items[0].summary or "")
    assert "segredo" not in (items[0].summary or "")
    assert "private" not in (items[0].summary or "")
    assert items[1].summary == "Resumo com texto seguro & útil."
    assert items[0].published_at == datetime(2026, 10, 4, 11, 0, tzinfo=UTC)
    assert items[0].source == "portugal-news"
    assert items[0].category == "portugal"
    assert items[0].url == "https://news.example.pt/portugal/medidas"
    assert all(item.published_at.tzinfo is not None for item in items)


def test_parse_atom_and_stable_ids() -> None:
    payload = load_fixture("sample-atom.xml")
    first = parse_rss(payload, source_id="family-feed", category="world", now=NOW)
    second = parse_rss(payload, source_id="family-feed", category="world", now=NOW)

    assert len(first) == 1
    assert first == second
    assert first[0].published_at == datetime(2026, 10, 4, 9, 45, tzinfo=UTC)
    assert first[0].category == "world"
    assert first[0].url == "https://atom.example.net/escolas"


def test_valid_empty_feed_returns_empty_list() -> None:
    assert (
        parse_rss(
            load_fixture("empty-rss.xml"),
            source_id="empty-feed",
            category="portugal",
            now=NOW,
        )
        == []
    )


def test_malformed_or_empty_response_raises_instead_of_looking_like_no_news() -> None:
    for payload in (load_fixture("malformed-rss.xml"), b"  \n"):
        with pytest.raises(ValueError):
            parse_rss(payload, source_id="broken-feed", category="portugal", now=NOW)


def test_parse_rss_bounds_candidates_and_sanitizes_untrusted_urls() -> None:
    payload = b"""<?xml version='1.0'?>
    <rss version='2.0'><channel><title>Test</title>
      <item><guid>1</guid><title>Bad URL</title><link>javascript:alert(1)</link>
        <pubDate>Sun, 04 Oct 2026 11:50:00 GMT</pubDate></item>
      <item><guid>2</guid><title>Segundo artigo</title><link>https://example.test/2</link>
        <pubDate>Sun, 04 Oct 2026 11:40:00 GMT</pubDate></item>
    </channel></rss>"""

    items = parse_rss(payload, source_id="safe-feed", category="portugal", now=NOW, max_items=1)

    assert len(items) == 1
    assert items[0].title == "Bad URL"
    assert items[0].url is None


def test_parse_rss_bounds_title_and_summary_lengths() -> None:
    long_title = "T" * 200
    long_summary = "Resumo " * 60
    payload = (
        "<rss version='2.0'><channel><item><guid>long</guid>"
        f"<title>{long_title}</title><description><![CDATA[{long_summary}]]></description>"
        "<pubDate>Sun, 04 Oct 2026 11:00:00 GMT</pubDate>"
        "</item></channel></rss>"
    ).encode()

    items = parse_rss(payload, source_id="bounded-feed", category="portugal", now=NOW)

    assert len(items) == 1
    assert len(items[0].title) == 160
    assert len(items[0].summary or "") <= 280


def test_parse_rss_rejects_naive_now_and_invalid_category() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_rss(
            b"", source_id="feed", category="portugal", now=datetime.fromisoformat("2026-10-04")
        )
    with pytest.raises(ValueError, match="category"):
        parse_rss(load_fixture("empty-rss.xml"), source_id="feed", category="local", now=NOW)  # type: ignore[arg-type]


def test_select_news_balances_categories_then_preserves_freshness() -> None:
    candidates = [
        news_item("pt-latest", "Portuguese update", NOW - timedelta(minutes=1)),
        news_item("pt-next", "Another Portuguese update", NOW - timedelta(minutes=2)),
        news_item(
            "world-latest",
            "World update",
            NOW - timedelta(minutes=5),
            category="world",
        ),
    ]

    selected = select_news(candidates, now=NOW)

    assert [item.id for item in selected] == ["pt-latest", "world-latest"]
    assert [item.category for item in selected] == ["portugal", "world"]


def test_select_news_deduplicates_and_rejects_stale_or_future_items() -> None:
    candidates = [
        news_item("fresh", "Fresh story", NOW - timedelta(minutes=5), url="https://a.test/story"),
        news_item(
            "duplicate",
            "Other headline",
            NOW - timedelta(minutes=4),
            url="https://A.test/story/#top",
        ),
        news_item("old", "Old story", NOW - timedelta(hours=49)),
        news_item("future", "Future story", NOW + timedelta(minutes=6)),
    ]

    selected = select_news(candidates, now=NOW, max_items=8)

    assert [item.id for item in selected] == ["duplicate"]


def test_select_news_requires_aware_now_and_bounds_result_count() -> None:
    candidates = [
        news_item(f"item-{index}", f"Story {index}", NOW - timedelta(minutes=index))
        for index in range(4)
    ]

    assert len(select_news(candidates, now=NOW, max_items=1)) == 1
    with pytest.raises(ValueError, match="timezone-aware"):
        select_news(candidates, now=datetime.fromisoformat("2026-10-04"))


def test_news_rotation_steps_through_stories_only_inside_configured_windows() -> None:
    from zoneinfo import ZoneInfo

    from app.decision.news import parse_window, rotate, rotation_offset

    lisbon = ZoneInfo("Europe/Lisbon")
    windows = ["07:30-08:30", "18:00-19:00"]

    def at(hour: int, minute: int) -> datetime:
        return datetime(2026, 10, 5, hour, minute, tzinfo=lisbon)

    assert rotation_offset(at(7, 29), windows, 5) is None
    assert rotation_offset(at(7, 30), windows, 5) == 0
    assert rotation_offset(at(7, 44), windows, 5) == 2
    assert rotation_offset(at(8, 30), windows, 5) is None
    assert rotation_offset(at(18, 10), windows, 5) == 2
    assert rotate(["a", "b", "c"], 2, 2) == ["c", "a"]
    assert rotate([], 3, 2) == []
    for invalid in ("morning", "08:30-07:30", "07:30"):
        with pytest.raises(ValueError):
            parse_window(invalid)
