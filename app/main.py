"""FastAPI lifecycle, serial refresh job, and cached image routes."""

import hashlib
import json
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from threading import Lock
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

from app.collectors.http import fetch_bytes
from app.collectors.pipeline import DataPipeline
from app.config import Settings, load_settings
from app.contracts.models import Screen, ScreenStatus, Status
from app.decision.rules import select_items
from app.jobs import build_scheduler
from app.rendering import demo_context, render
from app.storage.cache import ScreenCache
from app.storage.sources import SourceCache

# Pages in the order a tap on the Kindle walks through them.
SCREENS: tuple[Screen, ...] = ("news-weather", "news", "family", "calendar", "nearby", "photo")
# Seconds the Kindle waits before fetching the next page by itself.
TRMNL_SCREEN_SECONDS = 300


def _now(timezone_name: str, supplied: datetime | None) -> datetime:
    result = supplied or datetime.now(ZoneInfo(timezone_name))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("refresh time must include a timezone")
    return result


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds")


def _output_dimensions(settings: Settings) -> tuple[int, int]:
    if settings.screen_rotation in (90, 270):
        return settings.screen_height, settings.screen_width
    return settings.screen_width, settings.screen_height


def create_app(
    config: Settings | None = None, *, fetcher: Callable[[str], bytes] = fetch_bytes
) -> FastAPI:
    settings = config or load_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        cache = ScreenCache(settings.database_url, settings.cache_dir)
        signature_data = settings.model_dump(mode="json")
        for key in ("calendar_feeds", "rss_feeds", "event_feeds"):
            for value, feed in zip(signature_data[key], getattr(settings, key), strict=True):
                value["url"] = feed.url.get_secret_value()
        signature = hashlib.sha256(json.dumps(signature_data, sort_keys=True).encode()).hexdigest()
        cache.configure(signature)
        cache.cleanup_orphans()
        source_cache = SourceCache(settings.database_url)
        pipeline = (
            None if settings.demo_mode else DataPipeline(settings, source_cache, fetcher=fetcher)
        )
        application.state.data_pipeline = pipeline
        refresh_lock = Lock()
        output_width, output_height = _output_dimensions(settings)

        def refresh(now: datetime | None = None, screens: tuple[Screen, ...] = SCREENS) -> None:
            refresh_time = _now(settings.timezone, now)
            with refresh_lock:
                try:
                    context = (
                        demo_context(refresh_time, settings.timezone)
                        if pipeline is None
                        else pipeline.collect(refresh_time)
                    )
                except Exception:  # noqa: BLE001 — a failed demo context must not stop startup.
                    for screen in screens:
                        cache.record_failure(screen, output_width, output_height)
                    return
                family_first = next(
                    (
                        item.kind
                        for item_id in select_items(context, "family").item_ids
                        for item in context.items
                        if item.id == item_id
                    ),
                    None,
                )
                kinds = [item.kind for item in context.items]
                # Pages with nothing of their own, or repeating another page, are skipped.
                has_content: dict[Screen, bool] = {
                    "news-weather": True,
                    "news": kinds.count("news") >= 2 and not context.news_digest,
                    "family": True,
                    "calendar": "calendar" in kinds,
                    "nearby": "local_event" in kinds and family_first != "local_event",
                    "photo": "photo" in kinds and family_first != "photo",
                }
                for screen in screens:
                    try:
                        decision = select_items(context, screen)
                        application.state.screen_has_content[screen] = has_content[screen]
                        png = render(
                            screen,
                            context,
                            decision,
                            settings.screen_width,
                            settings.screen_height,
                            rotation=settings.screen_rotation,
                        )
                        if not isinstance(png, bytes):
                            raise TypeError("renderer did not return bytes")
                        cache.write(
                            screen,
                            png,
                            _timestamp(refresh_time),
                            output_width,
                            output_height,
                            settings.timezone,
                            settings.screen_rotation,
                        )
                    except Exception:  # noqa: BLE001 — keep the last good image after render errors.
                        cache.record_failure(screen, output_width, output_height)

        application.state.cache = cache
        application.state.refresh = refresh
        application.state.screen_has_content = {}
        application.state.display_position = -1
        try:
            missing_or_mismatched: list[Screen] = []
            for screen in SCREENS:
                cached = cache.read(screen)
                record = cache.record(screen)
                if (
                    cached is None
                    or record is None
                    or record["width"] != output_width
                    or record["height"] != output_height
                    or record["timezone"] != settings.timezone
                    or record["rotation"] != settings.screen_rotation
                ):
                    missing_or_mismatched.append(screen)
            if pipeline is not None:
                refresh()
            elif missing_or_mismatched:
                refresh(screens=tuple(missing_or_mismatched))

            scheduler = build_scheduler(refresh, settings.timezone, settings.refresh_minutes)
            application.state.scheduler = scheduler
            scheduler.start()
            yield
        finally:
            scheduler = getattr(application.state, "scheduler", None)
            if scheduler is not None and scheduler.running:
                scheduler.shutdown(wait=True)  # type: ignore[attr-defined]
            cache.close()
            source_cache.close()

    application = FastAPI(
        title="Kindle Family Dashboard",
        version="0.1.0",
        lifespan=lifespan,
    )

    @application.get("/healthz", include_in_schema=True)
    async def healthz() -> dict[str, bool]:
        return {"ok": True}

    @application.get("/api/status")
    @application.get("/kindle/status.json")
    def status() -> dict[str, Any]:
        cache: ScreenCache = application.state.cache
        current = datetime.now(ZoneInfo(settings.timezone))
        freshness_limit = settings.refresh_minutes * 60
        output_width, output_height = _output_dimensions(settings)
        screen_status: list[ScreenStatus] = []
        stale_sources: list[str] = []
        errors: list[str] = []
        latest: datetime | None = None
        all_available = True
        for screen in SCREENS:
            record = cache.record(screen)
            cached = cache.read(screen)
            present = cached is not None
            all_available = all_available and present
            generated_at = (
                datetime.fromisoformat(record["generated_at"])
                if record and record["generated_at"]
                else None
            )
            if generated_at is not None and (latest is None or generated_at > latest):
                latest = generated_at
            stale = True
            if record:
                stale = (
                    not present
                    or generated_at is None
                    or (current - generated_at).total_seconds() > freshness_limit
                    or record["width"] != output_width
                    or record["height"] != output_height
                    or record["timezone"] != settings.timezone
                    or record["rotation"] != settings.screen_rotation
                )
            last_error = record["last_error"] if record else None
            if stale:
                stale_sources.append(screen)
            if last_error:
                errors.append(last_error)
            screen_status.append(
                ScreenStatus(
                    screen=screen,
                    generated_at=generated_at,
                    width=record["width"] if record else output_width,
                    height=record["height"] if record else output_height,
                    stale=stale,
                    last_error=last_error,
                )
            )
        pipeline = application.state.data_pipeline
        source_status = pipeline.source_status(current) if pipeline is not None else []
        stale_sources.extend(source.id for source in source_status if source.stale)
        errors.extend(source.last_error for source in source_status if source.last_error)
        status_model = Status(
            ok=all_available and not errors,
            timezone=settings.timezone,
            screens=list(SCREENS),
            generated_at=latest,
            stale_sources=stale_sources,
            last_error=errors[0] if errors else None,
            navigation_order=list(SCREENS),
            demo=settings.demo_mode,
            screen_status=screen_status,
            source_status=source_status,
        )
        return status_model.model_dump(mode="json")

    @application.get("/api/preview/{screen}")
    def preview(screen: Screen) -> Response:
        return _cached_response(application, screen)

    @application.get("/api/display")
    def trmnl_display(request: Request) -> dict[str, Any]:
        """TRMNL-compatible endpoint for the KOReader TRMNL plugin (base URL = this server)."""
        # Every fetch, whether the Kindle's timer or a tap, moves on to the next page.
        has_content: dict[Screen, bool] = application.state.screen_has_content
        position = application.state.display_position
        for step in range(1, len(SCREENS) + 1):
            candidate = (position + step) % len(SCREENS)
            if has_content.get(SCREENS[candidate], True):
                position = candidate
                break
        application.state.display_position = position
        screen = SCREENS[position]
        cached = application.state.cache.read(screen)
        if cached is None:
            raise HTTPException(status_code=503, detail="screen image is not available")
        version = str(cached[1]["image_file"]).removesuffix(".png")
        return {
            "status": 0,
            "image_url": f"{str(request.base_url).rstrip('/')}/kindle/{screen}.png?v={version}",
            "filename": version,
            "refresh_rate": TRMNL_SCREEN_SECONDS,
        }

    @application.get("/kindle/current.png")
    def current_screen() -> Response:
        return _cached_response(application, "news-weather")

    @application.get("/kindle/{screen}.png")
    def named_screen(screen: Screen) -> Response:
        return _cached_response(application, screen)

    return application


def _cached_response(application: FastAPI, screen: Screen) -> Response:
    cache: ScreenCache = application.state.cache
    cached = cache.read(screen)
    if cached is None:
        raise HTTPException(status_code=503, detail="screen image is not available")
    content, record = cached
    return Response(
        content=content,
        media_type="image/png",
        headers={"ETag": f'"{record["image_file"]}"'},
    )


app = create_app()
