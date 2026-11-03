-- ==============================================================================
-- Filament Runtime Role Creation (Step 1: Run BEFORE migrations)
-- ==============================================================================
-- 1. Create runtime application role idempotently
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'filament_app') THEN
        CREATE ROLE filament_app WITH LOGIN NOBYPASSRLS PASSWORD 'FILAMENT_RUNTIME_PASSWORD_PLACEHOLDER';
    END IF;
END
$$;

-- Ensure NOBYPASSRLS and no schema-level creation
ALTER ROLE filament_app WITH NOBYPASSRLS;
GRANT USAGE ON SCHEMA public TO filament_app;
REVOKE CREATE ON SCHEMA public FROM filament_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

