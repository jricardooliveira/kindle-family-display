# ADR 0001: Server-rendered cached PNGs for Kindle

- Status: Rendering engine superseded by ADR 0003; cached PNG architecture retained
- Date: 2026-10-04

## Context
An older Kindle is a constrained display device. Device model and software path are not yet confirmed. The family needs a few stable screens, button navigation, and roughly 30-minute content refreshes.

## Decision
Render fixed HTML templates on the Beelink, capture them to configured-size grayscale PNGs, cache them, and expose stable HTTP routes. Kindle requests only retrieve cached images. Use Playwright/Chromium in the app image initially; split it into a local renderer container only if resource or packaging tests justify it.

## Consequences
- Device-specific complexity stays at the image-fetch/display edge; application logic remains replaceable.
- Large type, grayscale conversion and exact dimensions are controlled centrally.
- Chromium adds image size/memory cost; measure on N100.
- Exact Kindle compatibility, jailbreak/KOReader and refresh mechanism remain a Phase 0 hardware validation.
- Do not render or call external APIs synchronously for image requests.
