from datetime import UTC, datetime

import pytest

from app.contracts import NewsItem
from app.decision.ai import score_news


@pytest.mark.parametrize(
    "language,country,name",
    [("pt", "PT", "Portugal"), ("en", "GB", "United Kingdom"), ("de", "DE", "Germany")],
)
def test_ai_scores_for_configured_country(language, country, name):
    seen = []

    def transport(body, key):
        seen.append(body)
        return {}

    news = NewsItem(
        id="x", title="Example", published_at=datetime.now(UTC), source="fixture", category="world"
    )
    assert (
        score_news(
            [news],
            api_key="test",
            model="test",
            language=language,
            country=country,
            transport=transport,
        )
        == {}
    )
    instructions = seen[0]["messages"][0]["content"]
    assert name in instructions
    if country != "PT":
        assert "Portugal" not in instructions
