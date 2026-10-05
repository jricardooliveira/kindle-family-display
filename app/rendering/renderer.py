"""Fixed landscape layouts for the family display (design handoff M1–M6)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.contracts import (
    DisplayContext,
    DisplayDecision,
    DisplayFact,
    DisplayItem,
    WeatherPeriod,
    WeatherSnapshot,
)
from app.i18n import Language, format_number
from app.i18n.display import count_label, t
from app.rendering.canvas import BADGE_SHAPES, Canvas, Style

_SCREENS = ("news-weather", "news", "family", "calendar", "nearby", "photo")
_SCREEN_KINDS = {
    "news-weather": {"weather", "news", "alert"},
    "news": {"news", "alert"},
    "family": {"calendar", "countdown", "verse", "fact", "photo", "local_event", "alert"},
    "nearby": {"local_event", "alert"},
    "photo": {"photo", "alert"},
}
# Page geometry in design pixels (800×600); layouts stretch with the canvas.
_MX = 40
_MY = 26
_HEADER_BOTTOM = 94

_LABEL = Style(16, 600, leading=1.22, tracking=0.12, upper=True)
_NOTE = Style(16, 600, leading=1.22)
_CLOCK = Style(54, 700, display=True, leading=1.0)
_DATE = Style(24, 600, display=True, tracking=0.02)
_TITLE = Style(40, 700, display=True, leading=1.05, tracking=-0.02)
_HERO = Style(98, 700, display=True, leading=0.92)
_BODY = Style(24, leading=1.25)
_STRONG = Style(26, 600, leading=1.2)
# Agenda rows by importance: clock size, title size, title weight.
_AGENDA_TIERS = ((34, 38, 700), (28, 32, 600), (22, 26, 600))


def demo_context(now: datetime, timezone: str, language: Language = "pt") -> DisplayContext:
    """Return deterministic, synthetic content for the three display screens."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include a timezone")
    local_now = now.astimezone(ZoneInfo(timezone))
    source = "demo-synthetic"
    items = [
        DisplayItem(
            id="demo-weather",
            kind="weather",
            title=t("demo.weather.title", language),
            summary=t("demo.weather.summary", language),
            priority=55,
            occurred_at=local_now,
            source=source,
        ),
        DisplayItem(
            id="demo-news",
            kind="news",
            title=t("demo.news.title", language),
            summary=t("demo.news.summary", language),
            priority=30,
            occurred_at=local_now - timedelta(minutes=20),
            source=source,
            label=t("demo.news.label", language),
            url="https://example.com/noticia-de-exemplo",
        ),
        DisplayItem(
            id="demo-family",
            kind="countdown",
            title=t("demo.family.title", language),
            summary=t("demo.family.summary", language),
            priority=60,
            occurred_at=local_now + timedelta(days=3),
            source=source,
        ),
        DisplayItem(
            id="demo-calendar-morning",
            kind="calendar",
            title=t("demo.appointment", language),
            priority=65,
            occurred_at=local_now + timedelta(minutes=45),
            person=t("demo.person", language),
            source=source,
        ),
        DisplayItem(
            id="demo-calendar-evening",
            kind="calendar",
            title=t("demo.dinner", language),
            priority=55,
            occurred_at=local_now.replace(hour=19, minute=30, second=0, microsecond=0),
            source=source,
        ),
        DisplayItem(
            id="demo-calendar-tomorrow",
            kind="calendar",
            title=t("demo.lunch", language),
            priority=60,
            occurred_at=(local_now + timedelta(days=1)).replace(
                hour=13, minute=0, second=0, microsecond=0
            ),
            person=t("demo.everyone", language),
            source=source,
        ),
    ]
    weather = WeatherSnapshot(
        observed_at=local_now,
        timezone=timezone,
        source=source,
        current=WeatherPeriod(summary=t("demo.cloudy", language), temperature_c=17, wind_kph=12),
        today=WeatherPeriod(
            summary=t("demo.rain", language),
            temperature_min_c=14,
            temperature_max_c=19,
            rain_probability_pct=80,
            rain_mm=4,
        ),
        tomorrow=WeatherPeriod(
            summary=t("demo.clear", language), temperature_min_c=12, temperature_max_c=17
        ),
        sunrise=local_now.replace(hour=7, minute=21, second=0, microsecond=0),
        sunset=local_now.replace(hour=18, minute=58, second=0, microsecond=0),
    )
    return DisplayContext(
        generated_at=now.astimezone(UTC),
        timezone=timezone,
        language=language,
        mode="family",
        items=items,
        protected_alert_ids=[],
        weather=weather,
        people=[t("demo.person", language), t("demo.everyone", language)],
    )


