"""Automated tests validating Filament's SQLAlchemy domain models and metadata."""

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Table, UniqueConstraint

from filament_api.db.base import Base
from filament_api.models import (
    Agent,
    AuditEvent,
    Claim,
    ClaimEvidence,
    ClaimRelation,
    Evidence,
    User,
    Workspace,
)


EXPECTED_TABLES = {
    "workspaces",
    "users",
    "agents",
    "evidence",
    "claims",
    "claim_evidence",
    "claim_relations",
    "audit_events",
}


def test_all_eight_tables_registered_in_metadata() -> None:
    """Verifies that all 8 core domain tables are registered on Base.metadata."""
    registered_tables = set(Base.metadata.tables.keys())
    assert EXPECTED_TABLES.issubset(registered_tables), (
        f"Missing tables: {EXPECTED_TABLES - registered_tables}"
    )


def test_workspace_table_structure() -> None:
    """Verifies workspaces table primary key and unique slug index."""
    table: Table = Base.metadata.tables["workspaces"]
    assert "id" in table.primary_key.columns
    assert "slug" in table.columns
    assert table.columns["slug"].unique is True


def test_claim_table_constraints_and_composite_key() -> None:
    """Verifies claims table check constraints and composite uniqueness for workspace integrity."""
    table: Table = Base.metadata.tables["claims"]

    # Verify composite unique constraint (workspace_id, id)
    uq_names = [c.name for c in table.constraints if isinstance(c, UniqueConstraint)]
    assert "uq_claims_workspace_id" in uq_names

    # Verify check constraints
    check_constraints = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)}
    assert "ck_claims_status" in check_constraints
    assert "current" in check_constraints["ck_claims_status"]
    assert "superseded" in check_constraints["ck_claims_status"]
    assert "needs_review" in check_constraints["ck_claims_status"]
    assert "disputed" in check_constraints["ck_claims_status"]
    assert "retracted" in check_constraints["ck_claims_status"]

    assert "ck_claims_scope" in check_constraints
    assert "private" in check_constraints["ck_claims_scope"]
    assert "team" in check_constraints["ck_claims_scope"]
    assert "workspace" in check_constraints["ck_claims_scope"]

    assert "ck_claims_confidence" in check_constraints
    assert "ck_claims_claim_type" in check_constraints


def test_claim_relations_workspace_consistency_and_direction() -> None:
    """Verifies claim_relations composite foreign keys to (workspace_id, id) and no-self-loop check."""
    table: Table = Base.metadata.tables["claim_relations"]

    # Verify no self loop check
    check_constraints = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)}
    assert "ck_claim_relations_no_self_loops" in check_constraints
    assert "source_claim_id <> target_claim_id" in check_constraints["ck_claim_relations_no_self_loops"]

    assert "ck_claim_relations_relation_type" in check_constraints
    assert "supersedes" in check_constraints["ck_claim_relations_relation_type"]
    assert "depends_on" in check_constraints["ck_claim_relations_relation_type"]

    # Verify composite FK constraints enforcing cross-claim workspace consistency
    fk_constraints = [c for c in table.constraints if isinstance(c, ForeignKeyConstraint)]
    fk_names = {c.name for c in fk_constraints}
    assert "fk_claim_relations_source_claim" in fk_names
    assert "fk_claim_relations_target_claim" in fk_names

    for fk in fk_constraints:
        if fk.name == "fk_claim_relations_source_claim":
            assert [col.name for col in fk.columns] == ["workspace_id", "source_claim_id"]
            assert [elem.target_fullname for elem in fk.elements] == ["claims.workspace_id", "claims.id"]
        elif fk.name == "fk_claim_relations_target_claim":
            assert [col.name for col in fk.columns] == ["workspace_id", "target_claim_id"]
            assert [elem.target_fullname for elem in fk.elements] == ["claims.workspace_id", "claims.id"]


