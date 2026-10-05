# Data collection implementation plan

**Goal:** Obtain ICS calendars, configured weather and RSS data during scheduled refresh, persist last-good normalized facts, and render real data without AI.

**Architecture:** Existing one-process Python/Pillow app. Pure parser adapters consume bounded bytes; one shared HTTP fetcher validates and pins public destinations. SQLite stores per-source snapshots and freshness; the serial refresh merges those facts and renders cached screens. All image/status requests remain free of upstream calls.

**Tech stack:** Standard-library HTTP/SQLite, icalendar plus recurring-ical-events, feedparser, existing Pydantic/FastAPI/Pillow.

## Task ownership and sequence

1. Coordinator: public-address-pinned HTTP(S), manually validated redirects, size/time limits, sanitized failure codes; tests first. Settings and persistent source snapshots with configuration fingerprints. No URL/token in public status.
2. Luna calendar agent: pure ICS parser and synthetic fixtures covering aware/floating/all-day times, recurring instances/exceptions/cancellations, duplicates, overlapping events and bounded expansion. Existing T1/T2 interfaces accepted.
3. Luna adapter agent: pure Open-Meteo parser; configured coordinates only, original observation/forecast dates, unit/array validation. After acceptance, RSS/Atom parser and deterministic dedup/filtering.
4. Coordinator: source fetch/parse/publish isolation, valid-empty versus failure distinction, polling cadence and last-good snapshots; explicit demo/live mode with no synthetic fallback in live mode.
5. Coordinator: calendar all-day/end-time propagation, visible stale/not-configured states, date-preserving weather summaries and configurable forecast disruption thresholds. News eligibility is configured, not AI inferred.
6. Integration/review: fixture-only tests, failure/restart/source-removal and mode-transition tests, no upstream calls during requests. Astra major review; full tests/lint/format/types, Alpine build and memory exercise below existing 190 MiB cap.

## Open configuration

Home location/coordinates and preferred feeds have been requested. Until supplied, the weather adapter is available but disabled and RSS is only user-configured. Calendar URLs stay in the user's local environment. No real calendar URL or family detail enters fixtures/docs. AI stays disabled and no AI code is added.

## Success criteria

A configured source populates the three screen contexts; upstream failures preserve last-good facts and show freshness honestly. Removed or changed sources cannot reuse another source's cache. Valid empty calendars clear old commitments. The live mode never displays demo facts. Bounds and privacy are tested with synthetic fixtures, and memory is remeasured with the data pipeline loaded.
