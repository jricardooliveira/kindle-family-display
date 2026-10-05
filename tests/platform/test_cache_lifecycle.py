from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import SCREENS, create_app

NOW = datetime(2026, 10, 4, 7, 30, tzinfo=ZoneInfo("Europe/Lisbon"))


def png_bytes(screen: str, width: int = 800, height: int = 600, rotation: int = 0) -> bytes:
    if rotation in (90, 270):
        width, height = height, width
    image = Image.new("L", (width, height), 255 if screen == "family" else 0)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        timezone="Europe/Lisbon",
        screen_width=800,
        screen_height=600,
        screen_rotation=0,
        database_url=f"sqlite:///{tmp_path / 'dashboard.db'}",
        cache_dir=str(tmp_path / "cache"),
        refresh_minutes=30,
    )


def test_startup_renders_missing_screens_and_routes_serve_cached_pngs(tmp_path, monkeypatch):
    from app import main

    calls = []

    def render(screen, context, decision, width, height, rotation=0):
        calls.append((screen, context, decision, width, height, rotation))
        return png_bytes(screen, width, height, rotation)

    monkeypatch.setattr(main, "render", render)
    app = create_app(make_settings(tmp_path))

    with TestClient(app) as client:
        assert len(calls) == len(SCREENS)
        for screen in SCREENS:
            image = client.get(f"/kindle/{screen}.png")
            preview = client.get(f"/api/preview/{screen}")
            assert image.status_code == 200
            assert image.headers["content-type"] == "image/png"
            assert image.content == png_bytes(screen)
            assert preview.content == image.content
        assert client.get("/kindle/current.png").content == png_bytes("news-weather")
        assert client.get("/healthz").json() == {"ok": True}
        status = client.get("/api/status").json()
        assert status["demo"] is True
        assert status["navigation_order"] == list(SCREENS)
        assert all(entry["generated_at"] is not None for entry in status["screen_status"])


def test_restart_reuses_matching_cached_images_without_marking_them_fresh(tmp_path, monkeypatch):
    from app import main

    calls = []

    def render(screen, context, decision, width, height, rotation=0):
        calls.append(screen)
        return png_bytes(screen, width, height, rotation)

    monkeypatch.setattr(main, "render", render)
    first = create_app(make_settings(tmp_path))
    with TestClient(first) as client:
        before = client.get("/api/status").json()

    calls.clear()
    second = create_app(make_settings(tmp_path))
    with TestClient(second) as client:
        after = client.get("/api/status").json()
        assert calls == []
        assert after["screen_status"] == before["screen_status"]
        assert client.get("/kindle/family.png").content == png_bytes("family")


def test_failed_refresh_keeps_last_good_bytes_and_timestamp(tmp_path, monkeypatch):
    from app import main

    fail = False

    def render(screen, context, decision, width, height, rotation=0):
        if fail and screen == "family":
            raise RuntimeError("private event details and internal path")
        return png_bytes(screen, width, height, rotation)

    monkeypatch.setattr(main, "render", render)
    app = create_app(make_settings(tmp_path))
    with TestClient(app) as client:
        before = client.get("/api/status").json()
        fail = True
        app.state.refresh(now=NOW + timedelta(hours=1))
        after = client.get("/api/status").json()
        assert client.get("/kindle/family.png").content == png_bytes("family")
        before_family = next(row for row in before["screen_status"] if row["screen"] == "family")
        after_family = next(row for row in after["screen_status"] if row["screen"] == "family")
        assert after_family["generated_at"] == before_family["generated_at"]
        assert after_family["last_error"] == "render failed"
        assert "private event" not in str(after)


@pytest.mark.parametrize(
    "override",
    [
        {"timezone": "America/New_York"},
        {"screen_rotation": 180},
    ],
)
def test_restart_rerenders_when_timezone_or_rotation_changes(tmp_path, monkeypatch, override):
    from app import main

    calls = []

    def render(screen, context, decision, width, height, rotation=0):
        calls.append(screen)
        return png_bytes(screen, width, height, rotation)

    monkeypatch.setattr(main, "render", render)
    first = create_app(make_settings(tmp_path))
    with TestClient(first):
        pass

    calls.clear()
    changed_settings = make_settings(tmp_path).model_copy(update=override)
    second = create_app(changed_settings)
    with TestClient(second):
        assert calls == list(SCREENS)


def test_startup_recovers_a_corrupt_cached_png_for_only_that_screen(tmp_path, monkeypatch):
    from app import main

    calls = []

    def render(screen, context, decision, width, height, rotation=0):
        calls.append(screen)
        return png_bytes(screen, width, height, rotation)

    monkeypatch.setattr(main, "render", render)
    first = create_app(make_settings(tmp_path))
    with TestClient(first):
        cache_pngs = list((tmp_path / "cache").glob("family-*.png"))
        assert len(cache_pngs) == 1
        cache_pngs[0].write_bytes(b"corrupt image")

    calls.clear()
    second = create_app(make_settings(tmp_path))
    with TestClient(second) as client:
        assert calls == ["family"]
        assert client.get("/kindle/family.png").content == png_bytes("family")
        assert client.get("/api/status").json()["ok"] is True


def test_missing_renderer_result_is_reported_without_exposing_exception(tmp_path, monkeypatch):
    from app import main

    def render(screen, context, decision, width, height, rotation=0):
        raise RuntimeError("private upstream data")

    monkeypatch.setattr(main, "render", render)
    app = create_app(make_settings(tmp_path))
    with TestClient(app) as client:
        assert client.get("/kindle/news-weather.png").status_code == 503
        status = client.get("/api/status").json()
        assert status["ok"] is False
        assert status["last_error"] == "render failed"
        assert "private upstream" not in str(status)


def test_invalidating_source_configuration_removes_old_images(tmp_path):
    from app.storage.cache import ScreenCache

    settings = make_settings(tmp_path)
    cache = ScreenCache(settings.database_url, settings.cache_dir)
    cache.write("family", png_bytes("family"), NOW.isoformat(), 800, 600, "Europe/Lisbon", 0)
    cache.invalidate()
    assert cache.read("family") is None
    assert cache.records() == []
    assert list(Path(settings.cache_dir).glob("*.png")) == []
    cache.close()
