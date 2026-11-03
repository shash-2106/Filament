"""Automated tests validating Alembic migration configuration and offline SQL generation."""

import io
from pathlib import Path
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic import command
import pytest


@pytest.fixture
def alembic_config() -> Config:
    """Fixture providing Alembic Config object pointing to the api project configuration."""
    api_dir = Path(__file__).parent.parent
    ini_path = api_dir / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(api_dir / "alembic"))
    cfg.set_main_option("prepend_sys_path", str(api_dir / "src"))
    return cfg


def test_migration_revisions_discovery(alembic_config: Config) -> None:
    """Verifies that Alembic script directory discovers all revisions up to Supabase RLS."""
    script = ScriptDirectory.from_config(alembic_config)
    head_revision = script.get_current_head()
    assert head_revision == "20261103_0004"

    # Revision 1: initial schema
    rev1 = script.get_revision("20261029_0001")
    assert rev1 is not None
    assert rev1.down_revision is None
    assert rev1.doc == "initial_filament_schema"

    # Revision 2: global uniqueness constraint on agents.api_key_hash
    rev2 = script.get_revision("20261029_0002")
    assert rev2 is not None
    assert rev2.down_revision == "20261029_0001"
    assert rev2.doc.startswith("add_agent_api_key_hash_unique_constraint")

    # Revision 3: condition governance schema
    rev3 = script.get_revision("20261101_0003")
    assert rev3 is not None
    assert rev3.down_revision == "20261029_0002"
    assert rev3.doc.startswith("add_condition_governance_schema")

    # Revision 4: Supabase RLS and auth bootstrap
    rev4 = script.get_revision("20261103_0004")
    assert rev4 is not None
    assert rev4.down_revision == "20261101_0003"


def test_second_migration_source_contains_unique_constraint(alembic_config: Config) -> None:
    """Verifies that the second migration source defines create and drop for uq_agents_api_key_hash."""
    api_dir = Path(__file__).parent.parent
    migration_file = api_dir / "alembic" / "versions" / "20261029_0002_agent_api_key_hash_unique.py"
    assert migration_file.exists()

    content = migration_file.read_text(encoding="utf-8")
    assert "create_unique_constraint(" in content
    assert "'uq_agents_api_key_hash'" in content
    assert "'api_key_hash'" in content
    assert "drop_constraint(" in content


def test_third_migration_source_contains_condition_governance_schema(alembic_config: Config) -> None:
    """Verifies that the third migration defines condition governance tables, constraints, triggers, and downgrade."""
    api_dir = Path(__file__).parent.parent
    migration_file = api_dir / "alembic" / "versions" / "20261101_0003_add_condition_governance_schema.py"
    assert migration_file.exists()

    content = migration_file.read_text(encoding="utf-8")

    # Verify tables created
    assert "'environment_snapshots'" in content
    assert "'claim_condition_sets'" in content
    assert "'claim_conditions'" in content
    assert "'claim_verifications'" in content

    # Verify claim table extension and circular FK
    assert "active_condition_version" in content
    assert "'fk_claims_active_condition_set'" in content

    # Verify trigger function and 4 protection triggers
    assert "CREATE OR REPLACE FUNCTION filament_protect_condition_history()" in content
    assert "trg_protect_environment_snapshots" in content
    assert "trg_protect_claim_condition_sets" in content
    assert "trg_protect_claim_conditions" in content
    assert "trg_protect_claim_verifications" in content

    # Verify downgrade drops in reverse dependency order
    assert "DROP TRIGGER IF EXISTS trg_protect_claim_verifications ON claim_verifications;" in content
    assert "DROP TRIGGER IF EXISTS trg_protect_claim_conditions ON claim_conditions;" in content
    assert "DROP TRIGGER IF EXISTS trg_protect_claim_condition_sets ON claim_condition_sets;" in content
    assert "DROP TRIGGER IF EXISTS trg_protect_environment_snapshots ON environment_snapshots;" in content
    assert "DROP FUNCTION IF EXISTS filament_protect_condition_history();" in content
    assert "op.drop_constraint('fk_claims_active_condition_set', 'claims', type_='foreignkey')" in content
    assert "op.drop_column('claims', 'active_condition_version')" in content
    assert "op.drop_table('claim_verifications')" in content
    assert "op.drop_table('claim_conditions')" in content
    assert "op.drop_table('claim_condition_sets')" in content
    assert "op.drop_table('environment_snapshots')" in content


