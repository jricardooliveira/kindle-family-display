"""Scheduled collection and normalization of configured family information sources."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

from pydantic import SecretStr

from app.collectors.events import parse_events
from app.collectors.http import FetchError, fetch_bytes
from app.collectors.ics import parse_ics
from app.collectors.rss import parse_rss
from app.collectors.weather import parse_weather, weather_request_url
from app.config import CalendarFeed, EventFeed, RSSFeed, Settings
from app.contracts import (
    DisplayContext,
    DisplayFact,
    DisplayItem,
    Event,
    NewsItem,
    WeatherSnapshot,
)
from app.contracts.models import NearbyEvent, SourceStatus
from app.decision.ai import NewsScore, read_api_key, score_news
from app.decision.facts import fact_for
from app.decision.news import ROTATION_POOL, rotate, rotation_offset, select_news
from app.decision.periods import in_period
from app.i18n import Country, Language, format_number
from app.i18n.data import text as data_text
from app.storage.sources import SourceCache

SourceKind = Literal["calendar", "weather", "rss", "events"]
_MAX_CALENDAR_FILES = 8
_MAX_CALENDAR_FILE_BYTES = 1_048_576
_CALENDAR_NAME = re.compile(rb"^X-WR-CALNAME:([^\r\n]+)", re.MULTILINE)
# How many fresh stories are scored and ranked when AI scoring is on.
_AI_POOL = 40
_LIVE_PREFIX = re.compile(r"^\d{1,2}h\d{0,2}\.\s+")
_Feed = CalendarFeed | RSSFeed | EventFeed


class DataPipeline:
    """Collect due sources and merge last-good normalized facts into a context."""

    def __init__(
        self,
        settings: Settings,
        source_cache: SourceCache,
        fetcher: Callable[[str], bytes] = fetch_bytes,
        scorer: Callable[[list[NewsItem], list[str]], dict[str, NewsScore]] | None = None,
    ):
        self.settings = settings
        api_key = read_api_key(settings.ai_api_key_file) if settings.ai_enabled else None
        if scorer is None and api_key:
            model = settings.ai_model

            def scorer(stories: list[NewsItem], topics: list[str]) -> dict[str, NewsScore]:
                return score_news(
                    stories,
                    api_key=api_key,
                    model=model,
                    known_topics=topics,
                    country=settings.country,
                    language=settings.language,
                )

        self._scorer = scorer
        # Scores survive restarts so a deploy does not pay to score the same stories again.
        score_name = (
            "news_scores.json"
            if (settings.country, settings.language) == ("PT", "pt")
            else f"news_scores.{settings.country}.{settings.language}.json"
        )
        self._scores_path = Path(settings.cache_dir) / score_name
        self._news_scores: dict[str, NewsScore] = _load_scores(self._scores_path)
        self._score_retry_at: datetime | None = None
        self.source_cache = source_cache
        self.fetcher = fetcher
        self._feeds: dict[str, _Feed | None] = {}
        self._urls: dict[str, str] = {}
        self._files: dict[str, Path] = {}
        self._fingerprints: dict[str, str] = {}
        self._kinds: dict[str, SourceKind] = {}
        self._specs: list[dict[str, str]] = []
        self._configure_sources()

    def _configure_sources(self) -> None:
        for calendar_feed in self.settings.calendar_feeds:
            self._add_feed(calendar_feed, "calendar")
        for path in _calendar_files(self.settings.calendars_dir):
            self._add_calendar_file(path)
        for rss_feed in self.settings.rss_feeds:
            self._add_feed(rss_feed, "rss")
        for event_feed in self.settings.event_feeds:
            self._add_feed(event_feed, "events")
        if self.settings.weather_latitude is not None:
            assert self.settings.weather_longitude is not None
            source_id = "weather-home"
            url = weather_request_url(
                self.settings.weather_latitude,
                self.settings.weather_longitude,
                self.settings.timezone,
            )
            fingerprint = _fingerprint(
                {
                    "kind": "weather",
                    "language": self.settings.language,
                    "latitude": self.settings.weather_latitude,
                    "longitude": self.settings.weather_longitude,
                    "location": self.settings.weather_location,
                    "timezone": self.settings.timezone,
                }
            )
            self._remember(source_id, "weather", fingerprint, url, None)
        self.source_cache.sync(self._specs)

    def _add_feed(self, feed: _Feed, kind: Literal["calendar", "rss", "events"]) -> None:
        url = feed.url.get_secret_value()
        settings = feed.model_dump(mode="json", exclude={"url"})
        if kind == "calendar":
            settings["timezone"] = self.settings.timezone
            settings["calendar_days"] = self.settings.calendar_days
        fingerprint = _fingerprint({"kind": kind, "url": url, "settings": settings})
        self._remember(feed.id, kind, fingerprint, url, feed)

    def _add_calendar_file(self, path: Path) -> None:
        """Register a local .ics file; it is re-read on the calendar polling interval."""
        source_id = _file_source_id(path)
        if source_id in self._kinds:
            return
        stat = path.stat()
        feed = CalendarFeed.model_construct(
            id=source_id, label=_calendar_file_label(path), url=SecretStr(""), person=None
        )
        fingerprint = _fingerprint(
            {
                "kind": "calendar",
                "file": path.name,
                "size": stat.st_size,
                "modified": stat.st_mtime_ns,
                "timezone": self.settings.timezone,
                "calendar_days": self.settings.calendar_days,
            }
        )
        self._files[source_id] = path
        self._remember(source_id, "calendar", fingerprint, "", feed)

    def _remember(
        self,
        source_id: str,
        kind: SourceKind,
        fingerprint: str,
        url: str,
        feed: _Feed | None,
    ) -> None:
        if source_id in self._kinds:
            raise ValueError("source ids must be unique across configured sources")
        self._feeds[source_id] = feed
        self._urls[source_id] = url
        self._fingerprints[source_id] = fingerprint
        self._kinds[source_id] = kind
        self._specs.append({"id": source_id, "kind": kind, "fingerprint": fingerprint})

    def collect(self, now: datetime) -> DisplayContext:
        current = _aware(now)
        for source_id, kind in self._kinds.items():
            row = self.source_cache.get(source_id)
            if row is not None and not self._due(row, kind, current):
                continue
            self._refresh(source_id, kind, current)

        items: list[DisplayItem] = []
        weather: WeatherSnapshot | None = None
        nearby: list[tuple[NearbyEvent, float]] = []
        news_candidates: list[NewsItem] = []
        available: set[SourceKind] = set()
        for source_id, kind in self._kinds.items():
            row = self.source_cache.get(source_id)
            if row is None or row["data"] is None:
                continue
            try:
                facts = row["data"]
                if kind == "calendar":
                    events = [Event.model_validate(value) for value in facts["events"]]
                    zone = ZoneInfo(self.settings.timezone)
                    local_today = current.astimezone(zone).date()
                    window_start = datetime.combine(local_today, time.min, zone)
                    window_end = datetime.combine(
                        local_today + timedelta(days=self.settings.calendar_days), time.min, zone
                    )
                    items.extend(
                        _event_item(event, self._feed_label(source_id))
                        for event in events
                        if _overlaps_window(event, window_start, window_end)
                    )
                elif kind == "weather":
                    snapshot = WeatherSnapshot.model_validate(facts["snapshot"])
                    items.extend(_weather_items(snapshot, self.settings, current))
                    weather = snapshot
                elif kind == "events":
                    distance = self._feed(source_id, EventFeed).distance_km
                    nearby.extend(
                        (NearbyEvent.model_validate(value), distance) for value in facts["events"]
                    )
                else:
                    feed = self._feed(source_id, RSSFeed)
                    news = [NewsItem.model_validate(value) for value in facts["items"]]
                    news_candidates.extend(_eligible_news(news, feed))
                available.add(kind)
            except (KeyError, TypeError, ValueError):
                self.source_cache.failure(source_id, "invalid_cache", current)

        offset = rotation_offset(
            current.astimezone(ZoneInfo(self.settings.timezone)),
            self.settings.news_rotation_windows,
            self.settings.refresh_minutes,
        )
        local_now = current.astimezone(ZoneInfo(self.settings.timezone))
        digest = rotation_offset(local_now, self.settings.news_digest_windows, 1) is not None
        # Four stories feed the multi-story page; the weather page uses the first two.
        count = 4
        important = self._important_news(news_candidates, current)
        if important is not None:
            pool = important[:ROTATION_POOL]
            selected_news = pool[:count] if offset is None else rotate(pool, offset, count)
        elif offset is None:
            selected_news = select_news(news_candidates, now=current, max_items=count)
        else:
            recent = select_news(news_candidates, now=current, max_items=ROTATION_POOL)
            selected_news = rotate(recent, offset, count)
        feed_by_id = {feed.id: feed for feed in self.settings.rss_feeds}
        items.extend(
            # Priority keeps this order through the screen rules.
            _news_item(
                item, feed_by_id[item.source], self.settings.language, self.settings.country
            ).model_copy(update={"priority": 50 - index})
            for index, item in enumerate(selected_news)
        )
        local = current.astimezone(ZoneInfo(self.settings.timezone))
        if self.settings.facts_enabled:
            category, text = fact_for(local.date(), self.settings.language)
            items.append(
                DisplayItem(
                    id=f"fact:{local.date().isoformat()}",
                    kind="fact",
                    title=text,
                    occurred_at=current,
                    source=data_text("facts", self.settings.language),
                    label=data_text("fact.label", self.settings.language, category=category),
                )
            )
        items.extend(_nearby_items(nearby, local, self.settings.language))
        photo = _photo_of_the_day(self.settings.photos_dir, local.date())
        if photo is not None:
            items.append(
                DisplayItem(
                    id=f"photo:{local.date().isoformat()}",
                    kind="photo",
                    title=_photo_caption(photo, self.settings.language),
                    # Even hours favour the photo, odd hours the curiosity.
                    priority=1 if local.hour % 2 == 0 else 0,
                    occurred_at=current,
                    source=data_text("photos", self.settings.language),
                    image_path=str(photo),
                )
            )
        night = bool(self.settings.night_window) and in_period(
            self.settings.night_window, local.time()
        )
        status = self.source_status(current)
        warnings = [
            self._feed_label(source.id)
            or self.settings.weather_location
            or data_text("weather", self.settings.language)
            for source in status
            if source.stale or source.last_error
        ]
        configured = set(self._kinds.values())
        unavailable: list[Literal["calendar", "weather", "rss"]] = [
            kind
            for kind in ("calendar", "weather", "rss")
            if kind not in configured or kind not in available
        ]
        return DisplayContext(
            generated_at=current,
            language=self.settings.language,
            timezone=self.settings.timezone,
            mode="family",
            items=items,
            protected_alert_ids=[item.id for item in items if item.is_protected],
            demo=False,
            source_warnings=warnings,
            unavailable_kinds=unavailable,
            weather=weather,
            night=night,
            news_digest=digest,
            people=list(
                dict.fromkeys(feed.person for feed in self.settings.calendar_feeds if feed.person)
            ),
        )

    def _important_news(self, candidates: list[NewsItem], now: datetime) -> list[NewsItem] | None:
        """Rank fresh stories by AI importance; None means scoring is off or unavailable."""
        if self._scorer is None:
            return None
        fresh = select_news(candidates, now=now, max_items=_AI_POOL)
        unscored = [story for story in fresh if story.id not in self._news_scores]
        if unscored and (self._score_retry_at is None or now >= self._score_retry_at):
            # Only stories not seen before cost a request; a failed call waits before retrying.
            topics = [topic for _, topic in self._news_scores.values() if topic]
            scores = self._scorer(unscored, topics)
            self._news_scores.update(scores)
            self._score_retry_at = None if scores else now + timedelta(minutes=30)
            kept = {story.id for story in fresh}
            self._news_scores = {k: v for k, v in self._news_scores.items() if k in kept}
            if scores:
                _save_scores(self._scores_path, self._news_scores)
        scored = [story for story in fresh if story.id in self._news_scores]
        if not scored:
            return None
        scored.sort(
            key=lambda story: (-self._news_scores[story.id][0], -story.published_at.timestamp())
        )
        # One story per event: the best-scored, most recent one speaks for its topic.
        distinct: list[NewsItem] = []
        seen_topics: set[str] = set()
        for story in scored:
            topic = self._news_scores[story.id][1]
            if topic and topic in seen_topics:
                continue
            seen_topics.add(topic)
            distinct.append(story)
        threshold = self.settings.ai_news_min_score
        return [s for s in distinct if self._news_scores[s.id][0] >= threshold] or distinct[:1]

    def source_status(self, now: datetime) -> list[SourceStatus]:
        current = _aware(now)
        rows = {row["id"]: row for row in self.source_cache.records()}
        result: list[SourceStatus] = []
        for source_id, kind in self._kinds.items():
            row = rows.get(source_id)
            if row is None:
                continue
            last_attempt = _parse_time(row["last_attempt_at"])
            last_success = _parse_time(row["last_success_at"])
            polling = self._poll_minutes(kind)
            stale = (
                last_success is None
                or current - last_success > timedelta(minutes=polling * 2)
                or row["last_error"] is not None
                or row["data"] is None
            )
            data = row["data"]
            if kind == "weather" and isinstance(data, dict):
                try:
                    snapshot = WeatherSnapshot.model_validate(data["snapshot"])
                    zone = ZoneInfo(self.settings.timezone)
                    observed_date = snapshot.observed_at.astimezone(zone).date()
                    if observed_date < current.astimezone(zone).date():
                        stale = True
                    if current - snapshot.observed_at > timedelta(hours=2):
                        stale = True
                except (KeyError, TypeError, ValueError):
                    stale = True
            item_count = 0
            if isinstance(data, dict):
                values = data.get("items") if kind == "rss" else data.get("events")
                if isinstance(values, list):
                    item_count = len(values)
                elif kind == "weather" and isinstance(data.get("snapshot"), dict):
                    item_count = 1
            result.append(
                SourceStatus(
                    id=source_id,
                    kind=kind,
                    last_attempt_at=last_attempt,
                    last_success_at=last_success,
                    stale=stale,
                    last_error=row["last_error"],
                    item_count=item_count,
                )
            )
        return result

    def _refresh(self, source_id: str, kind: SourceKind, now: datetime) -> None:
        fetching = True
        try:
            local_file = self._files.get(source_id)
            payload = (
                self.fetcher(self._urls[source_id])
                if local_file is None
                else _read_calendar_file(local_file)
            )
            if not isinstance(payload, bytes):
                raise TypeError("fetcher returned a non-bytes response")
            fetching = False
            data: dict[str, Any]
            if kind == "calendar":
                calendar_feed = self._feed(source_id, CalendarFeed)
                zone = ZoneInfo(self.settings.timezone)
                local_today = now.astimezone(zone).date()
                start = datetime.combine(local_today, time.min, zone)
                end = datetime.combine(
                    local_today + timedelta(days=self.settings.calendar_days), time.min, zone
                )
                events = parse_ics(
                    payload,
                    source_id=source_id,
                    timezone=self.settings.timezone,
                    window_start=start,
                    window_end=end,
                    person=calendar_feed.person,
                )
                data = {"events": [event.model_dump(mode="json") for event in events]}
            elif kind == "rss":
                rss_feed = self._feed(source_id, RSSFeed)
                news = parse_rss(
                    payload,
                    source_id=source_id,
                    category=rss_feed.category,
                    now=now,
                )
                data = {"items": [item.model_dump(mode="json") for item in news]}
            elif kind == "events":
                found = parse_events(payload, source_id=source_id, timezone=self.settings.timezone)
                data = {"events": [event.model_dump(mode="json") for event in found]}
            else:
                snapshot = parse_weather(
                    payload, timezone=self.settings.timezone, language=self.settings.language
                )
                data = {"snapshot": snapshot.model_dump(mode="json")}
            self.source_cache.success(source_id, data, now)
        except Exception as error:  # noqa: BLE001 — never publish provider/parser exception text.
            if isinstance(error, FetchError):
                code = error.code
            elif fetching and isinstance(error, TimeoutError):
                code = "timeout"
            elif fetching and isinstance(error, OSError):
                code = "http_error"
            else:
                code = "invalid_payload"
            self.source_cache.failure(source_id, cast(str, code), now)

    def _due(self, row: dict[str, Any], kind: SourceKind, now: datetime) -> bool:
        last_attempt = _parse_time(row["last_attempt_at"])
        if row["last_error"] == "invalid_cache" or last_attempt is None:
            return True
        if kind in ("calendar", "weather"):
            zone = ZoneInfo(self.settings.timezone)
            if last_attempt.astimezone(zone).date() != now.astimezone(zone).date():
                return True
        return now - last_attempt >= timedelta(minutes=self._poll_minutes(kind))

    def _poll_minutes(self, kind: SourceKind) -> int:
        return {
            "calendar": self.settings.calendar_poll_minutes,
            "rss": self.settings.rss_poll_minutes,
            "weather": self.settings.weather_poll_minutes,
            "events": self.settings.events_poll_minutes,
        }[kind]

    def _feed_label(self, source_id: str) -> str:
        feed = self._feeds[source_id]
        return feed.label if feed is not None else ""

    def _feed(self, source_id: str, expected: type[_Feed]):
        feed = self._feeds[source_id]
        if not isinstance(feed, expected):
            raise TypeError("source configuration does not match its kind")
        return feed


def _calendar_files(directory: str | None) -> list[Path]:
    """Local .ics files, in name order; a missing or unreadable folder means none."""
    if not directory:
        return []
    try:
        found = sorted(
            path
            for path in Path(directory).iterdir()
            if path.is_file() and path.suffix.lower() == ".ics"
        )
    except OSError:
        return []
    return found[:_MAX_CALENDAR_FILES]


def _file_source_id(path: Path) -> str:
    plain = unicodedata.normalize("NFKD", path.stem).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", plain).strip("-").lower()
    return f"file-{slug or 'calendar'}"[:64]


def _calendar_file_label(path: Path) -> str:
    """Prefer the calendar's own name; fall back to the file name."""
    try:
        match = _CALENDAR_NAME.search(_read_calendar_file(path))
    except (OSError, ValueError):
        match = None
    name = match.group(1).decode("utf-8", "ignore").strip() if match else ""
    return (name or path.stem)[:80]


