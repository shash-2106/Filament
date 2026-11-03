"""Automated tests validating Filament's SQLAlchemy domain models and metadata."""

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Table, UniqueConstraint

from filament_api.db.base import Base
from filament_api.models import (
    Agent,
    AuditEvent,
    Claim,
    ClaimCondition,
    ClaimConditionSet,
    ClaimEvidence,
    ClaimRelation,
    ClaimVerification,
    EnvironmentSnapshot,
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
    "environment_snapshots",
    "claim_condition_sets",
    "claim_conditions",
    "claim_verifications",
}


def test_all_twelve_tables_registered_in_metadata() -> None:
    """Verifies that all 12 core domain tables are registered on Base.metadata."""
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


def test_agent_api_key_hash_global_uniqueness() -> None:
    """Verifies that the agents model declares a named unique constraint on api_key_hash."""
    table: Table = Base.metadata.tables["agents"]
    uq_constraints = {
        c.name: [col.name for col in c.columns]
        for c in table.constraints
        if isinstance(c, UniqueConstraint)
    }

    # Verify global uniqueness constraint exists on api_key_hash alone
    assert "uq_agents_api_key_hash" in uq_constraints
    assert uq_constraints["uq_agents_api_key_hash"] == ["api_key_hash"]

    # Verify workspace-scoped constraints are preserved
    assert "uq_agents_workspace_name" in uq_constraints
    assert uq_constraints["uq_agents_workspace_name"] == ["workspace_id", "name"]
    assert "uq_agents_workspace_id" in uq_constraints
    assert uq_constraints["uq_agents_workspace_id"] == ["workspace_id", "id"]


def test_environment_snapshot_table_structure_and_constraints() -> None:
    """Verifies environment_snapshots table columns, check constraints, composite FK, and uniqueness."""
    table: Table = Base.metadata.tables["environment_snapshots"]

    # Verify primary key and columns
    assert "id" in table.primary_key.columns
    expected_cols = {
        "id",
        "workspace_id",
        "collected_by_agent",
        "source_type",
        "verification_level",
        "source_ref",
        "scan_scope",
        "snapshot_data",
        "created_at",
    }
    assert expected_cols.issubset(set(table.columns.keys()))

    # Verify workspace uniqueness
    uq_names = {c.name: [col.name for col in c.columns] for c in table.constraints if isinstance(c, UniqueConstraint)}
    assert "uq_env_snapshots_workspace_id" in uq_names
    assert uq_names["uq_env_snapshots_workspace_id"] == ["workspace_id", "id"]

    # Verify check constraints
    check_constraints = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)}
    assert "ck_env_snapshots_source_type" in check_constraints
    assert "agent_client" in check_constraints["ck_env_snapshots_source_type"]
    assert "ci_webhook" in check_constraints["ck_env_snapshots_source_type"]
    assert "mcp_adapter" in check_constraints["ck_env_snapshots_source_type"]

    assert "ck_env_snapshots_verification_level" in check_constraints
    assert "agent_reported" in check_constraints["ck_env_snapshots_verification_level"]
    assert "independently_verified" in check_constraints["ck_env_snapshots_verification_level"]

    assert "ck_env_snapshots_scan_scope" in check_constraints
    assert "full_repository" in check_constraints["ck_env_snapshots_scan_scope"]
    assert "selective" in check_constraints["ck_env_snapshots_scan_scope"]

    # Verify agent composite FK with RESTRICT
    fks = {c.name: c for c in table.constraints if isinstance(c, ForeignKeyConstraint)}
    assert "fk_env_snapshots_agent" in fks
    assert [col.name for col in fks["fk_env_snapshots_agent"].columns] == ["workspace_id", "collected_by_agent"]
    assert [elem.target_fullname for elem in fks["fk_env_snapshots_agent"].elements] == ["agents.workspace_id", "agents.id"]
    assert fks["fk_env_snapshots_agent"].ondelete == "RESTRICT"


