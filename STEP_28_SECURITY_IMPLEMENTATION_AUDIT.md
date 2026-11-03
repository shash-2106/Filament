# Step 28 — Supabase Authentication, RLS & Least-Privilege Implementation Audit

**Date:** 2026-11-04  
**Author:** Antigravity / Engineering Team  
**Scope:** Local verification and implementation against PostgreSQL 16 (port 5433). Remote Supabase was untouched in accordance with protocol.  
**Verdict:** **PASS (READY FOR STAGED SUPABASE DEPLOYMENT)**

---

## 1. Executive Summary

In Step 28, the proposed Supabase security and authentication architecture was implemented and verified end-to-end against a live PostgreSQL 16 instance running in strict least-privilege mode.

Key accomplishments:
1. **Authentication Helper:** Created `public.filament_lookup_agent(p_api_key_hash text)` via Alembic migration `20261103_0004`. It executes as `SECURITY DEFINER` with a hardened search path (`pg_catalog, public, pg_temp`), validates SHA-256 inputs, and is revoked from `PUBLIC`, `anon`, and `authenticated`.
2. **Transaction-Local Context:** Updated FastAPI `get_current_agent` dependency (`apps/api/src/filament_api/api/dependencies/auth.py`) to query `filament_lookup_agent`, verify agent status, and set `app.current_workspace_id` scoped strictly to the current transaction (`is_local = true`).
3. **Comprehensive Row-Level Security:** Enabled RLS and created restrictive policies across all 12 Filament domain tables (`workspaces`, `users`, `agents`, `claims`, `evidence`, `claim_evidence`, `claim_relations`, `audit_events`, `environment_snapshots`, `claim_condition_sets`, `claim_conditions`, `claim_verifications`).
4. **Least-Privilege Database Role:** Configured the runtime role `filament_app` with `NOBYPASSRLS`, zero table creation or DDL permissions, zero `DELETE` privileges across the entire schema, and column-level `UPDATE` permissions restricted to mutable operational attributes.
5. **Full Suite Verification:** Verified 7/7 comprehensive RLS integration tests, 8/8 live PostgreSQL integration tests, 258/258 backend unit tests, 22/22 web frontend tests, and verified clean frontend production builds.

---

## 2. Security Architecture Implementation

### 2.1 Agent Authentication Flow
Authentication previously relied on an ORM `SELECT` directly on the `agents` table. Under RLS, querying `agents` without an active workspace context fails closed (0 rows returned). To break this circular dependency securely:
1. Client sends `X-Agent-API-Key` in the HTTP header.
2. FastAPI hashes the key with `hashlib.sha256(raw_key.encode()).hexdigest()`.
3. FastAPI executes `SELECT * FROM public.filament_lookup_agent(:api_key_hash)` with bound parameters.
4. If found and active:
   - FastAPI executes `SELECT set_config('app.current_workspace_id', :ws_id, true)`.
   - The third parameter `true` sets `is_local`, binding the configuration strictly to the current database transaction. When the transaction commits or aborts, the setting clears automatically, preventing connection leak across pool sessions.
5. If not found or inactive, an HTTP 401 Unauthorized response is immediately returned without leaking workspace existence.

### 2.2 RLS Policy Matrix Across All 12 Tables

All 12 tables have `ROW LEVEL SECURITY` explicitly enabled:

| Table | Operation | Policy Condition |
| :--- | :--- | :--- |
| `workspaces` | SELECT | `id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid` |
| `workspaces` | INSERT / UPDATE | `id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid` |
| `users` | SELECT / INSERT / UPDATE | `workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid` |
| `agents` | SELECT / INSERT / UPDATE | `workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid` |
| `claims` | SELECT / INSERT / UPDATE | `workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid` |
| `evidence` | SELECT / INSERT | `workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid` |
| `claim_evidence` | SELECT / INSERT | `workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid` |
| `claim_relations` | SELECT / INSERT | `workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid` |
| `audit_events` | SELECT / INSERT | `workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid` |
| `environment_snapshots` | SELECT / INSERT | `workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid` |
| `claim_condition_sets` | SELECT / INSERT | `workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid` |
| `claim_conditions` | SELECT / INSERT | `workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid` |
| `claim_verifications` | SELECT / INSERT | `workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid` |

