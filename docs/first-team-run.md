# First agent team run prompt

Use this prompt with GPT-6 Astra/Work as coordinator:

> You are coordinating the first implementation team for the Kindle Family Dashboard. Read `AGENTS.md`, `PROJECT.md`, `ARCHITECTURE.md`, both files in `ADRS/`, `ROADMAP.md`, `TASKS.md`, and `contracts/openapi.yaml`. First perform a planning-only pass: summarize the fixed product decisions, identify unresolved decisions without guessing, inspect the current scaffold, and map task dependencies/file ownership. Propose a bounded assignment plan using the roles in AGENTS.md. Do not edit files during this pass. In particular, establish T1 contracts before agents implement dependent modules; keep deterministic protected alerts independent of AI; keep Kindle requests cache-only. Then coordinate implementation in dependency order, with one integrator, tests/acceptance evidence per task, and no credentials or personal calendar data in git. Use demo fixtures until real hardware and provider choices are known.

## Coordinator checklist
- Confirm each assignment has one owner and explicit file boundaries.
- Ask agents to report blockers promptly, but continue independent tasks.
- Integrate T1 before work relying on model shapes; avoid duplicate edits.
- Validate using synthetic fixture inputs; never ask for real secrets in chat.
- Before declaring V1 ready, run the acceptance list in `PROJECT.md` and record unverified device-specific steps.
