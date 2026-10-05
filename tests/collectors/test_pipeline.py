from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.collectors.pipeline import DataPipeline
from app.config import Settings
from app.contracts import SourceStatus
from app.storage.sources import SourceCache

FIXTURES = Path(__file__).parents[1] / "fixtures"
NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def settings_for(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'sources.db'}",
        timezone="Europe/Lisbon",
        calendar_days=14,
        calendar_feeds=[
            {
                "id": "family-cal",
                "url": "https://calendar.example.test/family.ics?secret=private",
                "person": "Alex",
            }
        ],
        rss_feeds=[
            {
                "id": "portugal-news",
                "url": "https://news.example.test/pt.xml",
                "category": "portugal",
            },
            {
                "id": "world-news",
                "url": "https://news.example.test/world.xml",
                "category": "world",
                "keywords": ["escolas"],
            },
        ],
        weather_latitude=38.72,
        weather_longitude=-9.14,
        weather_location="Lisboa",
    )


def event_calendar(
    day: int, *, title: str = "Family visit", empty: bool = False, all_day: bool = False
) -> bytes:
    if empty:
        return b"BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR\n"
    if all_day:
        return (
            "BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:visit\n"
            f"DTSTART;VALUE=DATE:202610{day:02d}\n"
            f"DTEND;VALUE=DATE:202610{day + 1:02d}\nSUMMARY:{title}\n"
            "END:VEVENT\nEND:VCALENDAR\n"
        ).encode()
    return (
        "BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:visit\n"
        f"DTSTART;TZID=Europe/Lisbon:202610{day:02d}T090000\n"
        f"DTEND;TZID=Europe/Lisbon:202610{day:02d}T100000\nSUMMARY:{title}\n"
        "END:VEVENT\nEND:VCALENDAR\n"
    ).encode()


def payloads(*, calendar: bytes | None = None) -> dict[str, bytes]:
    return {
        "https://calendar.example.test/family.ics?secret=private": calendar or event_calendar(5),
        "https://news.example.test/pt.xml": fixture("rss/sample-rss.xml"),
        "https://news.example.test/world.xml": fixture("rss/sample-atom.xml"),
        "https://api.open-meteo.com/v1/forecast?latitude=38.72&longitude=-9.14&timezone=Europe%2FLisbon&temperature_unit=celsius&wind_speed_unit=kmh&precipitation_unit=mm&current=temperature_2m%2Cwind_speed_10m%2Cweather_code&daily=temperature_2m_max%2Ctemperature_2m_min%2Crain_sum%2Cprecipitation_probability_max%2Cwind_speed_10m_max%2Csunrise%2Csunset%2Cuv_index_max%2Cweather_code&forecast_days=2&hourly=rain%2Cwind_speed_10m": fixture(
            "weather/normal.json"
        ),
    }


def test_pipeline_collects_and_maps_configured_sources_without_leaking_urls(tmp_path):
    settings = settings_for(tmp_path)
    source_cache = SourceCache(settings.database_url)
    fetches: list[str] = []
    bodies = payloads()

    def fetcher(url: str) -> bytes:
        fetches.append(url)
        return bodies[url]

    pipeline = DataPipeline(settings, source_cache, fetcher=fetcher)
    context = pipeline.collect(NOW)

    assert context.demo is False
    assert context.timezone == "Europe/Lisbon"
    assert {item.kind for item in context.items} == {"calendar", "weather", "news", "fact"}
    event = next(item for item in context.items if item.kind == "calendar")
    assert event.title == "Family visit"
    assert event.person == "Alex"
    assert event.ends_at is not None
    assert not event.all_day
    weather = next(item for item in context.items if item.kind == "weather")
    assert "2026-10-04" in weather.summary
    assert "2026-10-05" in weather.summary
    assert "18.4" in weather.summary
    assert "22.1" in weather.summary
    assert "4.2" in weather.summary
    assert "vento 18km/h" in weather.summary
    assert "07:30" in weather.summary
    assert "19:15" in weather.summary
    assert len(weather.summary) <= 280
    stories = [item for item in context.items if item.kind == "news"]
    assert [item.title for item in stories][:2] == [
        "Portugal anuncia novas medidas",
        "Escolas preparam novas atividades",
    ]
    assert len(stories) <= 4
    assert len(fetches) == 4
    assert all("secret=private" not in warning for warning in context.source_warnings)
    assert all(isinstance(status, SourceStatus) for status in pipeline.source_status(NOW))
    assert all("secret=private" not in str(status) for status in pipeline.source_status(NOW))
    source_cache.close()


