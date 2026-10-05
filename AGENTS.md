# Agent collaboration guide

## Mission
Build a reliable family information display hosted on a Debian Beelink N100. The Kindle is a thin display client: the server prepares cached grayscale PNGs and the device fetches them over the local network.

## Roles
- **Coordinator / integrator:** owns scope, dependencies, interfaces, task assignment, integration, and final acceptance. Keep the project small; resolve decisions against `PROJECT.md` and ADRs.
- **Platform agent:** FastAPI app lifecycle, settings, SQLite, APScheduler, Docker, health/status endpoints, operational docs.
- **Data agent:** one collector at a time (ICS first, then weather, RSS); normalize external data into contracts and provide fixtures.
- **Decision agent:** deterministic alert precedence, candidate selection, optional AI adapter with strict structured output and fallback.
- **Display agent:** fixed HTML templates and Playwright rendering, Kindle-size grayscale PNG, page endpoints and cache.
- **Quality/security agent:** review contracts, tests, secret handling, feed/calendar URL safety, dependency and container configuration.

Roles are responsibilities, not separate services. One agent can hold several roles. Assign separate files or bounded interfaces to parallel agents; do not have multiple agents edit the same module concurrently.

## Collaboration rules
1. Before coding, read this file, `PROJECT.md`, the relevant ADR, and the assigned task in `TASKS.md`.
2. Work only on the assigned task. Confirm its dependencies are accepted before starting.
3. Agree on contracts before parallel implementation. Put shared models under `app/contracts/`.
4. Keep changes small and reviewable. Add/update tests with behavior changes. Never commit secrets, real calendar URLs, private family details, or photos.
5. Do not invent family requirements. Record unresolved choices in `PROJECT.md` under Open decisions.
6. Preserve deterministic critical alerts if the AI provider is unavailable, slow, or returns invalid data.
7. Report files changed, checks run, outcomes, risks, and any follow-up task. Coordinator integrates and checks the whole repository.

## First team run
Use GPT-6 Astra/Work as coordinator/reviewer and Codex agents for bounded implementation tasks. Start with a read-only planning pass: inspect the repository, map `TASKS.md` dependencies, and propose assignments. Then parallelize only independent tasks. Suggested first wave after task T0: T1 contracts, T2 app foundation, and T3 renderer prototype (interfaces first); T4 ICS collector depends on T1/T2; T5 rules depends on T1; later tasks follow the dependency table. Keep one integrator responsible for merges and avoid asking agents to make external accounts or publish anything.

## Definition of done
A task meets its listed acceptance criteria; tests cover changed behavior; formatting/type/lint checks pass when configured; docs and sample configuration match implementation; no secrets or personal data enter the repository; and the coordinator has reviewed the diff for scope and interface consistency.
