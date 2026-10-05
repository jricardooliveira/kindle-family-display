# ADR 0002: Deterministic rules with optional AI selection

- Status: Accepted
- Date: 2026-10-04

## Context
The user wants highly adaptive selection and layout, but family safety and factual reliability matter. The system should be lightweight and work without mandatory AI services.

## Decision
Deterministic rules identify and protect critical alerts and meaningful disruptions. An optional AI adapter may choose among supplied candidate IDs and an allowlisted set of fixed layouts, and may produce short summaries from supplied facts. It cannot invent facts, generate markup, discard protected alerts, or be required for startup or display. AI calls happen during scheduled refresh/decision work and are cached.

## Consequences
- Reliable alerts survive provider outages and invalid model output.
- AI credentials/cost are optional and controllable.
- Decision output needs strict schema validation, timeouts, a budget/cadence limit and deterministic fallback.
- Review any future request to let AI alter the priority policy as a product decision and ADR amendment.