def test_claim_evidence_support_types() -> None:
    """Verifies claim_evidence support_type check constraint and composite foreign keys."""
    table: Table = Base.metadata.tables["claim_evidence"]

    # Composite primary key (claim_id, evidence_id)
    pk_cols = {col.name for col in table.primary_key.columns}
    assert pk_cols == {"claim_id", "evidence_id"}

    check_constraints = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)}
    assert "ck_claim_evidence_support_type" in check_constraints
    assert "supports" in check_constraints["ck_claim_evidence_support_type"]
    assert "refutes" in check_constraints["ck_claim_evidence_support_type"]
    assert "mentions" in check_constraints["ck_claim_evidence_support_type"]

    # Verify composite foreign keys to claims and evidence enforcing workspace boundary
    fk_constraints = [c for c in table.constraints if isinstance(c, ForeignKeyConstraint)]
    fk_names = {c.name for c in fk_constraints}
    assert "fk_claim_evidence_claim" in fk_names
    assert "fk_claim_evidence_evidence" in fk_names

    for fk in fk_constraints:
        if fk.name == "fk_claim_evidence_claim":
            assert [col.name for col in fk.columns] == ["workspace_id", "claim_id"]
            assert [elem.target_fullname for elem in fk.elements] == ["claims.workspace_id", "claims.id"]
        elif fk.name == "fk_claim_evidence_evidence":
            assert [col.name for col in fk.columns] == ["workspace_id", "evidence_id"]
            assert [elem.target_fullname for elem in fk.elements] == ["evidence.workspace_id", "evidence.id"]


def test_cross_workspace_protection_constraints() -> None:
    """Verifies that agents, users, evidence, and claims have composite workspace foreign keys."""
    claims_table: Table = Base.metadata.tables["claims"]
    evidence_table: Table = Base.metadata.tables["evidence"]
    agents_table: Table = Base.metadata.tables["agents"]
    users_table: Table = Base.metadata.tables["users"]

    # Unique workspace identifiers on parent tables
    assert "uq_agents_workspace_id" in [c.name for c in agents_table.constraints if isinstance(c, UniqueConstraint)]
    assert "uq_users_workspace_id" in [c.name for c in users_table.constraints if isinstance(c, UniqueConstraint)]
    assert "uq_evidence_workspace_id" in [c.name for c in evidence_table.constraints if isinstance(c, UniqueConstraint)]

    # Claims agent authorship workspace protection
    claims_fks = {c.name: c for c in claims_table.constraints if isinstance(c, ForeignKeyConstraint)}
    assert "fk_claims_agent" in claims_fks
    assert [col.name for col in claims_fks["fk_claims_agent"].columns] == ["workspace_id", "agent_id"]
    assert [elem.target_fullname for elem in claims_fks["fk_claims_agent"].elements] == ["agents.workspace_id", "agents.id"]

    # Evidence collector workspace protection
    evidence_fks = {c.name: c for c in evidence_table.constraints if isinstance(c, ForeignKeyConstraint)}
    assert "fk_evidence_agent" in evidence_fks
    assert [col.name for col in evidence_fks["fk_evidence_agent"].columns] == ["workspace_id", "collected_by_agent"]
    assert [elem.target_fullname for elem in evidence_fks["fk_evidence_agent"].elements] == ["agents.workspace_id", "agents.id"]
    assert evidence_fks["fk_evidence_agent"].ondelete == "SET NULL (collected_by_agent)"

    assert "fk_evidence_user" in evidence_fks
    assert [col.name for col in evidence_fks["fk_evidence_user"].columns] == ["workspace_id", "collected_by_user"]
    assert [elem.target_fullname for elem in evidence_fks["fk_evidence_user"].elements] == ["users.workspace_id", "users.id"]
    assert evidence_fks["fk_evidence_user"].ondelete == "SET NULL (collected_by_user)"


def test_audit_events_actor_constraints() -> None:
    """Verifies audit_events actor check constraint and restricted delete policy."""
    table: Table = Base.metadata.tables["audit_events"]
    check_constraints = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)}
    assert "ck_audit_events_actor_type" in check_constraints
    assert "agent" in check_constraints["ck_audit_events_actor_type"]
    assert "user" in check_constraints["ck_audit_events_actor_type"]
    assert "system" in check_constraints["ck_audit_events_actor_type"]

    # Verify workspace foreign key uses ON DELETE RESTRICT
    fks = list(table.foreign_keys)
    ws_fk = next(fk for fk in fks if fk.column.table.name == "workspaces")
    assert ws_fk.ondelete == "RESTRICT"

