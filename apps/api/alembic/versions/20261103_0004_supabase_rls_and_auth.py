"""Add Supabase RLS policies and authentication bootstrap function.

Revision ID: 20261103_0004
Revises: 20261101_0003
Create Date: 2026-11-03 23:59:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20261103_0004'
down_revision: Union[str, None] = '20261101_0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES_WITH_RLS = [
    "workspaces",
    "users",
    "agents",
    "claims",
    "evidence",
    "claim_evidence",
    "claim_relations",
    "audit_events",
    "environment_snapshots",
    "claim_condition_sets",
    "claim_conditions",
    "claim_verifications",
]


def upgrade() -> None:
    # 1. Authentication Bootstrap Function
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.filament_lookup_agent(p_api_key_hash text)
        RETURNS TABLE (
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
            -- Enforce strict 64-char hexadecimal SHA-256 hash
            IF p_api_key_hash IS NULL OR length(p_api_key_hash) != 64 OR p_api_key_hash !~ '^[0-9a-fA-F]{64}$' THEN
                RETURN;
            END IF;

            RETURN QUERY
            SELECT a.id, a.workspace_id, a.name, a.default_scope, a.is_active
            FROM public.agents a
            WHERE a.api_key_hash = p_api_key_hash
              AND a.is_active = true
            LIMIT 1;
        END;
        $$;
        """
    )

    op.execute("REVOKE ALL ON FUNCTION public.filament_lookup_agent(text) FROM PUBLIC;")

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
                REVOKE ALL ON FUNCTION public.filament_lookup_agent(text) FROM anon;
            END IF;
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
                REVOKE ALL ON FUNCTION public.filament_lookup_agent(text) FROM authenticated;
            END IF;
        END
        $$;
        """
    )

    # 2. Enable RLS on all 12 tables
    for table in TABLES_WITH_RLS:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")

    # 3. Create RLS Policies (each in an independent op.execute call for asyncpg compatibility)
    # workspaces: id = current_ws()
    op.execute(
        """
        CREATE POLICY p_workspaces_select ON workspaces
            FOR SELECT
            USING (id = nullif(current_setting('app.current_workspace_id', true), '')::uuid);
        """
    )

    # users: workspace_id = current_ws()
    op.execute(
        """
        CREATE POLICY p_users_select ON users
            FOR SELECT
            USING (workspace_id = nullif(current_setting('app.current_workspace_id', true), '')::uuid);
        """
    )
    op.execute(
        """
        CREATE POLICY p_users_insert ON users
            FOR INSERT
            WITH CHECK (workspace_id = nullif(current_setting('app.current_workspace_id', true), '')::uuid);
        """
    )
    op.execute(
        """
        CREATE POLICY p_users_update ON users
            FOR UPDATE
            USING (workspace_id = nullif(current_setting('app.current_workspace_id', true), '')::uuid)
            WITH CHECK (workspace_id = nullif(current_setting('app.current_workspace_id', true), '')::uuid);
        """
    )

    # agents: workspace_id = current_ws()
    op.execute(
        """
        CREATE POLICY p_agents_select ON agents
            FOR SELECT
            USING (workspace_id = nullif(current_setting('app.current_workspace_id', true), '')::uuid);
        """
    )
    op.execute(
        """
        CREATE POLICY p_agents_insert ON agents
            FOR INSERT
            WITH CHECK (workspace_id = nullif(current_setting('app.current_workspace_id', true), '')::uuid);
        """
    )
    op.execute(
        """
        CREATE POLICY p_agents_update ON agents
            FOR UPDATE
            USING (workspace_id = nullif(current_setting('app.current_workspace_id', true), '')::uuid)
            WITH CHECK (workspace_id = nullif(current_setting('app.current_workspace_id', true), '')::uuid);
        """
    )

    # claims: workspace_id = current_ws()
    op.execute(
        """
        CREATE POLICY p_claims_select ON claims
            FOR SELECT
            USING (workspace_id = nullif(current_setting('app.current_workspace_id', true), '')::uuid);
        """
    )
    op.execute(
        """
        CREATE POLICY p_claims_insert ON claims
            FOR INSERT
            WITH CHECK (workspace_id = nullif(current_setting('app.current_workspace_id', true), '')::uuid);
        """
    )
    op.execute(
        """
        CREATE POLICY p_claims_update ON claims
            FOR UPDATE
            USING (workspace_id = nullif(current_setting('app.current_workspace_id', true), '')::uuid)
            WITH CHECK (workspace_id = nullif(current_setting('app.current_workspace_id', true), '')::uuid);
        """
    )

    # Append-only and immutable tables: SELECT and INSERT only
    simple_tables = [
        "evidence",
        "claim_evidence",
        "claim_relations",
        "audit_events",
        "environment_snapshots",
        "claim_condition_sets",
        "claim_conditions",
        "claim_verifications",
    ]
    for table in simple_tables:
        op.execute(
            f"""
            CREATE POLICY p_{table}_select ON {table}
                FOR SELECT
                USING (workspace_id = nullif(current_setting('app.current_workspace_id', true), '')::uuid);
            """
        )
        op.execute(
            f"""
            CREATE POLICY p_{table}_insert ON {table}
                FOR INSERT
                WITH CHECK (workspace_id = nullif(current_setting('app.current_workspace_id', true), '')::uuid);
            """
        )


def downgrade() -> None:
    # 1. Drop all policies
    all_policies = [
        ("workspaces", ["p_workspaces_select"]),
        ("users", ["p_users_select", "p_users_insert", "p_users_update"]),
        ("agents", ["p_agents_select", "p_agents_insert", "p_agents_update"]),
        ("claims", ["p_claims_select", "p_claims_insert", "p_claims_update"]),
        ("evidence", ["p_evidence_select", "p_evidence_insert"]),
        ("claim_evidence", ["p_claim_evidence_select", "p_claim_evidence_insert"]),
        ("claim_relations", ["p_claim_relations_select", "p_claim_relations_insert"]),
        ("audit_events", ["p_audit_events_select", "p_audit_events_insert"]),
        ("environment_snapshots", ["p_environment_snapshots_select", "p_environment_snapshots_insert"]),
        ("claim_condition_sets", ["p_claim_condition_sets_select", "p_claim_condition_sets_insert"]),
        ("claim_conditions", ["p_claim_conditions_select", "p_claim_conditions_insert"]),
        ("claim_verifications", ["p_claim_verifications_select", "p_claim_verifications_insert"]),
    ]

    for table, policies in all_policies:
        for pol in policies:
            op.execute(f"DROP POLICY IF EXISTS {pol} ON {table};")

    # 2. Disable RLS
    for table in TABLES_WITH_RLS:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    # 3. Drop function
    op.execute("DROP FUNCTION IF EXISTS public.filament_lookup_agent(text);")