def render(
    screen: str,
    context: DisplayContext,
    decision: DisplayDecision,
    width: int,
    height: int,
    rotation: int = 0,
) -> bytes:
    """Render a fixed family screen as a grayscale PNG byte string."""
    language = context.language
    if screen not in _SCREENS:
        raise ValueError(f"unsupported screen: {screen}")
    if width < 320 or height < 240 or width > 1648 or height > 1648:
        raise ValueError("width and height must be between 320x240 and 1648x1648")
    if rotation not in (0, 90, 180, 270):
        raise ValueError("rotation must be 0, 90, 180, or 270 degrees")

    local_now = context.generated_at.astimezone(ZoneInfo(context.timezone))
    protected_ids = set(context.protected_alert_ids) | set(decision.protected_alert_ids)
    protected = [
        entry
        for entry in context.items
        if entry.id in protected_ids or entry.is_protected or entry.severity == "critical"
    ]
    protected.sort(key=_alert_order)
    protected_ids |= {entry.id for entry in protected}

    by_id = {entry.id: entry for entry in context.items}
    selected = [
        by_id[item_id]
        for item_id in decision.item_ids
        if item_id in by_id
        and by_id[item_id].kind in _SCREEN_KINDS.get(screen, ())
        and item_id not in protected_ids
    ]
    if screen in ("family", "photo") and selected and selected[0].kind == "photo" and not protected:
        canvas = Canvas(width, height)
        path = selected[0].image_path
        if path and canvas.photo(path):
            _draw_photo_overlay(canvas, selected[0], local_now, language)
            return canvas.png(rotation)
    selected = [entry for entry in selected if entry.kind != "photo"]

    # Alerts take over the top screen as an inverted page; other screens keep a banner.
    alert_page = screen == "news-weather" and bool(protected)
    canvas = Canvas(width, height, inverted=alert_page)
    top = _draw_header(canvas, local_now, language)
    if alert_page:
        _draw_alert_page(canvas, protected, local_now, top, language)
        return canvas.png(rotation)

    if protected:
        top = _draw_alert_banner(canvas, protected, top, language)
    digest = [entry for entry in context.items if entry.kind == "news"][:4]
    wanted = screen == "news" or (screen == "news-weather" and context.news_digest)
    if not wanted or len(digest) < 2:
        digest = []
    _draw_footer(
        canvas, screen, context, t("digest", language, count=len(digest)) if digest else None
    )
    if screen == "calendar":
        _draw_agenda(canvas, context, local_now, protected_ids, top)
        return canvas.png(rotation)

    if digest:
        _draw_news_digest(canvas, digest, top, language)
    elif screen in ("news-weather", "news"):
        _draw_news_weather(canvas, selected, context, top)
    else:
        _draw_family(canvas, selected, context, local_now, top)
    return canvas.png(rotation)


def _draw_photo_overlay(
    canvas: Canvas, item: DisplayItem, now: datetime, language: Language = "pt"
) -> None:
    """Layout 5: a full-bleed photo with the time and a caption on paper labels."""
    clock = now.strftime("%H:%M")
    canvas.rect(0, 0, _MX + canvas.measure(clock, _CLOCK) + 24, _MY + 54 + 16, fill=canvas.paper)
    canvas.line(_MX, _MY, clock, _CLOCK)
    style = Style(20, 600)
    parts = [
        _short_date(now.date(), language),
        item.title if item.title != t("screen.photo", language) else "",
    ]
    caption = canvas.truncate(" · ".join(p for p in parts if p), style, canvas.width - 2 * _MX)
    top = canvas.height - 18 - 40
    canvas.rect(0, top, _MX + canvas.measure(caption, style) + 20, top + 40, fill=canvas.paper)
    canvas.line(_MX, top + (40 - style.line_height) / 2, caption, style)


def _alert_order(item: DisplayItem) -> tuple[int, int, datetime]:
    severity = {"critical": 0, "disruption": 1, "ordinary": 2}[item.severity]
    return (severity, -item.priority, item.occurred_at)


def _short_date(day: date, language: Language = "pt") -> str:
    ordinal = "." if language == "de" else ""
    return f"{t(f'weekday.{day.weekday()}', language)} {day.day}{ordinal} {t(f'month.{day.month}', language)}"


def _when(item: DisplayItem, now: datetime, language: Language = "pt") -> str:
    start = item.occurred_at.astimezone(now.tzinfo)
    days = (start.date() - now.date()).days
    if days < 0:
        return t("ongoing", language)
    clock = "" if item.all_day else start.strftime("%H:%M")
    if days == 0:
        return clock or t("today", language)
    day = t("tomorrow", language) if days == 1 else _short_date(start.date(), language)
    return f"{day} {clock}".strip()


def _item_label(item: DisplayItem, now: datetime, language: Language = "pt") -> str:
    if item.label:
        return item.label
    if item.kind == "calendar":
        parts = [item.person, _when(item, now, language)]
    elif item.kind == "countdown":
        days = (item.occurred_at.astimezone(now.tzinfo).date() - now.date()).days
        countdown = (
            t("today", language)
            if days <= 0
            else t("tomorrow", language)
            if days == 1
            else t("countdown", language, count=days)
        )
        parts = [item.person, countdown]
    elif item.kind == "local_event":
        parts = [_when(item, now, language)]
    else:
        parts = [
            (
                t(f"kind.{item.kind}", language)
                if item.kind in ("verse", "fact")
                else t("screen.photo", language)
                if item.kind == "photo"
                else None
            )
            or item.source
        ]
    return " · ".join(part for part in parts if part)


def _weather_icon(summary: str | None, code: int | None = None) -> str:
    if code is not None:
        if code >= 95:
            return "storm"
        if 51 <= code <= 67 or 80 <= code <= 82:
            return "rain"
        return "sun" if code == 0 else "cloud"
    text = (summary or "").casefold()
    if any(word in text for word in ("trovoada", "thunder", "gewitter")):
        return "storm"
    if any(word in text for word in ("chuv", "aguaceiro", "rain", "shower", "regen")):
        return "rain"
    if any(word in text for word in ("vento", "wind")):
        return "wind"
    if any(word in text for word in ("limpo", "clear", "klar")):
        return "sun"
    return "cloud"


