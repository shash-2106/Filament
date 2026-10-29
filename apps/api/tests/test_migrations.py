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


def test_initial_migration_revision_discovery(alembic_config: Config) -> None:
    """Verifies that Alembic script directory discovers the initial schema revision."""
    script = ScriptDirectory.from_config(alembic_config)
    head_revision = script.get_current_head()
    assert head_revision == "20261029_0001"

    rev = script.get_revision(head_revision)
    assert rev is not None
    assert rev.doc == "initial_filament_schema"


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

    # Verify all 8 tables appear in generated DDL
    expected_tables = [
        "CREATE TABLE workspaces",
        "CREATE TABLE users",
        "CREATE TABLE agents",
        "CREATE TABLE evidence",
        "CREATE TABLE claims",
        "CREATE TABLE claim_evidence",
        "CREATE TABLE claim_relations",
        "CREATE TABLE audit_events",
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
