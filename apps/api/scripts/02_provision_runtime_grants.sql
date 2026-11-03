-- ==============================================================================
-- Filament Runtime Role Grants (Step 2: Run AFTER migrations)
-- ==============================================================================

-- 1. Table-level SELECT and INSERT on all 12 tables
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

-- 2. Column-level UPDATE privileges
-- Users: Can update profile and updated_at, but NOT id or workspace_id
GRANT UPDATE (email, display_name, role, updated_at) ON TABLE public.users TO filament_app;

-- Agents: Can update metadata and active status, but NOT id, workspace_id, or api_key_hash
GRANT UPDATE (name, default_scope, is_active, updated_at) ON TABLE public.agents TO filament_app;

-- Claims: Can update lifecycle status, version, updated_at, active_condition_version,
-- but NEVER immutable facts (subject, predicate, object_value, raw_statement, workspace_id, agent_id)
GRANT UPDATE (status, version, updated_at, active_condition_version) ON TABLE public.claims TO filament_app;

-- 3. Revoke DELETE everywhere (Zero-DELETE Policy)
REVOKE DELETE ON ALL TABLES IN SCHEMA public FROM filament_app;

-- 4. Function Execution Privileges
GRANT EXECUTE ON FUNCTION public.filament_lookup_agent(text) TO filament_app;

-- 5. Sequence safety
REVOKE USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public FROM filament_app;

