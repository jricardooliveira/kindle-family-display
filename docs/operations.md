# Operations

## Startup and refresh

The demo needs no secrets or external network access. First startup renders missing screens; subsequent starts reuse valid matching cached images without claiming a new render time. Refresh runs serially about every 30 minutes. Only one Uvicorn worker/container should use the volumes.

`/healthz` reports process liveness; use `/api/status` for actual screen availability, age and render failures. A failed refresh keeps the last good image and its generation timestamp. On a first-ever failure a missing screen returns a service-unavailable response rather than an invented image. The Kindle's own copy should also remain visible if HTTP retrieval fails.

The service is currently a synthetic demo. Never interpret fixture temperatures, commitments or headlines as real information. AI is not yet implemented and stays disabled.

## Persistence and backup

Compose stores SQLite data in `app-data` and PNGs in `render-cache`. Both volumes form one cache and must be backed up together while the service is stopped. Use `docker compose stop`, back up both named volumes with your normal Docker backup tooling, then `docker compose start`. Do not use `docker compose down -v` unless you intend to erase the cache.

Restore both volumes together with the service stopped, preserve ownership for UID 10001, then start the app. If you intentionally discard the demo cache, remove both volumes and restart to regenerate it. Actual calendar storage and its backup policy belong to T4.

## Exposure and updates

Bind localhost by default. To use a Kindle, set `BIND_ADDRESS` to the host's private LAN IP and restrict access with the host firewall. No authentication or public internet deployment is supplied.

Builds install hash-locked runtime packages from `requirements.lock`. Review and regenerate the lock deliberately when updating dependencies, then rerun tests and the container memory exercise. There is no browser installed. The root filesystem is read-only, capabilities are dropped and the app runs as UID 10001; only the data/cache volumes and a small temporary filesystem are writable.

The 190 MiB cap is a guardrail, not proof of sufficient memory on every host or future feature set. See resource validation before enabling new collectors or changing supported dimensions.

## Live sources

Set `demo_mode=false` and configure calendar/RSS tables plus optional weather coordinates in `config.toml`. Restart the container after edits. Keep `config.toml`, `.env` and key files private and excluded from backups intended for sharing. The data volume contains normalized calendar titles and times; the cache volume contains rendered family information. Both require private storage and backups.

Source status exposes IDs, success/attempt timestamps, safe failure codes and item counts. It never exposes subscription URLs or event content. A valid empty calendar replaces old facts. Fetch failure preserves the last successful snapshot with a visible stale notice. Removing/changing a source clears its facts and invalidates images. No network access occurs in image/status handlers.

Calendar acquisition expands a bounded 14-day horizon. Calendar view shows today/tomorrow; Family uses upcoming commitments. Open-Meteo dates are retained during outages. Forecast disruption thresholds indicate forecasts, not official meteorological warnings. RSS entries are sanitized and limited to recent stories; only configured sources are fetched, and embedded media or linked pages are never fetched. World news eligibility must be explicitly configured with curated sources or keywords.

The default image refresh is 30 minutes; source polling is checked during those refreshes. Setting a source interval shorter than image refresh does not add extra polling jobs. All configured sources share one serial refresh worker.

## Configuration mount

Compose requires `config.toml` and mounts it read-only; copy `config.example.toml` for a new installation. The file must be readable by container UID/GID10001. On Debian, keep your user as owner and grant read access to the container group if needed: `sudo chgrp 10001 config.toml` then `chmod 640 config.toml`. The local macOS/Colima mount was verified readable with mode600. API keys are not mounted or used by the data collectors.

The previous local `.env` was preserved privately as `.env.before-config` during migration. It is ignored and excluded from builds; the active `.env` now only controls Docker port mapping. Edit source links and app settings in `config.toml`.
