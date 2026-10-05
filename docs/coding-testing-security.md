# Coding, testing and security conventions

## Code
- Python 3.12+, type annotations on public functions, Pydantic at external/API boundaries.
- Keep collectors, decision logic, rendering and HTTP routes separate; depend on interfaces and contracts.
- All datetimes must be timezone-aware. Store UTC and render in `TIMEZONE`.
- Use structured, bounded errors; isolate source failures. Do not silently replace valid cached data with empty data.
- Pillow layouts draw bounded plain text. Never execute source content or model-generated markup.

## Tests
- Unit-test normalization, rules, schema validation and fallback paths with deterministic fixtures.
- No live API calls in routine tests. Mock HTTP and AI clients.
- Test stale cache and upstream timeout cases, plus protected alert invariants.
- Render smoke tests assert PNG dimensions/mode; add visual snapshots only if stable in CI.
- Suggested local checks: `pytest`, `ruff check .`, `ruff format --check .`, `mypy app`.

## Security
- Secrets belong in local `.env`/Docker secrets and are never logged or committed.
- Allowlist source URLs; only HTTP(S); protect against private/loopback/link-local/metadata IP fetches and redirect bypass.
- Enforce request timeouts and body-size limits; sanitize upstream HTML/text; escape template output.
- Keep HTTP service LAN-only, non-root, drop Linux capabilities, and persist only necessary data.
- Calendar data is sensitive: use synthetic test fixtures, redact URLs and avoid raw payload logging.