def test_migration_source_contains_audit_protection_trigger(alembic_config: Config) -> None:
    """Verifies that the initial migration source defines the audit protection trigger and downgrade."""
    api_dir = Path(__file__).parent.parent
    migration_file = api_dir / "alembic" / "versions" / "20261029_0001_initial_schema.py"
    assert migration_file.exists()

    content = migration_file.read_text(encoding="utf-8")

    # Upgrade assertions
    assert "CREATE OR REPLACE FUNCTION filament_protect_audit_log()" in content
    assert "CREATE TRIGGER trg_protect_audit_events" in content
    assert "audit_events is append-only and cannot be updated or deleted" in content

    # Downgrade assertions
    assert "DROP TRIGGER IF EXISTS trg_protect_audit_events ON audit_events;" in content
    assert "DROP FUNCTION IF EXISTS filament_protect_audit_log();" in content


def test_offline_sql_generation_produces_ddl_without_live_database(
    alembic_config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifies that Alembic generates complete PostgreSQL DDL offline without connecting to a database."""
    # Execute offline upgrade to head
    command.upgrade(alembic_config, "head", sql=True)
    captured = capsys.readouterr()
    generated_sql = captured.out

    # Verify transaction envelope
    assert "BEGIN;" in generated_sql
    assert "COMMIT;" in generated_sql

    # Verify all 12 tables appear in generated DDL
    expected_tables = [
        "CREATE TABLE workspaces",
        "CREATE TABLE users",
        "CREATE TABLE agents",
        "CREATE TABLE evidence",
        "CREATE TABLE claims",
        "CREATE TABLE claim_evidence",
        "CREATE TABLE claim_relations",
        "CREATE TABLE audit_events",
        "CREATE TABLE environment_snapshots",
        "CREATE TABLE claim_condition_sets",
        "CREATE TABLE claim_conditions",
        "CREATE TABLE claim_verifications",
    ]
    for table_ddl in expected_tables:
        assert table_ddl in generated_sql, f"Missing DDL for: {table_ddl}"

    # Verify composite constraints in DDL
    assert "uq_claims_workspace_id" in generated_sql
    assert "fk_claims_agent" in generated_sql
    assert "fk_evidence_agent" in generated_sql
    assert "ON DELETE SET NULL (collected_by_agent)" in generated_sql
    assert "fk_evidence_user" in generated_sql
    assert "ON DELETE SET NULL (collected_by_user)" in generated_sql
    assert "fk_claim_evidence_claim" in generated_sql
    assert "fk_claim_evidence_evidence" in generated_sql
    assert "fk_claim_relations_source_claim" in generated_sql
    assert "fk_claim_relations_target_claim" in generated_sql

    # Verify audit trigger function and trigger in generated DDL
    assert "filament_protect_audit_log()" in generated_sql
    assert "trg_protect_audit_events" in generated_sql

    # Verify second revision constraint in generated DDL
    assert "ALTER TABLE agents ADD CONSTRAINT uq_agents_api_key_hash UNIQUE (api_key_hash);" in generated_sql

    # Verify third revision DDL (condition governance)
    assert "ALTER TABLE claims ADD COLUMN active_condition_version INTEGER;" in generated_sql
    assert "ALTER TABLE claims ADD CONSTRAINT fk_claims_active_condition_set" in generated_sql
    assert "filament_protect_condition_history()" in generated_sql
    assert "trg_protect_environment_snapshots" in generated_sql
    assert "trg_protect_claim_condition_sets" in generated_sql
    assert "trg_protect_claim_conditions" in generated_sql
    assert "trg_protect_claim_verifications" in generated_sql
    assert "UPDATE alembic_version SET version_num='20261101_0003'" in generated_sql
