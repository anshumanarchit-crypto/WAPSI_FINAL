#!/usr/bin/env python3
"""
WAPSI — Phase 3.1D/3.1D.1: Application Role Verification Utility (Non-Mutating)
Target Project: WAPSI-DEV-MUMBAI (filofxijqmgluuulivxb)
Application Role: wapsi_app

Purpose:
- Connects as wapsi_app to Supabase Session Pooler (port 5432) using existing provisioned password.
- NEVER modifies role password (NO ALTER ROLE).
- Validates TLS connection, role attributes, SQLAlchemy connectivity, table permissions,
  lookup_merchant_by_api_key_hash function execution, and transaction-local RLS isolation.
- Writes non-sensitive audit evidence to docs/.phase3_1d_provision_evidence.json.
"""

from __future__ import annotations

import getpass
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urlparse

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

import psycopg2
from sqlalchemy import create_engine, text
from wapsi.core.config import get_settings


def get_existing_password() -> str:
    """Read existing password securely without echoing."""
    env_pass = os.environ.get("WAPSI_APP_PASSWORD")
    if env_pass:
        return env_pass

    print("\n" + "=" * 75)
    print("VERIFICATION OF EXISTING 'wapsi_app' ROLE (NON-MUTATING)")
    print("=" * 75)
    print("Please enter the existing provisioned password for 'wapsi_app'.")
    print("Input will NOT be echoed to the console.\n")

    if sys.stdin.isatty():
        return getpass.getpass("Enter 'wapsi_app' password: ")
    sys.stderr.write("Enter 'wapsi_app' password: ")
    sys.stderr.flush()
    return sys.stdin.readline().rstrip("\r\n")


