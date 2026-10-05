# Agent-sized implementation tasks

Tasks are sequenced by dependencies; coordinator may parallelize tasks only when dependency and file ownership permit. “Verify” means run the task's specified checks; no real credentials or family data are needed.

| ID | Task | Owner role | Depends on |
|---|---|---|---|
| T0 | Confirm device facts, contracts, and settings decisions | Coordinator | — |
| T1 | Contracts and schema validation | Platform | T0 |
| T2 | FastAPI/Compose foundation and health/status | Platform | T1 |
| T3 | Three demo raster layouts, PNG rendering and cache | Display | T1 |
| T4 | ICS collection and Calendar screen data | Data | T2,T1 |
| T5 | Deterministic priority and layout selection | Decision | T1 |
| T6 | Weather adapter, cache and alert rules | Data | T2,T5 |
| T7 | RSS adapter and story filtering | Data | T2,T5 |
| T8 | Optional AI ranking adapter and fallback | Decision | T5,T7 |
| T9 | Kindle routes/status and device integration | Display | T2,T3 |
| T10 | Security hardening, operations docs, release review | Quality | T2-T9 |

## T0 — Confirm device facts and shared interfaces
**Files:** `PROJECT.md`, `contracts/openapi.yaml`, `ARCHITECTURE.md`.
**Acceptance:** exact known device facts recorded or explicitly marked unknown; screen dimensions configurable; endpoint names and normalized `DisplayItem`, `ProtectedAlert`, `DisplayDecision` agreed; no source credential enters docs. Do not block software work on physical access; use 800×600 placeholder until confirmed.

## T1 — Contracts and schema validation
**Files:** `app/contracts/`, `contracts/schemas/`, `contracts/openapi.yaml`, `tests/contracts/`.
**Acceptance:** schemas validate sample payloads and reject invalid severity/layout/item IDs; timestamps are timezone-aware; examples contain synthetic data only. Provide model fixtures for event, weather, news, status and decision.

## T2 — App and container foundation
**Files:** `app/main.py`, `app/config.py`, `app/jobs.py`, `compose.yaml`, `Dockerfile`, `pyproject.toml`, `.dockerignore`.
**Acceptance:** Compose builds and starts non-root app; `/healthz` and `/api/status` respond; SQLite/cache volumes persist; graceful shutdown closes scheduler/client; missing optional secrets do not prevent startup; config errors are actionable.

## T3 — Demo rendering and cached screens
**Files:** `app/rendering/`, `app/storage/`, `tests/rendering/`. Fixed Pillow layouts replace HTML/Chromium under ADR 0003.
**Acceptance:** synthetic fixtures render News/Weather, Family and Calendar at configured dimensions; output is PNG, grayscale, high contrast, and atomically cached; rendering failure keeps previous image; accessible text hierarchy and date/time header are present.

## T4 — ICS collector
**Files:** `app/collectors/ics.py`, `app/storage/`, `tests/collectors/test_ics.py`.
**Acceptance:** parses fixture calendars including all-day, timezone-aware, recurrence and cancellation cases; deduplicates by stable source/event identity; normalizes to contract; per-feed failures do not erase last good data; logs redact query strings/credentials.

## T5 — Deterministic decision engine
**Files:** `app/decision/rules.py`, `app/decision/layout.py`, `tests/decision/`.
**Acceptance:** severity ordering is critical > disruption > family/calendar > news > ambient; critical alerts are protected; selects at most 2–3 ordinary items; traffic/news do not appear absent configured significance; deterministic output for identical inputs.

## T6 — Weather adapter and alert rules
**Files:** `app/collectors/weather.py`, `app/decision/rules.py`, `tests/collectors/test_weather.py`.
**Acceptance:** provider-independent normalized weather model; location and key via settings; bounded timeout/body/retries; cache freshness recorded; fixture scenarios prove severe weather supersedes ordinary content and provider outage preserves last good image.

## T7 — RSS and news candidate pipeline
**Files:** `app/collectors/rss.py`, `app/decision/news.py`, `tests/collectors/test_rss.py`.
**Acceptance:** only configured feeds fetched; sanitize/strip HTML; deduplicate; retain source/time/category; Portugal/world categories; up to two stories selected; feed failure isolated and no ticker behavior.

