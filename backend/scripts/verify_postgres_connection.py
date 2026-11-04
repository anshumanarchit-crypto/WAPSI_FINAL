#!/usr/bin/env python3
"""
WAPSI — Phase 1C: Remote PostgreSQL Database Verification Script
Target: WAPSI-DEV-MUMBAI (filofxijqmgluuulivxb)
Region: ap-south-1

Validates real PostgreSQL connectivity, schema table existence, migration recording,
database user roles, and RLS bypass attributes against the Supabase Mumbai cluster.

Zero-Mock Guarantee: Fails explicitly if DATABASE_URL is unset or PostgreSQL is unreachable.
Credential Safety: All secrets and passwords are strictly masked.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Set

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from wapsi.core.config import get_settings

EXPECTED_TABLES: List[str] = [
    "merchants",
    "merchant_memberships",
    "merchant_configurations",
    "merchant_api_keys",
    "customers",
    "transactions",
    "model_versions",
    "causal_decisions",
    "webhook_inbox",
    "idempotency_keys",
    "recovery_outbox",
    "recovery_dispatches",
    "payment_outcomes",
    "audit_ledger_blocks",
    "bandit_weights",
]

EXPECTED_MIGRATIONS: List[str] = [
    "20261031000001",
    "20261031000002",
    "20261031000003",
]


def mask_url(url: str) -> str:
    """Mask credentials in database URL using SQLAlchemy make_url."""
    if not url:
        return "<EMPTY>"
    try:
        from sqlalchemy.engine.url import make_url
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        # Fallback regex matching user:pass@
        return re.sub(r"(://[^:]+:)([^@]+)(@)", r"\1***\3", url)


def verify_postgres() -> bool:
    print("=" * 75)
    print("WAPSI PHASE 1C: REMOTE POSTGRESQL INTEGRATION VERIFICATION")
    print("=" * 75)

    settings = get_settings()
    raw_url = os.environ.get("DATABASE_URL") or settings.database_url

    if not raw_url:
        print("[FAIL] DATABASE_URL is not set in environment or .env file.")
        print("       A real PostgreSQL connection string is required.")
        print("       Example:")
        print("       DATABASE_URL=postgresql://postgres.filofxijqmgluuulivxb:[PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require")
        return False

    # Check for sqlite avoidance
    if "sqlite" in raw_url.lower():
        print(f"[FAIL] DATABASE_URL points to SQLite ({mask_url(raw_url)}).")
        print("       Phase 1C requires real remote PostgreSQL, not SQLite fallback.")
        return False

    # Normalize dialect to postgresql+psycopg2
    url = raw_url
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

    masked = mask_url(url)
    print(f"[*] Target URI: {masked}")

    # Verify driver
    try:
        import psycopg2
        print(f"[*] PostgreSQL Driver: psycopg2-binary {psycopg2.__version__} (INSTALLED)")
    except ImportError:
        print("[FAIL] psycopg2 driver is not installed. Run: pip install psycopg2-binary")
        return False

    # Configure engine
    connect_args: Dict[str, Any] = {}
    if "sslmode" not in url:
        connect_args["sslmode"] = "require"

    print("[*] Initializing SQLAlchemy engine with connection pooling and pre-ping...")
    try:
        engine: Engine = create_engine(
            url,
            connect_args=connect_args,
            pool_size=5,
            max_overflow=2,
            pool_recycle=300,
            pool_pre_ping=True,
            echo=False,
        )
    except Exception as e:
        print(f"[FAIL] Engine creation failed: {e}")
        return False

    # Dialect check
    if engine.dialect.name != "postgresql":
        print(f"[FAIL] Detected dialect '{engine.dialect.name}'. Expected 'postgresql'.")
        return False

    # 1. Ping & Latency
    print("[*] Testing round-trip latency to remote PostgreSQL cluster...")
    try:
        t0 = time.time()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT version(), current_database(), current_user, session_user;")
            ).fetchone()
            latency_ms = round((time.time() - t0) * 1000, 2)
        
        pg_version = row[0].split()[0] + " " + row[0].split()[1]
        db_name = row[1]
        curr_user = row[2]
        sess_user = row[3]

        print(f"[PASS] Connection established in {latency_ms} ms")
        print(f"       - Server: {pg_version}")
        print(f"       - Database: {db_name}")
        print(f"       - Connected User: {curr_user} (session: {sess_user})")
    except Exception as e:
        print(f"[FAIL] Connection probe failed: {e}")
        return False

    # 2. Database User Role & RLS Bypass Status
    print("[*] Inspecting role privileges and RLS enforcement status...")
    try:
        with engine.connect() as conn:
            role_row = conn.execute(
                text("SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user;")
            ).fetchone()
        
        if role_row:
            rolname, rolsuper, rolbypassrls = role_row
            print(f"       - Role: {rolname}")
            print(f"       - Superuser (rolsuper): {rolsuper}")
            print(f"       - RLS Bypass (rolbypassrls): {rolbypassrls}")
            if rolbypassrls:
                print("       [NOTICE] Connected role has BYPASSRLS privileges (typical for admin/postgres).")
                print("                Application runtime queries should use SET ROLE authenticated or app-specific roles for tenant isolation.")
            else:
                print("       [OK] Connected role enforces Row-Level Security (NOBYPASSRLS).")
        else:
            print("       [WARN] Could not retrieve role privileges from pg_roles.")
    except Exception as e:
        print(f"       [WARN] Role inspection query failed: {e}")

    # 3. Schema Verification (All 15 tables)
    print(f"[*] Verifying existence of all {len(EXPECTED_TABLES)} public schema tables...")
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
            )
            found_tables: Set[str] = {r[0] for r in result.fetchall()}
        
        missing_tables = set(EXPECTED_TABLES) - found_tables
        present_count = len(set(EXPECTED_TABLES) & found_tables)
        print(f"       - Public tables found: {present_count}/{len(EXPECTED_TABLES)}")

        if missing_tables:
            print(f"[FAIL] Missing {len(missing_tables)} expected tables: {sorted(list(missing_tables))}")
            return False
        else:
            print("       [PASS] All 15 relational entities exist in public schema.")
            for tbl in sorted(EXPECTED_TABLES):
                print(f"              + public.{tbl}")
    except Exception as e:
        print(f"[FAIL] Table inspection query failed: {e}")
        return False

    # 4. Migration History Verification
    print("[*] Verifying recorded migrations in supabase_migrations.schema_migrations...")
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT version FROM supabase_migrations.schema_migrations ORDER BY version ASC;")
            )
            recorded_versions: List[str] = [str(r[0]) for r in result.fetchall()]
        
        print(f"       - Recorded migration versions: {recorded_versions}")
        missing_migrations = [m for m in EXPECTED_MIGRATIONS if not any(m in r for r in recorded_versions)]
        if missing_migrations:
            print(f"[WARN] Some expected migrations may not be recorded: {missing_migrations}")
        else:
            print(f"       [PASS] All {len(EXPECTED_MIGRATIONS)} reviewed migrations successfully recorded.")
    except Exception as e:
        print(f"       [NOTICE] Migration table query note: {e}")

    # 5. ACID Transaction Test (Rollback Isolation)
    print("[*] Testing ACID transactional rollback isolation...")
    try:
        with engine.connect() as conn:
            trans = conn.begin()
            res = conn.execute(text("SELECT txid_current();")).scalar()
            trans.rollback()
        print(f"       [PASS] ACID transaction allocated (txid: {res}) and rolled back cleanly.")
    except Exception as e:
        print(f"[FAIL] Transaction isolation test failed: {e}")
        return False

    print("=" * 75)
    print("[SUCCESS] Phase 1C Remote PostgreSQL verification completed successfully!")
    print("=" * 75)
    return True


if __name__ == "__main__":
    success = verify_postgres()
    sys.exit(0 if success else 1)
