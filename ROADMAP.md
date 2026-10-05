# Roadmap

## Phase 0 — Confirm device and interfaces
Identify Kindle model/firmware/resolution and the intended image-display method. Agree on data contracts, configuration shape, and LAN boundary. Keep rendering dimension configurable while device details are pending.

## Phase 1 — Bootable skeleton and demo screens
Build Compose app, settings, SQLite connection, health/status routes, scheduler shell, demo fixture data, three HTML screens, PNG renderer and cached Kindle routes. Acceptance: clean install produces three correctly sized grayscale PNGs and image fetches do no upstream work.

## Phase 2 — Calendar first
Implement configurable ICS polling, timezone-aware normalization, deduplication, today/tomorrow calendar screen, importance overrides and privacy-safe logs. Acceptance: fixture tests for all-day, recurring/timezone-aware events and stale/failing feed behavior.

## Phase 3 — Weather and rules
Add provider adapter and weather cache, sunrise/sunset and deterministic significance rules. Define severity thresholds in settings. Acceptance: warning dominates normal content; provider failure leaves last good value/image.

## Phase 4 — Trusted news and optional AI
Add allowlisted RSS ingestion, deduplication and relevance signals; cap displayed stories at two. Add optional strict-schema AI selection over supplied candidates, protected alert IDs, timeout/budget controls and deterministic fallback. Acceptance: disabled/invalid AI produces a valid view without losing alerts.

## Phase 5 — Family view and Kindle operation
Add important family events and screen navigation contract. Validate real Kindle download/display, refresh cadence, buttons, orientation and grayscale on the actual device. Add runbook and backup procedure.

## Phase 6 — V2/V3 extensions
Only after stable V1: photo folder, licensed verse source, fun facts; then traffic, events and travel adapters. Each source remains optional and cannot block core screens.

## Phase 7 — Adaptive learning
Consider opt-in usage history and richer selection after gathering real usage feedback. Keep learning explainable, local, resettable, and subordinate to explicit priorities.