def _read_calendar_file(path: Path) -> bytes:
    if path.stat().st_size > _MAX_CALENDAR_FILE_BYTES:
        raise ValueError("calendar file is too large")
    return path.read_bytes()


def _nearby_items(
    nearby: list[tuple[NearbyEvent, float]], local: datetime, language: Language = "pt"
) -> list[DisplayItem]:
    """Upcoming public events from now until the end of this week's Sunday."""
    week_end = datetime.combine(
        local.date() + timedelta(days=7 - local.weekday()), time.min, local.tzinfo
    )
    items: dict[str, DisplayItem] = {}
    for event, distance in sorted(nearby, key=lambda pair: (pair[0].starts_at, pair[0].id)):
        start = event.starts_at.astimezone(local.tzinfo)
        if start >= week_end or event.url in items:
            continue
        if event.all_day:
            last_day = (event.ends_at or event.starts_at).astimezone(local.tzinfo).date()
            if last_day < local.date():
                continue
        elif (event.ends_at or start + timedelta(hours=2)) <= local:
            continue
        items[event.url] = DisplayItem(
            id=f"event:{event.id}",
            kind="local_event",
            title=event.title,
            summary=event.venue,
            # Above the curiosity and the photo, below family commitments.
            priority=2,
            occurred_at=event.starts_at,
            ends_at=event.ends_at,
            all_day=event.all_day,
            source=data_text("events", language),
            url=event.url,
            distance_km=distance,
        )
    return list(items.values())


