# ADR 0003: Fixed raster layouts for the low-memory target

- Status: Accepted
- Date: 2026-10-04
- Supersedes: ADR 0001 rendering engine choice (cached PNG architecture retained)

## Context
The implementation request targets less than 200 MB RAM for the container. The three fixed e-ink screens need typography and simple lines, not browser layout. Python already supplies the scaffold and validation tools.

## Decision
Keep Python on the official Python 3.12 Alpine image. Binary Python wheels, DejaVu fonts and timezone data were verified locally. Draw fixed grayscale screens directly with Pillow and DejaVu fonts. Remove Chromium, Playwright and browser system dependencies. Keep one Uvicorn worker, one serial refresh job, SQLite through the standard library, and atomic PNG cache publication. Bound screen dimensions to limit allocations. Default Compose memory ceiling is 190 MiB (199,229,440 bytes), with swap disabled.

## Consequences
RAM feasibility must be measured during refresh and request load, not inferred from a limit. Simple layouts require explicit wrapping/truncation and visual review. HTML templates are no longer used; the preview endpoint returns the same PNG. Go remains an option only if measurements later justify a rewrite. Live collectors and AI need their own memory/security acceptance before enabling them.