def test_claim_condition_sets_structure_and_constraints() -> None:
    """Verifies claim_condition_sets versioned constraints, RESTRICT FKs, and composite integrity."""
    table: Table = Base.metadata.tables["claim_condition_sets"]

    assert "id" in table.primary_key.columns
    expected_cols = {
        "id",
        "workspace_id",
        "claim_id",
        "version",
        "based_on_snapshot_id",
        "established_by_agent",
        "rationale",
        "created_at",
    }
    assert expected_cols.issubset(set(table.columns.keys()))

    # Verify uniqueness on (workspace_id, claim_id, version)
    uq_names = {c.name: [col.name for col in c.columns] for c in table.constraints if isinstance(c, UniqueConstraint)}
    assert "uq_claim_condition_sets_version" in uq_names
    assert uq_names["uq_claim_condition_sets_version"] == ["workspace_id", "claim_id", "version"]

    # Verify composite FKs
    fks = {c.name: c for c in table.constraints if isinstance(c, ForeignKeyConstraint)}
    assert "fk_claim_condition_sets_claim" in fks
    assert [col.name for col in fks["fk_claim_condition_sets_claim"].columns] == ["workspace_id", "claim_id"]
    assert [elem.target_fullname for elem in fks["fk_claim_condition_sets_claim"].elements] == ["claims.workspace_id", "claims.id"]
    assert fks["fk_claim_condition_sets_claim"].ondelete == "RESTRICT"

    assert "fk_claim_condition_sets_snapshot" in fks
    assert [col.name for col in fks["fk_claim_condition_sets_snapshot"].columns] == ["workspace_id", "based_on_snapshot_id"]
    assert [elem.target_fullname for elem in fks["fk_claim_condition_sets_snapshot"].elements] == ["environment_snapshots.workspace_id", "environment_snapshots.id"]
    assert fks["fk_claim_condition_sets_snapshot"].ondelete == "RESTRICT"

    assert "fk_claim_condition_sets_agent" in fks
    assert [col.name for col in fks["fk_claim_condition_sets_agent"].columns] == ["workspace_id", "established_by_agent"]
    assert [elem.target_fullname for elem in fks["fk_claim_condition_sets_agent"].elements] == ["agents.workspace_id", "agents.id"]
    assert fks["fk_claim_condition_sets_agent"].ondelete == "RESTRICT"


def test_claim_conditions_structure_and_constraints() -> None:
    """Verifies claim_conditions check constraints, uniqueness, and CASCADE FK to condition set."""
    table: Table = Base.metadata.tables["claim_conditions"]

    assert "id" in table.primary_key.columns
    expected_cols = {
        "id",
        "workspace_id",
        "claim_id",
        "condition_set_version",
        "condition_type",
        "target_path",
        "comparator",
        "expected_hash",
        "expected_value",
        "is_critical",
        "created_at",
    }
    assert expected_cols.issubset(set(table.columns.keys()))

    # Verify uniqueness on (workspace_id, claim_id, condition_set_version, condition_type, target_path)
    uq_names = {c.name: [col.name for col in c.columns] for c in table.constraints if isinstance(c, UniqueConstraint)}
    assert "uq_claim_conditions_entry" in uq_names
    assert uq_names["uq_claim_conditions_entry"] == [
        "workspace_id",
        "claim_id",
        "condition_set_version",
        "condition_type",
        "target_path",
    ]

    # Verify check constraints
    check_constraints = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)}
    assert "ck_claim_conditions_type" in check_constraints
    assert "file_hash" in check_constraints["ck_claim_conditions_type"]
    assert "lockfile_hash" in check_constraints["ck_claim_conditions_type"]
    assert "package_version" in check_constraints["ck_claim_conditions_type"]
    assert "runtime_fact" in check_constraints["ck_claim_conditions_type"]

    assert "ck_claim_conditions_comparator" in check_constraints
    assert "hash_equals" in check_constraints["ck_claim_conditions_comparator"]
    assert "version_equals" in check_constraints["ck_claim_conditions_comparator"]
    assert "runtime_equals" in check_constraints["ck_claim_conditions_comparator"]

    # Verify CASCADE FK to parent condition set
    fks = {c.name: c for c in table.constraints if isinstance(c, ForeignKeyConstraint)}
    assert "fk_claim_conditions_set" in fks
    assert [col.name for col in fks["fk_claim_conditions_set"].columns] == [
        "workspace_id",
        "claim_id",
        "condition_set_version",
    ]
    assert [elem.target_fullname for elem in fks["fk_claim_conditions_set"].elements] == [
        "claim_condition_sets.workspace_id",
        "claim_condition_sets.claim_id",
        "claim_condition_sets.version",
    ]
    assert fks["fk_claim_conditions_set"].ondelete == "CASCADE"