def _photo_of_the_day(directory: str | None, day: date) -> Path | None:
    if not directory or not Path(directory).is_dir():
        return None
    photos = sorted(
        path
        for path in Path(directory).iterdir()
        if path.is_file()
        and path.suffix.lower() in (".jpg", ".jpeg", ".png")
        and not path.name.startswith(".")
    )
    return photos[day.toordinal() % len(photos)] if photos else None


def _photo_caption(path: Path, language: Language = "pt") -> str:
    """Use a descriptive file name as the caption; camera names like IMG_1234 are not."""
    text = re.sub(r"[_\-]+", " ", path.stem).strip()
    if not text or re.fullmatch(r"(?i)(img|dsc|dscn|pxl|photo|p)?[\s\d]*", text):
        return data_text("photo.default", language)
    return text[:160]


def _fingerprint(value: dict[str, Any]) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value


def _parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _event_item(event: Event, label: str) -> DisplayItem:
    return DisplayItem(
        id=event.id,
        kind="calendar",
        title=event.title,
        summary=event.summary,
        occurred_at=event.starts_at,
        ends_at=event.ends_at,
        all_day=event.all_day,
        person=event.person,
        source=label or event.source,
        is_protected=event.is_protected,
    )


def _overlaps_window(event: Event, start: datetime, end: datetime) -> bool:
    if event.starts_at >= end:
        return False
    if event.ends_at is not None:
        return event.ends_at > start
    return event.starts_at >= start


