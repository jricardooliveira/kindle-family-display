from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.contracts.models import (
    DisplayContext,
    DisplayDecision,
    DisplayItem,
    Event,
    NewsItem,
    Status,
    WeatherSnapshot,
)

LISBON = ZoneInfo("Europe/Lisbon")
NOW = datetime(2026, 10, 4, 7, 30, tzinfo=LISBON)


def item(**overrides):
    fields = {
        "id": "cal-1",
        "kind": "calendar",
        "title": "Museum visit",
        "priority": 65,
        "occurred_at": NOW,
    }
    fields.update(overrides)
    return DisplayItem(**fields)


def test_context_requires_aware_timestamps_and_unique_item_ids():
    with pytest.raises(ValidationError):
        item(occurred_at=datetime(2026, 10, 4, 7, 30))  # noqa: DTZ001

    with pytest.raises(ValidationError):
        DisplayContext(
            generated_at=NOW,
            timezone="Europe/Lisbon",
            mode="family",
            items=[item(), item()],
            protected_alert_ids=[],
        )


def test_context_rejects_unknown_or_unprotected_alert_ids():
    with pytest.raises(ValidationError):
        DisplayContext(
            generated_at=NOW,
            timezone="Europe/Lisbon",
            mode="family",
            items=[item()],
            protected_alert_ids=["missing"],
        )

    with pytest.raises(ValidationError):
        DisplayContext(
            generated_at=NOW,
            timezone="Europe/Lisbon",
            mode="family",
            items=[item(id="ordinary")],
            protected_alert_ids=["ordinary"],
        )


def test_weather_event_news_and_status_models_accept_normalized_payloads():
    weather = WeatherSnapshot.model_validate(
        {
            "observed_at": NOW,
            "timezone": "Europe/Lisbon",
            "source": "demo",
            "current": {"summary": "Cloudy", "temperature_c": 17},
            "today": {"rain_probability_pct": 20},
            "tomorrow": {"wind_kph": 12},
        }
    )
    event = Event.model_validate(
        {
            "id": "cal-1",
            "title": "Museum visit",
            "starts_at": NOW,
            "source": "calendar-fixture",
        }
    )
    news = NewsItem.model_validate(
        {
            "id": "rss-1",
            "title": "Local story",
            "published_at": NOW,
            "source": "news-fixture",
            "category": "portugal",
        }
    )
    status = Status.model_validate(
        {
            "ok": True,
            "timezone": "Europe/Lisbon",
            "screens": ["news-weather", "family", "calendar"],
            "generated_at": NOW,
        }
    )

    assert weather.source == "demo"
    assert event.starts_at == NOW
    assert news.category == "portugal"
    assert status.ok


def test_decision_has_fixed_layout_and_separate_protected_ids():
    decision = DisplayDecision.model_validate(
        {
            "layout": "weather_alert",
            "item_ids": ["cal-1"],
            "protected_alert_ids": ["alert-1"],
            "reason": "Critical alert with next event",
            "generated_at": NOW,
            "provider": "rules",
        }
    )
    assert decision.protected_alert_ids == ["alert-1"]

    with pytest.raises(ValidationError):
        DisplayDecision(
            layout="custom-html",
            item_ids=[],
            protected_alert_ids=[],
            reason="invalid layout",
            generated_at=NOW,
            provider="ai",
        )
