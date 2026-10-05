from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, load_settings
from app.contracts import DisplayContext, NewsItem


@pytest.mark.parametrize("language,country", [("pt", "PT"), ("en", "GB"), ("de", "DE")])
def test_language_and_country_load_independently(tmp_path, language, country):
    path = tmp_path / "config.toml"
    path.write_text(f'language="{language}"\ncountry="{country}"\ntimezone="UTC"\n')
    config = load_settings(path, _env_file=None)
    assert (config.language, config.country, config.timezone) == (language, country, "UTC")
    assert Settings(_env_file=None, language=language, country="PT").country == "PT"


def test_legacy_settings_and_context_remain_portuguese():
    assert Settings(_env_file=None).language == "pt"
    assert Settings(_env_file=None).country == "PT"
    context = DisplayContext(generated_at=datetime.now(UTC), timezone="UTC", items=[])
    assert context.language == "pt"


@pytest.mark.parametrize("language,expected", [("pt", "3,5"), ("en", "3.5"), ("de", "3,5")])
def test_compact_number_decimal_separator(language, expected):
    from app.i18n import format_number

    assert format_number(3.5, language) == expected


@pytest.mark.parametrize("overrides", [{"language": "fr"}, {"country": "XX"}])
def test_unsupported_locale_is_rejected(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


def test_national_news_contract():
    assert (
        NewsItem(
            id="news",
            title="Example",
            published_at=datetime.now(UTC),
            source="fixture",
            category="national",
        ).category
        == "national"
    )


def test_switching_language_replaces_cached_demo(tmp_path):
    from app.main import create_app

    images = []
    for language in ("pt", "en", "de"):
        settings = Settings(
            _env_file=None,
            language=language,
            database_url=f"sqlite:///{tmp_path / 'app.db'}",
            cache_dir=str(tmp_path / "cache"),
        )
        with TestClient(create_app(settings)) as client:
            response = client.get("/kindle/calendar.png")
            assert response.status_code == 200
            images.append(response.content)
    assert len(set(images)) == 3


@pytest.mark.parametrize(
    "language,country,zone",
    [
        ("pt", "PT", "Europe/Lisbon"),
        ("en", "GB", "Europe/London"),
        ("de", "DE", "Europe/Berlin"),
    ],
)
def test_country_starter_runs_without_accounts(tmp_path, language, country, zone):
    from app.main import SCREENS, create_app

    config = load_settings(
        f"config.{language}.example.toml",
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        cache_dir=str(tmp_path / "cache"),
    )
    assert (config.language, config.country, config.timezone) == (language, country, zone)
    assert not config.demo_mode
    assert not config.ai_enabled
    assert len(config.rss_feeds) == 1
    assert config.rss_feeds[0].category == "national"
    calls = []

    def fetch(url):
        calls.append(url)
        if "open-meteo" in url:
            return Path("tests/fixtures/weather/normal.json").read_bytes()
        return Path("tests/fixtures/rss/sample-rss.xml").read_bytes()

    with TestClient(create_app(config, fetcher=fetch)) as client:
        assert client.get("/healthz").json() == {"ok": True}
        count = len(calls)
        assert count == 2
        for screen in SCREENS:
            response = client.get(f"/kindle/{screen}.png")
            assert response.status_code == 200
            assert response.content.startswith(b"\x89PNG")
        assert len(calls) == count