def _weather_items(
    snapshot: WeatherSnapshot, settings: Settings, now: datetime
) -> list[DisplayItem]:
    language = settings.language
    zone = ZoneInfo(snapshot.timezone)
    observed_local = snapshot.observed_at.astimezone(zone)
    today = observed_local.date()
    tomorrow = today + timedelta(days=1)
    current = snapshot.current
    today_data = snapshot.today
    tomorrow_data = snapshot.tomorrow
    fields = [
        (
            f"{data_text('observation', language)} {observed_local:%Y-%m-%d %H:%M} {current.summary or '—'} "
            f"{_number(current.temperature_c)}°C {data_text('wind', language).lower()} {_number(current.wind_kph)}km/h"
        ),
        _weather_day(today, today_data, language),
        _weather_day(tomorrow, tomorrow_data, language),
    ]
    if snapshot.sunrise is not None:
        fields.append(f"{data_text('sunrise', language)} {snapshot.sunrise.astimezone(zone):%H:%M}")
    if snapshot.sunset is not None:
        fields.append(f"{data_text('sunset', language)} {snapshot.sunset.astimezone(zone):%H:%M}")
    # The full measurements remain in context.weather and the protected alert facts.
    summary = "; ".join(fields)
    if len(summary) > 280:
        summary = summary[:279].rstrip() + "…"
    items = [
        DisplayItem(
            id="weather:home",
            kind="weather",
            title=settings.weather_location or data_text("weather", language),
            summary=summary,
            occurred_at=snapshot.observed_at,
            source=snapshot.source,
        )
    ]
    now_local_date = now.astimezone(zone).date()
    for forecast_day, period in ((today, today_data), (tomorrow, tomorrow_data)):
        if forecast_day < now_local_date:
            continue
        day_label = _day_label(forecast_day, now_local_date, language)
        facts = [DisplayFact(label=data_text("day", language), value=day_label)]
        causes: list[str] = []
        if (
            settings.weather_rain_disruption_mm is not None
            and period.rain_mm is not None
            and period.rain_mm >= settings.weather_rain_disruption_mm
        ):
            causes.append("rain")
            facts.append(
                DisplayFact(
                    label=data_text("rain", language),
                    value=f"{format_number(period.rain_mm, language)} mm",
                )
            )
        if (
            settings.weather_wind_disruption_kph is not None
            and period.wind_kph is not None
            and period.wind_kph >= settings.weather_wind_disruption_kph
        ):
            causes.append("wind")
            facts.append(
                DisplayFact(
                    label=data_text("wind", language),
                    value=f"{format_number(period.wind_kph, language)} km/h",
                )
            )
        if causes:
            window = _alert_window(
                snapshot,
                forecast_day,
                None if "rain" in causes else settings.weather_wind_disruption_kph,
            )
            if window is not None:
                # With hourly data the page says when, as in the design: from, until, how much.
                amounts = " · ".join(fact.value for fact in facts[1:])
                facts = [
                    DisplayFact(label=data_text("from", language), value=window[0]),
                    DisplayFact(label=data_text("until", language), value=window[1]),
                    DisplayFact(label=data_text("forecast", language), value=amounts[:40]),
                ]
            items.append(
                DisplayItem(
                    id=f"weather-alert:{forecast_day.isoformat()}",
                    kind="alert",
                    title=data_text(
                        "alert.both" if len(causes) > 1 else f"alert.{causes[0]}", language
                    ),
                    summary=data_text("alert.description", language),
                    label=data_text("alert.label", language, day=day_label.lower()),
                    facts=facts,
                    occurred_at=datetime.combine(forecast_day, time.min, zone),
                    source=snapshot.source,
                    is_protected=True,
                    severity="disruption",
                )
            )
    return items


