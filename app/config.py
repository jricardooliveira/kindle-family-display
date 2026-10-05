"""Validated application settings."""

import os
import re
import tomllib
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.collectors.http import validate_url
from app.contracts.models import NewsCategory
from app.i18n import Country, Language

_SOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_MAX_CONFIG_BYTES = 64 * 1024


class _FeedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    id: str = Field(min_length=1, max_length=64)
    label: str = Field(default="", max_length=80)
    url: SecretStr

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not _SOURCE_ID.fullmatch(value):
            raise ValueError(
                "source id must use letters, numbers, dot, underscore, colon, or hyphen"
            )
        return value

    @field_validator("url")
    @classmethod
    def validate_feed_url(cls, value: SecretStr) -> SecretStr:
        validate_url(value.get_secret_value())
        return value

    @model_validator(mode="after")
    def default_label(self):
        if not self.label.strip():
            self.label = self.id
        return self


class CalendarFeed(_FeedConfig):
    person: str | None = Field(default=None, max_length=80)


class RSSFeed(_FeedConfig):
    category: NewsCategory = "portugal"
    curated: bool = False
    keywords: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, value: list[str]) -> list[str]:
        normalized = [keyword.strip() for keyword in value]
        if any(not keyword or len(keyword) > 80 for keyword in normalized):
            raise ValueError("keywords must be non-empty strings of at most 80 characters")
        return normalized


