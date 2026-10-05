from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from PIL import Image

from app.contracts import DisplayContext, DisplayDecision, DisplayItem, DisplayLayout
from app.contracts.models import DisplayFact, WeatherPeriod, WeatherSnapshot
from app.rendering import demo_context, render
from app.rendering.canvas import Canvas


def item(
    item_id: str,
    *,
    kind: str = "news",
    title: str | None = None,
    summary: str | None = None,
    occurred_at: datetime | None = None,
    source: str | None = "synthetic-fixture",
    is_protected: bool = False,
    severity: str = "ordinary",
    ends_at: datetime | None = None,
    all_day: bool = False,
    person: str | None = None,
    **extra: Any,
) -> DisplayItem:
    return DisplayItem(
        id=item_id,
        kind=kind,
        title=title or item_id,
        summary=summary,
        priority=100 if is_protected else 50,
        occurred_at=occurred_at or datetime(2026, 10, 4, 9, 0, tzinfo=UTC),
        person=person,
        source=source,
        is_protected=is_protected,
        severity=severity,
        ends_at=ends_at,
        all_day=all_day,
        **extra,
    )


def context_for(
    screen: str,
    items: list[DisplayItem],
    *,
    demo: bool = True,
    source_warnings: list[str] | None = None,
    unavailable_kinds: list[str] | None = None,
    **extra: Any,
) -> DisplayContext:
    return DisplayContext(
        generated_at=datetime(2026, 10, 4, 9, 0, tzinfo=UTC),
        timezone="Europe/Lisbon",
        mode="family",
        items=items,
        protected_alert_ids=[entry.id for entry in items if entry.is_protected],
        demo=demo,
        source_warnings=source_warnings or [],
        unavailable_kinds=unavailable_kinds or [],
        **extra,
    )


def decision_for(items: list[DisplayItem]) -> DisplayDecision:
    return DisplayDecision(
        layout=DisplayLayout.HERO,
        item_ids=[entry.id for entry in items if not entry.is_protected][:3],
        protected_alert_ids=[entry.id for entry in items if entry.is_protected],
        reason="synthetic fixture",
        generated_at=datetime(2026, 10, 4, 9, 0, tzinfo=UTC),
        provider="rules",
    )


def png(data: bytes) -> Image.Image:
    image = Image.open(BytesIO(data))
    image.load()
    return image


class Drawn:
    """Text lines the renderer drew, with their design-pixel position and width."""

    def __init__(self) -> None:
        self.entries: list[tuple[str, float, float, float]] = []

    @property
    def text(self) -> list[str]:
        return [entry[0] for entry in self.entries]

    @property
    def joined(self) -> str:
        return " ".join(self.text)

    def find(self, value: str) -> tuple[str, float, float, float]:
        return next(entry for entry in self.entries if entry[0] == value)


@pytest.fixture
def drawn(monkeypatch: Any) -> Drawn:
    record = Drawn()
    actual = Canvas.line

    def line(self: Canvas, x: float, top: float, text: str, style: Any, **kwargs: Any) -> float:
        width = actual(self, x, top, text, style, **kwargs)
        left = x - width if kwargs.get("anchor") == "r" else x
        record.entries.append((text, left, top, width))
        return width

    monkeypatch.setattr(Canvas, "line", line)
    return record


@pytest.mark.parametrize("screen", ["news-weather", "family", "calendar"])
def test_each_screen_renders_as_grayscale_png_with_date_header(screen: str) -> None:
    now = datetime(2026, 10, 4, 10, 30, tzinfo=UTC)
    context = demo_context(now, "Europe/Lisbon")

    image = png(render(screen, context, decision_for(context.items), 800, 600))

    assert image.format == "PNG"
    assert image.mode == "L"
    assert image.size == (800, 600)
    assert image.getextrema()[0] < 255


@pytest.mark.parametrize("size", [(320, 240), (800, 600), (1600, 1600)])
def test_renderer_supports_minimum_placeholder_and_large_dimensions(size: tuple[int, int]) -> None:
    context = demo_context(datetime(2026, 10, 4, 10, 30, tzinfo=UTC), "Europe/Lisbon")

    image = png(render("family", context, decision_for(context.items), *size))

    assert image.size == size
    assert image.mode == "L"