def _alert_window(
    snapshot: WeatherSnapshot, day: date, wind_threshold: float | None
) -> tuple[str, str] | None:
    """First and last hour of meaningful rain (or of wind over the threshold) on `day`."""
    zone = ZoneInfo(snapshot.timezone)
    hours = []
    for hour in snapshot.hourly:
        local = hour.at.astimezone(zone)
        if local.date() != day:
            continue
        if wind_threshold is None:
            active = hour.rain_mm is not None and hour.rain_mm >= 1.0
        else:
            active = hour.wind_kph is not None and hour.wind_kph >= wind_threshold
        if active:
            hours.append(local)
    if not hours:
        return None
    return f"{hours[0]:%H:%M}", f"{hours[-1] + timedelta(hours=1):%H:%M}"


def _day_label(day: date, today: date, language: Language = "pt") -> str:
    offset = (day - today).days
    if offset in (0, 1):
        return data_text(("today", "tomorrow")[offset], language)
    return f"{day.day:02}/{day.month:02}"


def _weather_day(day: date, period: Any, language: Language = "pt") -> str:
    parts = [day.isoformat()]
    if period.summary:
        parts.append(period.summary)
    if period.temperature_min_c is not None or period.temperature_max_c is not None:
        parts.append(f"{_number(period.temperature_min_c)}–{_number(period.temperature_max_c)}°C")
    if period.rain_mm is not None:
        parts.append(
            f"{data_text('rain', language).lower()} {format_number(period.rain_mm, language)}mm"
        )
    if period.rain_probability_pct is not None:
        parts.append(f"{period.rain_probability_pct}%")
    if period.wind_kph is not None:
        parts.append(
            f"{data_text('wind', language).lower()} {format_number(period.wind_kph, language)}km/h"
        )
    return " ".join(parts)


