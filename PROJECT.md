# Kindle Family Dashboard

## Product goal
Repurpose an older Kindle as a calm, glanceable family information display. A lightweight app runs on a Debian Beelink N100 and serves rendered, cached e-ink-friendly images. The device should normally show only the 2–3 most useful items, with date/time always visible.

## Product principles
- Contextual, uncluttered and family-first; never a scrolling news ticker.
- Critical facts and alerts are deterministic and cannot be hidden by AI.
- AI is optional, bounded to selecting/ranking/summarizing supplied facts, and never authors factual data.
- Local-first and low-maintenance: one main app container, SQLite, one scheduler; fixed Pillow raster layouts avoid a Chromium process (ADR 0003).
- Graceful degradation: stale cached image remains available if a collector or AI provider fails.

## Audience and locale
Families in Portugal, the United Kingdom and Germany. Portuguese (`pt`), English
(`en`) and German (`de`) have equal built-in display, date, weather, alert, fact and
demo support. Language, country and IANA timezone are independent settings; legacy
configs default to Portuguese/Portugal/Europe/Lisbon. Public starter configs use
Lisbon, London or Berlin as explicitly labeled example locations. Family names and
source content remain private configuration; examples use synthetic names.

## V1 goals and priorities
1. Prove Kindle can retrieve and display a PNG from the Beelink; the Kindle is a Paperwhite 11th generation (PW5), with native portrait resolution 1236×1648. Firmware 5.16.7 and existing jailbreak/KOReader installation confirmed; client navigation and refresh integration remain pending.
2. Three screens: **News/Weather**, **Family**, **Calendar**. The Paperwhite uses touch navigation between these views; automatic content refresh is about every 30 minutes, independently of navigation.
3. Shared ICS calendars; weather including current/today/tomorrow, rain/wind/temperature and sunrise/sunset; trusted RSS news from Portugal and major world events; date/time.
4. Adaptive composition normally selects 2–3 items. Weather/traffic disruption can dominate the News/Weather view. Calendar view shows time, title and family member across today/tomorrow.
5. Critical alerts override ordinary content. Priority order: critical changes; weather/traffic disruption; family/calendar commitments; important Portugal/world news; low-priority ambient content.
6. AI can choose among a small fixed set of layouts and select supplied item IDs. Rule-based behavior remains available without an AI key.

## Screens
- **News/Weather:** permanent date/time header; normally weather plus 0–2 trusted Portugal/world stories; weather warning takes precedence when warranted. Traffic is hidden unless a configured route has a meaningful disruption.
- **Family:** next important family item/countdown, birthdays/anniversaries, important school dates/trips/closures. When space and relevance permit: daily family photo, Catholic Portuguese Bible verse, or rotating fun fact. Never show a long list of countdowns.
- **Calendar:** today and tomorrow, ordered by start time; show time, title, person. Filter routine school-calendar noise; surface important closures/trips. Dates/events are configured from ICS feeds.

## Later priorities (not V1 blockers)
- V2: countdowns, Bible verse, fun fact, manually managed photo folder.
- V3: traffic disruption alerts, nearby weekend events, travel countdown/weather/status.
- V4: usage learning and richer adaptive behavior.
- Personal/work mode with AI, coding agents, developer productivity, cloud/platform/security news is a possible future mode, not part of family V1.

## Data sources
- ICS calendars: configured private URLs; poll every 15–30 minutes. Never commit actual URLs. Shared Apple Reminders are optional and need a separate feasibility decision.
- Weather: provider adapter using configured home coordinates; Open-Meteo selected; home town configured privately.
- News: allowlisted RSS feeds; national news for the configured country and major
  world stories. Ready-to-run presets use RTP País (PT), BBC UK (GB), and Tagesschau
  Inland (DE). `national` is country-neutral; legacy `portugal` is retained. Fetch
  many, show at most two in the weather layout (up to four in the news digest).
- Optional later adapters: traffic, nearby events, travel/flight status, verse provider, photo directory.
- Optional AI API: supplied normalized context only; avoid a request for every Kindle image fetch. Run on changed/expired decision, cache output, and enforce timeout/fallback.

## Non-functional requirements
- Runs on Debian Docker/Compose and modest N100 hardware. Target below 200 MB container RAM, including rendering; verify peaks and OOM events, not only idle RSS.
- Kindle endpoints serve promptly from pre-rendered cache; do not make external API/AI calls during image requests.
- Screen dimensions and rotation are configuration values until hardware is confirmed. Output grayscale, high contrast, large type, no animation.
- UTC-aware storage; render in configured local timezone. Bound HTTP timeouts, response sizes, retries and collection cadence.
- SQLite on a persistent volume; no separate database server, queue, Redis, Kubernetes or Home Assistant dependency.
- Private services stay on the LAN by default; no unauthenticated internet exposure.

## V1 acceptance
Compose starts the app; health/status endpoints work; demo mode produces three valid cached PNGs; each Kindle endpoint returns a PNG without upstream calls; fixtures exercise ICS/weather/RSS normalization; rules guarantee critical-alert precedence; AI disabled or invalid output falls back safely; config and runbook explain setup without disclosing secrets.

## Open decisions (do not block scaffolding)
1. Paperwhite 11th generation confirmed; native portrait 1236×1648 configured. Firmware 5.16.7 and existing jailbreak/KOReader installation confirmed. KOReader version, final orientation, touch navigation and refresh strategy remain open.
2. Weather uses Open-Meteo without an API key; home coordinates are local configuration.
3. RTP País, BBC UK and Tagesschau Inland are the editable PT/GB/DE starter sources;
   world feed/significance preferences remain open.
4. AI vendor/model and budget; default is disabled until configured.
5. Calendar feed count, labels, privacy classification, and importance overrides.
6. Exact Portuguese Bible translation/source and licensing; whether this belongs in V2.
7. How family photos are mounted and which file types are allowed.