def _degrees(value: float | None) -> str:
    return "—" if value is None else f"{round(value)}°"


def _range(period: WeatherPeriod) -> str:
    return f"{_degrees(period.temperature_min_c)} / {_degrees(period.temperature_max_c)}"


def _today_line(weather: WeatherSnapshot) -> str:
    today = weather.today
    parts = [today.summary or weather.current.summary]
    if today.temperature_min_c is not None or today.temperature_max_c is not None:
        parts.append(_range(today))
    return " · ".join(part for part in parts if part)


def _draw_header(canvas: Canvas, now: datetime, language: Language = "pt") -> float:
    clock = now.strftime("%H:%M")
    canvas.line(_MX, _MY, clock, _CLOCK)
    canvas.line(
        canvas.width - _MX,
        _MY,
        _short_date(now.date(), language),
        _DATE,
        anchor="r",
        baseline=canvas.baseline(_MY, _CLOCK),
    )
    canvas.rule(_MX, _HEADER_BOTTOM - 4, canvas.width - _MX, 4)
    return _HEADER_BOTTOM


def _draw_footer(
    canvas: Canvas, screen: str, context: DisplayContext, title: str | None = None
) -> None:
    language = context.language
    top = canvas.height - 18 - _LABEL.line_height
    notes = [title or t(f"screen.{screen}", language)]
    if context.demo:
        notes.append("DEMO")
    if context.source_warnings:
        notes.append(t("stale", language) + " · " + ", ".join(context.source_warnings))
    side, gap = 8, 9
    dots_width = 3 * side + 2 * gap
    room = canvas.width - 2 * _MX - dots_width - 24
    canvas.line(_MX, top, canvas.truncate(" · ".join(notes), _LABEL, room), _LABEL)
    left = canvas.width - _MX - dots_width
    for index, name in enumerate(_SCREENS):
        canvas.square(
            left + index * (side + gap),
            top + (_LABEL.line_height - side) / 2,
            side,
            filled=name == screen,
        )


def _draw_alert_banner(
    canvas: Canvas, alerts: list[DisplayItem], top: float, language: Language = "pt"
) -> float:
    """Keep protected alerts visible on screens that retain their own content."""
    style = Style(20, 600)
    first = alerts[0]
    parts = [first.title, *(fact.value for fact in first.facts[:1])]
    if len(alerts) > 1:
        parts.append(count_label("warnings", len(alerts) - 1, language))
    y = top + 8
    canvas.rect(_MX, y, canvas.width - _MX, y + 40)
    text = canvas.truncate(" · ".join(parts), style, canvas.width - 2 * _MX - 28)
    canvas.line(_MX + 14, y + (40 - style.line_height) / 2, text, style, fill=canvas.paper)
    return y + 40


def _draw_facts(canvas: Canvas, facts: Sequence[DisplayFact], x: float, y: float, width: float):
    value = Style(70, 700, display=True, leading=1.0)
    for index, fact in enumerate(facts[:3]):
        canvas.line(x, y, canvas.truncate(fact.label, _LABEL, width), _LABEL)
        y += _LABEL.line_height
        sizes: tuple[float, ...] = (70, 56, 44, 36) if index < 2 else (40, 32, 26)
        style, lines = canvas.fit(fact.value, value, sizes, width, sizes[0], 1)
        y = canvas.lines(x, y, lines, style) + 20


def _draw_alert_page(
    canvas: Canvas, alerts: list[DisplayItem], now: datetime, top: float, language: Language = "pt"
) -> None:
    """M4: inverted page with the cause on the left and its facts on the right."""
    alert = alerts[0]
    inner = canvas.width - 2 * _MX
    left_width = inner * 1.5 / 2.5
    grid_top = top + 26

    rule_top = canvas.height - 30
    if alert.summary:
        advice_style, advice = canvas.fit(alert.summary, _STRONG, (26, 24), inner, 26 * 1.2, 1)
        if advice[-1].endswith("…"):
            advice_style, advice = _STRONG, canvas.clamp(alert.summary, _STRONG, inner, 2)
        rule_top -= len(advice) * advice_style.line_height + 14
        canvas.rule(_MX, rule_top, canvas.width - _MX, 2)
        canvas.lines(_MX, rule_top + 14, advice, advice_style)

    label = alert.label or t("warning", language)
    if len(alerts) > 1:
        label += " · " + count_label("warnings", len(alerts) - 1, language)
    text_width = left_width - 24
    canvas.line(_MX, grid_top, canvas.truncate(label, _LABEL, text_width), _LABEL)
    y = grid_top + _LABEL.line_height + 20
    icon = _weather_icon(alert.title)
    if icon != "cloud":
        canvas.icon(icon, _MX, y, 120)
        y += 120 + 14
    title = Style(120, 700, display=True, leading=0.88, tracking=-0.05)
    style, lines = canvas.fit(
        alert.title, title, (120, 104, 88, 72, 60), text_width, rule_top - 12 - y, 3
    )
    canvas.lines(_MX, y, lines, style)

    divider = _MX + left_width
    canvas.vrule(divider, grid_top, rule_top - 16, 3)
    facts = alert.facts or [
        DisplayFact(label=t("when", language), value=_when(alert, now, language))
    ]
    _draw_facts(canvas, facts, divider + 3 + 26, grid_top + 6, inner - left_width - 29)


