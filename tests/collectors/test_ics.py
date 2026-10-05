from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.collectors.ics import parse_ics

FIXTURES = Path(__file__).parents[1] / "fixtures" / "ics"
LISBON = ZoneInfo("Europe/Lisbon")


def parse_fixture(name, start, end, **kwargs):
    source_id = kwargs.pop("source_id", "calendar-fixture")
    return parse_ics(
        (FIXTURES / name).read_bytes(),
        source_id=source_id,
        timezone="Europe/Lisbon",
        window_start=start,
        window_end=end,
        **kwargs,
    )


def test_normalizes_timed_floating_all_day_and_overlapping_events_to_utc():
    events = parse_fixture(
        "basic.ics",
        datetime(2026, 10, 26, 8, tzinfo=UTC),
        datetime(2026, 10, 30, 0, tzinfo=UTC),
        person="Alex",
    )
    by_title = {event.title: event for event in events}

    assert set(by_title) == {"Timed Lisbon", "Floating Lisbon", "Two-day trip", "Overnight"}
    timed = by_title["Timed Lisbon"]
    assert timed.starts_at == datetime(2026, 10, 26, 9, tzinfo=LISBON).astimezone(UTC)
    assert timed.person == "Alex"
    assert timed.source == "calendar-fixture"
    assert timed.summary == "Bring the printed map"
    floating = by_title["Floating Lisbon"]
    assert floating.starts_at == datetime(2026, 10, 28, 12, tzinfo=LISBON).astimezone(UTC)
    all_day = by_title["Two-day trip"]
    assert all_day.all_day is True
    assert all_day.starts_at.astimezone(LISBON).date() == date(2026, 10, 27)
    assert all_day.ends_at.astimezone(LISBON).date() == date(2026, 10, 29)
    assert all_day.starts_at.utcoffset().total_seconds() == 0
    assert by_title["Overnight"].starts_at < datetime(2026, 10, 26, 8, tzinfo=UTC)


def test_recurring_instances_honor_exdate_rdate_moved_and_cancelled_override():
    events = parse_fixture(
        "recurring.ics",
        datetime(2026, 10, 26, tzinfo=UTC),
        datetime(2026, 11, 10, tzinfo=UTC),
    )
    series = [event for event in events if event.title.startswith("Weekly")]

    assert len(series) == 2
    assert len({event.id for event in series}) == 2
    assert all(event.id.startswith("cal-") for event in series)
    starts = {event.starts_at for event in series}
    assert datetime(2026, 11, 3, 11, tzinfo=LISBON).astimezone(UTC) in starts
    assert datetime(2026, 11, 3, 9, tzinfo=LISBON).astimezone(UTC) in starts
    assert datetime(2026, 10, 29, 9, tzinfo=LISBON).astimezone(UTC) not in starts
    assert datetime(2026, 11, 5, 9, tzinfo=LISBON).astimezone(UTC) not in starts
    assert datetime(2026, 11, 12, 10, tzinfo=LISBON).astimezone(UTC) not in starts
    assert len(
        parse_fixture(
            "recurring.ics",
            datetime(2026, 10, 26, tzinfo=UTC),
            datetime(2026, 11, 10, tzinfo=UTC),
        )
    ) == len(events)


def test_identifiers_are_stable_for_source_uid_and_original_recurrence_id():
    start = datetime(2026, 10, 26, tzinfo=UTC)
    end = datetime(2026, 11, 10, tzinfo=UTC)
    first = parse_fixture("recurring.ics", start, end, source_id="feed-a")
    second = parse_fixture("recurring.ics", start, end, source_id="feed-a")
    other_source = parse_fixture("recurring.ics", start, end, source_id="feed-b")

    moved = next(event for event in first if event.title == "Weekly moved")
    other_moved = next(event for event in other_source if event.title == "Weekly moved")
    assert moved.id == next(event.id for event in second if event.title == "Weekly moved")
    assert moved.id != other_moved.id
    identity = "2026-11-05T09:00:00+00:00"
    expected = sha256(f"feed-a\0weekly-series\0{identity}".encode()).hexdigest()
    assert moved.id == f"cal-{expected}"


def test_cancelled_series_and_cancelled_standalone_events_are_omitted():
    events = parse_fixture(
        "cancelled.ics",
        datetime(2026, 10, 26, tzinfo=UTC),
        datetime(2026, 11, 10, tzinfo=UTC),
    )

    assert events == []


def test_latest_sequence_then_dtstamp_wins_duplicate_uid_revisions():
    events = parse_fixture(
        "revisions.ics",
        datetime(2026, 10, 26, tzinfo=UTC),
        datetime(2026, 10, 30, tzinfo=UTC),
    )

    assert len(events) == 1
    assert events[0].title == "Newest by DTSTAMP"
    assert events[0].starts_at == datetime(2026, 10, 27, 15, tzinfo=LISBON).astimezone(UTC)


def test_valid_empty_calendar_is_distinct_from_invalid_calendar():
    assert (
        parse_fixture(
            "empty.ics",
            datetime(2026, 10, 26, tzinfo=UTC),
            datetime(2026, 10, 30, tzinfo=UTC),
        )
        == []
    )
    with pytest.raises(ValueError):
        parse_fixture(
            "invalid.ics",
            datetime(2026, 10, 26, tzinfo=UTC),
            datetime(2026, 10, 30, tzinfo=UTC),
        )


def test_invalid_vevent_fails_the_entire_calendar_instead_of_skipping_it():
    with pytest.raises(ValueError, match="invalid iCalendar feed"):
        parse_fixture(
            "invalid-component.ics",
            datetime(2026, 10, 26, tzinfo=UTC),
            datetime(2026, 10, 30, tzinfo=UTC),
        )


