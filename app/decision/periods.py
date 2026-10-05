"""Local "HH:MM-HH:MM" periods, which may run past midnight."""

from datetime import time


def parse_period(value: str) -> tuple[time, time]:
    try:
        start_text, end_text = value.split("-")
        start, end = time.fromisoformat(start_text.strip()), time.fromisoformat(end_text.strip())
    except ValueError as exc:
        raise ValueError("periods must look like 21:30-06:30") from exc
    if start == end:
        raise ValueError("periods must not start and end at the same time")
    return start, end


def in_period(value: str, moment: time) -> bool:
    start, end = parse_period(value)
    if start < end:
        return start <= moment < end
    return moment >= start or moment < end