def _draw_weather_strip(canvas: Canvas, context: DisplayContext, now: datetime, top: float) -> None:
    language = context.language
    weather = context.weather
    if weather is None:
        return
    canvas.rule(_MX, top, canvas.width - _MX, 2)
    text_top = top + 14
    summary = weather.today.summary or weather.current.summary
    line = _today_line(weather)
    if context.night and now.hour >= 12:
        # In the evening the useful forecast is the next day's.
        summary = weather.tomorrow.summary
        line = " · ".join(
            part for part in (t("tomorrow", language), summary, _range(weather.tomorrow)) if part
        )
    canvas.icon(
        _weather_icon(
            summary,
            weather.tomorrow.code if context.night and now.hour >= 12 else weather.today.code,
        ),
        _MX,
        top + 12,
        34,
    )
    x = _MX + 34 + 14
    text = canvas.truncate(line, _STRONG, canvas.width - _MX - x)
    canvas.line(x, text_top, text, _STRONG)


def _draw_message(
    canvas: Canvas, messages: Sequence[str], x: float, top: float, width: float | None = None
) -> float:
    available = width if width is not None else canvas.width - _MX - x
    for message in messages:
        style, lines = canvas.fit(
            message, Style(30, 600, leading=1.25), (30, 28, 26, 24), available, 75, 2
        )
        top = canvas.lines(x, top, lines, style)
    return top


def _draw_family(
    canvas: Canvas,
    items: list[DisplayItem],
    context: DisplayContext,
    now: datetime,
    top: float,
) -> None:
    language = context.language
    footer_top = canvas.height - 52
    quote = items[0] if items and items[0].kind in ("verse", "fact") else None
    if quote is not None and context.weather is None:
        _draw_quote(canvas, quote, top, footer_top)
        return
    if items and items[0].kind == "local_event":
        _draw_nearby(canvas, items, context, now, top, footer_top)
        return
    if quote is not None or not items:
        _draw_family_empty(canvas, context, quote, now, top)
        return
    # A quote needs the whole page, so it never squeezes into a supporting slot.
    items = [items[0], *(item for item in items[1:] if item.kind not in ("verse", "fact"))]
    strip_top = canvas.height - 96
    grid_top = top + 26
    grid_bottom = strip_top - 4
    _draw_weather_strip(canvas, context, now, strip_top)

    inner = canvas.width - 2 * _MX
    left_width = inner * 1.4 / 2.4 if len(items) > 1 else inner
    text_width = left_width - 33 if len(items) > 1 else inner

    # M1 left: the highest-priority item as the hero.
    hero = items[0]
    canvas.line(
        _MX, grid_top, canvas.truncate(_item_label(hero, now, language), _LABEL, text_width), _LABEL
    )
    y = grid_top + _LABEL.line_height + 12
    summary_room = 20 + 2 * _BODY.line_height if hero.summary else 0
    style, lines = canvas.fit(
        hero.title, _HERO, (98, 84, 72, 60, 48), text_width, grid_bottom - y - summary_room, 3
    )
    y = canvas.lines(_MX, y, lines, style) + 20
    if hero.summary:
        canvas.block(_MX, y, hero.summary, _BODY, text_width, grid_bottom)
    if len(items) == 1:
        return

    # M1 right: supporting items; the lowest priority is dropped rather than squeezed.
    canvas.vrule(_MX + left_width - 3, grid_top, grid_bottom, 3)
    x = _MX + left_width + 30
    width = inner - left_width - 30
    second = items[1]
    canvas.line(
        x, grid_top, canvas.truncate(_item_label(second, now, language), _LABEL, width), _LABEL
    )
    y = grid_top + _LABEL.line_height + 4
    style, lines = canvas.fit(second.title, _TITLE, (40, 34, 28), width, grid_bottom - y, 3)
    y = canvas.lines(x, y, lines, style)
    if len(items) > 2:
        third = items[2]
        lines = canvas.clamp(third.title, _STRONG, width, 3)
        needed = 22 + 2 + 16 + _LABEL.line_height + 6 + len(lines) * _STRONG.line_height
        if y + needed <= grid_bottom:
            y += 22
            canvas.rule(x, y, x + width, 2)
            y += 2 + 16
            canvas.line(
                x, y, canvas.truncate(_item_label(third, now, language), _LABEL, width), _LABEL
            )
            canvas.lines(x, y + _LABEL.line_height + 6, lines, _STRONG)


def _draw_sun_hours(canvas: Canvas, context: DisplayContext, x: float, bottom: float) -> bool:
    weather = context.weather
    if weather is None or weather.sunrise is None or weather.sunset is None:
        return False
    zone = ZoneInfo(context.timezone)
    hours = f"{weather.sunrise.astimezone(zone):%H:%M} – {weather.sunset.astimezone(zone):%H:%M}"
    canvas.icon("sunrise", x, bottom - 30, 30)
    canvas.line(x + 30 + 10, bottom - 27, hours, Style(20))
    return True