def test_claim_verifications_structure_and_constraints() -> None:
    """Verifies claim_verifications audit trail, checks, CASCADE to set, and RESTRICT to snapshot and agent."""
    table: Table = Base.metadata.tables["claim_verifications"]

    assert "id" in table.primary_key.columns
    expected_cols = {
        "id",
        "workspace_id",
        "claim_id",
        "condition_set_version",
        "snapshot_id",
        "verification_type",
        "outcome",
        "evaluation_details",
        "verified_by_agent",
        "attestation_notes",
        "created_at",
    }
    assert expected_cols.issubset(set(table.columns.keys()))

    # Verify check constraints
    check_constraints = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)}
    assert "ck_claim_verifications_type" in check_constraints
    assert "initial" in check_constraints["ck_claim_verifications_type"]
    assert "reverification" in check_constraints["ck_claim_verifications_type"]

    assert "ck_claim_verifications_outcome" in check_constraints
    assert "applicable" in check_constraints["ck_claim_verifications_outcome"]
    assert "environment_mismatch" in check_constraints["ck_claim_verifications_outcome"]
    assert "indeterminate" in check_constraints["ck_claim_verifications_outcome"]

    # Verify FKs
    fks = {c.name: c for c in table.constraints if isinstance(c, ForeignKeyConstraint)}
    assert "fk_claim_verifications_set" in fks
    assert [col.name for col in fks["fk_claim_verifications_set"].columns] == [
        "workspace_id",
        "claim_id",
        "condition_set_version",
    ]
    assert [elem.target_fullname for elem in fks["fk_claim_verifications_set"].elements] == [
        "claim_condition_sets.workspace_id",
        "claim_condition_sets.claim_id",
        "claim_condition_sets.version",
    ]
    assert fks["fk_claim_verifications_set"].ondelete == "CASCADE"

    assert "fk_claim_verifications_snapshot" in fks
    assert [col.name for col in fks["fk_claim_verifications_snapshot"].columns] == ["workspace_id", "snapshot_id"]
    assert [elem.target_fullname for elem in fks["fk_claim_verifications_snapshot"].elements] == [
        "environment_snapshots.workspace_id",
        "environment_snapshots.id",
    ]
    assert fks["fk_claim_verifications_snapshot"].ondelete == "RESTRICT"

    assert "fk_claim_verifications_agent" in fks
    assert [col.name for col in fks["fk_claim_verifications_agent"].columns] == ["workspace_id", "verified_by_agent"]
    assert [elem.target_fullname for elem in fks["fk_claim_verifications_agent"].elements] == [
        "agents.workspace_id",
        "agents.id",
    ]
    assert fks["fk_claim_verifications_agent"].ondelete == "RESTRICT"


def test_claims_active_condition_version_and_composite_fk() -> None:
    """Verifies claims table active_condition_version column and composite foreign key to condition sets."""
    table: Table = Base.metadata.tables["claims"]

    # Verify column presence and nullability
    assert "active_condition_version" in table.columns
    col = table.columns["active_condition_version"]
    assert col.nullable is True

    # Verify composite FK constraint to claim_condition_sets
    fks = {c.name: c for c in table.constraints if isinstance(c, ForeignKeyConstraint)}
    assert "fk_claims_active_condition_set" in fks
    fk = fks["fk_claims_active_condition_set"]
    assert [c.name for c in fk.columns] == ["workspace_id", "id", "active_condition_version"]
    assert [elem.target_fullname for elem in fk.elements] == [
        "claim_condition_sets.workspace_id",
        "claim_condition_sets.claim_id",
        "claim_condition_sets.version",
    ]
    assert fk.ondelete == "RESTRICT"
    assert fk.use_alter is True

