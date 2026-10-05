"""Shared normalized data and decision contracts."""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Screen = Literal["news-weather", "news", "family", "calendar", "nearby", "photo"]
Mode = Literal["family"]
Severity = Literal["ordinary", "disruption", "critical"]
ItemKind = Literal[
    "alert",
    "calendar",
    "weather",
    "news",
    "countdown",
    "verse",
    "fact",
    "photo",
    "local_event",
]
NewsCategory = Literal["portugal", "world"]


class DisplayLayout(StrEnum):
    HERO = "hero"
    HERO_SECONDARY = "hero_secondary"
    THREE_ITEMS = "three_items"
    WEATHER_ALERT = "weather_alert"
    NEWS_QR = "news_qr"
    QUOTE = "quote"
    NEARBY = "nearby"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, hide_input_in_errors=True)


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return value


def _require_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone must be a valid IANA timezone") from exc
    return value


def _optional_aware(value: datetime | None) -> datetime | None:
    return None if value is None else _require_aware(value)


class WeatherPeriod(ContractModel):
    summary: str | None = None
    temperature_c: float | None = None
    temperature_min_c: float | None = None
    temperature_max_c: float | None = None
    rain_probability_pct: int | None = Field(default=None, ge=0, le=100)
    rain_mm: float | None = Field(default=None, ge=0)
    wind_kph: float | None = Field(default=None, ge=0)
    uv_index: float | None = Field(default=None, ge=0)


class WeatherHour(ContractModel):
    at: datetime
    rain_mm: float | None = Field(default=None, ge=0)
    wind_kph: float | None = Field(default=None, ge=0)

    _aware_at = field_validator("at")(_require_aware)


class WeatherSnapshot(ContractModel):
    observed_at: datetime
    timezone: str
    source: str
    current: WeatherPeriod
    today: WeatherPeriod
    tomorrow: WeatherPeriod
    sunrise: datetime | None = None
    sunset: datetime | None = None
    hourly: list[WeatherHour] = Field(default_factory=list, max_length=72)

    _aware_observed_at = field_validator("observed_at")(_require_aware)
    _valid_timezone = field_validator("timezone")(_require_timezone)
    _aware_sunrise = field_validator("sunrise")(_optional_aware)
    _aware_sunset = field_validator("sunset")(_optional_aware)


class DisplayFact(ContractModel):
    label: str = Field(min_length=1, max_length=40)
    value: str = Field(min_length=1, max_length=40)


class DisplayItem(ContractModel):
    id: str = Field(min_length=1, max_length=200)
    kind: ItemKind
    title: str = Field(min_length=1, max_length=160)
    summary: str | None = Field(default=None, max_length=280)
    priority: int = Field(default=0, ge=0, le=100)
    occurred_at: datetime
    person: str | None = None
    source: str | None = None
    is_protected: bool = False
    severity: Severity = "ordinary"
    ends_at: datetime | None = None
    all_day: bool = False
    label: str | None = Field(default=None, max_length=80)
    url: str | None = Field(default=None, max_length=2000)
    facts: list[DisplayFact] = Field(default_factory=list, max_length=3)
    distance_km: float | None = Field(default=None, ge=0)
    image_path: str | None = Field(default=None, max_length=500)

    _aware_occurred_at = field_validator("occurred_at")(_require_aware)
    _aware_ends_at = field_validator("ends_at")(_optional_aware)


