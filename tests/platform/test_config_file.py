import pytest
from pydantic import ValidationError

from app.config import Settings, load_settings


def test_loads_complete_settings_from_toml_with_secret_feed_urls(tmp_path):
    config = tmp_path / "family.toml"
    config.write_text(
        """
        timezone = "Europe/Lisbon"
        demo_mode = false
        calendar_days = 21
        weather_latitude = 38.72
        weather_longitude = -9.14
        weather_location = "Lisboa"

        [[calendar_feeds]]
        id = "family-cal"
        url = "https://calendar.example.test/private?token=fixture"
        person = "Alex"

        [[rss_feeds]]
        id = "world-news"
        url = "https://news.example.test/rss?token=fixture"
        category = "world"
        keywords = ["escolas"]
        """,
        encoding="utf-8",
    )

    settings = load_settings(config)

    assert settings.demo_mode is False
    assert settings.calendar_days == 21
    assert settings.weather_location == "Lisboa"
    assert settings.calendar_feeds[0].person == "Alex"
    assert settings.calendar_feeds[0].url.get_secret_value().endswith("token=fixture")
    assert settings.rss_feeds[0].category == "world"
    assert settings.rss_feeds[0].keywords == ["escolas"]
    assert "token=fixture" not in repr(settings)


def test_settings_precedence_is_overrides_then_environment_then_toml_then_dotenv(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("SCREEN_WIDTH=1100\nSCREEN_HEIGHT=500\n", encoding="utf-8")
    config = tmp_path / "settings.toml"
    config.write_text(
        'timezone = "Europe/Lisbon"\nscreen_width = 900\nscreen_height = 600\n', encoding="utf-8"
    )
    monkeypatch.setenv("TIMEZONE", "UTC")
    monkeypatch.delenv("SCREEN_WIDTH", raising=False)
    monkeypatch.delenv("SCREEN_HEIGHT", raising=False)

    settings = load_settings(config, screen_height=700)

    assert settings.timezone == "UTC"
    assert settings.screen_width == 900
    assert settings.screen_height == 700


def test_missing_default_toml_falls_back_to_dotenv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CONFIG_FILE", raising=False)
    monkeypatch.delenv("TIMEZONE", raising=False)
    (tmp_path / ".env").write_text('TIMEZONE="UTC"\n', encoding="utf-8")

    assert load_settings().timezone == "UTC"


@pytest.mark.parametrize("explicit", ["argument", "environment"])
def test_explicit_missing_config_file_fails_safely(tmp_path, monkeypatch, explicit):
    missing = tmp_path / "missing-private-config.toml"
    if explicit == "environment":
        monkeypatch.setenv("CONFIG_FILE", str(missing))
        call = lambda: load_settings()
    else:
        call = lambda: load_settings(missing)

    with pytest.raises(ValueError, match="configuration file") as error:
        call()
    assert "missing-private-config" not in str(error.value)


def test_malformed_unknown_and_oversized_toml_fail_without_echoing_private_values(tmp_path):
    config = tmp_path / "invalid.toml"
    secret_url = "https://calendar.example.test/private?token=do-not-print"

    config.write_text(f'url = "{secret_url}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="malformed") as malformed:
        load_settings(config)
    assert "do-not-print" not in str(malformed.value)

    config.write_text(f'private_token = "{secret_url}"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="unknown") as unknown:
        load_settings(config)
    assert "do-not-print" not in str(unknown.value)

    config.write_bytes(b"#" + b"x" * (64 * 1024))
    with pytest.raises(ValueError, match="64 KiB"):
        load_settings(config)


def test_feed_validation_errors_hide_secret_values(tmp_path):
    config = tmp_path / "bad-feed.toml"
    secret_url = "https://127.0.0.1/feed?token=do-not-print"
    config.write_text(f'[[calendar_feeds]]\nid="bad"\nurl="{secret_url}"\n', encoding="utf-8")

    with pytest.raises(ValidationError) as error:
        load_settings(config)

    assert "do-not-print" not in str(error.value)
    assert secret_url not in str(error.value)


def test_existing_settings_constructor_does_not_load_toml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text('timezone = "UTC"\n', encoding="utf-8")

    settings = Settings(_env_file=None)

    assert settings.timezone == "Europe/Lisbon"


def test_example_toml_loads_without_private_sources_or_keys():
    settings = load_settings("config.example.toml", _env_file=None)
    assert settings.demo_mode
    assert settings.calendar_feeds == []
    assert settings.rss_feeds == []
    assert not settings.ai_enabled
