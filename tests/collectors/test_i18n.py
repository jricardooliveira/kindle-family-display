from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.collectors.pipeline import _news_item, _photo_caption, _weather_items
from app.collectors.weather import parse_weather
from app.config import RSSFeed, Settings
from app.contracts import NewsItem
from app.decision.news import select_news

FIXTURES = Path(__file__).parents[1] / "fixtures" / "weather"


@pytest.mark.parametrize(
    ("language", "summary", "alert"),
    [
        ("pt", "Trovoada forte com granizo", "Chuva e vento fortes"),
        ("en", "Heavy thunderstorm with hail", "Heavy rain and strong wind"),
        ("de", "Starkes Gewitter mit Hagel", "Starkregen und starker Wind"),
    ],
)
def test_localized_weather_preserves_codes_and_protected_alerts(language, summary, alert):
    snapshot = parse_weather(
        (FIXTURES / "severe-wet-wind.json").read_bytes(),
        timezone="Europe/Lisbon",
        language=language,
    )
    assert snapshot.current.summary == summary
    assert snapshot.current.code == 99
    settings = Settings(
        _env_file=None,
        language=language,
        weather_rain_disruption_mm=20,
        weather_wind_disruption_kph=60,
    )
    items = _weather_items(snapshot, settings, datetime(2026, 10, 4, tzinfo=UTC))
    assert items[1].title == alert
    assert items[1].is_protected
    assert items[1].severity == "disruption"


@pytest.mark.parametrize(
    "language,expected", [("pt", "4,5 mm"), ("en", "4.5 mm"), ("de", "4,5 mm")]
)
def test_weather_alert_amount_uses_language_decimal_separator(language, expected):
    snapshot = parse_weather(
        (FIXTURES / "severe-wet-wind.json").read_bytes(),
        timezone="Europe/Lisbon",
        language=language,
    )
    snapshot.today.rain_mm = 4.5
    settings = Settings(
        _env_file=None,
        language=language,
        weather_rain_disruption_mm=4,
        weather_wind_disruption_kph=None,
    )
    items = _weather_items(snapshot, settings, datetime(2026, 10, 4, tzinfo=UTC))
    assert expected in [fact.value for fact in items[1].facts]


def test_national_news_is_selected_and_labelled_for_country():
    now = datetime(2026, 10, 4, tzinfo=UTC)
    item = NewsItem(
        id="news:1", title="Original headline", source="news", published_at=now, category="national"
    )
    feed = RSSFeed(id="news", label="Publisher", url="https://example.com/rss", category="national")
    assert select_news([item], now=now) == [item]
    display = _news_item(item, feed, language="de", country="DE")
    assert display.label == "Deutschland · Publisher"
    assert display.title == item.title


def test_photo_caption_localizes_only_the_default():
    assert _photo_caption(Path("IMG_1234.jpg"), "de") == "Foto des Tages"
    assert _photo_caption(Path("Family holiday.jpg"), "de") == "Family holiday"


def test_language_change_refreshes_weather_without_waiting_for_poll(tmp_path):
    from app.collectors.pipeline import DataPipeline
    from app.storage.sources import SourceCache

    now = datetime(2026, 10, 4, 12, tzinfo=UTC)
    settings = Settings(
        _env_file=None,
        config_file=None,
        language="pt",
        calendar_feeds=[],
        rss_feeds=[],
        weather_latitude=38.72,
        weather_longitude=-9.14,
        weather_location="Lisboa",
        database_url=f"sqlite:///{tmp_path / 'sources.db'}",
        cache_dir=str(tmp_path),
    )
    cache = SourceCache(settings.database_url)
    calls = []

    def fetch(url):
        calls.append(url)
        return (FIXTURES / "normal.json").read_bytes()

    try:
        first = DataPipeline(settings, cache, fetcher=fetch).collect(now)
        translated = DataPipeline(
            settings.model_copy(update={"language": "de"}), cache, fetcher=fetch
        ).collect(now)
        assert first.weather.current.summary == "Chuva moderada"
        assert translated.weather.current.summary == "Mäßiger Regen"
        assert translated.language == "de"
        assert len(calls) == 2
    finally:
        cache.close()


def test_ai_score_cache_is_separate_for_country_and_language(tmp_path):
    from app.collectors.pipeline import DataPipeline
    from app.storage.sources import SourceCache

    (tmp_path / "news_scores.json").write_text('{"old": [9, "topic"]}')
    settings = Settings(
        _env_file=None,
        config_file=None,
        cache_dir=str(tmp_path),
        calendar_feeds=[],
        rss_feeds=[],
        weather_latitude=None,
        weather_longitude=None,
        database_url=f"sqlite:///{tmp_path / 'sources.db'}",
    )
    cache = SourceCache(settings.database_url)
    try:
        original = DataPipeline(settings, cache)
        german = DataPipeline(
            settings.model_copy(update={"language": "de", "country": "DE"}), cache
        )
        english = DataPipeline(
            settings.model_copy(update={"language": "en", "country": "DE"}), cache
        )
        assert original._news_scores == {"old": (9, "topic")}
        assert german._news_scores == {}
        assert len({original._scores_path, german._scores_path, english._scores_path}) == 3
    finally:
        cache.close()


def test_long_german_weather_descriptions_keep_weather_and_alerts():
    snapshot = parse_weather(
        (FIXTURES / "severe-wet-wind.json").read_bytes(), timezone="Europe/Lisbon", language="de"
    )
    for period in (snapshot.current, snapshot.today, snapshot.tomorrow):
        period.summary = "Starker gefrierender Nieselregen"
    settings = Settings(
        _env_file=None, language="de", weather_rain_disruption_mm=20, weather_wind_disruption_kph=60
    )
    items = _weather_items(snapshot, settings, datetime(2026, 10, 4, tzinfo=UTC))
    assert items[0].kind == "weather"
    assert len(items[0].summary) <= 280
    assert items[1].is_protected
    assert items[1].facts
