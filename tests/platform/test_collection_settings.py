import pytest
from pydantic import ValidationError

from app.config import Settings


def test_collection_settings_have_safe_demo_defaults():
    settings = Settings(_env_file=None)

    assert settings.demo_mode is True
    assert settings.calendar_feeds == []
    assert settings.rss_feeds == []
    assert settings.calendar_days == 14
    assert settings.calendar_poll_minutes == 30
    assert settings.rss_poll_minutes == 60
    assert settings.weather_poll_minutes == 30
    assert settings.weather_latitude is None
    assert settings.weather_longitude is None


def test_feed_urls_are_secret_and_only_public_http_urls_are_accepted():
    settings = Settings(
        _env_file=None,
        calendar_feeds=[
            {"id": "family-cal", "url": "https://calendar.example.test/private?token=abc"}
        ],
    )

    assert settings.calendar_feeds[0].url.get_secret_value().endswith("token=abc")
    assert "token=abc" not in repr(settings.calendar_feeds[0])
    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            rss_feeds=[{"id": "bad", "url": "https://127.0.0.1/feed?token=private"}],
        )
    assert "token=private" not in str(error.value)


@pytest.mark.parametrize(
    "overrides",
    [
        {"calendar_feeds": [{"id": "bad/id", "url": "https://example.test/feed.ics"}]},
        {"rss_feeds": [{"id": "world", "url": "https://example.test/rss", "category": "local"}]},
        {"weather_latitude": 38.7},
        {"weather_longitude": -9.1},
        {"weather_latitude": 91, "weather_longitude": -9.1, "weather_location": "Lisbon"},
        {"calendar_days": 32},
        {"calendar_poll_minutes": 0},
        {"weather_rain_disruption_mm": -1},
    ],
)
def test_collection_settings_reject_invalid_sources_and_bounds(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


def test_feed_and_weather_source_count_is_limited_to_eight():
    feeds = [
        {"id": f"cal-{index}", "url": f"https://example.test/{index}.ics"} for index in range(8)
    ]
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            calendar_feeds=feeds,
            weather_latitude=38.7,
            weather_longitude=-9.1,
            weather_location="Lisbon",
        )


def test_world_feed_is_untrusted_until_curated_or_keywords_are_configured():
    feed = Settings(
        _env_file=None,
        rss_feeds=[{"id": "world", "category": "world", "url": "https://example.test/rss"}],
    ).rss_feeds[0]

    assert feed.curated is False
    assert feed.keywords == []