@pytest.mark.parametrize(
    ("rotation", "expected_size"),
    [(0, (800, 600)), (90, (600, 800)), (180, (800, 600)), (270, (600, 800))],
)
def test_renderer_applies_supported_rotation(rotation: int, expected_size: tuple[int, int]) -> None:
    context = demo_context(datetime(2026, 10, 4, 10, 30, tzinfo=UTC), "Europe/Lisbon")

    image = png(render("news-weather", context, decision_for(context.items), 800, 600, rotation))

    assert image.size == expected_size


def test_renderer_rejects_unsupported_rotation() -> None:
    context = demo_context(datetime(2026, 10, 4, 10, 30, tzinfo=UTC), "Europe/Lisbon")

    with pytest.raises(ValueError, match="rotation"):
        render("family", context, decision_for(context.items), 800, 600, 45)


def weather_snapshot() -> WeatherSnapshot:
    observed = datetime(2026, 10, 4, 9, 0, tzinfo=UTC)
    return WeatherSnapshot(
        observed_at=observed,
        timezone="Europe/Lisbon",
        source="synthetic-fixture",
        current=WeatherPeriod(summary="Nublado", temperature_c=17.4),
        today=WeatherPeriod(summary="Chuva fraca", temperature_min_c=14, temperature_max_c=19),
        tomorrow=WeatherPeriod(summary="Céu limpo", temperature_min_c=12, temperature_max_c=17),
        sunrise=observed.replace(hour=6, minute=21),
        sunset=observed.replace(hour=17, minute=58),
    )


def test_alert_takes_over_the_top_screen_as_an_inverted_page(drawn: Drawn) -> None:
    entries = [
        item("story", title="Notícia do dia"),
        item(
            "alert",
            kind="alert",
            title="Chuva forte",
            summary="Recolha a roupa.",
            is_protected=True,
            severity="critical",
            label="Aviso meteorológico",
            facts=[DisplayFact(label="Das", value="17:00"), DisplayFact(label="Às", value="23:00")],
        ),
        item("alert-two", kind="alert", title="Vento", is_protected=True, severity="disruption"),
    ]
    context = context_for("news-weather", entries)

    image = png(render("news-weather", context, decision_for(entries), 800, 600))

    assert image.getpixel((3, 3)) == 0
    assert "Chuva forte" in drawn.joined
    assert "Aviso meteorológico · +1 avisos" in drawn.text
    assert {"Das", "17:00", "Às", "23:00", "Recolha a roupa."} <= set(drawn.text)
    assert "Notícia do dia" not in drawn.text


@pytest.mark.parametrize("screen", ["family", "calendar"])
def test_other_screens_keep_their_content_under_an_alert_banner(drawn: Drawn, screen: str) -> None:
    now = datetime(2026, 10, 4, 9, 0, tzinfo=UTC)
    entries = [
        item("event", kind="calendar", title="Dentista", occurred_at=now + timedelta(hours=2)),
        item("alert", kind="alert", title="Chuva forte", is_protected=True, severity="critical"),
    ]
    context = context_for(screen, entries)

    image = png(render(screen, context, decision_for(entries), 800, 600))

    assert image.getpixel((3, 3)) == 255
    assert "Chuva forte" in drawn.text
    assert "Dentista" in drawn.text


def test_family_screen_keeps_family_content_from_other_screen_items(drawn: Drawn) -> None:
    entries = [
        item("weather", kind="weather", title="Tempo em Lisboa"),
        item("news", kind="news", title="Notícia do dia"),
        item("family", kind="countdown", title="Passeio em família"),
    ]
    context = context_for("family", entries)
    decision = DisplayDecision(
        layout=DisplayLayout.THREE_ITEMS,
        item_ids=["weather", "news", "family"],
        protected_alert_ids=[],
        reason="synthetic fixture",
        generated_at=context.generated_at,
        provider="rules",
    )

    render("family", context, decision, 800, 600)

    assert "Passeio em família" in drawn.joined
    assert "Tempo em Lisboa" not in drawn.joined
    assert "Notícia do dia" not in drawn.text