def test_all_day_exclusive_end_keeps_local_dates_across_dst_change():
    event = parse_fixture(
        "dst-all-day.ics",
        datetime(2026, 3, 27, tzinfo=UTC),
        datetime(2026, 3, 31, tzinfo=UTC),
    )[0]

    assert event.all_day
    assert event.starts_at.astimezone(LISBON).date() == date(2026, 3, 28)
    assert event.ends_at.astimezone(LISBON).date() == date(2026, 3, 30)
    assert (event.ends_at - event.starts_at).total_seconds() == 47 * 60 * 60


def test_rejects_component_and_expansion_limits_without_truncating():
    events = parse_fixture(
        "revisions.ics",
        datetime(2026, 10, 26, tzinfo=UTC),
        datetime(2026, 10, 30, tzinfo=UTC),
        max_events=1,
    )
    assert events

    with pytest.raises(ValueError, match="max_events"):
        parse_fixture(
            "basic.ics",
            datetime(2026, 10, 26, tzinfo=UTC),
            datetime(2026, 10, 30, tzinfo=UTC),
            max_events=1,
        )
    with pytest.raises(ValueError, match="component limit"):
        parse_ics(
            make_calendar(513),
            source_id="large-fixture",
            timezone="Europe/Lisbon",
            window_start=datetime(2026, 10, 26, tzinfo=UTC),
            window_end=datetime(2026, 10, 30, tzinfo=UTC),
        )


def test_rejects_unsafe_recurrence_density_and_invalid_ranges():
    with pytest.raises(ValueError, match="unsupported recurrence density"):
        parse_fixture(
            "dense.ics",
            datetime(2026, 10, 26, tzinfo=UTC),
            datetime(2026, 10, 30, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_ics(
            (FIXTURES / "empty.ics").read_bytes(),
            source_id="feed",
            timezone="Europe/Lisbon",
            window_start=datetime(2026, 10, 26),  # noqa: DTZ001
            window_end=datetime(2026, 10, 30, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="window_start must be before window_end"):
        parse_ics(
            (FIXTURES / "empty.ics").read_bytes(),
            source_id="feed",
            timezone="Europe/Lisbon",
            window_start=datetime(2026, 10, 30, tzinfo=UTC),
            window_end=datetime(2026, 10, 26, tzinfo=UTC),
        )


def test_rejects_hourly_until_series_without_small_count():
    payload = make_single_event(
        "DTSTART:19000101T000000Z",
        "DTEND:19000101T003000Z",
        "RRULE:FREQ=HOURLY;UNTIL=20991231T235959Z",
    )

    with pytest.raises(ValueError, match="unsupported recurrence density"):
        parse_ics(
            payload,
            source_id="bounded-hourly",
            timezone="Europe/Lisbon",
            window_start=datetime(1900, 1, 1, tzinfo=UTC),
            window_end=datetime(2099, 12, 31, tzinfo=UTC),
        )


def test_hourly_count_limit_applies_even_when_until_is_present():
    payload = make_single_event(
        "DTSTART:20261027T100000Z",
        "DTEND:20261027T103000Z",
        "RRULE:FREQ=HOURLY;COUNT=1001;UNTIL=20991231T235959Z",
    )

    with pytest.raises(ValueError, match="unsupported recurrence density"):
        parse_ics(
            payload,
            source_id="bounded-hourly",
            timezone="Europe/Lisbon",
            window_start=datetime(2026, 10, 27, tzinfo=UTC),
            window_end=datetime(2026, 10, 28, tzinfo=UTC),
        )


def test_rejects_daily_series_with_dense_byhour_expansion():
    payload = make_single_event(
        "DTSTART:19000101T000000Z",
        "DTEND:19000101T003000Z",
        "RRULE:FREQ=DAILY;BYHOUR=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23;UNTIL=20991231T235959Z",
    )

    with pytest.raises(ValueError, match="unsupported recurrence density"):
        parse_ics(
            payload,
            source_id="dense-daily",
            timezone="Europe/Lisbon",
            window_start=datetime(1900, 1, 1, tzinfo=UTC),
            window_end=datetime(2099, 12, 31, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    "fields",
    [
        ("DTEND:20261027T090000Z",),
        ("DURATION:-PT1H",),
        ("DTEND:20261027T120000Z", "DURATION:PT1H"),
    ],
)
def test_rejects_invalid_event_intervals_before_expansion(fields):
    payload = make_single_event("DTSTART:20261027T100000Z", *fields)

    with pytest.raises(ValueError, match="invalid iCalendar feed"):
        parse_ics(
            payload,
            source_id="invalid-interval",
            timezone="Europe/Lisbon",
            window_start=datetime(2026, 10, 26, tzinfo=UTC),
            window_end=datetime(2026, 10, 30, tzinfo=UTC),
        )


def make_single_event(*fields: str) -> bytes:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "BEGIN:VEVENT",
        "UID:single-test-event",
        *fields,
        "SUMMARY:Test event",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return ("\r\n".join(lines) + "\r\n").encode()


def make_calendar(count: int) -> bytes:
    events = [
        "BEGIN:VEVENT",
        "UID:event-0",
        "DTSTART:20261027T100000Z",
        "SUMMARY:Event 0",
        "END:VEVENT",
    ]
    for index in range(1, count):
        events.extend(
            [
                "BEGIN:VEVENT",
                f"UID:event-{index}",
                "DTSTART:20261027T100000Z",
                f"SUMMARY:Event {index}",
                "END:VEVENT",
            ]
        )
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n" + "\r\n".join(events) + "\r\nEND:VCALENDAR\r\n"
    ).encode()
