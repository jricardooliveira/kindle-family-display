# English quick start

Install Docker with Docker Compose on a home server. After cloning, run these
commands from the repository directory. A browser is enough to try it; no Kindle,
calendar, account or API key is required.

```sh
cp config.en.example.toml config.toml
mkdir -p photos calendars secrets
docker compose up --build -d
```

Open [news and weather](http://127.0.0.1:8000/kindle/news-weather.png) or
[family](http://127.0.0.1:8000/kindle/family.png) on the server.
The preset uses English, `Europe/London`, **London** weather and **BBC UK** news.
Without a calendar, the family page shows weather and a daily fact.
[Status](http://127.0.0.1:8000/api/status) reports source errors and update times.

For an offline demo, set `demo_mode = true` in `config.toml`; this renders
synthetic English content without upstream requests. The initial Docker build
still needs Internet access. Set it back to `false` for live data.

After editing, restart with `docker compose up -d --force-recreate`.

## Customize

- `language = "pt"`, `"en"` or `"de"` controls built-in display text.
- `country = "PT"`, `"GB"` or `"DE"` controls national news labels and optional
  AI relevance. Language, country and timezone are independent.
- Replace the example weather coordinates and label with your town. There is
  no automatic location detection.
- `config.example.toml` documents calendars, dimensions and other settings.
  Source headlines, calendar entries, names and photo captions stay in their
  original language. Changing language does not replace configured feeds.
- The default size is 800×600; for a landscape Paperwhite 11 use width 1648,
  height 1236 and rotation 90.

`config.toml` is private and ignored by Git. Environment variables override its
settings. Live feeds need Internet access; outages retain last-good data.

## Connect a Kindle

Set `BIND_ADDRESS` in `.env` to the server's LAN address and restart. Keep the
service on your home network; it has no login. Follow the
[Kindle setup](../README.md#kindle-setup) for KOReader and its TRMNL plugin.

The preset uses the [BBC's RSS service](https://support.bbc.co.uk/platform/feeds/NewsFeeds.htm).
Add other feeds in `config.toml`: `national` uses the selected country; `world`
needs `curated = true` or explicit `keywords`. Publisher terms apply.

Other starters: [Deutsch](setup.de.md) · [Português](setup.pt.md).