## T8 — Optional AI selector
**Files:** `app/decision/ai.py`, `app/config.py`, `tests/decision/test_ai.py`.
**Acceptance:** disabled by default; strict structured response allows only supplied IDs and fixed layout enum; protected alerts always retained; timeout, provider error, invalid JSON or unknown IDs use deterministic fallback; AI is invoked by refresh jobs only, never image endpoints.

## T9 — Kindle interface and device validation
**Files:** `app/api/kindle.py`, `tests/api/test_kindle.py`, `docs/device-setup.md`.
**Acceptance:** stable screen PNG routes and current alias return `image/png` from cache; status JSON reports screen IDs, dimensions and update time; navigation cycle is News/Weather → Family → Calendar; device-specific setup is documented only after model confirmation.

## T10 — Hardening and V1 review
**Files:** configuration/docs/deployment/tests as needed.
**Acceptance:** review SSRF/redirect/IP restrictions, secret handling, logs, container privileges and dependencies; document backup/restore and stale-data behavior; run configured tests/lint/type checks; all PROJECT V1 criteria pass on Debian/N100 or limitations are recorded.

## Current implementation scope — 2026-10-04

The first delivery targets T0/T1/T2/T3/T5 and the software portion of T9. ADR 0003 replaces browser rendering with Pillow to address the requested memory budget. T0 hardware and provider facts remain explicitly unknown; 800×600 is still a placeholder.

T4/T6/T7 are implemented in the data collection slice below. T8 (AI), physical-device validation in T9, and full hardware release acceptance in T10 remain pending. The demo foundation does not claim the full V1 acceptance criteria. See `docs/resource-validation.md` for measured container evidence and host limitations.

### Verified demo foundation

- T0 software direction/interfaces recorded; hardware/provider facts remain open.
- T1 contracts and synthetic fixtures implemented; aware timestamps, IDs, severity/layout and protected selection validated.
- T2 app/container lifecycle implemented; Compose health, persistent volumes and restart checked.
- T3 three fixed grayscale layouts implemented; dimensions, rotation, text/overflow and failure preservation checked.
- T5 core deterministic ranking and critical protection implemented; source significance policies will be integrated with T6/T7.
- T9 cached image/status routes implemented; physical navigation/client validation remains pending.
- T10 container restrictions and demo operations reviewed; full V1 release acceptance remains pending collectors/device validation.

Evidence: 61 tests passed on host and Alpine; lint/format/types passed. Final memory peaks were 54.75 MB (800×600) and 76.91 MB (1600×1600 with rotation), with no OOM/limit-hit events. Detailed workload and hardware caveats are in `docs/resource-validation.md`.

### Data collection slice — 2026-10-04

T4/T6/T7 now include pure bounded ICS/Open-Meteo/RSS parsers and persistent per-source snapshots. Live configuration uses the private family calendar, home-town weather and an editable RTP Portuguese default. AI remains deferred. Pipeline and rendering tests cover failure retention, valid-empty clearing, removal/configuration changes, original weather dates and calendar all-day/overlap behavior. Host verification: 156 tests, lint, formatting and types pass. Final eight-source workload peaks: 66.40 MB at 800×600 and 84.40 MB at 1600×1600/90°, with zero OOM/limit-hit events; see resource validation for exact evidence. Hardware validation remains pending.

### Editable configuration — 2026-10-04

Application settings and source URLs can be edited in private `config.toml`. `config.example.toml` provides documented defaults. File loading is bounded and validated with secret-safe errors; explicit overrides/environment take precedence and legacy .env remains supported. Compose mounts the file read-only and keeps deployment port mappings separately configurable. API keys remain separate and AI remains disabled.

Validation: 166 host tests, lint, formatting and types pass. Rebuilt Alpine Compose service successfully reads the private file through its read-only mount and reports successful calendar/weather/RSS source snapshots.

### Identified Kindle — 2026-10-04

Paperwhite 11th generation (PW5) recorded. Native 1236×1648 portrait output configured and verified in running Compose. Renderer/settings support both axes through 1648, including 90° rotation; 170 host tests and lint/format/types pass. Eight-source resource workload peaked 76.39MB at native size and 87.68MB at 1648×1648/90°, without OOM events. Firmware/client setup and physical display validation remain pending.
