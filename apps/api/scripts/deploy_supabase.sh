#!/usr/bin/env bash
# ==============================================================================
# Filament Staged Supabase Deployment Orchestrator
# ==============================================================================
# Executes full deployment sequence safely:
# 1. Validates local environment variables without printing passwords.
# 2. Creates runtime role filament_app (idempotent, NOBYPASSRLS).
# 3. Applies Alembic migrations 0001 -> 0004 using direct 5432 admin connection.
# 4. Grants DML & column-level privileges to filament_app.
# 5. Runs non-destructive preflight verification connecting as filament_app.
# 6. Runs end-to-end smoke test against Supabase.
#
# Exits immediately on any error. Never prints complete connection strings.
# ==============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

PROJECT_REF="${SUPABASE_PROJECT_REF:-rvceucunelqysdwbnkud}"
ADMIN_HOST="db.${PROJECT_REF}.supabase.co"

echo "========================================================================"
echo "FILAMENT SUPABASE STAGED DEPLOYMENT"
echo "========================================================================"
echo "Target Project Ref: ${PROJECT_REF}"
echo "Direct DB Host:     ${ADMIN_HOST}:5432"
echo "========================================================================"

# 1. Load local .env if present and validate Environment Variables
if [ -f "$REPO_ROOT/.env" ]; then
    # Export non-commented variables from .env
    set -a
    # shellcheck disable=SC1091
    source "$REPO_ROOT/.env"
    set +a
fi

if [ -z "${SUPABASE_DB_PASSWORD:-}" ]; then
    echo "❌ Error: SUPABASE_DB_PASSWORD is not set in environment or .env."
    echo "Set SUPABASE_DB_PASSWORD before running this script."
    exit 1
fi

if [ -z "${FILAMENT_RUNTIME_DB_PASSWORD:-}" ]; then
    echo "❌ Error: FILAMENT_RUNTIME_DB_PASSWORD is not set."
    echo "Specify a secure password for the filament_app runtime role, e.g.:"
    echo "  export FILAMENT_RUNTIME_DB_PASSWORD='<your-secure-runtime-password>'"
    exit 1
fi

echo "✅ Required environment variables verified (passwords masked)."

# 2. URL-encode passwords safely using python helper
ENCODED_ADMIN_PW=$("$REPO_ROOT/apps/api/.venv/bin/python3" -c 'import os, urllib.parse; print(urllib.parse.quote_plus(os.environ["SUPABASE_DB_PASSWORD"]))')
ENCODED_RUNTIME_PW=$("$REPO_ROOT/apps/api/.venv/bin/python3" -c 'import os, urllib.parse; print(urllib.parse.quote_plus(os.environ["FILAMENT_RUNTIME_DB_PASSWORD"]))')

ADMIN_URL="postgresql+asyncpg://postgres:${ENCODED_ADMIN_PW}@${ADMIN_HOST}:5432/postgres"
RUNTIME_URL="postgresql+asyncpg://filament_app:${ENCODED_RUNTIME_PW}@${ADMIN_HOST}:5432/postgres"

# Helper to execute SQL via admin connection using asyncpg
exec_admin_sql() {
    local sql_content="$1"
    SQL_PAYLOAD="$sql_content" "$REPO_ROOT/apps/api/.venv/bin/python3" -c "
import asyncio, os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

def split_sql(full_text: str):
    statements = []
    current = []
    in_dollar = False
    idx = 0
    n = len(full_text)
    while idx < n:
        if not in_dollar:
            if full_text[idx:idx+2] == '\$\$':
                in_dollar = True
                current.append('\$\$')
                idx += 2
                continue
            elif full_text[idx] == ';':
                stmt = ''.join(current).strip()
                if stmt:
                    statements.append(stmt)
                current = []
                idx += 1
                continue
        else:
            if full_text[idx:idx+2] == '\$\$':
                in_dollar = False
                current.append('\$\$')
                idx += 2
                continue
        current.append(full_text[idx])
        idx += 1
    rem = ''.join(current).strip()
    if rem:
        statements.append(rem)
    return statements

async def run():
    engine = create_async_engine('$ADMIN_URL')
    sql_text = os.environ['SQL_PAYLOAD']
    statements = split_sql(sql_text)
    async with engine.begin() as conn:
        for s in statements:
            # Strip comments and check if non-empty
            lines = [line for line in s.splitlines() if not line.strip().startswith('--')]
            clean_s = '\n'.join(lines).strip()
            if clean_s:
                await conn.execute(text(clean_s))
    await engine.dispose()

asyncio.run(run())
"
}

# Step 1: Provision Runtime Role (Before Migrations)
echo ""
echo "------------------------------------------------------------------------"
echo "STEP 1: Provisioning runtime role filament_app (Admin Connection)..."
echo "------------------------------------------------------------------------"
STEP1_SQL=$(sed "s/FILAMENT_RUNTIME_PASSWORD_PLACEHOLDER/${FILAMENT_RUNTIME_DB_PASSWORD}/g" "$REPO_ROOT/apps/api/scripts/01_provision_runtime_role.sql")
exec_admin_sql "$STEP1_SQL"
echo "✅ Role filament_app provisioned with NOBYPASSRLS."

# Step 2: Apply Alembic Migrations 0001 -> 0004
echo ""
echo "------------------------------------------------------------------------"
echo "STEP 2: Applying Alembic Migrations (0001 -> 0004)..."
echo "------------------------------------------------------------------------"
DATABASE_URL="$ADMIN_URL" "$REPO_ROOT/apps/api/.venv/bin/alembic" -c "$REPO_ROOT/apps/api/alembic.ini" upgrade head
echo "✅ Migrations applied successfully."

# Step 3: Apply Runtime Role DML & Column Grants (After Tables Exist)
echo ""
echo "------------------------------------------------------------------------"
echo "STEP 3: Applying Least-Privilege DML & Column Grants to filament_app..."
echo "------------------------------------------------------------------------"
STEP2_SQL=$(cat "$REPO_ROOT/apps/api/scripts/02_provision_runtime_grants.sql")
exec_admin_sql "$STEP2_SQL"
echo "✅ Table and column-level privileges granted."

# Step 4: Run Supabase Preflight as filament_app
echo ""
echo "------------------------------------------------------------------------"
echo "STEP 4: Running Post-Migration Verification as filament_app..."
echo "------------------------------------------------------------------------"
DATABASE_URL="$RUNTIME_URL" PREFLIGHT_MODE="post_migration" "$REPO_ROOT/apps/api/.venv/bin/python3" "$REPO_ROOT/apps/api/scripts/supabase_preflight.py"
echo "✅ Post-migration inspection passed under restricted role."

# Step 5: Run End-to-End Smoke Test
echo ""
echo "------------------------------------------------------------------------"
echo "STEP 5: Running End-to-End API & Isolation Smoke Test..."
echo "------------------------------------------------------------------------"
SUPABASE_DB_PASSWORD="$SUPABASE_DB_PASSWORD" \
FILAMENT_RUNTIME_DB_PASSWORD="$FILAMENT_RUNTIME_DB_PASSWORD" \
SUPABASE_PROJECT_REF="$PROJECT_REF" \
"$REPO_ROOT/apps/api/.venv/bin/python3" "$REPO_ROOT/apps/api/scripts/supabase_smoke_test.py"

echo ""
echo "========================================================================"
echo "🎉 DEPLOYMENT AND VERIFICATION COMPLETED SUCCESSFULLY!"
echo "========================================================================"

