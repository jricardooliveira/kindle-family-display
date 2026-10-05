"""Open-Meteo request construction and weather-response normalization."""

from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.contracts import WeatherPeriod, WeatherSnapshot
from app.contracts.models import WeatherHour

OPEN_METEO_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
_CURRENT = "temperature_2m,wind_speed_10m,weather_code"
_HOURLY = "rain,wind_speed_10m"
_DAILY = (
    "temperature_2m_max,temperature_2m_min,rain_sum,precipitation_probability_max,"
    "wind_speed_10m_max,sunrise,sunset,uv_index_max,weather_code"
)
_WMO_SUMMARIES = {
    0: "Céu limpo",
    1: "Predominantemente limpo",
    2: "Parcialmente nublado",
    3: "Nublado",
    45: "Nevoeiro",
    48: "Nevoeiro com geada",
    51: "Chuvisco ligeiro",
    53: "Chuvisco moderado",
    55: "Chuvisco intenso",
    56: "Chuvisco gelado ligeiro",
    57: "Chuvisco gelado intenso",
    61: "Chuva fraca",
    63: "Chuva moderada",
    65: "Chuva forte",
    66: "Chuva gelada ligeira",
    67: "Chuva gelada forte",
    71: "Neve fraca",
    73: "Neve moderada",
    75: "Neve forte",
    77: "Grãos de neve",
    80: "Aguaceiros fracos",
    81: "Aguaceiros moderados",
    82: "Aguaceiros muito fortes",
    85: "Aguaceiros de neve fracos",
    86: "Aguaceiros de neve fortes",
    95: "Trovoada",
    96: "Trovoada com granizo ligeiro",
    99: "Trovoada forte com granizo",
}
_EXPECTED_CURRENT_UNITS = {
    "time": "iso8601",
    "temperature_2m": "°C",
    "wind_speed_10m": "km/h",
    "weather_code": "wmo code",
}
_EXPECTED_DAILY_UNITS = {
    "time": "iso8601",
    "temperature_2m_max": "°C",
    "temperature_2m_min": "°C",
    "rain_sum": "mm",
    "precipitation_probability_max": "%",
    "wind_speed_10m_max": "km/h",
    "sunrise": "iso8601",
    "sunset": "iso8601",
    "uv_index_max": "index",
    "weather_code": "wmo code",
}
_DAILY_ARRAYS = tuple(_EXPECTED_DAILY_UNITS)[1:]


def weather_request_url(latitude: float, longitude: float, timezone: str) -> str:
    """Build the fixed metric Open-Meteo request URL without making a request."""
    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise ValueError("latitude must be a finite value from -90 through 90")
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError("longitude must be a finite value from -180 through 180")
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone must be a valid IANA timezone") from exc
    query = urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone,
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
            "current": _CURRENT,
            "daily": _DAILY,
            "forecast_days": 2,
            "hourly": _HOURLY,
        }
    )
    return f"{OPEN_METEO_ENDPOINT}?{query}"


def parse_weather(payload: bytes, *, timezone: str) -> WeatherSnapshot:
    """Validate and normalize an Open-Meteo forecast response."""
    zone = _timezone(timezone)
    data = _decode_json(payload)
    if data.get("timezone") != timezone:
        raise ValueError("response timezone does not match requested timezone")

    current_units = _object(data, "current_units")
    current_values = _object(data, "current")
    daily_units = _object(data, "daily_units")
    daily = _object(data, "daily")
    _check_units(current_units, _EXPECTED_CURRENT_UNITS, "current")
    _check_units(daily_units, _EXPECTED_DAILY_UNITS, "daily")

    times = _array(daily, "time")
    if len(times) != 2:
        raise ValueError("daily.time must contain exactly two forecast dates")
    try:
        forecast_dates = [date.fromisoformat(_string(value, "daily.time")) for value in times]
    except ValueError as exc:
        raise ValueError("daily.time contains an invalid date") from exc

    local_observed_at = _provider_datetime(
        _string(current_values.get("time"), "current.time"), zone, "current.time"
    )
    if forecast_dates[0] != local_observed_at.date():
        raise ValueError("daily first date must match current local date")
    if forecast_dates[1] != forecast_dates[0] + timedelta(days=1):
        raise ValueError("daily second date must be the day after current local date")

    arrays = {key: _array(daily, key) for key in _DAILY_ARRAYS}
    for key, values in arrays.items():
        if len(values) != 2:
            raise ValueError(f"daily.{key} must contain exactly two values")

    current_temp = _number(current_values, "temperature_2m", required=True)
    current_wind = _number(current_values, "wind_speed_10m", minimum=0, required=True)
    current_code = _integer(current_values, "weather_code", required=True)
    snapshot = WeatherSnapshot(
        observed_at=local_observed_at.astimezone(UTC),
        timezone=timezone,
        source="Open-Meteo",
        current=WeatherPeriod(
            summary=_weather_summary(current_code),
            temperature_c=current_temp,
            wind_kph=current_wind,
        ),
        today=_period(arrays, 0),
        tomorrow=_period(arrays, 1),
        sunrise=_optional_provider_datetime(arrays["sunrise"][0], zone, "daily.sunrise"),
        sunset=_optional_provider_datetime(arrays["sunset"][0], zone, "daily.sunset"),
        hourly=_hours(data, zone),
    )
    return snapshot


