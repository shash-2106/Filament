-- ==============================================================================
-- Filament Runtime Role Provisioning Script (PostgreSQL / Supabase)
-- ==============================================================================
-- ROLE RESPONSIBILITY MATRIX:
-- 1. filament_migrator / postgres:
--    - Administrative role with SUPERUSER or BYPASSRLS.
--    - Used exclusively by Alembic for DDL, schema migrations, and trigger setup.
--    - Connects on Port 5432 (direct connection or session-mode pooler).
--
-- 2. filament_app:
--    - Runtime application role with NOBYPASSRLS.
--    - Used exclusively by the FastAPI backend service for DML operations.
--    - Subject to all Row-Level Security (RLS) policies.
--    - Strict least-privilege: zero DELETE, zero DDL, column-level UPDATE restrictions.
--
-- DO NOT EXECUTE AGAINST REMOTE SUPABASE WITHOUT EXPLICIT AUTHORIZATION.
-- ==============================================================================

-- 1. Create runtime application role with secure credentials if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'filament_app') THEN
        CREATE ROLE filament_app WITH LOGIN NOBYPASSRLS PASSWORD 'REPLACE_WITH_SECURE_RUNTIME_PASSWORD';
    END IF;
END
$$;

-- Ensure NOBYPASSRLS is strictly enforced
ALTER ROLE filament_app WITH NOBYPASSRLS;

-- 2. Schema-level usage
GRANT USAGE ON SCHEMA public TO filament_app;
REVOKE CREATE ON SCHEMA public FROM filament_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- 3. Table-level SELECT and INSERT privileges on all 12 tables
GRANT SELECT, INSERT ON TABLE
    public.workspaces,
    public.users,
    public.agents,
    public.claims,
    public.evidence,
    public.claim_evidence,
    public.claim_relations,
    public.audit_events,
    public.environment_snapshots,
    public.claim_condition_sets,
    public.claim_conditions,
    public.claim_verifications
TO filament_app;

-- 4. Column-level UPDATE privileges
-- Users: Can update profile and updated_at, but NOT id or workspace_id
GRANT UPDATE (email, display_name, role, updated_at) ON TABLE public.users TO filament_app;

-- Agents: Can update metadata and active status, but NOT id, workspace_id, or api_key_hash
GRANT UPDATE (name, default_scope, is_active, updated_at) ON TABLE public.agents TO filament_app;

-- Claims: Can update lifecycle state, version, and active condition pointer,
-- but NEVER immutable core facts (subject, predicate, object_value, workspace_id, agent_id)
GRANT UPDATE (status, version, updated_at, active_condition_version) ON TABLE public.claims TO filament_app;

-- 5. Revoke DELETE everywhere (Zero-DELETE Policy)
REVOKE DELETE ON ALL TABLES IN SCHEMA public FROM filament_app;

-- 6. Function Privileges
GRANT EXECUTE ON FUNCTION public.filament_lookup_agent(text) TO filament_app;

-- 7. Sequence Privileges (Filament uses UUID PKs; no sequences needed, but ensure default safety)
REVOKE USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public FROM filament_app;

