# Architecture

## Deployment
Debian on Beelink N100, Docker Compose with an Alpine-based image, one `kindle-hub` Python/FastAPI process. Pillow draws fixed grayscale layouts directly (ADR 0003); no browser process or renderer service is needed. SQLite lives on a persistent volume. APScheduler runs in-process (one replica only).

## Data flow
```text
ICS / weather API / allowlisted RSS
              ↓ scheduled collectors
     normalized facts + SQLite cache
              ↓ deterministic rules
     protected alerts + candidates
              ↓ optional AI ranking/layout
        validated display decision
              ↓ fixed Pillow layouts → grayscale PNG
              ↓ atomic cache replacement
       /kindle/*.png (LAN client)
```

Collectors never run in request handlers. Scheduler jobs normalize timestamps and source IDs, upsert current facts, then select and render the three cached screens. Each source obeys its polling cadence within the serial refresh. If decision-making/rendering fails, keep serving the last known good image. Demo mode renders synthetic facts. Live mode shows configured facts or an unavailable state, without synthetic fallback.

## Modules
- `app/main.py`: FastAPI app factory/lifespan and router registration.
- `app/config.py`: validated TOML configuration with environment/legacy .env overrides. Compose mounts the private file read-only.
- `app/contracts/`: Pydantic request/response and internal normalized models.
- `app/collectors/`: ICS, weather and RSS adapters; shared bounded HTTP client.
- `app/decision/`: deterministic alert rules, candidate ranking, optional AI adapter/schema validator.
- `app/rendering/`: fixed raster layouts, grayscale PNG generation and synthetic demo facts. `canvas.py` holds the scaled drawing primitives (bundled OFL fonts, weather icons, person badges, QR); `renderer.py` holds the landscape layouts from `design_handoff_kindle_landscape/` (designed at 800×600 and scaled to the configured size).
- `app/storage/`: SQLite metadata and atomic persistent PNG cache, using the standard library.
- `app/jobs.py`: APScheduler jobs and single-process guard.
- Health, status, preview and Kindle routes currently live in `app/main.py`.
- `app/rendering/`: fixed layouts; future AI returns a layout key, never executable markup.

## Runtime behavior
- Baseline refresh: roughly 30 minutes. ICS/weather 15–30 minutes, RSS about 60 minutes. Keep intervals configurable; respect provider limits.
- Decision cache is separate from screen request cache. Never spend AI tokens because a Kindle polls an image URL.
- Critical alerts are assembled by deterministic rules before AI. AI may reorder non-critical candidates but cannot remove protected IDs.
- Validate AI output against an allowlisted layout and existing item IDs. On timeout, malformed JSON, unavailable provider or budget disablement, choose deterministic layout/ranking.
- Store fetch timestamps and freshness; show “updated” time or stale indication where useful.
- Use content hashes/ETags and stable URLs. Write PNG to a temporary file then atomically replace the cache.

## API summary
See `contracts/openapi.yaml` and `contracts/schemas/`. Main routes: `GET /healthz`, `GET /api/status`, `GET /api/preview/{screen}`, `GET /kindle/current.png`, `GET /kindle/{news-weather|family|calendar}.png`, `GET /kindle/status.json`.

## Storage
SQLite stores screen metadata and per-source normalized events, news and weather snapshots. Source snapshots include attempt/success timestamps, safe error codes and opaque configuration fingerprints; valid empty updates replace old facts and failures retain last-good data. Keep raw upstream payload retention minimal; never store AI credentials in SQLite. Back up the volume and document restore. V1 may use a small schema without user accounts.

## Security and resilience
- Bind to LAN/localhost through deployment config; no public exposure by default.
- Treat calendar/feed URLs and all fetched content as untrusted. Restrict to HTTP(S), block loopback/private/link-local/metadata targets unless explicitly needed; re-check redirects and resolved IPs to reduce SSRF risk.
- Set connect/read timeouts, maximum body sizes, bounded retries, and per-source error isolation.
- Escape rendered text; never execute feed HTML. Render sanitized plain text.
- Secrets only through environment/secrets files excluded from version control. Use least-privilege container, non-root user, read-only root filesystem where compatible, writable data/cache mounts, pinned dependencies, and health checks.
- Do not log URLs with credentials, API keys, calendar content, or unnecessary family details.

## Resource profile
Single process and SQLite are appropriate for a home dashboard and N100. Keep scheduled work serial or bounded; use one scheduler instance. Rendering stays serial. Compose caps RAM at 190 MiB with swap disabled. Measure cgroup peak and OOM events on the deployment host; see docs/resource-validation.md for local evidence and limits.

## Implementation status
ICS, Open-Meteo and RSS/Atom acquisition now run during scheduled refresh with source isolation, bounded public-address-pinned HTTP and persistent last-good snapshots. AI is deferred and disabled. Fixed grayscale layouts support demo/live, all-day and overlapping calendar events, dated weather and source attribution. `/api/preview/{screen}` returns PNG, and `/kindle/current.png` aliases News/Weather until device navigation is confirmed.