*Note:* Append-only tables have no UPDATE policy. Furthermore, NO table has a DELETE policy, aligning database privileges with domain immutability.

### 2.3 Least-Privilege Role: `filament_app`
Implemented in `apps/api/scripts/provision_supabase_roles.sql`:
- **Role attributes:** `NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOINHERIT, LOGIN, NOBYPASSRLS`.
- **DDL:** No `CREATE` on `public` schema. Table creation, altering, or dropping is blocked.
- **DML Grants:**
  - `SELECT`, `INSERT` on all 12 tables.
  - `DELETE` is completely revoked / not granted on any table.
  - `UPDATE` is strictly restricted to designated mutable columns:
    - `workspaces`: `name`, `updated_at`
    - `users`: `display_name`, `role`, `updated_at`
    - `agents`: `name`, `default_scope`, `is_active`, `updated_at`
    - `claims`: `state`, `decay_score`, `last_verified_at`, `active_condition_set_version`, `updated_at`
  - `EXECUTE` granted on `public.filament_lookup_agent(text)` and immutable trigger functions.

---

## 3. Alembic Migration Implementation

**File:** `apps/api/alembic/versions/20261103_0004_supabase_rls_and_auth.py`  
**Revision ID:** `20261103_0004`  
**Down Revision:** `20261101_0003`

### Upgrade Logic:
1. Creates helper function `public.filament_lookup_agent(p_api_key_hash text)`:
   ```sql
   CREATE OR REPLACE FUNCTION public.filament_lookup_agent(p_api_key_hash text)
   RETURNS TABLE(
       id uuid,
       workspace_id uuid,
       name varchar(128),
       default_scope varchar(32),
       is_active boolean
   )
   LANGUAGE plpgsql
   STABLE
   SECURITY DEFINER
   SET search_path = pg_catalog, public, pg_temp
   AS $$
   BEGIN
       IF p_api_key_hash IS NULL OR length(p_api_key_hash) != 64 OR p_api_key_hash !~ '^[0-9a-fA-F]{64}$' THEN
           RETURN;
       END IF;

       RETURN QUERY
       SELECT a.id, a.workspace_id, a.name, a.default_scope, a.is_active
       FROM public.agents a
       WHERE a.api_key_hash = lower(p_api_key_hash)
         AND a.is_active = true
       LIMIT 1;
   END;
   $$;
   ```
2. Revokes execution from `PUBLIC`, `anon`, and `authenticated`.
3. Issues `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` across all 12 tables.
4. Creates granular RLS policies for `SELECT`, `INSERT`, and `UPDATE` using `app.current_workspace_id`.

### Downgrade Logic:
Cleanly removes all 24 policies, executes `DISABLE ROW LEVEL SECURITY` on all 12 tables, and drops `public.filament_lookup_agent`. Downgrade and re-upgrade cycles were tested and verified against the live test database.

---

## 4. Verification & Test Evidence

### 4.1 RLS & Security Integration Suite (`test_supabase_rls_integration.py`)
Executed with runtime database role `filament_app` connecting to PostgreSQL 16 on port 5433:

```text
apps/api/tests/test_supabase_rls_integration.py::test_runtime_role_has_nobypassrls_and_cannot_create_tables PASSED [ 14%]
apps/api/tests/test_supabase_rls_integration.py::test_filament_lookup_agent_execution_and_security PASSED [ 28%]
apps/api/tests/test_supabase_rls_integration.py::test_rls_workspace_isolation_and_cross_workspace_blocking PASSED [ 42%]
apps/api/tests/test_supabase_rls_integration.py::test_rls_all_12_tables_fail_closed_without_context PASSED [ 57%]
apps/api/tests/test_supabase_rls_integration.py::test_zero_delete_and_column_level_updates PASSED [ 71%]
apps/api/tests/test_supabase_rls_integration.py::test_e2e_http_api_under_restricted_runtime_role PASSED [ 85%]
apps/api/tests/test_supabase_rls_integration.py::test_threat_boundary_arbitrary_sql_can_alter_custom_setting PASSED [100%]

============================== 7 passed in 0.42s ===============================
```