def test_family_hero_secondary_and_weather_strip(drawn: Drawn) -> None:
    now = datetime(2026, 10, 4, 9, 0, tzinfo=UTC)
    entries = [
        item(
            "trip",
            kind="calendar",
            title="Visita de estudo",
            summary="Lanche e impermeável.",
            occurred_at=now + timedelta(hours=1),
            person="Pedro",
        ),
        item("dentist", kind="calendar", title="Dentista", occurred_at=now + timedelta(days=1)),
        item(
            "pickup",
            kind="calendar",
            title="Levantar encomenda",
            occurred_at=now + timedelta(days=3),
        ),
    ]
    context = context_for("family", entries, weather=weather_snapshot())

    render("family", context, decision_for(entries), 800, 600)

    assert drawn.text[:2] == ["10:00", "Dom 4 Out"]
    assert {"Pedro · 11:00", "Amanhã 10:00", "Qua 7 Out 10:00"} <= set(drawn.text)
    assert {"Visita de", "estudo", "Lanche e impermeável.", "Dentista"} <= set(drawn.text)
    assert "Chuva fraca · 14° / 19°" in drawn.text
    hero, secondary = drawn.find("Visita de"), drawn.find("Dentista")
    assert hero[1] + hero[3] < secondary[1]


def test_family_defaults_to_weather_when_there_are_no_family_items(drawn: Drawn) -> None:
    context = context_for("family", [], weather=weather_snapshot())

    render("family", context, decision_for([]), 800, 600)

    assert {"17°", "Nublado", "14° / 19°", "12° / 17°", "07:21 – 18:58"} <= set(drawn.text)
    assert "Sem compromissos próximos" in drawn.joined


def test_family_shows_a_quote_when_nothing_more_urgent_is_selected(drawn: Drawn) -> None:
    verse = item("verse", kind="verse", title="Texto de exemplo.", summary="Referência 1, 2")
    context = context_for("family", [verse])

    render("family", context, decision_for([verse]), 800, 600)

    assert {"“", "Texto de exemplo.", "Referência 1, 2"} <= set(drawn.text)


def test_family_shows_nearby_events_with_distance(drawn: Drawn) -> None:
    events = [
        item(f"near-{km}", kind="local_event", title=f"Evento {km}", distance_km=km)
        for km in (8, 17, 23)
    ]
    context = context_for("family", events)

    render("family", context, decision_for(events), 800, 600)

    assert {"8", "17", "23", "km", "Evento 8", "Evento 23"} <= set(drawn.text)
    assert drawn.find("8")[1] < drawn.find("17")[1] < drawn.find("23")[1]


def test_news_weather_shows_structured_weather_and_story_with_source(drawn: Drawn) -> None:
    story = item(
        "story",
        title="Notícia de exemplo",
        summary="Resumo curto.",
        source="Jornal de Exemplo",
        label="Portugal · Jornal de Exemplo",
        url="https://example.com/story",
    )
    context = context_for("news-weather", [story], demo=False, weather=weather_snapshot())

    with_qr = render("news-weather", context, decision_for([story]), 800, 600)

    assert {"17°", "Nublado", "Hoje", "14° / 19°", "Amanhã", "12° / 17°"} <= set(drawn.text)
    assert {"Portugal · Jornal de Exemplo", "Resumo curto.", "07:21 – 18:58"} <= set(drawn.text)
    without_url = story.model_copy(update={"url": None})
    without_qr = render(
        "news-weather",
        context.model_copy(update={"items": [without_url]}),
        decision_for([without_url]),
        800,
        600,
    )
    assert with_qr != without_qr


def test_renderer_handles_long_words_and_bounds_long_summaries() -> None:
    long_text = "supercalifragilisticexpialidocious" * 8
    entries = [item("long-story", title=long_text[:160], summary=long_text)]
    context = context_for("news-weather", entries)

    image = png(render("news-weather", context, decision_for(entries), 320, 240))

    assert image.size == (320, 240)
    assert image.mode == "L"


def test_protected_alerts_take_precedence_over_ordinary_items() -> None:
    entries = [
        item("ordinary-one", title="Notícia familiar"),
        item(
            "rain-alert",
            kind="alert",
            title="Aviso de chuva intensa",
            is_protected=True,
            severity="critical",
        ),
    ]
    context = context_for("news-weather", entries)
    decision = decision_for(entries)

    image = png(render("news-weather", context, decision, 800, 600))

    assert image.getextrema()[0] < 255
    assert decision.protected_alert_ids == ["rain-alert"]
    without_alert = context_for("news-weather", [entries[0]])
    ordinary_decision = decision_for([entries[0]])
    ordinary_image = png(render("news-weather", without_alert, ordinary_decision, 800, 600))
    assert (
        image.crop((0, 150, 800, 400)).tobytes()
        != ordinary_image.crop((0, 150, 800, 400)).tobytes()
    )


