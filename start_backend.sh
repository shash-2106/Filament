#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

# Construct Supabase pooler URL
PROJECT_REF="${SUPABASE_PROJECT_REF:-rvceucunelqysdwbnkud}"
ADMIN_PW="${SUPABASE_DB_PASSWORD:-}"

if [ -n "$ADMIN_PW" ]; then
  ENCODED_PW=$("$REPO_ROOT/apps/api/.venv/bin/python3" -c 'import os, urllib.parse; print(urllib.parse.quote_plus(os.environ["SUPABASE_DB_PASSWORD"]))')
  export DATABASE_URL="postgresql+asyncpg://postgres.${PROJECT_REF}:${ENCODED_PW}@aws-0-eu-west-1.pooler.supabase.com:5432/postgres"
fi

echo "Starting FastAPI server on http://127.0.0.1:8000..."
exec "$REPO_ROOT/apps/api/.venv/bin/uvicorn" filament_api.main:app --host 127.0.0.1 --port 8000 --reload
