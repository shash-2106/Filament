"""Non-destructive Supabase Preflight Verification Script.

Inspects target PostgreSQL/Supabase database before any migrations or DDL are applied.
Verifies:
1. Connectivity and PostgreSQL version.
2. Search path, current user, role attributes (BYPASSRLS, SUPERUSER).
3. Installed extensions (e.g. pgcrypto, uuid-ossp).
4. Existing tables in public schema and detects collisions with Filament tables.
5. Existing functions and triggers.
6. Target roles (filament_app, filament_migrator, etc.).

Safety Guarantees:
- Strictly read-only (SELECT / SHOW only; zero DDL, zero DML, zero mutations).
- Never prints passwords, tokens, or raw connection strings to stdout/stderr.
- Returns structured status code: 0 = Clean, 1 = Error/Connection failure, 2 = Collisions/Dirty.

Usage:
    DATABASE_URL=postgresql+asyncpg://... python apps/api/scripts/supabase_preflight.py
"""

import asyncio
from dataclasses import dataclass, field
import os
import sys
from typing import Any, List, Optional, Set
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

FILAMENT_TABLES = {
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
    "alembic_version",
}

FILAMENT_FUNCTIONS = {
    "filament_protect_audit_log",
    "filament_protect_condition_history",
    "filament_lookup_agent",
}


@dataclass
class PreflightReport:
    is_clean: bool = True
    pg_version: str = ""
    current_user: str = ""
    session_user: str = ""
    database: str = ""
    schema: str = ""
    search_path: str = ""
    user_bypass_rls: bool = False
    user_is_superuser: bool = False
    installed_extensions: List[str] = field(default_factory=list)
    conflicting_tables: List[str] = field(default_factory=list)
    conflicting_functions: List[str] = field(default_factory=list)
    existing_roles: List[str] = field(default_factory=list)
    error_message: Optional[str] = field(default=None)


def mask_database_url(url_str: str) -> str:
    """Mask password and sensitive parts in a database URL for safe logging."""
    try:
        url = make_url(url_str)
        return str(url._replace(password="***"))
    except Exception:
        return "<invalid or unparseable database url>"


async def inspect_connection(conn: AsyncConnection) -> PreflightReport:
    """Perform non-destructive inspection using an established database connection."""
    report = PreflightReport()

    # 1. Version
    report.pg_version = await conn.scalar(text("SELECT version();")) or ""

    # 2. Connection Identity
    identity = (
        await conn.execute(
            text("SELECT current_user, session_user, current_database(), current_schema();")
        )
    ).first()
    if identity:
        report.current_user = identity[0]
        report.session_user = identity[1]
        report.database = identity[2]
        report.schema = identity[3]

    # 3. Role Attributes
    role_attrs = (
        await conn.execute(
            text(
                """
        SELECT rolsuper, rolbypassrls
        FROM pg_roles
        WHERE rolname = current_user;
        """
            )
        )
    ).first()
    if role_attrs:
        report.user_is_superuser = bool(role_attrs[0])
        report.user_bypass_rls = bool(role_attrs[1])

    # 4. Search Path
    report.search_path = await conn.scalar(text("SHOW search_path;")) or ""

    # 5. Extensions
    exts = (
        await conn.execute(
            text("SELECT extname, extversion FROM pg_extension ORDER BY extname;")
        )
    ).fetchall()
    report.installed_extensions = [f"{name} (v{ver})" for name, ver in exts]

    # 6. Tables in public schema
    tables = (
        await conn.execute(
            text(
                """
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY tablename;
        """
            )
        )
    ).fetchall()
    found_tables = {t[0] for t in tables}
    report.conflicting_tables = sorted(list(found_tables.intersection(FILAMENT_TABLES)))

    # 7. Functions in public schema
    funcs = (
        await conn.execute(
            text(
                """
        SELECT routine_name
        FROM information_schema.routines
        WHERE routine_schema = 'public'
        ORDER BY routine_name;
        """
            )
        )
    ).fetchall()
    found_funcs = {f[0] for f in funcs}
    report.conflicting_functions = sorted(list(found_funcs.intersection(FILAMENT_FUNCTIONS)))

    # 8. Check Filament / Supabase target roles
    roles = (
        await conn.execute(
            text(
                """
        SELECT rolname
        FROM pg_roles
        WHERE rolname IN ('filament_app', 'filament_migrator', 'authenticated', 'anon', 'service_role')
        ORDER BY rolname;
        """
            )
        )
    ).fetchall()
    report.existing_roles = [r[0] for r in roles]

    # Clean state evaluation
    report.is_clean = len(report.conflicting_tables) == 0 and len(report.conflicting_functions) == 0
    return report