**Test Behaviors Validated:**
1. `test_runtime_role_has_nobypassrls_and_cannot_create_tables`:
   - Confirms `pg_roles.rolbypassrls` is `false` for `filament_app`.
   - Confirms DDL `CREATE TABLE` is denied (`permission denied for schema public`).
2. `test_filament_lookup_agent_execution_and_security`:
   - Validates correct agent metadata return for valid SHA-256 hash.
   - Validates 0 rows returned for inactive agents or missing hashes.
   - Validates regex guard rejecting malformed or truncated hashes.
3. `test_rls_workspace_isolation_and_cross_workspace_blocking`:
   - Confirms cross-workspace data is invisible under context of Workspace 1.
   - Confirms cross-workspace `INSERT` is blocked by RLS check policy (`new row violates row-level security policy`).
4. `test_rls_all_12_tables_fail_closed_without_context`:
   - Confirms all 12 tables return 0 rows when queried by `filament_app` without `app.current_workspace_id`.
5. `test_zero_delete_and_column_level_updates`:
   - Confirms `DELETE` is blocked at SQL permission level on all tested entities.
   - Confirms `UPDATE` on protected columns (e.g., `subject`, `predicate`, `created_at`) is blocked at column permission level.
   - Confirms `UPDATE` on authorized columns (e.g., `claims.state`, `claims.decay_score`) succeeds.
6. `test_e2e_http_api_under_restricted_runtime_role`:
   - Runs full FastAPI `AsyncClient` over live PostgreSQL connected with role `filament_app`.
   - Authenticates via header, sets transaction context, retrieves claims via `GET /api/v1/claims`.
7. `test_threat_boundary_arbitrary_sql_can_alter_custom_setting`:
   - Proves the threat boundary and limitations of session variable RLS under arbitrary SQL injection.

### 4.2 Full Regression Verification

| Test Suite | Scope | Target | Result | Duration |
| :--- | :--- | :--- | :--- | :--- |
| **RLS Integration** | Supabase RLS & Role Tests | PostgreSQL 16 (port 5433) | **7 passed** | 0.42s |
| **PostgreSQL Integration** | Foreign Keys, Triggers, Concurrency | PostgreSQL 16 (port 5433) | **8 passed** | 0.57s |
| **Backend Unit** | All services, routes, schemas | Mocked / Local Engine | **258 passed** | 1.50s |
| **Frontend Unit** | React components, pages, hooks | Vitest + JSDOM | **22 passed** | 0.89s |
| **Frontend Build** | TypeScript checking & bundle | Vite + Rollup | **Success** | 0.15s |

---

## 5. Threat Model Analysis & Security Boundary

### 5.1 Defense-in-Depth vs. Primary Security Boundary
- **What RLS Provides:** RLS acts as a database-level firewall against application bugs. If an endpoint omits `WHERE workspace_id = ...` or an ORM join leaks rows, PostgreSQL filters the query at the storage engine level.
- **Session Variable Boundary (`set_config`):** Setting `app.current_workspace_id` via `set_config` uses `is_local = true`. This prevents connection-leakage across pooled connections.
- **Arbitrary SQL Limitations:** Because `set_config` is accessible to ordinary connections, any code path allowing arbitrary SQL execution could call `set_config` to alter the workspace ID. Therefore, **the FastAPI application authorization layer remains the primary perimeter**, with RLS serving as defense-in-depth against data leakage and logic bugs.

---

## 6. Deployment Prerequisites for Supabase

When proceeding to remote Supabase deployment:
1. **Database Role Provisioning:** Run `apps/api/scripts/provision_supabase_roles.sql` as the Supabase `postgres` administrator to create the `filament_app` role with a production password.
2. **Apply Migrations:** Execute `alembic upgrade head` using the administrative migration connection string to apply migrations 0001 through 0004.
3. **Configure Application Connection:** Set `FILAMENT_DATABASE_URL` in production to use the restricted `filament_app` role credentials.
4. **Run Remote Preflight:** Execute `python -m apps.api.scripts.supabase_preflight` against the remote instance to verify all 12 tables, triggers, and function definitions before directing user traffic.