def test_pipeline_respects_polling_intervals(tmp_path):
    settings = settings_for(tmp_path)
    cache = SourceCache(settings.database_url)
    bodies = payloads()
    fetches: list[str] = []
    pipeline = DataPipeline(settings, cache, fetcher=lambda url: fetches.append(url) or bodies[url])

    pipeline.collect(NOW)
    pipeline.collect(NOW + timedelta(minutes=10))

    assert len(fetches) == 4
    cache.close()


def test_outage_keeps_last_good_events_and_restart_uses_cached_facts(tmp_path):
    settings = settings_for(tmp_path)
    cache = SourceCache(settings.database_url)
    good = payloads()
    DataPipeline(settings, cache, fetcher=lambda url: good[url]).collect(NOW)
    cache.close()

    reopened = SourceCache(settings.database_url)
    failed_pipeline = DataPipeline(
        settings,
        reopened,
        fetcher=lambda _url: (_ for _ in ()).throw(TimeoutError("private exception text")),
    )
    context = failed_pipeline.collect(NOW + timedelta(hours=2))

    assert any(item.title == "Family visit" for item in context.items)
    assert context.source_warnings
    assert "private exception text" not in str(failed_pipeline.source_status(NOW))
    assert all(status.last_success_at is not None for status in failed_pipeline.source_status(NOW))
    next_day = datetime(2026, 10, 5, 12, tzinfo=UTC)
    failed_pipeline.collect(next_day)
    weather_status = next(
        status for status in failed_pipeline.source_status(next_day) if status.kind == "weather"
    )
    assert weather_status.stale
    reopened.close()


def test_valid_empty_calendar_clears_old_events_and_source_removal_clears_snapshot(tmp_path):
    settings = settings_for(tmp_path)
    cache = SourceCache(settings.database_url)
    bodies = payloads()
    DataPipeline(settings, cache, fetcher=lambda url: bodies[url]).collect(NOW)

    empty_bodies = payloads(calendar=event_calendar(5, empty=True))
    second = DataPipeline(settings, cache, fetcher=lambda url: empty_bodies[url]).collect(
        NOW + timedelta(minutes=31)
    )
    assert not any(item.kind == "calendar" for item in second.items)

    reduced = Settings(
        _env_file=None,
        database_url=settings.database_url,
        timezone=settings.timezone,
        rss_feeds=settings.rss_feeds,
    )
    DataPipeline(reduced, cache, fetcher=lambda _url: b"").collect(NOW + timedelta(hours=3))
    assert all(row["kind"] == "rss" for row in cache.records())
    cache.close()


def test_unconfigured_kinds_are_explicitly_unavailable_and_no_fetch_occurs(tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'empty.db'}")
    cache = SourceCache(settings.database_url)
    calls: list[str] = []
    context = DataPipeline(settings, cache, fetcher=lambda url: calls.append(url) or b"").collect(
        NOW
    )

    assert context.unavailable_kinds == ["calendar", "weather", "rss"]
    assert calls == []
    cache.close()


def test_pipeline_preserves_all_day_exclusive_end_and_protected_forecast_thresholds(tmp_path):
    settings = settings_for(tmp_path).model_copy(
        update={"weather_rain_disruption_mm": 4, "weather_wind_disruption_kph": 17}
    )
    cache = SourceCache(settings.database_url)
    bodies = payloads(calendar=event_calendar(5, all_day=True))
    pipeline = DataPipeline(settings, cache, fetcher=lambda url: bodies[url])

    context = pipeline.collect(NOW)
    event = next(item for item in context.items if item.kind == "calendar")
    alerts = [item for item in context.items if item.kind == "alert"]

    assert event.all_day
    assert event.ends_at is not None
    assert event.ends_at.astimezone(ZoneInfo("Europe/Lisbon")).date().isoformat() == "2026-10-06"
    assert len(alerts) == 1
    assert alerts[0].is_protected
    assert alerts[0].severity == "disruption"
    assert alerts[0].title == "Chuva e vento fortes"
    assert [(fact.label, fact.value) for fact in alerts[0].facts] == [
        ("Dia", "Hoje"),
        ("Chuva", "4.2 mm"),
        ("Vento", "18 km/h"),
    ]
    assert context.weather is not None
    assert context.people == ["Alex"]
    assert context.protected_alert_ids == [alerts[0].id]

    next_day = pipeline.collect(datetime(2026, 10, 5, 12, tzinfo=UTC))
    assert not any(
        item.kind == "alert" and item.id == "weather-alert:2026-10-04" for item in next_day.items
    )
    cache.close()