class EventFeed(_FeedConfig):
    """A public listing page of local events and its rough distance from home."""

    distance_km: float = Field(default=0, ge=0, le=500)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_env: str = "development"
    language: Language = "pt"
    country: Country = "PT"
    timezone: str = "Europe/Lisbon"
    screen_width: int = Field(default=800, ge=320, le=1648)
    screen_height: int = Field(default=600, ge=240, le=1648)
    screen_rotation: int = 0
    database_url: str = "sqlite:////data/kindle.db"
    cache_dir: str = "/cache"
    refresh_minutes: int = Field(default=30, ge=1, le=1440)
    # Optional AI scoring of news importance; without a readable key the rules are used.
    ai_enabled: bool = False
    ai_api_key_file: str | None = None
    ai_model: str = Field(default="gpt-4o-mini", min_length=1, max_length=80)
    # Stories scoring below this (0-10) are not shown while a better one exists.
    ai_news_min_score: int = Field(default=6, ge=0, le=10)
    demo_mode: bool = True
    calendar_feeds: list[CalendarFeed] = Field(default_factory=list)
    rss_feeds: list[RSSFeed] = Field(default_factory=list)
    event_feeds: list[EventFeed] = Field(default_factory=list)
    calendar_days: int = Field(default=14, ge=2, le=31)
    calendar_poll_minutes: int = Field(default=30, ge=1, le=1440)
    rss_poll_minutes: int = Field(default=60, ge=1, le=1440)
    weather_poll_minutes: int = Field(default=30, ge=1, le=1440)
    events_poll_minutes: int = Field(default=360, ge=15, le=1440)
    # Local "HH:MM-HH:MM" periods in which each refresh shows the next recent stories.
    news_rotation_windows: list[str] = Field(default_factory=list, max_length=8)
    # Local "HH:MM-HH:MM" periods in which the news screen shows one lead story and three briefs.
    news_digest_windows: list[str] = Field(default_factory=list, max_length=8)
    # Local period in which the family screen shows only the next morning; "" disables it.
    night_window: str = "21:30-06:30"
    # Show a rotating curiosity on the family screen when nothing more important is due.
    facts_enabled: bool = True
    # Folder of family photos (jpg/png); one is shown each day in alternate hours.
    photos_dir: str | None = None
    # Folder of calendar files (.ics) used alongside, or instead of, calendar links.
    calendars_dir: str | None = None
    weather_latitude: float | None = Field(default=None, ge=-90, le=90)
    weather_longitude: float | None = Field(default=None, ge=-180, le=180)
    weather_location: str | None = Field(default=None, max_length=80)
    weather_rain_disruption_mm: float | None = Field(default=None, ge=0)
    weather_wind_disruption_kph: float | None = Field(default=None, ge=0)

    @field_validator(
        "weather_latitude",
        "weather_longitude",
        "weather_rain_disruption_mm",
        "weather_wind_disruption_kph",
        mode="before",
    )
    @classmethod
    def normalize_empty_coordinates(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("weather_location", mode="before")
    @classmethod
    def normalize_empty_location(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("news_rotation_windows", "news_digest_windows")
    @classmethod
    def validate_rotation_windows(cls, value: list[str]) -> list[str]:
        from app.decision.news import parse_window

        for window in value:
            parse_window(window)
        return value

    @field_validator("night_window")
    @classmethod
    def validate_night_window(cls, value: str) -> str:
        from app.decision.periods import parse_period

        if value:
            parse_period(value)
        return value

    @field_validator("screen_rotation")
    @classmethod
    def validate_rotation(cls, value: int) -> int:
        if value not in (0, 90, 180, 270):
            raise ValueError("screen_rotation must be 0, 90, 180, or 270 degrees")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(
                "timezone must be a valid IANA timezone, such as Europe/Lisbon"
            ) from exc
        return value

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        prefix = "sqlite:///"
        if not value.startswith(prefix):
            raise ValueError(
                "database_url must be a file-backed SQLite URL (sqlite:////path/file.db)"
            )
        database_path = value[len(prefix) :]
        if not database_path or database_path == ":memory:" or "?" in database_path:
            raise ValueError("database_url must point to a persistent SQLite database file")
        return value

    @model_validator(mode="after")
    def validate_supported_features(self) -> "Settings":
        if (self.weather_latitude is None) != (self.weather_longitude is None):
            raise ValueError("weather_latitude and weather_longitude must be configured together")
        if self.weather_latitude is not None and not (self.weather_location or "").strip():
            raise ValueError("weather_location is required when weather coordinates are configured")
        if self.weather_location is not None and not self.weather_location.strip():
            raise ValueError("weather_location must not be empty")
        source_count = len(self.calendar_feeds) + len(self.rss_feeds) + len(self.event_feeds)
        if self.weather_latitude is not None:
            source_count += 1
        if source_count > 8:
            raise ValueError("at most eight data sources may be configured")
        ids = [feed.id for feed in [*self.calendar_feeds, *self.rss_feeds, *self.event_feeds]]
        if self.weather_latitude is not None and "weather-home" in ids:
            raise ValueError("weather-home is reserved for the configured weather source")
        if len(set(ids)) != len(ids):
            raise ValueError("source ids must be unique across calendar and RSS feeds")
        return self


def load_settings(
    config_path: str | Path | None = None,
    **overrides: object,
) -> Settings:
    """Load settings with precedence: overrides, environment, TOML, .env, defaults."""
    explicit_path = config_path is not None or "CONFIG_FILE" in os.environ
    selected_path = Path(config_path or os.environ.get("CONFIG_FILE", "config.toml"))
    try:
        with selected_path.open("rb") as config_file:
            content = config_file.read(_MAX_CONFIG_BYTES + 1)
    except FileNotFoundError:
        if explicit_path:
            raise ValueError("configuration file was not found") from None
        content = b""
    except OSError:
        raise ValueError("configuration file could not be read") from None

    if len(content) > _MAX_CONFIG_BYTES:
        raise ValueError("configuration file exceeds the 64 KiB limit")
    if content:
        try:
            config_values = tomllib.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, tomllib.TOMLDecodeError):
            raise ValueError("configuration file contains malformed TOML") from None
    else:
        config_values = {}
    unknown_keys = set(config_values) - set(Settings.model_fields)
    if unknown_keys:
        raise ValueError("configuration file contains unknown settings keys")

    class _TomlSettings(Settings):
        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls,
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        ):
            def toml_settings() -> dict[str, object]:
                return config_values

            return (
                init_settings,
                env_settings,
                toml_settings,
                dotenv_settings,
                file_secret_settings,
            )

    settings_class: Any = _TomlSettings
    return settings_class(**overrides)
