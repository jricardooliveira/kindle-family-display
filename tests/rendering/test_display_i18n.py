from datetime import UTC, datetime
from io import BytesIO

import pytest
from PIL import Image

from app.rendering import demo_context, render
from app.rendering.canvas import Canvas
from tests.rendering.test_renderer import decision_for


@pytest.mark.parametrize(
    ("language", "today", "tomorrow", "weekday"),
    [
        ("pt", "Hoje", "Amanhã", "Dom 4 Out"),
        ("en", "Today", "Tomorrow", "Sun 4 Oct"),
        ("de", "Heute", "Morgen", "So 4. Okt"),
    ],
)
@pytest.mark.parametrize(("width", "height"), [(320, 240), (800, 600), (1236, 1648)])
def test_localized_demo_all_screens(monkeypatch, language, today, tomorrow, weekday, width, height):
    texts = []
    original = Canvas.line

    def capture(self, x, y, text, style, **kwargs):
        texts.append(text)
        return original(self, x, y, text, style, **kwargs)

    monkeypatch.setattr(Canvas, "line", capture)
    context = demo_context(datetime(2026, 10, 4, 9, tzinfo=UTC), "Europe/Berlin", language)
    assert context.language == language
    for screen in ("news-weather", "news", "family", "calendar", "nearby", "photo"):
        image = Image.open(
            BytesIO(render(screen, context, decision_for(context.items), width, height))
        )
        assert image.mode == "L"
        assert image.size == (width, height)
    assert today in texts
    assert any(tomorrow in text for text in texts)
    assert weekday in texts
    if language != "pt":
        assert "Passeio em família" not in " ".join(texts)
        assert "Hoje" not in texts


def test_weather_icons_do_not_depend_on_translated_summary():
    from app.rendering.renderer import _weather_icon

    assert _weather_icon("Unfamiliar description", 95) == "storm"
    assert _weather_icon("Unfamiliar description", 61) == "rain"
    assert _weather_icon("Unfamiliar description", 0) == "sun"


def test_catalog_has_equal_keys_and_placeholders():
    from string import Formatter

    from app.i18n.display import CATALOG

    assert set(CATALOG) == {"pt", "en", "de"}
    assert CATALOG["pt"].keys() == CATALOG["en"].keys() == CATALOG["de"].keys()
    for key in CATALOG["pt"]:
        fields = [
            {name for _, name, _, _ in Formatter().parse(CATALOG[language][key]) if name}
            for language in CATALOG
        ]
        assert fields[0] == fields[1] == fields[2], key


@pytest.mark.parametrize("screen", ["news-weather", "calendar", "family"])
def test_german_unavailable_messages_stay_in_their_columns(monkeypatch, screen):
    original = Canvas.line
    context = demo_context(datetime(2026, 10, 4, 9, tzinfo=UTC), "Europe/Berlin", "de")
    context = context.model_copy(
        update={"items": [], "weather": None, "unavailable_kinds": ["weather", "rss", "calendar"]}
    )

    def capture(self, x, y, text, style, **kwargs):
        if "verfügbar" in text or "Nachrichten" == text:
            right = 760 if x > 400 or screen == "family" else 396
            assert x + self.measure(text, style) <= right
        return original(self, x, y, text, style, **kwargs)

    monkeypatch.setattr(Canvas, "line", capture)
    render(screen, context, decision_for([]), 800, 600)


@pytest.mark.parametrize(
    ("language", "countdown", "all_day", "ongoing"),
    [
        ("pt", "Faltam 3 dias", "Todo o dia", "Em curso"),
        ("en", "In 3 days", "All day", "Ongoing"),
        ("de", "In 3 Tagen", "Ganztägig", "Läuft"),
    ],
)
def test_countdowns_calendar_and_external_content(language, countdown, all_day, ongoing):
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    from app.rendering.renderer import _calendar_days, _item_label

    context = demo_context(datetime(2026, 10, 4, 9, tzinfo=UTC), "Europe/Berlin", language)
    now = context.generated_at.astimezone(ZoneInfo(context.timezone))
    trip = next(item for item in context.items if item.kind == "countdown")
    assert _item_label(trip, now, language) == countdown
    assert (
        _item_label(trip.model_copy(update={"label": "Original source label"}), now, language)
        == "Original source label"
    )
    event = next(item for item in context.items if item.kind == "calendar")
    event = event.model_copy(update={"all_day": True})
    rows = _calendar_days([event], ZoneInfo(context.timezone), now.date(), set(), language)
    assert rows[now.date()][0][1] == all_day
    event = event.model_copy(
        update={
            "all_day": False,
            "occurred_at": now - timedelta(days=1),
            "ends_at": now + timedelta(days=1),
        }
    )
    rows = _calendar_days([event], ZoneInfo(context.timezone), now.date(), set(), language)
    assert rows[now.date()][0][1] == ongoing


@pytest.mark.parametrize(("language", "decimal"), [("pt", ","), ("en", "."), ("de", ",")])
@pytest.mark.parametrize(
    ("field", "amount", "unit"), [("rain_mm", 4.5, "mm"), ("wind_kph", 45.5, "km/h")]
)
def test_weather_decimal_formatting(monkeypatch, language, decimal, field, amount, unit):
    texts = []
    original = Canvas.line

    def capture(self, x, y, text, style, **kwargs):
        texts.append(text)
        return original(self, x, y, text, style, **kwargs)

    monkeypatch.setattr(Canvas, "line", capture)
    context = demo_context(datetime(2026, 10, 4, 9, tzinfo=UTC), "Europe/Berlin", language)
    today = context.weather.today.model_copy(
        update={"rain_mm": None, "rain_probability_pct": None, field: amount}
    )
    context = context.model_copy(
        update={"weather": context.weather.model_copy(update={"today": today})}
    )
    render("news-weather", context, decision_for(context.items), 800, 600)
    expected = f"{amount:g}".replace(".", decimal)
    assert f"{expected} {unit}" in " ".join(texts)


def test_german_agenda_dates_use_day_ordinals(monkeypatch):
    from datetime import timedelta

    texts = []
    original = Canvas.line

    def capture(self, x, y, text, style, **kwargs):
        texts.append(text)
        return original(self, x, y, text, style, **kwargs)

    monkeypatch.setattr(Canvas, "line", capture)
    context = demo_context(datetime(2026, 10, 4, 9, tzinfo=UTC), "Europe/Berlin", "de")
    render("calendar", context, decision_for(context.items), 800, 600)
    assert "Morgen · Mo 5." in texts
    future = next(item for item in context.items if item.kind == "calendar").model_copy(
        update={"occurred_at": context.generated_at + timedelta(days=4)}
    )
    context = context.model_copy(update={"items": [future]})
    render("calendar", context, decision_for(context.items), 800, 600)
    assert "Do 8." in texts
