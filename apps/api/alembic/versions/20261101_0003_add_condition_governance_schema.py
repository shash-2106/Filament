"""add_condition_governance_schema

Revision ID: 20261101_0003
Revises: 20261029_0002
Create Date: 2026-11-01 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20261101_0003'
down_revision: Union[str, None] = '20261029_0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. environment_snapshots
    op.create_table(
        'environment_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('collected_by_agent', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_type', sa.String(length=32), nullable=False, server_default='agent_client'),
        sa.Column('verification_level', sa.String(length=32), nullable=False, server_default='agent_reported'),
        sa.Column('source_ref', sa.String(length=128), nullable=False),
        sa.Column('scan_scope', sa.String(length=32), nullable=False, server_default='full_repository'),
        sa.Column('snapshot_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("source_type IN ('agent_client', 'ci_webhook', 'mcp_adapter')", name='ck_env_snapshots_source_type'),
        sa.CheckConstraint("verification_level IN ('agent_reported', 'independently_verified')", name='ck_env_snapshots_verification_level'),
        sa.CheckConstraint("scan_scope IN ('full_repository', 'selective')", name='ck_env_snapshots_scan_scope'),
        sa.ForeignKeyConstraint(['workspace_id', 'collected_by_agent'], ['agents.workspace_id', 'agents.id'], name='fk_env_snapshots_agent', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_env_snapshots_workspace_id'),
    )
    op.create_index('idx_env_snapshots_lookup', 'environment_snapshots', ['workspace_id', 'source_ref', 'created_at'], unique=False)

    # 2. claim_condition_sets
    op.create_table(
        'claim_condition_sets',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('claim_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('based_on_snapshot_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('established_by_agent', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id', 'claim_id'], ['claims.workspace_id', 'claims.id'], name='fk_claim_condition_sets_claim', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['workspace_id', 'based_on_snapshot_id'], ['environment_snapshots.workspace_id', 'environment_snapshots.id'], name='fk_claim_condition_sets_snapshot', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['workspace_id', 'established_by_agent'], ['agents.workspace_id', 'agents.id'], name='fk_claim_condition_sets_agent', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'claim_id', 'version', name='uq_claim_condition_sets_version'),
    )
    op.create_index('idx_claim_condition_sets_claim', 'claim_condition_sets', ['workspace_id', 'claim_id', 'version'], unique=False)

    # 3. claim_conditions
    op.create_table(
        'claim_conditions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('claim_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('condition_set_version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('condition_type', sa.String(length=32), nullable=False),
        sa.Column('target_path', sa.Text(), nullable=False),
        sa.Column('comparator', sa.String(length=32), nullable=False, server_default='hash_equals'),
        sa.Column('expected_hash', sa.String(length=64), nullable=True),
        sa.Column('expected_value', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('is_critical', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("condition_type IN ('file_hash', 'lockfile_hash', 'package_version', 'runtime_fact')", name='ck_claim_conditions_type'),
        sa.CheckConstraint("comparator IN ('hash_equals', 'version_equals', 'runtime_equals')", name='ck_claim_conditions_comparator'),
        sa.ForeignKeyConstraint(['workspace_id', 'claim_id', 'condition_set_version'], ['claim_condition_sets.workspace_id', 'claim_condition_sets.claim_id', 'claim_condition_sets.version'], name='fk_claim_conditions_set', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'claim_id', 'condition_set_version', 'condition_type', 'target_path', name='uq_claim_conditions_entry'),
    )
    op.create_index('idx_claim_conditions_query', 'claim_conditions', ['workspace_id', 'claim_id', 'condition_set_version'], unique=False)

    # 4. claim_verifications
    op.create_table(
        'claim_verifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('claim_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('condition_set_version', sa.Integer(), nullable=False),
        sa.Column('snapshot_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('verification_type', sa.String(length=32), nullable=False, server_default='reverification'),
        sa.Column('outcome', sa.String(length=32), nullable=False),
        sa.Column('evaluation_details', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('verified_by_agent', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('attestation_notes', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("verification_type IN ('initial', 'reverification')", name='ck_claim_verifications_type'),
        sa.CheckConstraint("outcome IN ('applicable', 'environment_mismatch', 'indeterminate')", name='ck_claim_verifications_outcome'),
        sa.ForeignKeyConstraint(['workspace_id', 'claim_id', 'condition_set_version'], ['claim_condition_sets.workspace_id', 'claim_condition_sets.claim_id', 'claim_condition_sets.version'], name='fk_claim_verifications_set', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id', 'snapshot_id'], ['environment_snapshots.workspace_id', 'environment_snapshots.id'], name='fk_claim_verifications_snapshot', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['workspace_id', 'verified_by_agent'], ['agents.workspace_id', 'agents.id'], name='fk_claim_verifications_agent', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_claim_verifications_timeline', 'claim_verifications', ['workspace_id', 'claim_id', 'created_at'], unique=False)

    # 5. Extend claims table with active_condition_version and circular composite foreign key
    op.add_column('claims', sa.Column('active_condition_version', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_claims_active_condition_set',
        'claims',
        'claim_condition_sets',
        ['workspace_id', 'id', 'active_condition_version'],
        ['workspace_id', 'claim_id', 'version'],
        ondelete='RESTRICT',
    )

    # 6. Condition History Immutability Protection (PostgreSQL Function & Triggers)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION filament_protect_condition_history() RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only and cannot be updated or deleted', TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_protect_environment_snapshots
        BEFORE UPDATE OR DELETE ON environment_snapshots
        FOR EACH ROW EXECUTE FUNCTION filament_protect_condition_history();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_protect_claim_condition_sets
        BEFORE UPDATE OR DELETE ON claim_condition_sets
        FOR EACH ROW EXECUTE FUNCTION filament_protect_condition_history();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_protect_claim_conditions
        BEFORE UPDATE OR DELETE ON claim_conditions
        FOR EACH ROW EXECUTE FUNCTION filament_protect_condition_history();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_protect_claim_verifications
        BEFORE UPDATE OR DELETE ON claim_verifications
        FOR EACH ROW EXECUTE FUNCTION filament_protect_condition_history();
        """
    )


def downgrade() -> None:
    # 1. Drop immutability triggers
    op.execute("DROP TRIGGER IF EXISTS trg_protect_claim_verifications ON claim_verifications;")
    op.execute("DROP TRIGGER IF EXISTS trg_protect_claim_conditions ON claim_conditions;")
    op.execute("DROP TRIGGER IF EXISTS trg_protect_claim_condition_sets ON claim_condition_sets;")
    op.execute("DROP TRIGGER IF EXISTS trg_protect_environment_snapshots ON environment_snapshots;")

    # 2. Drop protect function
    op.execute("DROP FUNCTION IF EXISTS filament_protect_condition_history();")

    # 3. Drop circular foreign key and column on claims
    op.drop_constraint('fk_claims_active_condition_set', 'claims', type_='foreignkey')
    op.drop_column('claims', 'active_condition_version')

    # 4. Drop tables in reverse dependency order
    op.drop_table('claim_verifications')
    op.drop_table('claim_conditions')
    op.drop_table('claim_condition_sets')
    op.drop_table('environment_snapshots')

