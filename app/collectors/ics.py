"""Pure, bounded conversion from iCalendar feeds to normalized calendar Events."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from hashlib import sha256
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from icalendar import Calendar  # type: ignore[import-untyped]
from recurring_ical_events import of  # type: ignore[import-untyped]

from app.contracts import Event

_MAX_COMPONENTS = 512
_MAX_EVENTS = 256
_MAX_RRULE_COUNT = 10_000
_MAX_HOURLY_RRULE_COUNT = 1_000
_ALLOWED_FREQUENCIES = {"HOURLY", "DAILY", "WEEKLY", "MONTHLY", "YEARLY"}


def parse_ics(
    payload: bytes,
    *,
    source_id: str,
    timezone: str,
    window_start: datetime,
    window_end: datetime,
    person: str | None = None,
    max_events: int = 256,
) -> list[Event]:
    """Parse one ICS byte payload without network or persistence side effects.

    Recurrences are limited to hourly, daily, weekly, monthly, and yearly rules.
    SECONDLY/MINUTELY rules, BYSECOND/BYMINUTE, and multi-value BYHOUR
    expansion are rejected.
    Hourly rules require COUNT <= 1,000, even if UNTIL is present, to bound
    recurrence expansion independently of the requested date window. Other
    COUNT values above 10,000 are rejected. Event intervals must have a
    positive end and may use DTEND or DURATION, but not both.
    The expanded result is capped at ``max_events`` (at most 256).
    """
    if not isinstance(payload, bytes) or not payload:
        raise ValueError("invalid iCalendar feed")
    if not source_id.strip():
        raise ValueError("source_id must not be empty")
    if not 1 <= max_events <= _MAX_EVENTS:
        raise ValueError(f"max_events must be between 1 and {_MAX_EVENTS}")
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone must be a valid IANA timezone") from exc
    _validate_window(window_start, window_end)
    start = window_start.astimezone(zone)
    end = window_end.astimezone(zone)

    try:
        calendar = Calendar.from_ical(payload)
        if calendar.name != "VCALENDAR":
            raise ValueError
        components = calendar.walk()
        if len(components) > _MAX_COMPONENTS:
            raise ValueError("component limit exceeded")
        events = [component for component in components if component.name == "VEVENT"]
        selected = _latest_revisions(events, zone)
        for component in selected:
            _validate_event(component, max_events, zone)
        calendar.subcomponents = [
            component for component in calendar.subcomponents if component.name != "VEVENT"
        ] + selected

        query = of(calendar, keep_recurrence_attributes=True, skip_bad_series=False)
        page = next(
            iter(query.paginate(max_events + 1, earliest_end=start, latest_start=end)),
            None,
        )
        occurrences = page.components if page is not None else []
        normalized: dict[str, tuple[tuple[int, str], Event]] = {}
        for component in occurrences:
            if _status(component) == "CANCELLED":
                continue
            event, revision = _normalize_component(component, source_id, zone, person)
            previous = normalized.get(event.id)
            if previous is None or revision > previous[0]:
                normalized[event.id] = (revision, event)
        if len(normalized) > max_events or len(occurrences) > max_events:
            raise ValueError("max_events expansion limit exceeded")
        return sorted(
            (value[1] for value in normalized.values()),
            key=lambda event: (event.starts_at, event.id),
        )
    except ValueError as exc:
        if str(exc) == "component limit exceeded" or str(exc).startswith(
            ("unsupported recurrence", "max_events expansion")
        ):
            raise
        raise ValueError("invalid iCalendar feed") from None
    except Exception:  # noqa: BLE001 — parser errors may include private calendar content.
        # Do not surface third-party parser details that can contain calendar data.
        raise ValueError("invalid iCalendar feed") from None


def _validate_window(start: datetime, end: datetime) -> None:
    if start.tzinfo is None or start.utcoffset() is None:
        raise ValueError("window_start must be timezone-aware")
    if end.tzinfo is None or end.utcoffset() is None:
        raise ValueError("window_end must be timezone-aware")
    if start >= end:
        raise ValueError("window_start must be before window_end")


def _latest_revisions(events: list[Any], zone: tzinfo) -> list[Any]:
    latest: dict[tuple[str, str], tuple[tuple[int, str], Any]] = {}
    for component in events:
        uid_property = component.get("UID")
        if uid_property is None:
            raise ValueError("VEVENT has no UID")
        uid = str(uid_property).strip()
        if not uid:
            raise ValueError("VEVENT has no UID")
        recurrence = component.get("RECURRENCE-ID")
        recurrence_key = _identity_time(recurrence.dt, zone) if recurrence is not None else "master"
        key = (uid, recurrence_key)
        revision = _revision_key(component, zone)
        if key not in latest or revision > latest[key][0]:
            latest[key] = (revision, component)
    return [entry[1] for entry in latest.values()]


def _revision_key(component: Any, zone: tzinfo) -> tuple[int, str]:
    try:
        sequence = int(component.get("SEQUENCE", 0))
    except (TypeError, ValueError):
        raise ValueError("VEVENT has invalid revision") from None
    dtstamp = component.get("DTSTAMP")
    stamp = _identity_time(dtstamp.dt, zone) if dtstamp is not None else ""
    return sequence, stamp


def _validate_event(component: Any, max_events: int, zone: tzinfo) -> None:
    status = _status(component)
    if status and status not in {"CONFIRMED", "TENTATIVE", "CANCELLED"}:
        raise ValueError("VEVENT has invalid status")
    start_property = component.get("DTSTART")
    if start_property is None:
        raise ValueError("VEVENT has no DTSTART")
    raw_start = start_property.dt
    end_property = component.get("DTEND")
    duration = component.get("DURATION")
    if end_property is not None and duration is not None:
        raise ValueError("VEVENT has both DTEND and DURATION")
    if end_property is not None:
        raw_end = end_property.dt
        if isinstance(raw_start, datetime) != isinstance(raw_end, datetime):
            raise ValueError("VEVENT has mismatched DTSTART and DTEND types")
        if _to_aware(raw_end, zone) <= _to_aware(raw_start, zone):
            raise ValueError("VEVENT end must be after DTSTART")
    if duration is not None and duration.dt <= timedelta(0):
        raise ValueError("VEVENT DURATION must be positive")
    rule = component.get("RRULE")
    if rule is not None:
        values = {key.upper(): _rule_values(value) for key, value in rule.items()}
        frequency = (values.get("FREQ") or [""])[0].upper()
        if frequency in {"SECONDLY", "MINUTELY"}:
            raise ValueError("unsupported recurrence density")
        if frequency not in _ALLOWED_FREQUENCIES:
            raise ValueError("unsupported recurrence frequency")
        if values.get("BYSECOND") or values.get("BYMINUTE"):
            raise ValueError("unsupported recurrence density")
        counts = values.get("COUNT", [])
        try:
            count_values = [int(value) for value in counts]
        except (TypeError, ValueError):
            raise ValueError("unsupported recurrence count") from None
        if any(value < 1 or value > _MAX_RRULE_COUNT for value in count_values):
            raise ValueError("unsupported recurrence count")
        if frequency == "HOURLY" and (
            len(count_values) != 1 or count_values[0] > _MAX_HOURLY_RRULE_COUNT
        ):
            raise ValueError("unsupported recurrence density")
        by_hours = values.get("BYHOUR", [])
        if len(set(by_hours)) > 1 or len(by_hours) > max_events:
            raise ValueError("unsupported recurrence density")


def _rule_values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]


def _status(component: Any) -> str:
    return str(component.get("STATUS", "")).strip().upper()


def _normalize_component(
    component: Any,
    source_id: str,
    zone: tzinfo,
    person: str | None,
) -> tuple[Event, tuple[int, str]]:
    uid = str(component.get("UID", "")).strip()
    start_property = component.get("DTSTART")
    if start_property is None:
        raise ValueError("VEVENT has no DTSTART")
    raw_start = start_property.dt
    all_day = isinstance(raw_start, date) and not isinstance(raw_start, datetime)
    starts_at = _to_aware(raw_start, zone)
    raw_end = _component_end(component, raw_start, all_day)
    ends_at = _to_aware(raw_end, zone) if raw_end is not None else None
    title = _plain_text(component.get("SUMMARY"), 160) or "Untitled event"
    summary = _plain_text(component.get("DESCRIPTION"), 280)
    recurrence = component.get("RECURRENCE-ID")
    recurrence_key = _identity_time(recurrence.dt, zone) if recurrence is not None else "master"
    identity = sha256(f"{source_id}\0{uid}\0{recurrence_key}".encode()).hexdigest()
    event = Event(
        id=f"cal-{identity}",
        title=title,
        starts_at=starts_at.astimezone(UTC),
        ends_at=ends_at.astimezone(UTC) if ends_at is not None else None,
        summary=summary,
        person=person,
        source=source_id,
        all_day=all_day,
        is_protected=False,
    )
    return event, _revision_key(component, zone)


def _component_end(
    component: Any, raw_start: date | datetime, all_day: bool
) -> date | datetime | None:
    end_property = component.get("DTEND")
    if end_property is not None:
        return end_property.dt
    duration = component.get("DURATION")
    if duration is not None:
        return raw_start + duration.dt
    if all_day:
        return raw_start + timedelta(days=1)
    return None


def _to_aware(value: date | datetime, zone: tzinfo) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=zone)
    return datetime.combine(value, time.min, tzinfo=zone)


def _identity_time(value: date | datetime, zone: tzinfo) -> str:
    if isinstance(value, datetime):
        return _to_aware(value, zone).astimezone(UTC).isoformat(timespec="seconds")
    return value.isoformat()


def _plain_text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text[:limit] if text else None