class DisplayContext(ContractModel):
    generated_at: datetime
    timezone: str
    mode: Mode = "family"
    items: list[DisplayItem]
    protected_alert_ids: list[str] = Field(default_factory=list)
    demo: bool = True
    source_warnings: list[str] = Field(default_factory=list)
    unavailable_kinds: list[Literal["calendar", "weather", "rss"]] = Field(default_factory=list)
    weather: WeatherSnapshot | None = None
    people: list[str] = Field(default_factory=list)
    night: bool = False
    news_digest: bool = False

    _aware_generated_at = field_validator("generated_at")(_require_aware)
    _valid_timezone = field_validator("timezone")(_require_timezone)

    @model_validator(mode="after")
    def validate_ids_and_protection(self) -> "DisplayContext":
        by_id = {item.id: item for item in self.items}
        if len(by_id) != len(self.items):
            raise ValueError("item ids must be unique")
        if len(set(self.protected_alert_ids)) != len(self.protected_alert_ids):
            raise ValueError("protected_alert_ids must be unique")
        for alert_id in self.protected_alert_ids:
            item = by_id.get(alert_id)
            if item is None:
                raise ValueError(f"protected alert id {alert_id!r} is unknown")
            if not (item.is_protected or item.severity == "critical"):
                raise ValueError(f"protected alert id {alert_id!r} is not protected")
        return self


class DisplayDecision(ContractModel):
    layout: DisplayLayout
    item_ids: list[str] = Field(max_length=3)
    protected_alert_ids: list[str]
    reason: str = Field(max_length=240)
    generated_at: datetime
    provider: Literal["rules", "ai"] = "rules"

    _aware_generated_at = field_validator("generated_at")(_require_aware)

    @model_validator(mode="after")
    def validate_selection(self) -> "DisplayDecision":
        if len(set(self.item_ids)) != len(self.item_ids):
            raise ValueError("item_ids must be unique")
        if len(set(self.protected_alert_ids)) != len(self.protected_alert_ids):
            raise ValueError("protected_alert_ids must be unique")
        if set(self.item_ids) & set(self.protected_alert_ids):
            raise ValueError("ordinary item_ids and protected_alert_ids must be separate")
        return self


class Event(ContractModel):
    id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=160)
    starts_at: datetime
    ends_at: datetime | None = None
    summary: str | None = Field(default=None, max_length=280)
    person: str | None = None
    source: str
    all_day: bool = False
    is_protected: bool = False

    _aware_starts_at = field_validator("starts_at")(_require_aware)
    _aware_ends_at = field_validator("ends_at")(_optional_aware)


class NearbyEvent(ContractModel):
    id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=160)
    starts_at: datetime
    ends_at: datetime | None = None
    all_day: bool = False
    venue: str | None = Field(default=None, max_length=80)
    url: str = Field(max_length=2000)

    _aware_starts_at = field_validator("starts_at")(_require_aware)
    _aware_ends_at = field_validator("ends_at")(_optional_aware)


class NewsItem(ContractModel):
    id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=160)
    summary: str | None = Field(default=None, max_length=280)
    published_at: datetime
    source: str
    category: NewsCategory
    url: str | None = None

    _aware_published_at = field_validator("published_at")(_require_aware)


class ScreenStatus(ContractModel):
    screen: Screen
    generated_at: datetime | None = None
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    stale: bool
    last_error: str | None = None

    _aware_generated_at = field_validator("generated_at")(_optional_aware)


class SourceStatus(ContractModel):
    id: str
    kind: Literal["calendar", "weather", "rss", "events"]
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    stale: bool = True
    last_error: str | None = None
    item_count: int = Field(default=0, ge=0)

    _aware_attempt = field_validator("last_attempt_at")(_optional_aware)
    _aware_success = field_validator("last_success_at")(_optional_aware)


class Status(ContractModel):
    ok: bool
    timezone: str
    screens: list[Screen]
    generated_at: datetime | None = None
    stale_sources: list[str] = Field(default_factory=list)
    last_error: str | None = None
    navigation_order: list[Screen] = Field(default_factory=list)
    demo: bool = True
    screen_status: list[ScreenStatus] = Field(default_factory=list)
    source_status: list[SourceStatus] = Field(default_factory=list)

    _valid_timezone = field_validator("timezone")(_require_timezone)
    _aware_generated_at = field_validator("generated_at")(_optional_aware)
