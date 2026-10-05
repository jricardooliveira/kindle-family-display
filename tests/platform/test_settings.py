import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.parametrize(
    "overrides",
    [
        {"timezone": "Mars/Olympus"},
        {"screen_width": 319},
        {"screen_height": 1649},
        {"screen_rotation": 45},
        {"refresh_minutes": 0},
        {"database_url": "postgresql://localhost/kindle"},
    ],
)
def test_settings_reject_invalid_or_unsupported_configuration(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


def test_settings_accepts_supported_dimensions_rotation_and_file_sqlite(tmp_path):
    settings = Settings(
        _env_file=None,
        screen_width=320,
        screen_height=1648,
        screen_rotation=270,
        database_url=f"sqlite:///{tmp_path / 'dashboard.db'}",
        cache_dir=str(tmp_path / "cache"),
    )

    assert settings.screen_width == 320
    assert settings.screen_height == 1648
    assert settings.screen_rotation == 270


@pytest.mark.parametrize(
    ("width", "height"),
    [(1236, 1648), (1648, 1236)],
)
def test_settings_accept_paperwhite_native_dimensions(width, height):
    settings = Settings(_env_file=None, screen_width=width, screen_height=height)

    assert (settings.screen_width, settings.screen_height) == (width, height)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_settings_accept_rotation_from_environment(monkeypatch, rotation):
    monkeypatch.setenv("SCREEN_ROTATION", str(rotation))
    assert Settings(_env_file=None).screen_rotation == rotation


def test_sample_env_loads_without_optional_secrets():
    settings = Settings(_env_file=".env.example")
    assert settings.screen_rotation == 0
    assert settings.timezone == "Europe/Lisbon"
    assert settings.database_url == "sqlite:///.data/kindle.db"
