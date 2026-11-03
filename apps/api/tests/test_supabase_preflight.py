"""Tests for the non-destructive Supabase preflight inspection script."""

import os
import sys
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure apps/api is in sys.path
scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from supabase_preflight import (
    PreflightReport,
    inspect_connection,
    mask_database_url,
    run_preflight,
    FILAMENT_TABLES,
    FILAMENT_FUNCTIONS,
)


def test_mask_database_url():
    raw_url = "postgresql+asyncpg://my_user:super_secret_pw@db.project.supabase.co:5432/postgres"
    masked = mask_database_url(raw_url)
    assert "super_secret_pw" not in masked
    assert "***" in masked
    assert "my_user" in masked
    assert "db.project.supabase.co" in masked


def test_mask_database_url_invalid():
    assert mask_database_url("invalid:::url") == "<invalid or unparseable database url>"


@pytest.mark.asyncio
async def test_inspect_connection_clean_database():
    mock_conn = AsyncMock()

    # Mock version
    mock_conn.scalar.side_effect = [
        "PostgreSQL 15.6 on x86_64",  # SELECT version()
        '"$user", public',           # SHOW search_path
    ]

    # Mock execute results
    id_result = MagicMock()
    id_result.first.return_value = ("postgres", "postgres", "postgres", "public")

    role_result = MagicMock()
    role_result.first.return_value = (True, True)  # superuser=True, bypassrls=True

    ext_result = MagicMock()
    ext_result.fetchall.return_value = [("uuid-ossp", "1.1"), ("pgcrypto", "1.3")]

    tables_result = MagicMock()
    # No filament tables
    tables_result.fetchall.return_value = [("spatial_ref_sys",)]

    funcs_result = MagicMock()
    # No filament functions
    funcs_result.fetchall.return_value = []

    roles_result = MagicMock()
    roles_result.fetchall.return_value = [("authenticated",), ("anon",), ("service_role",)]

    mock_conn.execute.side_effect = [
        id_result,
        role_result,
        ext_result,
        tables_result,
        funcs_result,
        roles_result,
    ]

    report = await inspect_connection(mock_conn)

    assert report.is_clean is True
    assert report.pg_version.startswith("PostgreSQL 15.6")
    assert report.current_user == "postgres"
    assert report.user_is_superuser is True
    assert report.user_bypass_rls is True
    assert len(report.conflicting_tables) == 0
    assert len(report.conflicting_functions) == 0
    assert "uuid-ossp (v1.1)" in report.installed_extensions

    # Verify strictly non-destructive: all queries are SELECT or SHOW
    for call in mock_conn.execute.call_args_list:
        query_text = str(call[0][0].text).strip().upper()
        assert query_text.startswith("SELECT") or query_text.startswith("SHOW")
        assert not any(kw in query_text for kw in ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE"])


@pytest.mark.asyncio
async def test_inspect_connection_detects_conflicts():
    mock_conn = AsyncMock()
    mock_conn.scalar.side_effect = ["PostgreSQL 16.0", "public"]

    id_result = MagicMock()
    id_result.first.return_value = ("filament_app", "filament_app", "postgres", "public")

    role_result = MagicMock()
    role_result.first.return_value = (False, False)

    ext_result = MagicMock()
    ext_result.fetchall.return_value = []

    # Partially provisioned tables
    tables_result = MagicMock()
    tables_result.fetchall.return_value = [("claims",), ("workspaces",), ("some_other_table",)]

    # Partially provisioned functions
    funcs_result = MagicMock()
    funcs_result.fetchall.return_value = [("filament_protect_audit_log",)]

    roles_result = MagicMock()
    roles_result.fetchall.return_value = [("filament_app",)]

    mock_conn.execute.side_effect = [
        id_result,
        role_result,
        ext_result,
        tables_result,
        funcs_result,
        roles_result,
    ]

    report = await inspect_connection(mock_conn)

    assert report.is_clean is False
    assert report.conflicting_tables == ["claims", "workspaces"]
    assert report.conflicting_functions == ["filament_protect_audit_log"]


@pytest.mark.asyncio
async def test_run_preflight_connection_error_never_leaks_password():
    secret_url = "postgresql+asyncpg://admin:super_secret_password_123@supabase.invalid:5432/postgres"

    with patch("supabase_preflight.create_async_engine") as mock_engine:
        mock_engine.side_effect = Exception("Failed to resolve host with credentials password_123")

        report = await run_preflight(secret_url)

        assert report.is_clean is False
        assert report.error_message is not None
        # Must not leak password
        assert "super_secret_password_123" not in report.error_message
        assert "***" in report.error_message
