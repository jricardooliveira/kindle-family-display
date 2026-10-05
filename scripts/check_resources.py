"""Run inside the built image, without external networking; emit cgroup evidence."""

import json
import os
import platform
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from io import BytesIO
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo

import uvicorn
from PIL import Image

from app.config import Settings
from app.main import create_app


def cgroup(name: str) -> str | None:
    path = Path("/sys/fs/cgroup") / name
    return path.read_text().strip() if path.is_file() else None


def main() -> None:
    started = time.monotonic()
    live = os.environ.get("RESOURCE_LIVE") == "1"
    current = datetime.now(ZoneInfo("Europe/Lisbon"))
    weather = json.loads(Path("/fixtures/weather/normal.json").read_text()) if live else {}
    if live:
        weather["current"]["time"] = current.strftime("%Y-%m-%dT%H:%M")
        days = [current.date(), (current + timedelta(days=1)).date()]
        weather["daily"]["time"] = [day.isoformat() for day in days]
        for key, clock in (("sunrise", "07:30"), ("sunset", "19:15")):
            weather["daily"][key] = [f"{day.isoformat()}T{clock}" for day in days]

    def fixture_fetch(url: str) -> bytes:
        if "open-meteo" in url:
            return json.dumps(weather).encode()
        if url.endswith(".ics"):
            stamp = (current + timedelta(hours=1)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
            events = "".join(
                f"BEGIN:VEVENT\r\nUID:fixture-{i}\r\nDTSTART:{stamp}\r\nSUMMARY:Compromisso sintético {i}\r\nEND:VEVENT\r\n"
                for i in range(256)
            )
            return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:Resource test\r\n{events}END:VCALENDAR\r\n".encode()
        entries = "".join(
            f"<item><guid>{i}</guid><title>Notícia sintética {i}</title><pubDate>{format_datetime(current)}</pubDate></item>"
            for i in range(64)
        )
        return f"<rss version='2.0'><channel><title>Teste</title>{entries}</channel></rss>".encode()

    with tempfile.TemporaryDirectory() as directory:
        settings = Settings(
            _env_file=None,
            database_url=f"sqlite:///{directory}/state.db",
            cache_dir=f"{directory}/cache",
            demo_mode=not live,
            calendar_feeds=[
                {"id": f"calendar-{i}", "url": f"https://example.com/{i}.ics"} for i in range(6)
            ]
            if live
            else [],
            rss_feeds=[
                {"id": "news", "url": "https://example.com/news.xml", "category": "portugal"}
            ]
            if live
            else [],
            weather_latitude=41.0 if live else None,
            weather_longitude=-8.0 if live else None,
            weather_location="Teste" if live else "",
            calendar_poll_minutes=1,
            weather_poll_minutes=1,
            rss_poll_minutes=1,
        )
        app = create_app(settings, fetcher=fixture_fetch)
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8765, log_level="error"))
        thread = threading.Thread(target=server.run)
        thread.start()
        try:
            for _ in range(200):
                if server.started:
                    break
                if not thread.is_alive():
                    raise RuntimeError("server exited during startup")
                time.sleep(0.05)
            else:
                raise RuntimeError("server startup timed out")

            def fetch(index: int) -> int:
                screen = ("news-weather", "family", "calendar")[index % 3]
                with urlopen(f"http://127.0.0.1:8765/kindle/{screen}.png", timeout=10) as response:
                    assert response.headers.get_content_type() == "image/png"
                    body = response.read()
                with Image.open(BytesIO(body)) as picture:
                    expected = (settings.screen_width, settings.screen_height)
                    if settings.screen_rotation in (90, 270):
                        expected = expected[::-1]
                    assert picture.mode == "L" and picture.size == expected
                    picture.load()
                return len(body)

            now = datetime.now(UTC)
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = [pool.submit(fetch, i) for i in range(240)]
                for iteration in range(20):
                    app.state.refresh(now=now + timedelta(minutes=iteration))
                total_bytes = sum(future.result() for future in futures)
            with urlopen("http://127.0.0.1:8765/api/status", timeout=10) as response:
                status = json.load(response)
            assert status["ok"], status
            if live:
                assert len(status["source_status"]) == 8
                assert (
                    sum(s["item_count"] for s in status["source_status"] if s["kind"] == "calendar")
                    == 1536
                )
        finally:
            server.should_exit = True
            thread.join(timeout=15)
            if thread.is_alive():
                raise RuntimeError("server failed to shut down")
        print(
            json.dumps(
                {
                    "architecture": platform.machine(),
                    "live_fixture_sources": 8 if live else 0,
                    "calendar_events": 1536 if live else 0,
                    "dimensions": [settings.screen_width, settings.screen_height],
                    "rotation": settings.screen_rotation,
                    "refreshes": 20,
                    "http_requests": 240,
                    "client_threads": 8,
                    "total_png_bytes": total_bytes,
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                    "memory_current_bytes": cgroup("memory.current"),
                    "memory_peak_bytes": cgroup("memory.peak"),
                    "memory_limit_bytes": cgroup("memory.max"),
                    "memory_events": cgroup("memory.events"),
                    "swap_limit_bytes": cgroup("memory.swap.max"),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