def test_calendar_configuration_change_invalidates_cached_normalization(tmp_path):
    settings = settings_for(tmp_path)
    cache = SourceCache(settings.database_url)
    first_bodies = payloads()
    DataPipeline(settings, cache, fetcher=lambda url: first_bodies[url]).collect(NOW)
    original = cache.get("family-cal")
    assert original is not None and original["data"] is not None

    changed = Settings(
        _env_file=None,
        database_url=settings.database_url,
        timezone="UTC",
        calendar_days=20,
        calendar_feeds=[
            {
                "id": "family-cal",
                "url": "https://calendar.example.test/family.ics?secret=private",
                "person": "Alex",
            }
        ],
    )
    changed_pipeline = DataPipeline(changed, cache, fetcher=lambda _url: event_calendar(5))
    reset = cache.get("family-cal")
    assert reset is not None
    assert reset["fingerprint"] != original["fingerprint"]
    assert reset["data"] is None
    changed_pipeline.collect(NOW)
    recovered = cache.get("family-cal")
    assert recovered is not None and recovered["data"] is not None
    cache.close()


def test_calendar_and_weather_refresh_once_when_local_date_changes(tmp_path):
    settings = settings_for(tmp_path).model_copy(
        update={
            "calendar_poll_minutes": 1440,
            "weather_poll_minutes": 1440,
            "rss_poll_minutes": 1440,
        }
    )
    cache = SourceCache(settings.database_url)
    bodies = payloads()
    fetches: list[str] = []
    pipeline = DataPipeline(settings, cache, fetcher=lambda url: fetches.append(url) or bodies[url])

    before_midnight = datetime(2026, 10, 4, 22, 55, tzinfo=UTC)
    after_midnight = datetime(2026, 10, 4, 23, 5, tzinfo=UTC)
    pipeline.collect(before_midnight)
    pipeline.collect(after_midnight)

    assert len(fetches) == 6
    cache.close()


def test_failed_rss_source_still_respects_its_polling_interval(tmp_path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'rss.db'}",
        rss_feeds=[
            {"id": "rss-only", "url": "https://news.example.test/rss", "category": "portugal"}
        ],
    )
    cache = SourceCache(settings.database_url)
    calls: list[str] = []

    def unavailable(url: str) -> bytes:
        calls.append(url)
        raise TimeoutError("safe synthetic timeout")

    pipeline = DataPipeline(settings, cache, fetcher=unavailable)
    pipeline.collect(NOW)
    pipeline.collect(NOW + timedelta(minutes=30))
    assert len(calls) == 1
    pipeline.collect(NOW + timedelta(minutes=60))
    assert len(calls) == 2
    cache.close()


def test_same_day_old_weather_observation_is_stale_even_after_successful_fetch(tmp_path):
    settings = settings_for(tmp_path)
    cache = SourceCache(settings.database_url)
    bodies = payloads()
    pipeline = DataPipeline(settings, cache, fetcher=lambda url: bodies[url])
    from datetime import timedelta

    later = NOW + timedelta(hours=3)
    pipeline.collect(later)
    weather = next(source for source in pipeline.source_status(later) if source.kind == "weather")
    assert weather.last_error is None
    assert weather.stale
    cache.close()


def test_pipeline_adds_one_daily_curiosity_and_marks_the_night_period(tmp_path):
    settings = settings_for(tmp_path)
    cache = SourceCache(settings.database_url)
    bodies = payloads()
    pipeline = DataPipeline(settings, cache, fetcher=lambda url: bodies[url])

    day = pipeline.collect(NOW)
    night = pipeline.collect(datetime(2026, 10, 4, 22, 30, tzinfo=UTC))

    facts = [item for item in day.items if item.kind == "fact"]
    assert len(facts) == 1
    assert facts[0].label.startswith("Curiosidade · ")
    assert not day.night
    assert night.night
    cache.close()


def test_weather_alert_uses_hourly_data_to_say_when(tmp_path):
    from app.collectors.pipeline import _weather_items
    from app.contracts.models import WeatherHour, WeatherPeriod, WeatherSnapshot

    zone = ZoneInfo("Europe/Lisbon")
    observed = datetime(2026, 10, 4, 13, 0, tzinfo=zone)
    snapshot = WeatherSnapshot(
        observed_at=observed,
        timezone="Europe/Lisbon",
        source="fixture",
        current=WeatherPeriod(summary="Nublado", temperature_c=17),
        today=WeatherPeriod(rain_mm=32, wind_kph=20),
        tomorrow=WeatherPeriod(rain_mm=0, wind_kph=10),
        hourly=[
            WeatherHour(at=observed.replace(hour=hour), rain_mm=rain)
            for hour, rain in ((15, 0.2), (17, 6), (18, 12), (22, 3), (23, 0))
        ],
    )
    settings = settings_for(tmp_path).model_copy(update={"weather_rain_disruption_mm": 20})

    alert = next(
        item for item in _weather_items(snapshot, settings, observed) if item.kind == "alert"
    )

    assert alert.title == "Chuva forte"
    assert alert.label == "Tempo adverso · hoje"
    assert [(fact.label, fact.value) for fact in alert.facts] == [
        ("Das", "17:00"),
        ("Às", "23:00"),
        ("Previsão", "32 mm"),
    ]