def test_calendar_uses_all_context_events_in_time_order() -> None:
    lisbon = "Europe/Lisbon"
    now = datetime(2026, 10, 4, 9, 0, tzinfo=UTC)
    entries = [
        item("late", kind="calendar", title="Jantar", occurred_at=now + timedelta(hours=9)),
        item("early", kind="calendar", title="Levar a Inês", occurred_at=now + timedelta(hours=1)),
        item(
            "tomorrow",
            kind="calendar",
            title="Passeio",
            occurred_at=now + timedelta(days=1, hours=3),
        ),
        item("irrelevant", kind="news", title="Notícia", occurred_at=now),
        item("middle", kind="calendar", title="Reunião", occurred_at=now + timedelta(hours=4)),
    ]
    context = DisplayContext(
        generated_at=now,
        timezone=lisbon,
        mode="family",
        items=entries,
        protected_alert_ids=[],
    )
    # The AI/rules selection is deliberately capped; the calendar list comes from context.
    decision = DisplayDecision(
        layout=DisplayLayout.HERO,
        item_ids=["late", "early", "tomorrow"],
        protected_alert_ids=[],
        reason="synthetic fixture",
        generated_at=now,
        provider="rules",
    )

    image = png(render("calendar", context, decision, 800, 600))

    assert image.size == (800, 600)
    assert image.mode == "L"

    reversed_context = context.model_copy(update={"items": list(reversed(entries))})
    same_events_image = png(render("calendar", reversed_context, decision, 800, 600))
    assert image.tobytes() == same_events_image.tobytes()
    without_middle = context.model_copy(
        update={"items": [entry for entry in entries if entry.id != "middle"]}
    )
    fewer_events_image = png(render("calendar", without_middle, decision, 800, 600))
    assert image.tobytes() != fewer_events_image.tobytes()


def test_demo_context_is_deterministic_and_localizes_time() -> None:
    now = datetime(2026, 10, 4, 10, 30, tzinfo=UTC)

    first = demo_context(now, "Europe/Lisbon")
    second = demo_context(now, "Europe/Lisbon")

    assert first == second
    assert first.generated_at == now
    assert first.items
    assert all("synthetic" in item.source for item in first.items)
    assert any(
        entry.kind == "calendar"
        and entry.occurred_at.astimezone(ZoneInfo("Europe/Lisbon")).date()
        == (now.astimezone(ZoneInfo("Europe/Lisbon")).date() + timedelta(days=1))
        for entry in first.items
    )
    assert first.timezone == "Europe/Lisbon"


def test_rendered_header_uses_the_configured_timezone() -> None:
    now = datetime(2026, 10, 4, 23, 30, tzinfo=UTC)
    lisbon = demo_context(now, "Europe/Lisbon")
    utc = lisbon.model_copy(update={"timezone": "UTC"})
    decision = decision_for(lisbon.items)

    lisbon_png = render("family", lisbon, decision, 800, 600)
    utc_png = render("family", utc, decision, 800, 600)

    assert lisbon_png != utc_png


def test_small_header_keeps_time_and_date_in_separate_widths(drawn: Drawn) -> None:
    context = demo_context(datetime(2026, 10, 4, 10, 30, tzinfo=UTC), "Europe/Lisbon")

    render("family", context, decision_for(context.items), 320, 240)

    clock, date = drawn.entries[0], drawn.entries[1]
    assert clock[1] + clock[3] < date[1]


def test_calendar_time_column_has_gap_before_event_title(drawn: Drawn) -> None:
    now = datetime(2026, 10, 4, 9, 0, tzinfo=UTC)
    event = item("event", kind="calendar", title="Reunião", occurred_at=now + timedelta(hours=1))
    context = context_for("calendar", [event])

    render("calendar", context, decision_for([event]), 800, 600)

    title, clock = drawn.find("Reunião"), drawn.find("11:00")
    assert title[1] > clock[1] + clock[3] + 5


def test_calendar_overflow_is_counted_from_all_context_events(drawn: Drawn) -> None:
    now = datetime(2026, 10, 4, 6, 0, tzinfo=UTC)
    entries = [
        item(
            f"event-{index}",
            kind="calendar",
            title=f"Compromisso {index}",
            occurred_at=now + timedelta(minutes=30 * index),
        )
        for index in range(12)
    ]
    context = context_for("calendar", entries)

    render("calendar", context, decision_for(entries), 800, 600)

    counter = next(text for text in drawn.text if text.startswith("+"))
    shown = sum(text.startswith("Compromisso") for text in drawn.text)
    assert counter == f"+{12 - shown} eventos"
    assert 0 < shown < 12


