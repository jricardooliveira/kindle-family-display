from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from app.collectors.weather import parse_weather, weather_request_url

FIXTURES = Path(__file__).parents[1] / "fixtures" / "weather"


def load_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_weather_request_url_uses_fixed_metric_open_meteo_endpoint() -> None:
    url = weather_request_url(38.72, -9.14, "Europe/Lisbon")
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "api.open-meteo.com"
    assert parsed.path == "/v1/forecast"
    assert query["latitude"] == ["38.72"]
    assert query["longitude"] == ["-9.14"]
    assert query["timezone"] == ["Europe/Lisbon"]
    assert query["temperature_unit"] == ["celsius"]
    assert query["wind_speed_unit"] == ["kmh"]
    assert query["precipitation_unit"] == ["mm"]
    assert query["forecast_days"] == ["2"]
    assert query["hourly"] == ["rain,wind_speed_10m"]
    assert query["current"] == ["temperature_2m,wind_speed_10m,weather_code"]
    assert query["daily"] == [
        (
            "temperature_2m_max,temperature_2m_min,rain_sum,"
            "precipitation_probability_max,wind_speed_10m_max,sunrise,sunset,"
            "uv_index_max,weather_code"
        )
    ]


def test_parse_weather_normalizes_current_and_two_local_days() -> None:
    snapshot = parse_weather(load_fixture("normal.json"), timezone="Europe/Lisbon")

    assert snapshot.source == "Open-Meteo"
    assert snapshot.timezone == "Europe/Lisbon"
    assert snapshot.observed_at.isoformat() == "2026-10-04T11:00:00+00:00"
    assert snapshot.current.temperature_c == 18.4
    assert snapshot.current.wind_kph == 12.6
    assert snapshot.current.summary == "Chuva moderada"
    assert snapshot.today.temperature_c == 22.1
    assert snapshot.today.temperature_min_c == 15.2
    assert snapshot.today.temperature_max_c == 22.1
    assert snapshot.today.rain_mm == 4.2
    assert snapshot.today.rain_probability_pct == 70
    assert snapshot.today.wind_kph == 18.0
    assert snapshot.today.uv_index == 4.5
    assert snapshot.today.summary == "Nublado"
    assert snapshot.tomorrow.temperature_c == 23.0
    assert snapshot.tomorrow.temperature_min_c == 14.8
    assert snapshot.tomorrow.temperature_max_c == 23.0
    assert snapshot.tomorrow.summary == "Predominantemente limpo"
    assert snapshot.sunrise.isoformat() == "2026-10-04T07:30:00+01:00"
    assert snapshot.sunset.isoformat() == "2026-10-04T19:15:00+01:00"


def test_parse_weather_accepts_severe_rain_and_wind_as_data_without_alerting() -> None:
    snapshot = parse_weather(load_fixture("severe-wet-wind.json"), timezone="Europe/Lisbon")

    assert snapshot.current.summary == "Trovoada forte com granizo"
    assert snapshot.today.rain_mm == 42.8
    assert snapshot.today.wind_kph == 83.0
    assert snapshot.today.summary == "Aguaceiros muito fortes"


def test_parse_weather_preserves_zero_and_missing_optional_values() -> None:
    snapshot = parse_weather(load_fixture("zero-and-none.json"), timezone="Europe/Lisbon")

    assert snapshot.today.rain_mm == 0
    assert snapshot.today.rain_probability_pct == 0
    assert snapshot.today.wind_kph is None
    assert snapshot.tomorrow.uv_index is None
    assert snapshot.sunrise is None
    assert snapshot.sunset is None


@pytest.mark.parametrize(
    ("fixture", "timezone", "message"),
    [
        ("malformed-date.json", "Europe/Lisbon", "date"),
        ("wrong-units.json", "Europe/Lisbon", "unit"),
        ("normal.json", "UTC", "timezone"),
    ],
)
def test_parse_weather_rejects_inconsistent_provider_data(
    fixture: str, timezone: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        parse_weather(load_fixture(fixture), timezone=timezone)


def test_parse_weather_rejects_non_finite_numbers() -> None:
    payload = json.loads(load_fixture("normal.json"))
    payload["current"]["temperature_2m"] = float("nan")

    with pytest.raises(ValueError, match="finite"):
        parse_weather(json.dumps(payload, allow_nan=True).encode(), timezone="Europe/Lisbon")


def test_parse_weather_rejects_missing_required_arrays() -> None:
    payload = json.loads(load_fixture("normal.json"))
    del payload["daily"]["rain_sum"]

    with pytest.raises((ValueError, TypeError), match="rain_sum"):
        parse_weather(json.dumps(payload).encode(), timezone="Europe/Lisbon")


def test_accepts_live_open_meteo_dimensionless_uv_unit():
    payload = json.loads(load_fixture("normal.json"))
    payload["daily_units"]["uv_index_max"] = ""
    assert (
        parse_weather(json.dumps(payload).encode(), timezone="Europe/Lisbon").today.uv_index == 4.5
    )


def test_parse_weather_reads_optional_hourly_rain_and_wind() -> None:
    payload = json.loads(load_fixture("normal.json"))
    assert parse_weather(json.dumps(payload).encode(), timezone="Europe/Lisbon").hourly == []
    day = payload["daily"]["time"][0]
    payload["hourly_units"] = {"time": "iso8601", "rain": "mm", "wind_speed_10m": "km/h"}
    payload["hourly"] = {
        "time": [f"{day}T17:00", f"{day}T18:00"],
        "rain": [2.5, None],
        "wind_speed_10m": [30, 45.5],
    }

    hours = parse_weather(json.dumps(payload).encode(), timezone="Europe/Lisbon").hourly

    assert [(hour.at.hour, hour.rain_mm, hour.wind_kph) for hour in hours] == [
        (17, 2.5, 30.0),
        (18, None, 45.5),
    ]
    payload["hourly"]["rain"] = [2.5]
    with pytest.raises(ValueError):
        parse_weather(json.dumps(payload).encode(), timezone="Europe/Lisbon")