def _number(value: float | None) -> str:
    return "—" if value is None else f"{value:g}"


def _eligible_news(news: list[NewsItem], feed: RSSFeed) -> list[NewsItem]:
    if feed.category in ("national", "portugal") or feed.curated:
        return news
    keywords = [keyword.casefold() for keyword in feed.keywords]
    if not keywords:
        return []
    return [
        item
        for item in news
        if any(keyword in f"{item.title} {item.summary or ''}".casefold() for keyword in keywords)
    ]


def _load_scores(path: Path) -> dict[str, NewsScore]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {
            str(key): (int(value[0]), str(value[1]))
            for key, value in raw.items()
            if isinstance(value, list) and len(value) == 2 and 0 <= int(value[0]) <= 10
        }
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def _save_scores(path: Path, scores: dict[str, NewsScore]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(scores, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        pass  # Losing the cache only costs one extra scoring request after a restart.


def _news_title(title: str) -> str:
    """Drop live-blog time prefixes such as "7h. " or "14h30. " from a headline."""
    return _LIVE_PREFIX.sub("", title, count=1) or title


def _news_item(
    item: NewsItem, feed: RSSFeed, language: Language = "pt", country: Country = "PT"
) -> DisplayItem:
    category = (
        "country.PT"
        if item.category == "portugal"
        else (f"country.{country}" if item.category == "national" else "world")
    )
    return DisplayItem(
        id=item.id,
        kind="news",
        title=_news_title(item.title),
        summary=item.summary,
        occurred_at=item.published_at,
        source=feed.label,
        label=f"{data_text(category, language)} · {feed.label}"[:80],
        url=item.url if item.url and len(item.url) <= 2000 else None,
    )