def _draw_family_empty(
    canvas: Canvas, context: DisplayContext, quote: DisplayItem | None, now: datetime, top: float
) -> None:
    """With no family items the weather becomes the page, beside a quote when there is one."""
    language = context.language
    unavailable = "calendar" in context.unavailable_kinds
    message = t("unavailable.calendar", language) if unavailable else t("empty.family", language)
    grid_top = top + 22
    if context.weather is None:
        _draw_message(canvas, [message], _MX, grid_top)
        return
    grid_bottom = canvas.height - 84
    column = (canvas.width - 2 * _MX) / 2
    canvas.vrule(_MX + column - 3, grid_top, grid_bottom, 3)
    _draw_current_weather(canvas, context.weather, grid_top, grid_bottom, column - 31, language)
    x = _MX + column + 28
    width = column - 28
    if quote is not None and not unavailable:
        canvas.line(
            x, grid_top, canvas.truncate(_item_label(quote, now, language), _LABEL, width), _LABEL
        )
        y = grid_top + _LABEL.line_height + 10
        style, lines = canvas.fit(
            quote.title, _TITLE, (36, 32, 28, 24), width, grid_bottom - 42 - y, 9
        )
    else:
        canvas.line(x, grid_top, t("screen.calendar", language), _LABEL)
        y = grid_top + _LABEL.line_height + 10
        style, lines = canvas.fit(message, _TITLE, (38, 34, 30), width, 160, 3)
    canvas.lines(x, y, lines, style)
    _draw_sun_hours(canvas, context, x, grid_bottom)


def _draw_quote(canvas: Canvas, item: DisplayItem, top: float, footer_top: float) -> None:
    """M5: a verse, fact or message shown when nothing more urgent needs the page."""
    grid_top = top + 70
    canvas.line(_MX, grid_top + 12, "“", Style(200, 700, display=True, leading=0.7))
    x = _MX + 90 + 20
    width = canvas.width - _MX - x
    reference = item.summary or item.label
    caption = Style(20, 600, leading=1.3, tracking=0.12, upper=True)
    caption_lines = canvas.clamp(reference, caption, width, 2) if reference else []
    caption_room = 28 + len(caption_lines) * caption.line_height if caption_lines else 0
    quote = Style(72, 700, display=True, leading=1.02, tracking=-0.03)
    style, lines = canvas.fit(
        item.title, quote, (72, 60, 50, 42, 34), width, footer_top - grid_top - caption_room, 5
    )
    y = canvas.lines(x, grid_top, lines, style)
    if caption_lines:
        canvas.lines(x, y + 28, caption_lines, caption)


def _draw_nearby(
    canvas: Canvas,
    items: list[DisplayItem],
    context: DisplayContext,
    now: datetime,
    top: float,
    footer_top: float,
) -> None:
    """M6: up to three nearby events side by side; the distance is the key number."""
    language = context.language
    events = [item for item in items if item.kind == "local_event"][:3]
    y = top + 14
    today = all(item.occurred_at.astimezone(now.tzinfo).date() == now.date() for item in events)
    canvas.line(
        _MX, y + 4, t("nearby.today", language) if today else t("screen.nearby", language), _LABEL
    )
    if context.weather is not None:
        style = Style(22, 600)
        text = _today_line(context.weather)
        width = canvas.line(canvas.width - _MX, y, text, style, anchor="r")
        icon = _weather_icon(
            context.weather.today.summary or context.weather.current.summary,
            context.weather.today.code,
        )
        canvas.icon(icon, canvas.width - _MX - width - 30 - 10, y - 2, 30)

    grid_top = y + 27 + 22
    grid_bottom = footer_top - 21
    column = (canvas.width - 2 * _MX) / 3
    number = Style(96, 700, display=True, leading=0.85, tracking=-0.05)
    unit = Style(24, 600, display=True)
    title = Style(34, 700, display=True, leading=1.05, tracking=-0.02)
    place = Style(20, leading=1.25)
    for index, event in enumerate(events):
        x = _MX + index * column
        width = column - 20
        if index:
            canvas.vrule(x, grid_top, grid_bottom, 3)
            x += 3 + 20
            width -= 3 + 20
        y = grid_top
        bottom = grid_bottom
        if index == 0 and event.url:
            bottom -= canvas.qr(event.url, x + 80, grid_bottom, 80) + 10
        if event.distance_km is not None:
            distance = f"{event.distance_km:.0f}"
            advance = canvas.line(x, y, distance, number)
            canvas.line(x + advance + 8, y, "km", unit, baseline=canvas.baseline(y, number))
            y += number.line_height + 16
        else:
            canvas.line(
                x, y, canvas.truncate(_item_label(event, now, language), _LABEL, width), _LABEL
            )
            y += _LABEL.line_height + 12
        style, lines = canvas.fit(event.title, title, (34, 30, 26), width, bottom - y, 4)
        y = canvas.lines(x, y, lines, style) + 8
        detail = " · ".join(part for part in (event.summary, _when(event, now, language)) if part)
        canvas.block(x, y, detail, place, width, bottom)


