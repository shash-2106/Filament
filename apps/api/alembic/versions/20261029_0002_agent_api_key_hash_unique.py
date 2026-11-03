"""add_agent_api_key_hash_unique_constraint

Revision ID: 20261029_0002
Revises: 20261029_0001
Create Date: 2026-10-29 10:50:00.000000

DEPLOYMENT PRECONDITION:
Before applying this migration to an existing live database with pre-populated records,
operators must verify that no duplicate values exist in the agents.api_key_hash column:
    SELECT api_key_hash, COUNT(*) FROM agents GROUP BY api_key_hash HAVING COUNT(*) > 1;
Any duplicates must be resolved or rotated prior to execution.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '20261029_0002'
down_revision: Union[str, None] = '20261029_0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enforce global uniqueness on agents.api_key_hash across all workspaces
    op.create_unique_constraint(
        'uq_agents_api_key_hash',
        'agents',
        ['api_key_hash'],
    )


def downgrade() -> None:
    # Drop global uniqueness constraint on agents.api_key_hash
    op.drop_constraint(
        'uq_agents_api_key_hash',
        'agents',
        type_='unique',
    )

