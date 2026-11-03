# Step 27D: Final Supabase Security Consistency Audit

**Audit Date:** 2026-11-03  
**Target Repository:** `/Users/shash/Downloads/Filament`  
**Mode:** Read-Only Audit (Zero Remote Mutations, Zero Supabase Connections)

---

## 1. Executive Verdict

### **Verdict: CONDITIONAL (BLOCKED FROM REMOTE DEPLOYMENT)**

While the architectural principles (defense-in-depth RLS, dual-role isolation, zero-DELETE baseline, append-only immutability triggers) are structurally sound, **remote Supabase deployment cannot proceed**. 

The primary blocker is that **the security model exists only as markdown design prose**:
1. No Alembic migration or version-controlled SQL script currently creates the roles, grants, RLS policies, or the `filament_lookup_agent` function.
2. The backend authentication dependency ([`apps/api/src/filament_api/api/dependencies/auth.py#L78-L98`](file:///Users/shash/Downloads/Filament/apps/api/src/filament_api/api/dependencies/auth.py#L78-L98)) still executes standard un-scoped queries (`SELECT ... FROM agents WHERE api_key_hash = ...`) without invoking `filament_lookup_agent` or injecting `app.current_workspace_id` into the session. Applying the proposed RLS to Supabase today would immediately cause **100% of all API requests to fail with HTTP 401 Unauthorized**.
3. Schema discrepancies exist between markdown grant proposals (`active_condition_set_id`) and the actual persisted schema ([`claims.active_condition_version`](file:///Users/shash/Downloads/Filament/apps/api/src/filament_api/models/claim.py#L103)).

---

## 2. Findings Matrix

| Finding ID | Severity | Category | Description | File & Line Reference | Remediation Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **AUDIT-01** | **CRITICAL** | Implementation Gap | DDL for roles, RLS policies, and grants exists **only in markdown prose**, not in Alembic migrations or executable SQL scripts. | [`supabase_security_design_preflight.md`](file:///Users/shash/.gemini/antigravity/brain/1e4e0e5c-f509-4e8f-8298-53e18857c330/supabase_security_design_preflight.md) | **OPEN**: Must create migration `0004` or deployment script. |
| **AUDIT-02** | **CRITICAL** | Runtime Breakage | Backend `get_current_agent_context` does not call `filament_lookup_agent` or set `app.current_workspace_id`. Under RLS, agent lookup fails closed. | [`apps/api/src/filament_api/api/dependencies/auth.py#L78-L98`](file:///Users/shash/Downloads/Filament/apps/api/src/filament_api/api/dependencies/auth.py#L78-L98) | **OPEN**: Backend auth dependency must be updated. |
| **AUDIT-03** | **HIGH** | Schema Mismatch | Proposed grant referenced non-existent column `active_condition_set_id` instead of actual schema column `active_condition_version`. | [`supabase_security_design_preflight.md#L326`](file:///Users/shash/.gemini/antigravity/brain/1e4e0e5c-f509-4e8f-8298-53e18857c330/supabase_security_design_preflight.md#L326) vs [`models/claim.py#L103`](file:///Users/shash/Downloads/Filament/apps/api/src/filament_api/models/claim.py#L103) | **RESOLVED IN DOCS**: Fixed column name to `active_condition_version`. |
| **AUDIT-04** | **HIGH** | Preflight Accuracy | `supabase_preflight.py` checked for fictitious function names (`prevent_audit_mutation`) instead of actual migration triggers (`filament_protect_audit_log`). | [`apps/api/scripts/supabase_preflight.py#L46-L50`](file:///Users/shash/Downloads/Filament/apps/api/scripts/supabase_preflight.py#L46-L50) vs [`alembic/versions/20261029_0001_initial_schema.py#L202`](file:///Users/shash/Downloads/Filament/apps/api/alembic/versions/20261029_0001_initial_schema.py#L202) | **RESOLVED**: Corrected in `supabase_preflight.py` and verified by tests. |
| **AUDIT-05** | **MEDIUM** | Auth Leakage | Initial `filament_lookup_agent` design returned `api_key_hash` and lacked `PUBLIC` execution revocations. | [`supabase_security_design_preflight.md#L105`](file:///Users/shash/.gemini/antigravity/brain/1e4e0e5c-f509-4e8f-8298-53e18857c330/supabase_security_design_preflight.md#L105) | **RESOLVED IN DOCS**: Hardened with parameter validation and explicit REVOKE. |
| **AUDIT-06** | **LOW** | Test Infrastructure | Local PostgreSQL test cluster cleared on reboot; `initdb` required macOS sandbox elevation for `shmget`. | [`apps/api/tests/test_postgres_integration.py#L45`](file:///Users/shash/Downloads/Filament/apps/api/tests/test_postgres_integration.py#L45) | **RESOLVED**: Automated in [`apps/api/scripts/start_test_db.sh`](file:///Users/shash/Downloads/Filament/apps/api/scripts/start_test_db.sh). |

---

## 3. Authentication Helper (`filament_lookup_agent`) Audit

### 3.1 Actual SQL Definition & Security Properties

The hardened definition finalized in Step 27C:

```sql
CREATE OR REPLACE FUNCTION public.filament_lookup_agent(p_api_key_hash text)
RETURNS TABLE (
    id uuid,
    workspace_id uuid,
    name varchar(255),
    role varchar(64),
    is_active boolean
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    -- 1. Input Validation: Enforce strict 64-character hexadecimal format
    IF p_api_key_hash IS NULL OR length(p_api_key_hash) != 64 OR p_api_key_hash !~ '^[0-9a-fA-F]{64}$' THEN
        RETURN;
    END IF;

    -- 2. Scoped Lookup: Never reflect api_key_hash or updated_at
    RETURN QUERY
    SELECT a.id, a.workspace_id, a.name, a.role, a.is_active
    FROM public.agents a
    WHERE a.api_key_hash = p_api_key_hash
      AND a.is_active = true
    LIMIT 1;
END;
$$;

-- 3. Execution Lockdown: Revoke from PUBLIC, grant ONLY to runtime role
REVOKE ALL ON FUNCTION public.filament_lookup_agent(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.filament_lookup_agent(text) FROM anon;
REVOKE ALL ON FUNCTION public.filament_lookup_agent(text) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.filament_lookup_agent(text) TO filament_app;
```

### 3.2 Concrete Attack-Surface Analysis

1. **Owner Privileges & BYPASSRLS**:
   The function is owned by `filament_migrator` (or admin `postgres`), which has `BYPASSRLS`. Because it is marked `SECURITY DEFINER`, it bypasses the RLS policy on `agents`. This bypass is necessary because `workspace_id` is unknown prior to agent lookup.
2. **Search Path Hijacking**:
   The function specifies `SET search_path = pg_catalog, public, pg_temp;`. All table references are fully qualified (`public.agents`). This prevents malicious search_path shadowing attacks.
3. **Information Disclosure & Credential Leaks**:
   - `api_key_hash` is **not** returned.
   - Only `(id, workspace_id, name, role, is_active)` are returned.
   - For inactive agents (`is_active = false`) or non-existent keys, the function returns 0 rows, completely preventing active status enumeration.
4. **Cross-Workspace Leakage**:
   The incoming parameter is matched against `agents.api_key_hash`, which is constrained by a UNIQUE index ([`uq_agents_api_key_hash`](file:///Users/shash/Downloads/Filament/apps/api/alembic/versions/20261029_0002_agent_api_key_hash_unique.py#L22)). A valid token can resolve to exactly one agent in exactly one workspace. A caller cannot supply an arbitrary `workspace_id` to spoof context.

---

## 4. Row-Level Security (RLS) Coverage Matrix

### 4.1 All 12 Tables Evaluated

The expression used across all policies:
`nullif(current_setting('app.current_workspace_id', true), '')::uuid`

| # | Table Name | SELECT Policy | INSERT Policy (`WITH CHECK`) | UPDATE Policy | DELETE Policy | Invariant Protection |
| :---: | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `workspaces` | `id = current_ws()` | Denied (Admin only) | Denied | Denied | Reads workspace metadata |
| 2 | `users` | `workspace_id = current_ws()` | `workspace_id = current_ws()` | `workspace_id = current_ws()` | Denied | Scoped to workspace |
| 3 | `agents` | `workspace_id = current_ws()` | `workspace_id = current_ws()` | `workspace_id = current_ws()` | Denied | Scoped to workspace |
| 4 | `claims` | `workspace_id = current_ws()` | `workspace_id = current_ws()` | `workspace_id = current_ws()` | Denied | Scoped to workspace |
| 5 | `evidence` | `workspace_id = current_ws()` | `workspace_id = current_ws()` | Denied (Immutable) | Denied | Append-only raw observations |
| 6 | `claim_evidence` | `workspace_id = current_ws()` | `workspace_id = current_ws()` | Denied (Immutable) | Denied | Append-only claim bindings |
| 7 | `claim_relations` | `workspace_id = current_ws()` | `workspace_id = current_ws()` | Denied (Immutable) | Denied | Append-only causal graph |
| 8 | `audit_events` | `workspace_id = current_ws()` | `workspace_id = current_ws()` | Denied (Immutable) | Denied | Immutable audit ledger |
| 9 | `environment_snapshots` | `workspace_id = current_ws()` | `workspace_id = current_ws()` | Denied (Immutable) | Denied | Immutable runtime facts |
| 10 | `claim_condition_sets` | `workspace_id = current_ws()` | `workspace_id = current_ws()` | Denied (Immutable) | Denied | Versioned condition roots |
| 11 | `claim_conditions` | `workspace_id = current_ws()` | `workspace_id = current_ws()` | Denied (Immutable) | Denied | Versioned atomic rules |
| 12 | `claim_verifications` | `workspace_id = current_ws()` | `workspace_id = current_ws()` | Denied (Immutable) | Denied | Append-only verification proofs |

### 4.2 Behavior on Invalid / Edge Contexts

- **Missing Context (`NULL`)**: `current_setting('app.current_workspace_id', true)` returns `NULL`. Equality against `NULL` evaluates to `UNKNOWN`. In PostgreSQL RLS, boolean `UNKNOWN` is treated as `FALSE`. **Fails closed.**
- **Empty String (`""`)**: `nullif('', '')` returns `NULL`. **Fails closed.**
- **Malformed String (`"not-a-uuid"`)**: Casting `"not-a-uuid"::uuid` raises PostgreSQL error `22P02: invalid input syntax for type uuid`, immediately aborting the transaction. **Fails closed.**
- **Cross-Workspace Foreign Keys**: Every child table has composite foreign keys matching `(workspace_id, parent_id)`. Attempting to link a claim from Workspace A to an evidence record from Workspace B is blocked simultaneously by the composite foreign key constraint and RLS `WITH CHECK`.

### 4.3 Threat Model Distinction

> [!WARNING]
> **Application Bug Protection vs. Connection Compromise**:
> Setting `app.current_workspace_id` via `set_config` is **not** a hardware- or cryptographic-enforced role boundary. Because `filament_app` has the SQL execution privilege, any attacker with arbitrary SQL injection capability can execute `SELECT set_config('app.current_workspace_id', '<other_uuid>', false)`.
> 
> Therefore, RLS acts as a **structural defense against application developer bugs, omitted WHERE clauses, and unintended ORM joins**, but the application API authorization layer remains the primary security boundary against external compromise.

---

## 5. SQLAlchemy Operations to Database Grants Mapping

An audit of all service methods in [`apps/api/src/filament_api/services/`](file:///Users/shash/Downloads/Filament/apps/api/src/filament_api/services/) verified the following mapping:

| Table | SQLAlchemy Service Operation | SQL Verbs Required | Column-Level Restrictions | Zero-DELETE Compatible? |
| :--- | :--- | :---: | :--- | :---: |
| `workspaces` | `select(Workspace)` in `claim.py`, `evidence.py` | `SELECT` | All columns | **YES** (No deletes) |
| `users` | User profile lookups and updates | `SELECT`, `INSERT`, `UPDATE` | `UPDATE (email, role, updated_at)` | **YES** (No deletes) |
| `agents` | `select(Agent)` in `auth.py`, `claim.py` | `SELECT`, `INSERT`, `UPDATE` | `UPDATE (name, role, is_active, updated_at)` *(Excludes `api_key_hash`, `workspace_id`)* | **YES** (No deletes) |
| `claims` | `create_claim`, `update_status`, `add_evidence`, `reverify_claim` | `SELECT`, `INSERT`, `UPDATE` | `UPDATE (status, version, updated_at, active_condition_version)` *(Excludes `subject`, `predicate`, `object_value`)* | **YES** (No deletes) |
| `evidence` | `ingest_evidence`, `get_evidence` | `SELECT`, `INSERT` | NO UPDATE (Immutable) | **YES** (No deletes) |
| `claim_evidence` | `add_evidence` | `SELECT`, `INSERT` | NO UPDATE (Immutable) | **YES** (No deletes) |
| `claim_relations`| `create_relation`, `list_relations` | `SELECT`, `INSERT` | NO UPDATE (Immutable) | **YES** (No deletes) |
| `audit_events` | `record_event`, `get_provenance` | `SELECT`, `INSERT` | NO UPDATE (Backed by trigger) | **YES** (No deletes) |
| `environment_snapshots` | `record_snapshot`, `get_snapshot` | `SELECT`, `INSERT` | NO UPDATE (Backed by trigger) | **YES** (No deletes) |
| `claim_condition_sets` | `establish_initial_conditions`, `reverify_claim` | `SELECT`, `INSERT` | NO UPDATE (Backed by trigger) | **YES** (No deletes) |
| `claim_conditions` | `establish_initial_conditions`, `reverify_claim` | `SELECT`, `INSERT` | NO UPDATE (Backed by trigger) | **YES** (No deletes) |
| `claim_verifications` | `establish_initial_conditions`, `reverify_claim` | `SELECT`, `INSERT` | NO UPDATE (Backed by trigger) | **YES** (No deletes) |

**Conclusion on Zero DELETE**: Not a single service method in Filament executes a `DELETE` statement. Lineage relations, condition versions, and verifications are strictly additive journals. Zero `DELETE` privileges are **100% compatible** with existing backend operations.

---

## 6. Local Test Execution Results

All local test suites were executed against the codebase and the local PostgreSQL instance on port `5433`:

| Test Suite | Commands Executed | Result | Details |
| :--- | :--- | :---: | :--- |
| **Backend Unit Suite** | `pytest apps/api/tests/ --ignore=test_postgres_integration.py` | **PASS** | **258 passed** in 1.44s |
| **Preflight Inspection Tests** | `pytest apps/api/tests/test_supabase_preflight.py` | **PASS** | **5 passed** in 0.04s (mocked DB) |
| **Live PostgreSQL Integration** | `pytest apps/api/tests/test_postgres_integration.py` | **PASS** | **8 passed** in 0.50s (PostgreSQL 16 on port 5433) |
| **Frontend Unit Suite** | `npm --prefix apps/web test` | **PASS** | **22 passed** across 7 test files in 0.79s |
| **Frontend Production Build** | `npm --prefix apps/web run build` | **PASS** | Built in 134ms (Vite 8.3.5) |

---

## 7. Prerequisites Before Remote Supabase Preflight

Before initiating remote preflight or applying DDL to Supabase, the following steps must be taken:

1. **Implement Backend Context Injection**:
   Update `apps/api/src/filament_api/api/dependencies/auth.py` and `db/session.py` to:
   - Call `public.filament_lookup_agent(token_hash)` during authentication.
   - Inject `await session.execute(text("SELECT set_config('app.current_workspace_id', :ws_id, true)"), {"ws_id": str(context.workspace_id)})`.
2. **Author Formal Migration `0004`**:
   Create a dedicated Alembic revision (`20261103_0004_supabase_security_and_rls.py`) to codify:
   - Creation of function `public.filament_lookup_agent`.
   - `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` across all 12 tables.
   - All 12 table policies (`USING` and `WITH CHECK`).
3. **Author Administrative Role Provisioning Script**:
   Create `apps/api/scripts/provision_supabase_roles.sql` for the Supabase administrator to execute:
   - Creation of role `filament_app WITH LOGIN NOBYPASSRLS`.
   - Granting of column-level `UPDATE` permissions and schema usage.
4. **Execute Non-Destructive Preflight**:
   Run `DATABASE_URL=... python apps/api/scripts/supabase_preflight.py` to verify clean Supabase database state.