def test_calendar_marks_people_with_badges_and_a_legend(drawn: Drawn) -> None:
    now = datetime(2026, 10, 4, 9, 0, tzinfo=UTC)
    event = item("event", kind="calendar", title="Natação", occurred_at=now, person="Pedro")
    context = context_for("calendar", [event], people=["Pedro", "João"])
    without_person = context_for("calendar", [event.model_copy(update={"person": None})])

    image = render("calendar", context, decision_for([event]), 800, 600)

    assert "Pedro" in drawn.text
    assert image != render("calendar", without_person, decision_for([event]), 800, 600)


def test_live_screens_hide_demo_label_and_show_stale_source_warning(drawn: Drawn) -> None:
    context = context_for("news-weather", [], demo=False, source_warnings=["RTP", "Tempo"])

    render("news-weather", context, decision_for([]), 800, 600)

    assert not any("DEMO" in text for text in drawn.text)
    assert any("Dados desatualizados · RTP, Tempo" in text for text in drawn.text)


def test_demo_label_and_stale_warning_remain_at_minimum_screen_size(drawn: Drawn) -> None:
    context = context_for("news-weather", [], source_warnings=["weather source is stale"])

    render("news-weather", context, decision_for([]), 320, 240)

    assert any("DEMO · Dados desatualizados" in text for text in drawn.text)


@pytest.mark.parametrize(
    ("screen", "unavailable", "expected"),
    [
        ("news-weather", ["weather", "rss"], ["Tempo indisponível", "Notícias indisponíveis"]),
        ("family", ["calendar"], ["Calendário indisponível"]),
        ("calendar", ["calendar"], ["Calendário indisponível"]),
    ],
)
def test_live_unavailable_sources_get_generic_state_not_fake_empty_claims(
    drawn: Drawn, screen: str, unavailable: list[str], expected: list[str]
) -> None:
    context = context_for(screen, [], demo=False, unavailable_kinds=unavailable)

    render(screen, context, decision_for([]), 800, 600)

    for message in expected:
        assert message in drawn.text
    assert "Sem eventos" not in drawn.text
    assert "Sem compromissos próximos" not in drawn.text


def test_calendar_displays_all_day_and_overlapping_multiday_events(drawn: Drawn) -> None:
    zone = ZoneInfo("Europe/Lisbon")
    all_day = item(
        "all-day",
        kind="calendar",
        title="Festa",
        occurred_at=datetime(2026, 10, 3, 0, 0, tzinfo=zone),
        ends_at=datetime(2026, 10, 5, 0, 0, tzinfo=zone),
        all_day=True,
    )
    multiday = item(
        "multiday",
        kind="calendar",
        title="Obras",
        occurred_at=datetime(2026, 10, 3, 18, 0, tzinfo=zone),
        ends_at=datetime(2026, 10, 5, 12, 0, tzinfo=zone),
    )
    context = context_for("calendar", [all_day, multiday], demo=False)

    render("calendar", context, decision_for([all_day, multiday]), 800, 600)

    assert drawn.text.count("Festa") == 1
    assert drawn.text.count("Obras") == 2
    assert drawn.text.count("Todo o dia") == 1
    assert drawn.text.count("Em curso") == 2


def test_calendar_honors_exclusive_end_date_and_shows_ongoing_previous_day(drawn: Drawn) -> None:
    zone = ZoneInfo("Europe/Lisbon")
    event = item(
        "ends-at-midnight",
        kind="calendar",
        title="Feira",
        occurred_at=datetime(2026, 10, 3, 16, 0, tzinfo=zone),
        ends_at=datetime(2026, 10, 5, 0, 0, tzinfo=zone),
    )
    context = context_for("calendar", [event], demo=False)

    render("calendar", context, decision_for([event]), 800, 600)

    assert drawn.text.count("Feira") == 1
    assert drawn.text.count("Em curso") == 1
    assert "Sem eventos" in drawn.text


def test_calendar_fills_a_free_tomorrow_with_the_next_events(drawn: Drawn) -> None:
    now = datetime(2026, 10, 4, 9, 0, tzinfo=UTC)
    later = item("later", kind="calendar", title="Natação", occurred_at=now + timedelta(days=4))
    context = context_for("calendar", [later])

    render("calendar", context, decision_for([later]), 800, 600)

    assert {"A seguir", "Qui 8", "10:00 · Natação"} <= set(drawn.text)
    assert drawn.text.count("Sem eventos") == 1


