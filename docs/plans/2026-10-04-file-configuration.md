# File configuration

User-authorized scope: editable source links and application settings in one file. Keep Python/Alpine and the existing collectors; add no AI work.

Use flat TOML matching the validated Settings fields, with calendar/RSS array tables. Python's built-in tomllib avoids another dependency. config.example.toml contains synthetic examples; private config.toml is ignored, excluded from builds and mounted read-only in Compose. API key files remain separate and ignored.

Precedence: explicit application overrides, process environment, TOML, legacy .env, defaults. Existing Settings construction remains unchanged for tests/callers; load_settings enables file loading. CONFIG_FILE selects the file; missing default config.toml is permitted for demo/backward compatibility, but an explicitly selected missing or malformed file fails with safe messages. Reject unknown TOML settings and cap size64KiB without including contents in errors.

Migrate current private source settings to config.toml without printing URLs, preserving .env as a private backup. Compose passes only CONFIG_FILE and fixed persistent storage locations so its defaults do not override file values. Docker port binding stays deployment configuration in .env/Compose; document that distinction.

Verify file parsing, priorities, error privacy, full suite/lint/types, then rebuild/restart Compose with existing persistent data and confirm source success and cached image endpoints. No new service, UI or AI adapter.