def test_pipeline_offers_one_photo_a_day_with_a_caption_from_its_name(tmp_path):
    photos = tmp_path / "photos"
    photos.mkdir()
    (photos / "Ferias_no_Geres.jpg").write_bytes(b"x")
    (photos / "notes.txt").write_text("ignored")
    settings = settings_for(tmp_path).model_copy(update={"photos_dir": str(photos)})
    cache = SourceCache(settings.database_url)
    bodies = payloads()
    pipeline = DataPipeline(settings, cache, fetcher=lambda url: bodies[url])

    even = pipeline.collect(datetime(2026, 10, 4, 14, 0, tzinfo=ZoneInfo("Europe/Lisbon")))
    odd = pipeline.collect(datetime(2026, 10, 4, 15, 0, tzinfo=ZoneInfo("Europe/Lisbon")))

    photo = next(item for item in even.items if item.kind == "photo")
    assert photo.title == "Ferias no Geres"
    assert photo.image_path.endswith("Ferias_no_Geres.jpg")
    assert photo.priority == 1
    assert next(item for item in odd.items if item.kind == "photo").priority == 0
    cache.close()


def test_photo_caption_ignores_camera_file_names():
    from pathlib import Path

    from app.collectors.pipeline import _photo_caption

    assert _photo_caption(Path("IMG_1234.jpg")) == "Foto do dia"
    assert _photo_caption(Path("2024-08-01.png")) == "Foto do dia"
    assert _photo_caption(Path("natal-2024-avos.jpg")) == "natal 2024 avos"


def test_pipeline_marks_digest_periods_from_configuration(tmp_path):
    settings = settings_for(tmp_path).model_copy(update={"news_digest_windows": ["12:30-13:30"]})
    cache = SourceCache(settings.database_url)
    bodies = payloads()
    pipeline = DataPipeline(settings, cache, fetcher=lambda url: bodies[url])
    zone = ZoneInfo("Europe/Lisbon")

    assert pipeline.collect(datetime(2026, 10, 4, 12, 45, tzinfo=zone)).news_digest
    assert not pipeline.collect(datetime(2026, 10, 4, 14, 0, tzinfo=zone)).news_digest
    cache.close()


def test_pipeline_ranks_news_by_ai_importance_and_scores_each_story_once(tmp_path):
    settings = settings_for(tmp_path).model_copy(update={"cache_dir": str(tmp_path / "cache")})
    cache = SourceCache(settings.database_url)
    bodies = payloads()
    calls: list[list[str]] = []

    def scorer(stories, topics):
        calls.append([story.id for story in stories])
        last = len(stories) - 1
        return {story.id: ((9 if index == last else 2), "") for index, story in enumerate(stories)}

    pipeline = DataPipeline(settings, cache, fetcher=lambda url: bodies[url], scorer=scorer)

    first = pipeline.collect(NOW)
    second = pipeline.collect(NOW)

    news = [item for item in first.items if item.kind == "news"]
    assert len(calls) == 1 and len(calls[0]) >= 2
    assert [item.id for item in news] == [calls[0][-1]]
    assert [item.id for item in second.items if item.kind == "news"] == [news[0].id]

    # A new process reuses the saved scores instead of paying to score again.
    restarted = DataPipeline(settings, cache, fetcher=lambda url: bodies[url], scorer=scorer)
    assert [item.id for item in restarted.collect(NOW).items if item.kind == "news"] == [news[0].id]
    assert len(calls) == 1

    other = settings.model_copy(update={"cache_dir": str(tmp_path / "other")})
    silent = DataPipeline(other, cache, fetcher=lambda url: bodies[url], scorer=lambda s, t: {})
    assert len([item for item in silent.collect(NOW).items if item.kind == "news"]) >= 2
    cache.close()


def test_pipeline_shows_one_story_per_topic_and_cleans_live_blog_titles(tmp_path):
    from app.collectors.pipeline import _news_title

    settings = settings_for(tmp_path).model_copy(update={"cache_dir": str(tmp_path / "cache")})
    cache = SourceCache(settings.database_url)
    bodies = payloads()
    same_topic = DataPipeline(
        settings,
        cache,
        fetcher=lambda url: bodies[url],
        scorer=lambda stories, topics: {story.id: (8, "mesmo tema") for story in stories},
    )

    assert len([item for item in same_topic.collect(NOW).items if item.kind == "news"]) == 1
    assert _news_title("7h. Eleições no Brasil") == "Eleições no Brasil"
    assert _news_title("14h30. Greve") == "Greve"
    assert _news_title("7 homens detidos") == "7 homens detidos"
    cache.close()
