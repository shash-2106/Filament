"""initial_filament_schema

Revision ID: 20261029_0001
Revises: 
Create Date: 2026-10-29 10:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20261029_0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. workspaces
    op.create_table(
        'workspaces',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('slug', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug', name='uq_workspaces_slug')
    )
    op.create_index('ix_workspaces_slug', 'workspaces', ['slug'], unique=False)

    # 2. users
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('display_name', sa.String(length=128), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False, server_default='member'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("role IN ('owner', 'admin', 'member', 'auditor')", name='ck_users_role'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'email', name='uq_users_workspace_email'),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_users_workspace_id')
    )
    op.create_index('idx_users_workspace_id', 'users', ['workspace_id'], unique=False)

    # 3. agents
    op.create_table(
        'agents',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('api_key_hash', sa.String(length=64), nullable=False),
        sa.Column('system_prompt_hash', sa.String(length=64), nullable=True),
        sa.Column('default_scope', sa.String(length=32), nullable=False, server_default='private'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("default_scope IN ('private', 'team', 'workspace')", name='ck_agents_default_scope'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'name', name='uq_agents_workspace_name'),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_agents_workspace_id')
    )
    op.create_index('idx_agents_workspace', 'agents', ['workspace_id'], unique=False)

    # 4. evidence
    op.create_table(
        'evidence',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_type', sa.String(length=32), nullable=False),
        sa.Column('source_uri', sa.Text(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('raw_snippet', sa.Text(), nullable=False),
        sa.Column('collected_by_agent', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('collected_by_user', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("source_type IN ('file', 'git_commit', 'user_turn', 'tool_output', 'api_response')", name='ck_evidence_source_type'),
        sa.ForeignKeyConstraint(['workspace_id', 'collected_by_agent'], ['agents.workspace_id', 'agents.id'], name='fk_evidence_agent', ondelete='SET NULL (collected_by_agent)'),
        sa.ForeignKeyConstraint(['workspace_id', 'collected_by_user'], ['users.workspace_id', 'users.id'], name='fk_evidence_user', ondelete='SET NULL (collected_by_user)'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_evidence_workspace_id')
    )
    op.create_index('idx_evidence_workspace', 'evidence', ['workspace_id'], unique=False)
    op.create_index('idx_evidence_source_lookup', 'evidence', ['workspace_id', 'source_type', 'content_hash'], unique=False)
    op.create_index('idx_evidence_metadata_gin', 'evidence', ['metadata'], unique=False, postgresql_using='gin')

    # 5. claims
    op.create_table(
        'claims',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('claim_type', sa.String(length=32), nullable=False),
        sa.Column('subject', sa.String(length=128), nullable=False),
        sa.Column('predicate', sa.String(length=64), nullable=False),
        sa.Column('object_value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('raw_statement', sa.Text(), nullable=False),
        sa.Column('scope', sa.String(length=32), nullable=False, server_default='private'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='current'),
        sa.Column('confidence', sa.Numeric(precision=3, scale=2), nullable=False, server_default=sa.text('1.00')),
        sa.Column('version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("claim_type IN ('fact', 'recommendation', 'decision', 'preference', 'constraint')", name='ck_claims_claim_type'),
        sa.CheckConstraint("scope IN ('private', 'team', 'workspace')", name='ck_claims_scope'),
        sa.CheckConstraint("status IN ('current', 'superseded', 'disputed', 'needs_review', 'retracted')", name='ck_claims_status'),
        sa.CheckConstraint('confidence >= 0.00 AND confidence <= 1.00', name='ck_claims_confidence'),
        sa.ForeignKeyConstraint(['workspace_id', 'agent_id'], ['agents.workspace_id', 'agents.id'], name='fk_claims_agent', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_claims_workspace_id')
    )
    op.create_index('idx_claims_query_active', 'claims', ['workspace_id', 'scope', 'status', 'subject'], unique=False)
    op.create_index('idx_claims_agent_scope', 'claims', ['workspace_id', 'agent_id', 'scope'], unique=False)
    op.create_index('idx_claims_status', 'claims', ['status'], unique=False)
    op.create_index('idx_claims_object_gin', 'claims', ['object_value'], unique=False, postgresql_using='gin')

    # 6. claim_evidence
    op.create_table(
        'claim_evidence',
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('claim_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('evidence_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('support_type', sa.String(length=16), nullable=False, server_default='supports'),
        sa.Column('extraction_notes', sa.Text(), nullable=True),
        sa.Column('confidence_weight', sa.Numeric(precision=3, scale=2), nullable=False, server_default=sa.text('1.00')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("support_type IN ('supports', 'refutes', 'mentions')", name='ck_claim_evidence_support_type'),
        sa.CheckConstraint('confidence_weight >= 0.00 AND confidence_weight <= 1.00', name='ck_claim_evidence_confidence_weight'),
        sa.ForeignKeyConstraint(['workspace_id', 'claim_id'], ['claims.workspace_id', 'claims.id'], name='fk_claim_evidence_claim', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id', 'evidence_id'], ['evidence.workspace_id', 'evidence.id'], name='fk_claim_evidence_evidence', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('claim_id', 'evidence_id')
    )
    op.create_index('idx_claim_evidence_reverse', 'claim_evidence', ['evidence_id', 'claim_id'], unique=False)
    op.create_index('idx_claim_evidence_workspace', 'claim_evidence', ['workspace_id'], unique=False)

    # 7. claim_relations
    op.create_table(
        'claim_relations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_claim_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('target_claim_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('relation_type', sa.String(length=32), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('created_by_agent', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('source_claim_id <> target_claim_id', name='ck_claim_relations_no_self_loops'),
        sa.CheckConstraint("relation_type IN ('supersedes', 'depends_on', 'contradicts', 'corroborates')", name='ck_claim_relations_relation_type'),
        sa.ForeignKeyConstraint(['created_by_agent'], ['agents.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['workspace_id', 'source_claim_id'], ['claims.workspace_id', 'claims.id'], name='fk_claim_relations_source_claim', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['workspace_id', 'target_claim_id'], ['claims.workspace_id', 'claims.id'], name='fk_claim_relations_target_claim', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_claim_id', 'target_claim_id', 'relation_type', name='uq_claim_relation_edge')
    )
    op.create_index('idx_claim_relations_target', 'claim_relations', ['target_claim_id', 'relation_type'], unique=False)
    op.create_index('idx_claim_relations_workspace', 'claim_relations', ['workspace_id'], unique=False)

    # 8. audit_events
    op.create_table(
        'audit_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('actor_type', sa.String(length=32), nullable=False),
        sa.Column('actor_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('target_type', sa.String(length=32), nullable=False),
        sa.Column('target_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('idempotency_key', sa.String(length=64), nullable=True),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("actor_type IN ('agent', 'user', 'system')", name='ck_audit_events_actor_type'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_audit_events_timeline', 'audit_events', ['workspace_id', sa.text('created_at DESC')], unique=False)
    op.create_index('idx_audit_target', 'audit_events', ['target_type', 'target_id'], unique=False)
    op.create_index('idx_audit_event_type', 'audit_events', ['event_type'], unique=False)
    op.create_index(
        'uq_audit_idempotency',
        'audit_events',
        ['workspace_id', 'idempotency_key'],
        unique=True,
        postgresql_where=sa.text('idempotency_key IS NOT NULL')
    )

    # 9. Audit Event Integrity Protection (PostgreSQL Function & Trigger)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION filament_protect_audit_log() RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only and cannot be updated or deleted';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_protect_audit_events
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION filament_protect_audit_log();
        """
    )


def downgrade() -> None:
    # 1. Drop trigger and protect function first
    op.execute("DROP TRIGGER IF EXISTS trg_protect_audit_events ON audit_events;")
    op.execute("DROP FUNCTION IF EXISTS filament_protect_audit_log();")

    # 2. Drop tables in reverse dependency order
    op.drop_table('audit_events')
    op.drop_table('claim_relations')
    op.drop_table('claim_evidence')
    op.drop_table('claims')
    op.drop_table('evidence')
    op.drop_table('agents')
    op.drop_table('users')
    op.drop_table('workspaces')