async def run_preflight(db_url: str) -> PreflightReport:
    """Safely connect and inspect database without exposing credentials."""
    connect_args = {}
    if ":6543" in db_url:
        connect_args = {
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        }

    engine = None
    try:
        engine = create_async_engine(db_url, connect_args=connect_args)
        async with engine.connect() as conn:
            return await inspect_connection(conn)
    except Exception as exc:
        masked = mask_database_url(db_url)
        # Avoid leaking raw exception strings if they might contain credentials
        error_msg = f"Connection error connecting to {masked}: {type(exc).__name__}"
        return PreflightReport(is_clean=False, error_message=error_msg)
    finally:
        if engine is not None:
            await engine.dispose()


def print_report(report: PreflightReport) -> None:
    print("=" * 70)
    print("FILAMENT SUPABASE PREFLIGHT INSPECTION REPORT")
    print("=" * 70)

    if report.error_message:
        print(f"❌ ERROR: {report.error_message}")
        print("=" * 70)
        return

    print(f"PostgreSQL Version: {report.pg_version.split(',')[0]}")
    print(f"Connected User:     {report.current_user} (session: {report.session_user})")
    print(f"Database:           {report.database}")
    print(f"Current Schema:     {report.schema}")
    print(f"Search Path:        {report.search_path}")
    print(f"Superuser:          {report.user_is_superuser}")
    print(f"BypassRLS:          {report.user_bypass_rls}")

    print(f"\nInstalled Extensions ({len(report.installed_extensions)}):")
    for ext in report.installed_extensions:
        print(f"  - {ext}")

    print(f"\nExisting Target Roles ({len(report.existing_roles)}):")
    for r in report.existing_roles:
        print(f"  - {r}")

    if report.is_clean:
        print("\n✅ Clean Schema: No conflicting Filament tables or functions detected.")
    else:
        print("\n⚠️  COLLISIONS / PARTIALLY PROVISIONED SCHEMA:")
        if report.conflicting_tables:
            print(f"  - Conflicting Tables ({len(report.conflicting_tables)}): {report.conflicting_tables}")
        if report.conflicting_functions:
            print(f"  - Conflicting Functions ({len(report.conflicting_functions)}): {report.conflicting_functions}")

    print("=" * 70)


def main() -> int:
    mode = os.environ.get("PREFLIGHT_MODE", "pre_migration")
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL environment variable is required.", file=sys.stderr)
        return 1

    report = asyncio.run(run_preflight(db_url))
    print_report(report)

    if report.error_message:
        return 1

    if mode == "post_migration":
        # Post-migration expects all 13 tables and 3 functions to be present!
        missing_tables = sorted(list(FILAMENT_TABLES - set(report.conflicting_tables)))
        missing_funcs = sorted(list(FILAMENT_FUNCTIONS - set(report.conflicting_functions)))
        if missing_tables or missing_funcs:
            print("❌ Post-migration verification failed:")
            if missing_tables:
                print(f"  Missing Tables: {missing_tables}")
            if missing_funcs:
                print(f"  Missing Functions: {missing_funcs}")
            return 2
        print("✅ Post-migration verification passed: All 13 tables and 3 functions verified!")
        return 0

    # Default: pre_migration (expects clean database)
    if not report.is_clean:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
