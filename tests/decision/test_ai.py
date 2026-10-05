from __future__ import annotations

import json
from datetime import UTC, datetime

from app.contracts import NewsItem
from app.decision.ai import read_api_key, score_news

NOW = datetime(2026, 10, 5, 8, 0, tzinfo=UTC)


def story(index: int) -> NewsItem:
    return NewsItem(
        id=f"s{index}", title=f"Título {index}", published_at=NOW, source="x", category="portugal"
    )


def reply(scores: object) -> dict:
    return {"choices": [{"message": {"content": json.dumps({"scores": scores})}}]}


def test_score_news_maps_valid_scores_and_ignores_invalid_entries() -> None:
    seen: dict = {}

    def transport(body: dict, key: str) -> dict:
        seen.update(body=body, key=key)
        return reply(
            [
                {"n": 1, "score": 9, "topic": " Eleições  Brasil "},
                {"n": 2, "score": 11},
                {"n": 7, "score": 5},
                {"n": 3, "score": True},
                "junk",
            ]
        )

    scores = score_news(
        [story(1), story(2), story(3)],
        api_key="k",
        model="m",
        known_topics=["greve cp"],
        transport=transport,
    )

    assert scores == {"s1": (9, "eleições brasil")}
    assert "Temas já usados: greve cp" in seen["body"]["messages"][1]["content"]
    assert seen["key"] == "k"
    assert "1. Título 1" in seen["body"]["messages"][1]["content"]
    assert seen["body"]["response_format"]["json_schema"]["strict"] is True


def test_score_news_falls_back_to_nothing_on_any_provider_problem() -> None:
    def broken(body: dict, key: str) -> dict:
        raise TimeoutError

    assert score_news([story(1)], api_key="k", model="m", transport=broken) == {}
    assert score_news([story(1)], api_key="k", model="m", transport=lambda b, k: {}) == {}
    assert score_news([], api_key="k", model="m", transport=broken) == {}


def test_read_api_key_accepts_bare_or_named_keys(tmp_path) -> None:
    named = tmp_path / "named"
    named.write_text("APIKEY='abc123'\n")
    bare = tmp_path / "bare"
    bare.write_text("xyz\n")

    assert read_api_key(str(named)) == "abc123"
    assert read_api_key(str(bare)) == "xyz"
    assert read_api_key(str(tmp_path / "missing")) is None
    assert read_api_key(None) is None
