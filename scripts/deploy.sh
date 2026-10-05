#!/bin/sh
# Sync the project to the home server and rebuild the container.
# Usage: scripts/deploy.sh user@host [remote-dir]   (run from the repository root)
# The target may also come from the DEPLOY_TARGET environment variable.
set -eu

TARGET="${1:-${DEPLOY_TARGET:-}}"
if [ -z "$TARGET" ]; then
  echo "usage: scripts/deploy.sh user@host [remote-dir]" >&2
  exit 2
fi
REMOTE_DIR="${2:-homelab/kindle-hub}"

# The server keeps its own .env (bind address and port); secrets and caches stay local.
rsync -az --delete \
  --exclude '.venv/' --exclude '__pycache__/' --exclude '.cache/' --exclude '.data/' \
  --exclude '.pytest_cache/' --exclude '.ruff_cache/' --exclude '.mypy_cache/' \
  --exclude '.env' --exclude '.env.*' --exclude 'openapi_key' --exclude 'openai_key' \
  --exclude '.DS_Store' --exclude '*.zip' --exclude '*.egg-info/' \
  --exclude 'design_handoff_kindle_landscape*/' --exclude '.playwright-mcp/' --exclude 'photos/' --exclude 'secrets/' \
  ./ "$TARGET:$REMOTE_DIR/"

# Photos are only added, never removed, so ones placed on the server directly survive.
mkdir -p photos
rsync -az --exclude '.DS_Store' photos/ "$TARGET:$REMOTE_DIR/photos/"

# The optional AI key lives outside the image; it is copied only when present locally.
ssh "$TARGET" "mkdir -p $REMOTE_DIR/secrets"
if [ -f openapi_key ]; then
  rsync -az openapi_key "$TARGET:$REMOTE_DIR/secrets/ai_key"
fi

# The container runs as another user, so the mounted config must be readable by it;
# the directory itself stays private to the login user.
ssh "$TARGET" "cd $REMOTE_DIR && chmod 700 . && chmod 644 config.toml && chmod -R a+rX photos secrets && docker compose up --build -d --force-recreate"
