"""Add model usage and budget tracking ledger table with security definer global summary function.

Revision ID: 20261104_0005
Revises: 20261103_0004
Create Date: 2026-11-04 15:50:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '20261104_0005'
down_revision: Union[str, None] = '20261103_0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create model_usage_records table
    op.create_table(
        'model_usage_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('feature', sa.String(length=64), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('estimated_input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_reserved_output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('actual_input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('actual_output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reserved_cost_usd', sa.Numeric(precision=12, scale=6), nullable=False, server_default='0.000000'),
        sa.Column('actual_cost_usd', sa.Numeric(precision=12, scale=6), nullable=False, server_default='0.000000'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='RESERVED'),
        sa.Column('provider_request_id', sa.String(length=128), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('RESERVED', 'SUCCEEDED', 'FAILED', 'UNKNOWN')", name='ck_model_usage_status'),
        sa.CheckConstraint('reserved_cost_usd >= 0', name='ck_model_usage_reserved_cost_non_negative'),
        sa.CheckConstraint('actual_cost_usd >= 0', name='ck_model_usage_actual_cost_non_negative'),
        sa.CheckConstraint('estimated_input_tokens >= 0', name='ck_model_usage_est_input_non_negative'),
        sa.CheckConstraint('max_reserved_output_tokens >= 0', name='ck_model_usage_max_output_non_negative'),
    )

    op.create_index('ix_model_usage_status', 'model_usage_records', ['status'])
    op.create_index('ix_model_usage_created_at', 'model_usage_records', ['created_at'])
    op.create_index('ix_model_usage_workspace_created', 'model_usage_records', ['workspace_id', 'created_at'])

    # 2. Enable RLS on model_usage_records
    op.execute("ALTER TABLE public.model_usage_records ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY filament_model_usage_select ON public.model_usage_records
        FOR SELECT TO public
        USING (workspace_id = NULLIF(current_setting('filament.current_workspace_id', true), '')::uuid);
        """
    )
    op.execute(
        """
        CREATE POLICY filament_model_usage_insert ON public.model_usage_records
        FOR INSERT TO public
        WITH CHECK (workspace_id = NULLIF(current_setting('filament.current_workspace_id', true), '')::uuid);
        """
    )
    op.execute(
        """
        CREATE POLICY filament_model_usage_update ON public.model_usage_records
        FOR UPDATE TO public
        USING (workspace_id = NULLIF(current_setting('filament.current_workspace_id', true), '')::uuid)
        WITH CHECK (workspace_id = NULLIF(current_setting('filament.current_workspace_id', true), '')::uuid);
        """
    )

    # 3. Create Narrowly Scoped SECURITY DEFINER function to compute genuine GLOBAL spending totals across all workspaces
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.filament_get_global_model_budget_summary()
        RETURNS TABLE (
            actual_spend_usd numeric(12, 6),
            reserved_spend_usd numeric(12, 6),
            unknown_spend_usd numeric(12, 6),
            total_committed_usd numeric(12, 6),
            daily_spend_usd numeric(12, 6),
            total_requests bigint,
            succeeded_count bigint,
            reserved_count bigint,
            failed_count bigint,
            unknown_count bigint
        )
        LANGUAGE plpgsql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, pg_temp
        AS $$
        DECLARE
            v_actual numeric(12, 6);
            v_reserved numeric(12, 6);
            v_unknown numeric(12, 6);
            v_total numeric(12, 6);
            v_daily_actual numeric(12, 6);
            v_daily_pending numeric(12, 6);
            v_daily numeric(12, 6);
            v_tot_req bigint;
            v_succ bigint;
            v_res bigint;
            v_fail bigint;
            v_unk bigint;
        BEGIN
            -- Global actual spend (SUCCEEDED)
            SELECT COALESCE(SUM(m.actual_cost_usd), 0.000000)
            INTO v_actual
            FROM public.model_usage_records m
            WHERE m.status = 'SUCCEEDED';

            -- Global reserved in-flight spend (RESERVED)
            SELECT COALESCE(SUM(m.reserved_cost_usd), 0.000000)
            INTO v_reserved
            FROM public.model_usage_records m
            WHERE m.status = 'RESERVED';

            -- Global unknown / ambiguous spend (UNKNOWN)
            SELECT COALESCE(SUM(m.reserved_cost_usd), 0.000000)
            INTO v_unknown
            FROM public.model_usage_records m
            WHERE m.status = 'UNKNOWN';

            v_total := v_actual + v_reserved + v_unknown;

            -- Daily spend (past 24h rolling)
            SELECT COALESCE(SUM(m.actual_cost_usd), 0.000000)
            INTO v_daily_actual
            FROM public.model_usage_records m
            WHERE m.status = 'SUCCEEDED' AND m.created_at >= (now() - interval '24 hours');

            SELECT COALESCE(SUM(m.reserved_cost_usd), 0.000000)
            INTO v_daily_pending
            FROM public.model_usage_records m
            WHERE m.status IN ('RESERVED', 'UNKNOWN') AND m.created_at >= (now() - interval '24 hours');

            v_daily := v_daily_actual + v_daily_pending;

            -- Status Counts
            SELECT COUNT(*) INTO v_tot_req FROM public.model_usage_records;
            SELECT COUNT(*) INTO v_succ FROM public.model_usage_records WHERE status = 'SUCCEEDED';
            SELECT COUNT(*) INTO v_res FROM public.model_usage_records WHERE status = 'RESERVED';
            SELECT COUNT(*) INTO v_fail FROM public.model_usage_records WHERE status = 'FAILED';
            SELECT COUNT(*) INTO v_unk FROM public.model_usage_records WHERE status = 'UNKNOWN';

            RETURN QUERY SELECT
                v_actual,
                v_reserved,
                v_unknown,
                v_total,
                v_daily,
                v_tot_req,
                v_succ,
                v_res,
                v_fail,
                v_unk;
        END;
        $$;
        """
    )

    # 4. Grant execute permissions to runtime role filament_app
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'filament_app') THEN
                GRANT SELECT, INSERT ON public.model_usage_records TO filament_app;
                GRANT UPDATE (status, actual_input_tokens, actual_output_tokens, actual_cost_usd, provider_request_id, error_message, completed_at) ON public.model_usage_records TO filament_app;
                GRANT EXECUTE ON FUNCTION public.filament_get_global_model_budget_summary() TO filament_app;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.filament_get_global_model_budget_summary();")
    op.drop_table('model_usage_records')