def _draw_news_weather(
    canvas: Canvas, items: list[DisplayItem], context: DisplayContext, top: float
) -> None:
    """M2: weather on the left, up to two stories with a QR to the source on the right."""
    language = context.language
    grid_top = top + 22
    grid_bottom = canvas.height - 84
    column = (canvas.width - 2 * _MX) / 2
    canvas.vrule(_MX + column - 3, grid_top, grid_bottom, 3)
    weather = context.weather
    left_width = column - 31

    if weather is not None:
        _draw_current_weather(canvas, weather, grid_top, grid_bottom, left_width, language)
    else:
        legacy = next((item for item in items if item.kind == "weather"), None)
        y = grid_top
        if "weather" in context.unavailable_kinds:
            y = _draw_message(canvas, [t("unavailable.weather", language)], _MX, y, left_width) + 12
        if legacy is not None:
            style, lines = canvas.fit(
                legacy.title, _TITLE, (38, 32, 26), left_width, grid_bottom - y, 3
            )
            y = canvas.lines(_MX, y, lines, style) + 12
            if legacy.summary:
                canvas.block(
                    _MX, y, legacy.summary, Style(21, leading=1.3), left_width, grid_bottom
                )

    x = _MX + column + 28
    width = column - 28
    stories = [item for item in items if item.kind == "news"][:2]
    limit = grid_bottom
    if _draw_sun_hours(canvas, context, x, grid_bottom):
        limit = grid_bottom - 30 - 12
    if stories and stories[0].url and stories[0].url.startswith(("http://", "https://")):
        used = canvas.qr(stories[0].url, canvas.width - _MX, grid_bottom, 88)
        if used:
            limit = min(limit, grid_bottom - used - 12)

    y = grid_top
    if not stories and "rss" in context.unavailable_kinds:
        _draw_message(canvas, [t("unavailable.rss", language)], x, y, width)
    headline = _TITLE.sized(38)
    body = Style(21, leading=1.3)
    for index, story in enumerate(stories):
        label = story.label or story.source or t("screen.news", language)
        if index == 0:
            canvas.line(x, y, canvas.truncate(label, _LABEL, width), _LABEL)
            y += _LABEL.line_height + 10
            style, lines = canvas.fit(story.title, headline, (38, 34, 30, 26), width, limit - y, 5)
            y = canvas.lines(x, y, lines, style)
            if story.summary and y + 12 + body.line_height <= limit:
                room = int((limit - y - 12) // body.line_height)
                wanted = 2 if len(stories) > 1 else 4
                summary = canvas.clamp(story.summary, body, width, min(wanted, room))
                y = canvas.lines(x, y + 12, summary, body)
            continue
        # The second story is the lowest priority: drop it rather than squeeze the first.
        lines = canvas.clamp(story.title, _STRONG.sized(22), width, 3)
        style = _STRONG.sized(22)
        needed = 14 + 2 + 12 + _LABEL.line_height + 6 + len(lines) * style.line_height
        if y + needed <= limit:
            y += 14
            canvas.rule(x, y, x + width, 2)
            y += 2 + 12
            canvas.line(x, y, canvas.truncate(label, _LABEL, width), _LABEL)
            canvas.lines(x, y + _LABEL.line_height + 6, lines, style)


def _draw_news_digest(
    canvas: Canvas, stories: list[DisplayItem], top: float, language: Language = "pt"
) -> None:
    """M7: one lead story with a QR and up to three briefs, for busy news periods."""
    grid_top = top + 18
    grid_bottom = canvas.height - 118
    inner = canvas.width - 2 * _MX
    left_width = inner * 1.2 / 2.2
    canvas.vrule(_MX + left_width - 3, grid_top, grid_bottom, 3)

    lead = stories[0]
    width = left_width - 33
    limit = grid_bottom
    if lead.url and lead.url.startswith(("http://", "https://")):
        used = canvas.qr(lead.url, _MX + width, grid_bottom, 88)
        if used:
            canvas.line(_MX, grid_bottom - _LABEL.line_height, t("read_phone", language), _LABEL)
            limit = grid_bottom - used - 12
    canvas.line(_MX, grid_top, canvas.truncate(_story_label(lead, language), _LABEL, width), _LABEL)
    y = grid_top + _LABEL.line_height + 8
    headline = Style(40, 700, display=True, leading=1.0, tracking=-0.03)
    style, lines = canvas.fit(lead.title, headline, (40, 36, 32, 28), width, limit - y, 5)
    y = canvas.lines(_MX, y, lines, style) + 10
    if lead.summary:
        canvas.block(_MX, y, lead.summary, Style(21, leading=1.25), width, limit)

    x = _MX + left_width + 30
    width = inner - left_width - 30
    title = Style(24, 700, display=True, leading=1.05, tracking=-0.02)
    detail = Style(20, leading=1.25)
    y = grid_top
    for index, story in enumerate(stories[1:4]):
        lines = canvas.clamp(story.title, title, width, 2)
        height = _LABEL.line_height + 4 + len(lines) * title.line_height
        if story.summary:
            height += 6 + detail.line_height
        # Briefs are in priority order: stop rather than squeeze one in.
        if y + (12 if index else 0) + height > grid_bottom:
            break
        if index:
            canvas.rule(x, y, x + width, 2)
            y += 12
        canvas.line(x, y, canvas.truncate(_story_label(story, language), _LABEL, width), _LABEL)
        y = canvas.lines(x, y + _LABEL.line_height + 4, lines, title)
        if story.summary:
            canvas.line(x, y + 6, canvas.truncate(story.summary, detail, width), detail)
            y += 6 + detail.line_height
        y += 10


def _story_label(story: DisplayItem, language: Language = "pt") -> str:
    return story.label or story.source or t("screen.news", language)


def _draw_current_weather(
    canvas: Canvas,
    weather: WeatherSnapshot,
    top: float,
    bottom: float,
    width: float,
    language: Language = "pt",
) -> None:
    current = weather.current
    temperature = current.temperature_c
    figure = Style(200, 700, display=True, leading=0.8, tracking=-0.06)
    y = top
    if temperature is not None:
        text = _degrees(temperature)
        style, _ = canvas.fit(text, figure, (200, 170, 140, 110), width - 96 - 18, 200, 1)
        advance = canvas.line(_MX, y, text, style)
        y += style.line_height
        canvas.icon(
            _weather_icon(current.summary, current.code), _MX + advance + 18, y - 4 - 96, 96
        )
    else:
        canvas.icon(_weather_icon(current.summary, current.code), _MX, y, 96)
        y += 96

    cells_top = bottom - 72
    parts = [current.summary or weather.today.summary]
    today, tomorrow = weather.today, weather.tomorrow
    if today.rain_mm is not None and today.rain_mm >= 0.5:
        parts.append(t("rain.today", language, amount=format_number(today.rain_mm, language)))
    elif today.rain_probability_pct is not None and today.rain_probability_pct >= 50:
        parts.append(t("rain.probable", language, chance=today.rain_probability_pct))
    elif today.wind_kph is not None and today.wind_kph >= 40:
        parts.append(t("wind.until", language, speed=format_number(today.wind_kph, language)))
    if tomorrow.summary and _weather_icon(tomorrow.summary, tomorrow.code) in ("rain", "storm"):
        # German nouns keep their capital mid-sentence; Portuguese and English do not.
        summary = tomorrow.summary
        if language != "de":
            summary = summary[:1].lower() + summary[1:]
        parts.append(t("forecast.tomorrow", language, summary=summary))
    description = ". ".join(part for part in parts if part)
    if description:
        canvas.block(_MX, y + 22, description, Style(30, 600, leading=1.15), width, cells_top - 8)

    canvas.rule(_MX, cells_top, _MX + width, 2)
    cell = (width - 18) / 2
    value = Style(22, leading=1.22)
    for index, (label, period) in enumerate(
        ((t("today", language), weather.today), (t("tomorrow", language), weather.tomorrow))
    ):
        x = _MX + index * (cell + 18)
        canvas.line(x, cells_top + 14, label, _LABEL)
        row = cells_top + 14 + _LABEL.line_height + 4
        canvas.icon(_weather_icon(period.summary, period.code), x, row, 34)
        canvas.line(x + 34 + 8, row + (34 - value.line_height) / 2, _range(period), value)


def _badge_shape(person: str, people: Sequence[str]) -> str:
    """Give each person one fixed badge shape, following the configured roster order."""
    roster = list(people)
    index = roster.index(person) if person in roster else len(roster) + sum(map(ord, person))
    return BADGE_SHAPES[index % len(BADGE_SHAPES)]


def _calendar_days(
    items: Sequence[DisplayItem],
    zone: ZoneInfo,
    today: date,
    protected_ids: set[str],
    language: Language = "pt",
) -> dict[date, list[tuple[DisplayItem, str]]]:
    days = (today, today + timedelta(days=1))
    rows: dict[date, list[tuple[DisplayItem, datetime, str]]] = {day: [] for day in days}
    for entry in items:
        if entry.kind != "calendar" or entry.id in protected_ids:
            continue
        start = entry.occurred_at.astimezone(zone)
        end = entry.ends_at.astimezone(zone) if entry.ends_at is not None else None
        for day in days:
            day_start = datetime.combine(day, time.min, tzinfo=zone)
            day_end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
            overlaps = start.date() == day if end is None else start < day_end and end > day_start
            if not overlaps:
                continue
            if entry.all_day:
                time_label = t("all_day", language)
            elif start.date() < day:
                time_label = t("ongoing", language)
            else:
                time_label = start.strftime("%H:%M")
            rows[day].append((entry, start, time_label))
    return {
        day: [(entry, label) for entry, _, label in sorted(found, key=lambda r: (r[1], r[0].id))]
        for day, found in rows.items()
    }


def _draw_agenda(
    canvas: Canvas,
    context: DisplayContext,
    now: datetime,
    protected_ids: set[str],
    top: float,
) -> None:
    """M3: today and tomorrow side by side; row size follows importance."""
    language = context.language
    zone = ZoneInfo(context.timezone)
    today = now.date()
    tomorrow = today + timedelta(days=1)
    events = _calendar_days(context.items, zone, today, protected_ids, language)
    unavailable = "calendar" in context.unavailable_kinds

    grid_top = top + 18
    grid_bottom = canvas.height - 88
    inner = canvas.width - 2 * _MX
    left_width = inner * 1.15 / 2.15
    canvas.vrule(_MX + left_width - 3, grid_top, grid_bottom, 3)
    ordinal = "." if language == "de" else ""
    right_label = f"{t('tomorrow', language)} · {t(f'weekday.{tomorrow.weekday()}', language)} {tomorrow.day}{ordinal}"
    titles: dict[str, str] = {}
    if not events[tomorrow]:
        # A free tomorrow gives its column to whatever comes next in the calendar.
        later = _upcoming(context.items, zone, tomorrow, protected_ids, language)
        if later:
            right_label = t("next", language)
            events[tomorrow] = [(entry, label) for entry, label, _ in later]
            titles = {entry.id: title for entry, _, title in later}
    columns = (
        (today, t("today", language), _MX, left_width - 29, 0),
        (
            tomorrow,
            right_label,
            _MX + left_width + 26,
            inner - left_width - 26,
            1,
        ),
    )
    shown_people: list[str] = []
    y = grid_top
    for day, label, x, width, first_tier in columns:
        canvas.line(x, grid_top, label, _LABEL)
        y = grid_top + _LABEL.line_height + 6
        rows = events[day]
        if not rows:
            if unavailable:
                if day == today:
                    _draw_message(canvas, [t("unavailable.calendar", language)], x, y + 8, width)
            else:
                canvas.rule(x, y, x + width, 2)
                canvas.line(x, y + 11, t("empty.events", language), Style(22, leading=1.22))
            continue
        layouts = [
            _agenda_row(
                canvas,
                entry,
                time_label,
                min(first_tier + index, 2),
                width,
                titles.get(entry.id, entry.title),
            )
            for index, (entry, time_label) in enumerate(rows)
        ]
        fits = _rows_fitting(layouts, grid_bottom - y)
        if fits < len(layouts):
            fits = _rows_fitting(layouts, grid_bottom - y - 28)
            canvas.line(
                x,
                grid_bottom - _NOTE.line_height,
                count_label("events", len(layouts) - fits, language),
                _NOTE,
            )
        for (entry, _), row in zip(rows[:fits], layouts[:fits], strict=True):
            _draw_agenda_row(canvas, entry, row, x, y, width, context.people)
            y += row["height"]
            if entry.person and entry.person not in shown_people:
                shown_people.append(entry.person)

    # Legend of people under tomorrow's events, when there is room for it.
    if not shown_people:
        return
    roster = [person for person in context.people if person in shown_people]
    roster += sorted(person for person in shown_people if person not in roster)
    x, width = columns[1][2], columns[1][3]
    legend_rows = (len(roster) + 1) // 2
    legend_top = grid_bottom - legend_rows * 40 + 8
    if legend_top < y + 16:
        return
    name = Style(16, leading=1.22, tracking=0.06)
    for index, person in enumerate(roster):
        left = x + (index % 2) * (width + 8) / 2
        row_top = legend_top + (index // 2) * 40
        canvas.badge(left, row_top, person[:1], _badge_shape(person, context.people))
        text = canvas.truncate(person, name, (width - 8) / 2 - 40)
        canvas.line(left + 40, row_top + (32 - name.line_height) / 2, text, name)


def _upcoming(
    items: Sequence[DisplayItem],
    zone: ZoneInfo,
    after: date,
    protected_ids: set[str],
    language: Language = "pt",
) -> list[tuple[DisplayItem, str, str]]:
    """Events starting after `after`, as (item, date label, title with its time)."""
    found = [
        (entry.occurred_at.astimezone(zone), entry)
        for entry in items
        if entry.kind == "calendar"
        and entry.id not in protected_ids
        and entry.occurred_at.astimezone(zone).date() > after
    ]
    found.sort(key=lambda pair: (pair[0], pair[1].id))
    return [
        (
            entry,
            f"{t(f'weekday.{start.weekday()}', language)} {start.day}{'.' if language == 'de' else ''}",
            entry.title if entry.all_day else f"{start:%H:%M} · {entry.title}",
        )
        for start, entry in found[:6]
    ]


def _agenda_row(
    canvas: Canvas, entry: DisplayItem, time_label: str, tier: int, width: float, text: str
):
    clock_size, title_size, weight = _AGENDA_TIERS[tier]
    clock = Style(clock_size, 700, display=True)
    if not time_label[:1].isdigit():
        clock = Style(18, 600)
    title = Style(title_size, weight, display=True, leading=1.1, tracking=-0.02)
    clock_width = canvas.measure(time_label, clock)
    if time_label[:1].isdigit():
        # A fixed column (about 2.9× the clock size) keeps badges and titles aligned.
        clock_width = max(clock_width, 2.9 * clock_size - 10)
    offset = clock_width + 10 + (42 if entry.person else 0)
    lines = canvas.clamp(text, title, max(40.0, width - offset), 2)
    content = max(clock.line_height, len(lines) * title.line_height, 32 if entry.person else 0)
    return {
        "clock": clock,
        "label": time_label,
        "title": title,
        "lines": lines,
        "clock_width": clock_width,
        "content": content,
        "height": 2 + 9 + content + 9,
    }


def _rows_fitting(layouts: list[dict], room: float) -> int:
    used, count = 0.0, 0
    for row in layouts:
        if used + row["height"] > room:
            break
        used += row["height"]
        count += 1
    return count


def _draw_agenda_row(
    canvas: Canvas,
    entry: DisplayItem,
    row: dict,
    x: float,
    y: float,
    width: float,
    people: Sequence[str],
) -> None:
    canvas.rule(x, y, x + width, 2)
    top = y + 2 + 9
    clock: Style = row["clock"]
    title: Style = row["title"]
    content: float = row["content"]
    canvas.line(x, top + (content - clock.line_height) / 2, row["label"], clock)
    left = x + row["clock_width"] + 10
    if entry.person:
        canvas.badge(
            left, top + (content - 32) / 2, entry.person[:1], _badge_shape(entry.person, people)
        )
        left += 42
    lines: list[str] = row["lines"]
    canvas.lines(left, top + (content - len(lines) * title.line_height) / 2, lines, title)