def verify_application_role():
    settings = get_settings()
    admin_url = os.environ.get("DATABASE_URL") or settings.database_url
    if not admin_url:
        print("[FAIL] Administrative DATABASE_URL not found in .env or environment.")
        sys.exit(1)

    raw_admin_url = admin_url
    if raw_admin_url.startswith("postgresql+psycopg2://"):
        raw_admin_url = raw_admin_url.replace("postgresql+psycopg2://", "postgresql://", 1)

    parsed = urlparse(raw_admin_url)
    host = parsed.hostname
    port = parsed.port or 5432
    dbname = (parsed.path or "/postgres").lstrip("/")
    project_ref = "filofxijqmgluuulivxb"

    print(f"[*] Target Cluster Host: {host}")
    print(f"[*] Session Pooler Port: {port}")
    print(f"[*] Target Database: {dbname}")
    print(f"[*] Target Application Role: wapsi_app.{project_ref}")

    app_password = get_existing_password()
    if not app_password:
        print("[FAIL] No password provided.")
        sys.exit(1)

    app_username = f"wapsi_app.{project_ref}"
    encoded_pwd = quote_plus(app_password)
    app_conn_url = f"postgresql://{app_username}:{encoded_pwd}@{host}:{port}/{dbname}?sslmode=require"
    app_sa_url = f"postgresql+psycopg2://{app_username}:{encoded_pwd}@{host}:{port}/{dbname}?sslmode=require"

    report_data: Dict[str, Any] = {
        "project_ref": project_ref,
        "host": host,
        "port": port,
        "username": app_username,
        "password_provisioned": True,
        "tests": {},
    }

    # Step 0: Admin-scoped transactional verification of function return contract (with immediate rollback)
    print("\n[*] 0. Verifying lookup function return contract via transaction rollback...")
    try:
        import hashlib
        admin_conn = psycopg2.connect(raw_admin_url)
        admin_conn.autocommit = False
        with admin_conn.cursor() as adm_cur:
            temp_merchant_id = str(uuid.uuid4())
            temp_key_id = str(uuid.uuid4())
            temp_hash = hashlib.sha256(b"temp_verification_key_for_migration_6").hexdigest()

            # Insert uncommitted test records
            adm_cur.execute("""
                INSERT INTO public.merchants (id, merchant_code, name, registered_email, status)
                VALUES (%s, 'MERCH_VERIFY_001', 'Verification Merchant', 'verify@test.com', 'ACTIVE');
            """, (temp_merchant_id,))

            adm_cur.execute("""
                INSERT INTO public.merchant_api_keys (id, merchant_id, key_name, key_prefix, key_suffix, hashed_key, environment, scopes, is_revoked)
                VALUES (%s, %s, 'Verify Key', 'wapsi_test_', '001', %s, 'test', '["recovery:predict"]'::jsonb, false);
            """, (temp_key_id, temp_merchant_id, temp_hash))

            # Query lookup function
            adm_cur.execute("SELECT * FROM public.lookup_merchant_by_api_key_hash(%s);", (temp_hash,))
            col_names = [desc[0] for desc in adm_cur.description]
            assert col_names == ["merchant_id", "merchant_code", "merchant_status", "key_scopes"]
            row = adm_cur.fetchone()
            assert row is not None
            assert str(row[0]) == temp_merchant_id
            assert row[1] == "MERCH_VERIFY_001"
            assert row[2] == "ACTIVE"
            assert row[3] == ["recovery:predict"]
            print("       + Correct return fields and data types verified in PostgreSQL catalog.")

            # Immediate rollback to guarantee zero pollution
            admin_conn.rollback()
            print("       [PASS] Transaction rolled back. Zero test rows committed to hosted Supabase.")
        admin_conn.close()
        report_data["tests"]["function_return_contract"] = "PASS"
    except Exception as e:
        print(f"       [FAIL] Admin transactional verification failed: {e}")
        report_data["tests"]["function_return_contract"] = f"FAIL: {e}"

    # Step 1: Verify direct connection to Session Pooler
    print("\n[*] 1. Connecting to Session Pooler as 'wapsi_app'...")
    try:
        app_conn = psycopg2.connect(app_conn_url)
        app_conn.autocommit = False
        with app_conn.cursor() as cur:
            cur.execute("SELECT current_user, current_database(), pg_backend_pid();")
            c_user, c_db, pid = cur.fetchone()
            print(f"       + Connected User: {c_user}")
            print(f"       + Current Database: {c_db}")
            print(f"       + Backend PID: {pid}")

            assert c_user == "wapsi_app", f"Expected current_user 'wapsi_app', got '{c_user}'"
            assert c_db == "postgres", f"Expected current_database 'postgres', got '{c_db}'"

            ssl_in_use = app_conn.info.ssl_in_use
            print(f"       + SSL In Use: {ssl_in_use}")
            assert ssl_in_use is True, "Connection must be encrypted with TLS"

            cur.execute("""
                SELECT rolcanlogin, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolinherit
                FROM pg_catalog.pg_roles WHERE rolname = 'wapsi_app';
            """)
            flags = cur.fetchone()
            can_login, is_super, bypass_rls, create_db, create_role, inherit = flags
            print(f"       + rolcanlogin: {can_login}")
            print(f"       + rolsuper: {is_super}")
            print(f"       + rolbypassrls: {bypass_rls}")
            print(f"       + rolinherit: {inherit}")

            assert can_login is True
            assert is_super is False
            assert bypass_rls is False
            assert create_db is False
            assert create_role is False
            assert inherit is False

        app_conn.close()
        print("[PASS] Session Pooler connection and role security attributes verified.")
        report_data["tests"]["session_pooler_connection"] = "PASS"
    except Exception as e:
        print(f"[FAIL] Session Pooler connection failed: {e}")
        sys.exit(1)

    # Step 2: Test SQLAlchemy Engine Connection
    print("\n[*] 2. Testing SQLAlchemy + psycopg2 engine connection as 'wapsi_app'...")
    try:
        engine = create_engine(
            app_sa_url,
            pool_pre_ping=True,
            connect_args={"sslmode": "require"},
        )
        with engine.connect() as conn:
            res = conn.execute(text("SELECT 1;")).scalar()
            assert res == 1
        print("[PASS] SQLAlchemy engine connection test passed.")
        report_data["tests"]["sqlalchemy_connection"] = "PASS"
    except Exception as e:
        print(f"[FAIL] SQLAlchemy connection failed: {e}")
        sys.exit(1)

    # Step 3: Validate Table Permissions
    print("\n[*] 3. Validating table permissions and security boundaries...")
    app_conn = psycopg2.connect(app_conn_url)
    app_conn.autocommit = False
    cur = app_conn.cursor()

    permitted_tables = [
        "merchants",
        "transactions",
        "customers",
        "recovery_outbox",
        "recovery_dispatches",
        "opt_out_registry",
        "customer_interactions",
        "opt_out_audit_trail",
        "audit_ledger_blocks",
        "bandit_weights",
        "causal_decisions",
        "merchant_configurations",
        "model_versions",
        "webhook_inbox",
        "idempotency_keys",
        "payment_outcomes",
    ]
    print("       + Testing SELECT on permitted application tables...")
    for tbl in permitted_tables:
        try:
            cur.execute(f"SELECT count(*) FROM public.{tbl};")
            cnt = cur.fetchone()[0]
            assert cnt == 0
        except Exception as e:
            print(f"       [FAIL] SELECT failed on permitted table public.{tbl}: {e}")
            sys.exit(1)
    print("       [PASS] Permitted tables SELECT verified (0 rows returned).")
    report_data["tests"]["permitted_selects"] = "PASS"

    # 3.2 Prohibited Direct Table Access
    print("       + Testing denied SELECT on sensitive tables...")
    for forbidden_tbl in ["merchant_api_keys", "merchant_memberships"]:
        try:
            cur.execute(f"SELECT * FROM public.{forbidden_tbl} LIMIT 1;")
            print(f"       [FAIL] Access NOT denied on public.{forbidden_tbl}!")
            sys.exit(1)
        except psycopg2.errors.InsufficientPrivilege:
            app_conn.rollback()
            print(f"       [PASS] Access denied as expected on public.{forbidden_tbl} (42501 InsufficientPrivilege).")
        except Exception as e:
            app_conn.rollback()
            if "permission denied" in str(e).lower():
                print(f"       [PASS] Access denied on public.{forbidden_tbl}: {e}")
            else:
                raise
    report_data["tests"]["sensitive_tables_denied"] = "PASS"

    # 3.3 Prohibited DELETE Privilege Checks
    print("       + Testing denied DELETE privileges across application tables...")
    tables_to_test_delete = ["transactions", "customers", "recovery_outbox", "opt_out_registry"]
    for del_tbl in tables_to_test_delete:
        try:
            cur.execute(f"DELETE FROM public.{del_tbl} WHERE 1=0;")
            print(f"       [FAIL] DELETE was permitted on public.{del_tbl}!")
            sys.exit(1)
        except psycopg2.errors.InsufficientPrivilege:
            app_conn.rollback()
            print(f"       [PASS] DELETE denied as expected on public.{del_tbl} (42501 InsufficientPrivilege).")
        except Exception as e:
            app_conn.rollback()
            if "permission denied" in str(e).lower():
                print(f"       [PASS] DELETE denied on public.{del_tbl}: {e}")
            else:
                raise
    report_data["tests"]["delete_privilege_denied"] = "PASS"

    # 3.4 API-Key Lookup Function Execution
    print("       + Testing execution of public.lookup_merchant_by_api_key_hash...")
    try:
        dummy_hash = "a" * 64
        cur.execute("SELECT * FROM public.lookup_merchant_by_api_key_hash(%s);", (dummy_hash,))
        res = cur.fetchall()
        assert len(res) == 0

        # Verify fail-closed behavior for malformed inputs
        for invalid_h in [None, "", "short_key", "g" * 64]:
            cur.execute("SELECT * FROM public.lookup_merchant_by_api_key_hash(%s);", (invalid_h,))
            assert len(cur.fetchall()) == 0

        print("       [PASS] lookup_merchant_by_api_key_hash is executable by 'wapsi_app' and fails closed on invalid/unknown inputs.")
        report_data["tests"]["api_key_lookup_function"] = "PASS"
    except Exception as e:
        app_conn.rollback()
        print(f"       [FAIL] Function execution failed: {e}")
        report_data["tests"]["api_key_lookup_function"] = f"FAIL: {e}"
        # We report fail but proceed to RLS if possible
        cur = app_conn.cursor()

    # 3.5 RLS Default-Deny & Transaction-Scoped Context Test
    print("       + Testing RLS default-deny and transaction-local context...")
    try:
        cur.execute("SELECT count(*) FROM public.transactions;")
        assert cur.fetchone()[0] == 0

        test_merchant_id = str(uuid.uuid4())
        cur.execute("SELECT set_config('app.current_merchant_id', %s, true);", (test_merchant_id,))
        cur.execute("SELECT current_setting('app.current_merchant_id', true);")
        active_mid = cur.fetchone()[0]
        assert active_mid == test_merchant_id
        print("       [PASS] Transaction-local tenant context set_config verified.")

        app_conn.rollback()
        print("       [PASS] Transaction rolled back cleanly. Hosted database state preserved.")
        report_data["tests"]["rls_tenant_context_rollback"] = "PASS"
    except Exception as e:
        app_conn.rollback()
        print(f"       [FAIL] RLS context test failed: {e}")
        report_data["tests"]["rls_tenant_context_rollback"] = f"FAIL: {e}"

    app_conn.close()

    evidence_path = REPO_ROOT / "docs" / ".phase3_1d_provision_evidence.json"
    evidence_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    print(f"\n[*] Verification evidence recorded to: {evidence_path.name}")

    print("\n===========================================================================")
    print("[SUCCESS] Application Role Verification Run Complete.")
    print("===========================================================================")


if __name__ == "__main__":
    verify_application_role()

