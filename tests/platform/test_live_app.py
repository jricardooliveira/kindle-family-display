from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_live_empty_calendar_and_requests_never_fetch(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        return b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:test\r\nEND:VCALENDAR\r\n"

    settings = Settings(
        _env_file=None,
        demo_mode=False,
        calendar_feeds=[
            {"id": "family", "label": "Family", "url": "https://example.com/private.ics"}
        ],
        database_url=f"sqlite:///{tmp_path}/state.db",
        cache_dir=str(tmp_path / "cache"),
    )
    with TestClient(create_app(settings, fetcher=fetch)) as client:
        assert len(calls) == 1
        for screen in ("family", "calendar", "news-weather"):
            assert client.get(f"/kindle/{screen}.png").status_code == 200
        status = client.get("/api/status").json()
        assert status["demo"] is False
        assert status["source_status"][0]["item_count"] == 0
        assert status["source_status"][0]["last_success_at"]
        assert "private.ics" not in str(status)
        assert len(calls) == 1


def test_switch_to_live_never_serves_old_demo_after_render_failure(tmp_path, monkeypatch):
    from app import main

    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path}/state.db",
        cache_dir=str(tmp_path / "cache"),
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/kindle/family.png").status_code == 200

    def failed_render(*args, **kwargs):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(main, "render", failed_render)
    with TestClient(create_app(settings.model_copy(update={"demo_mode": False}))) as client:
        assert client.get("/kindle/family.png").status_code == 503
        assert client.get("/api/status").json()["demo"] is False


def test_default_app_factory_uses_file_settings(tmp_path, monkeypatch):
    config = tmp_path / "display.toml"
    config.write_text(
        f'demo_mode = false\ndatabase_url = "sqlite:///{tmp_path}/state.db"\ncache_dir = "{tmp_path}/cache"\n'
    )
    monkeypatch.setenv("CONFIG_FILE", str(config))
    with TestClient(create_app()) as client:
        assert client.get("/api/status").json()["demo"] is False


def test_trmnl_display_points_the_koreader_plugin_at_a_cached_screen(tmp_path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path}/state.db",
        cache_dir=str(tmp_path / "cache"),
    )
    with TestClient(create_app(settings)) as client:
        display = client.get("/api/display", headers={"access-token": "any"}).json()

        assert display["status"] == 0
        assert display["refresh_rate"] > 0
        assert display["image_url"].startswith("http://testserver/kindle/")
        image = client.get(display["image_url"])
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"


def test_every_display_fetch_moves_to_the_next_page_with_content(tmp_path):
    settings = Settings(
        _env_file=None,
        demo_mode=False,
        database_url=f"sqlite:///{tmp_path}/state.db",
        cache_dir=str(tmp_path / "cache"),
    )
    with TestClient(create_app(settings)) as client:
        assert client.app.state.screen_has_content == {
            "news-weather": True,
            "news": False,
            "family": True,
            "calendar": False,
            "nearby": False,
            "photo": False,
        }

        def page() -> str:
            return client.get("/api/display").json()["image_url"].split("/kindle/")[1].split(".")[0]

        assert [page(), page(), page()] == ["news-weather", "family", "news-weather"]

        client.app.state.screen_has_content["calendar"] = True
        assert [page(), page(), page()] == ["family", "calendar", "news-weather"]
        for screen in ("news", "nearby", "photo"):
            assert client.get(f"/kindle/{screen}.png").status_code == 200