def _hours(data: dict[str, Any], zone: ZoneInfo) -> list[WeatherHour]:
    """Normalize the optional hourly rain and wind series used to time alerts."""
    if "hourly" not in data:
        return []
    hourly = _object(data, "hourly")
    units = _object(data, "hourly_units")
    _check_units(units, {"time": "iso8601", "rain": "mm", "wind_speed_10m": "km/h"}, "hourly")
    times = _array(hourly, "time")
    rain = _array(hourly, "rain")
    wind = _array(hourly, "wind_speed_10m")
    if not len(times) == len(rain) == len(wind) or len(times) > 72:
        raise ValueError("hourly arrays must have the same length of at most 72 values")
    return [
        WeatherHour(
            at=_provider_datetime(_string(value, "hourly.time"), zone, "hourly.time"),
            rain_mm=_number({"rain": rain[index]}, "rain", minimum=0),
            wind_kph=_number({"wind_speed_10m": wind[index]}, "wind_speed_10m", minimum=0),
        )
        for index, value in enumerate(times)
    ]


def _decode_json(payload: bytes) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number {value} is not allowed")

    try:
        data = json.loads(payload, parse_constant=reject_constant)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("invalid Open-Meteo JSON") from exc
    if not isinstance(data, dict):
        raise TypeError("Open-Meteo response must be a JSON object")
    return data


def _timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone must be a valid IANA timezone") from exc


def _object(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be an object")
    return value


def _array(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        raise TypeError(f"daily.{key} must be an array")
    return value


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _check_units(actual: dict[str, Any], expected: dict[str, str], section: str) -> None:
    for key, unit in expected.items():
        if key == "uv_index_max" and actual.get(key) == "":
            continue  # Open-Meteo returns an empty unit for the dimensionless UV index.
        if actual.get(key) != unit:
            raise ValueError(f"{section}.{key} unit must be {unit!r}")


def _number(
    data: dict[str, Any], key: str, *, minimum: float | None = None, required: bool = False
) -> float | None:
    value = data.get(key)
    if value is None and not required:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{key} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{key} must be a finite number")
    if minimum is not None and number < minimum:
        raise ValueError(f"{key} must be at least {minimum}")
    return number


def _integer(data: dict[str, Any], key: str, *, required: bool = False) -> int | None:
    value = data.get(key)
    if value is None and not required:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be an integer")
    return value


def _daily_number(
    values: list[Any], key: str, index: int, minimum: float | None = None
) -> float | None:
    return _number({key: values[index]}, key, minimum=minimum)


def _daily_percent(values: list[Any], key: str, index: int) -> int | None:
    value = values[index]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise ValueError(f"{key} must be an integer from 0 through 100 or null")
    return value


def _weather_summary(code: int | None) -> str | None:
    if code is None:
        return None
    return _WMO_SUMMARIES.get(code, "Condições meteorológicas variadas")


def _period(arrays: dict[str, list[Any]], index: int) -> WeatherPeriod:
    code = _integer({"weather_code": arrays["weather_code"][index]}, "weather_code")
    maximum = _daily_number(arrays["temperature_2m_max"], "temperature_2m_max", index)
    minimum = _daily_number(arrays["temperature_2m_min"], "temperature_2m_min", index)
    return WeatherPeriod(
        summary=_weather_summary(code),
        temperature_c=maximum,
        temperature_min_c=minimum,
        temperature_max_c=maximum,
        rain_mm=_daily_number(arrays["rain_sum"], "rain_sum", index, minimum=0),
        rain_probability_pct=_daily_percent(
            arrays["precipitation_probability_max"], "precipitation_probability_max", index
        ),
        wind_kph=_daily_number(
            arrays["wind_speed_10m_max"], "wind_speed_10m_max", index, minimum=0
        ),
        uv_index=_daily_number(arrays["uv_index_max"], "uv_index_max", index, minimum=0),
    )


def _provider_datetime(value: str, zone: ZoneInfo, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO 8601 datetime") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone)


def _optional_provider_datetime(value: Any, zone: ZoneInfo, field: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be an ISO 8601 datetime or null")
    return _provider_datetime(value, zone, field)