def test_family_pairs_weather_with_the_curiosity_when_no_events_are_due(drawn: Drawn) -> None:
    fact = item(
        "fact", kind="fact", title="Os polvos têm três corações.", label="Curiosidade · Natureza"
    )
    context = context_for("family", [fact], weather=weather_snapshot())

    render("family", context, decision_for([fact]), 800, 600)

    assert {"17°", "Curiosidade · Natureza"} <= set(drawn.text)
    assert "Os polvos têm três corações." in drawn.joined
    assert "“" not in drawn.text


def test_family_evening_strip_shows_tomorrows_forecast(drawn: Drawn) -> None:
    now = datetime(2026, 10, 4, 21, 0, tzinfo=UTC)
    event = item("early", kind="calendar", title="Natação", occurred_at=now + timedelta(hours=10))
    context = context_for("family", [event], weather=weather_snapshot(), night=True).model_copy(
        update={"generated_at": now}
    )

    render("family", context, decision_for([event]), 800, 600)

    assert "Amanhã 08:00" in drawn.text
    assert "Amanhã · Céu limpo · 12° / 17°" in drawn.text


def test_family_photo_fills_the_page_in_four_grey_levels(tmp_path: Any, drawn: Drawn) -> None:
    path = tmp_path / "Praia_da_Nazare.png"
    Image.linear_gradient("L").resize((640, 480)).save(path)
    photo = item("photo", kind="photo", title="Praia da Nazare", image_path=str(path))
    fact = item("fact", kind="fact", title="Um facto.")
    context = context_for("family", [photo, fact], weather=weather_snapshot())
    decision = decision_for([photo, fact])

    image = png(render("family", context, decision, 800, 600))

    assert set(image.crop((400, 100, 800, 500)).getdata()) <= {0, 85, 170, 255}
    assert drawn.text == ["10:00", "Dom 4 Out · Praia da Nazare"]

    drawn.entries.clear()
    missing = photo.model_copy(update={"image_path": str(tmp_path / "gone.png")})
    render("family", context.model_copy(update={"items": [missing, fact]}), decision, 800, 600)
    assert "Um facto." in drawn.joined


def test_news_digest_shows_a_lead_story_and_up_to_three_briefs(drawn: Drawn) -> None:
    stories = [
        item(
            f"story-{index}",
            title=f"Título {index}",
            summary=f"Resumo {index}.",
            label=f"Portugal · Fonte {index}",
            url="https://example.com/lead" if index == 0 else None,
        )
        for index in range(5)
    ]
    context = context_for("news-weather", stories, weather=weather_snapshot(), news_digest=True)

    render("news-weather", context, decision_for(stories), 800, 600)

    assert "Notícias · 4 histórias · DEMO" in drawn.text
    assert "Ler no telemóvel" in drawn.text
    assert [text for text in drawn.text if text.startswith("Título")] == [
        "Título 0",
        "Título 1",
        "Título 2",
        "Título 3",
    ]
    assert "17°" not in drawn.text
    lead, brief = drawn.find("Título 0"), drawn.find("Título 1")
    assert lead[1] + lead[3] < brief[1]


def test_news_digest_needs_several_stories_and_yields_to_alerts(drawn: Drawn) -> None:
    story = item("story", title="Única notícia")
    context = context_for("news-weather", [story], weather=weather_snapshot(), news_digest=True)

    render("news-weather", context, decision_for([story]), 800, 600)

    assert "17°" in drawn.text


def test_dedicated_pages_show_news_nearby_events_and_photo_on_demand(
    tmp_path: Any, drawn: Drawn
) -> None:
    now = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
    stories = [item(f"s{index}", title=f"Título {index}") for index in range(3)]
    near = item("near", kind="local_event", title="Concerto", occurred_at=now, distance_km=10)
    event = item("event", kind="calendar", title="Dentista", occurred_at=now + timedelta(hours=2))
    path = tmp_path / "foto.png"
    Image.linear_gradient("L").save(path)
    photo = item("photo", kind="photo", title="Foto do dia", image_path=str(path))
    context = context_for("news", [*stories, near, event, photo], weather=weather_snapshot())

    def shown(screen: str, entries: list[DisplayItem]) -> str:
        drawn.entries.clear()
        render(screen, context, decision_for(entries), 800, 600)
        return drawn.joined

    assert "Notícias · 3 histórias" in shown("news", stories)
    nearby = shown("nearby", [near])
    assert "Concerto" in nearby and "Dentista" not in nearby
    assert shown("photo", [photo]) == "10:00 Dom 4 Out"
