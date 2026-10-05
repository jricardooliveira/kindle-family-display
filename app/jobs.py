"""Single-process refresh scheduler."""

from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore[import-untyped]


def build_scheduler(refresh, timezone: str, refresh_minutes: int) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=timezone)
    scheduler.add_job(
        refresh,
        trigger="interval",
        minutes=refresh_minutes,
        id="refresh-screens",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=max(60, refresh_minutes * 60),
    )
    return scheduler
