#!/usr/bin/env python3
"""
WAPSI — Phase 3.1D: Secure Application Role Provisioning & Verification Utility
Target Project: WAPSI-DEV-MUMBAI (filofxijqmgluuulivxb)
Application Role: wapsi_app

Requirements:
1. Loads administrative connection privately from .env (never echoed/printed).
2. Prompts operator twice for the new application password using getpass (min 32 chars).
3. Safely executes ALTER ROLE wapsi_app WITH PASSWORD ... using psycopg2.sql composition.
4. Never logs, prints, or persists the plaintext password.
5. Independently tests connection to Session Pooler (port 5432) as wapsi_app.
6. Runs full permission audit (SELECT permitted, DELETE denied, sensitive tables denied, function execute, RLS context test with rollback).
7. Does NOT modify DATABASE_URL or write synthetic data to hosted Supabase.
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
from psycopg2 import sql
from sqlalchemy import create_engine, text
from wapsi.core.config import get_settings


def get_secure_password() -> str:
    """Prompt operator securely for password with confirmation and 32-char validation."""
    env_pass = os.environ.get("WAPSI_APP_NEW_PASSWORD")
    if env_pass:
        if len(env_pass) < 32:
            print(f"[ERROR] WAPSI_APP_NEW_PASSWORD is too short ({len(env_pass)} chars). Minimum 32 chars required.\n")
            sys.exit(1)
        print("[*] Secure password supplied via environment variable.")
        return env_pass

    print("\n" + "=" * 75)
    print("SECURE PASSWORD PROVISIONING FOR 'wapsi_app'")
    print("=" * 75)
    print("Requirement: Minimum 32 characters, high entropy.")
    print("Plaintext input will NOT be echoed to the console.\n")

    def _read_pass(prompt: str) -> str:
        if sys.stdin.isatty():
            return getpass.getpass(prompt)
        # Non-interactive / piped fallback
        sys.stderr.write(prompt)
        sys.stderr.flush()
        line = sys.stdin.readline()
        return line.rstrip("\r\n")

    while True:
        pwd1 = _read_pass("Enter new password for 'wapsi_app' (min 32 chars): ")
        if not pwd1:
            print("[ERROR] Password cannot be empty. Please try again.\n")
            continue
        if len(pwd1) < 32:
            print(f"[ERROR] Password is too short ({len(pwd1)} characters). Minimum is 32 characters.\n")
            continue

        pwd2 = _read_pass("Confirm new password for 'wapsi_app': ")
        if pwd1 != pwd2:
            print("[ERROR] Passwords do not match. Please try again.\n")
            continue

        return pwd1


def mask_url(url: str) -> str:
    """Mask credentials in connection string."""
    if not url:
        return "<EMPTY>"
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)


def provision_and_verify():
    settings = get_settings()
    admin_url = os.environ.get("DATABASE_URL") or settings.database_url
    if not admin_url:
        print("[FAIL] Administrative DATABASE_URL not found in .env or environment.")
        sys.exit(1)

    # Normalize admin_url for psycopg2
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

    # Prompt operator interactively
    new_password = get_secure_password()

    # Step 1: Execute ALTER ROLE as admin
    print("\n[*] 1. Connecting as administrator to provision 'wapsi_app' password...")
    try:
        admin_conn = psycopg2.connect(raw_admin_url)
        admin_conn.autocommit = True
        with admin_conn.cursor() as cur:
            # Safe SQL composition with psycopg2.sql
            alter_query = sql.SQL("ALTER ROLE wapsi_app WITH PASSWORD {};").format(sql.Literal(new_password))
            cur.execute(alter_query)
        admin_conn.close()
        print("[PASS] ALTER ROLE wapsi_app executed successfully via safe SQL composition.")
    except Exception as e:
        print(f"[FAIL] Administrative execution failed: {e}")
        sys.exit(1)

    # Step 2: Establish independent connection as wapsi_app
    app_username = f"wapsi_app.{project_ref}"
    encoded_pwd = quote_plus(new_password)
    app_conn_url = f"postgresql://{app_username}:{encoded_pwd}@{host}:{port}/{dbname}?sslmode=require"
    app_sa_url = f"postgresql+psycopg2://{app_username}:{encoded_pwd}@{host}:{port}/{dbname}?sslmode=require"

    print("\n[*] 2. Verifying independent connection to Session Pooler as 'wapsi_app'...")
    report_data: Dict[str, Any] = {
        "project_ref": project_ref,
        "host": host,
        "port": port,
        "username": app_username,
        "password_provisioned": True,
        "tests": {},
    }

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

            # Check SSL status
            ssl_in_use = app_conn.info.ssl_in_use
            print(f"       + SSL In Use: {ssl_in_use}")
            assert ssl_in_use is True, "Connection must be encrypted with TLS"

            # Check role security flags
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
        print("[PASS] Independent Session Pooler connection verified for 'wapsi_app'.")
        report_data["tests"]["session_pooler_connection"] = "PASS"
    except Exception as e:
        print(f"[FAIL] Application connection failed: {e}")
        sys.exit(1)

    # Step 3: Test SQLAlchemy Engine Connection
    print("\n[*] 3. Testing SQLAlchemy + psycopg2 engine connection as 'wapsi_app'...")
    try:
        engine = create_engine(
            app_sa_url,
            pool_pre_ping=True,
            connect_args={"sslmode": "require"},
        )
        with engine.connect() as conn:
            res = conn.execute(text("SELECT 1;")).scalar()
            assert res == 1
        print("[PASS] SQLAlchemy connection test passed.")
        report_data["tests"]["sqlalchemy_connection"] = "PASS"
    except Exception as e:
        print(f"[FAIL] SQLAlchemy connection failed: {e}")
        sys.exit(1)

    # Step 4: Validate Actual Permissions (Allowed vs Denied)
    print("\n[*] 4. Validating table permissions and security boundaries...")
    app_conn = psycopg2.connect(app_conn_url)
    app_conn.autocommit = False
    cur = app_conn.cursor()

    # 4.1 Permitted SELECT tests
    print("       + Testing SELECT on permitted application tables...")
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

    # 4.2 Prohibited Direct Table Access (merchant_api_keys, merchant_memberships)
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

    # 4.3 Prohibited DELETE Privilege Checks
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

    # 4.4 Hardened API-Key Lookup Function Execution
    print("       + Testing execution of public.lookup_merchant_by_api_key_hash...")
    try:
        # Valid 64-hex dummy key (must execute and return empty set safely)
        dummy_hash = "a" * 64
        cur.execute("SELECT * FROM public.lookup_merchant_by_api_key_hash(%s);", (dummy_hash,))
        res = cur.fetchall()
        assert len(res) == 0
        print("       [PASS] lookup_merchant_by_api_key_hash is executable by 'wapsi_app'.")
        report_data["tests"]["api_key_lookup_function"] = "PASS"
    except Exception as e:
        app_conn.rollback()
        print(f"       [FAIL] Function execution failed: {e}")
        sys.exit(1)

    # 4.5 RLS Default-Deny & Transaction-Scoped Context Test
    print("       + Testing RLS default-deny and transaction-local context...")
    try:
        # Without context -> default deny (0 rows)
        cur.execute("SELECT count(*) FROM public.transactions;")
        assert cur.fetchone()[0] == 0

        # Set transaction-local context
        test_merchant_id = str(uuid.uuid4())
        cur.execute("SELECT set_config('app.current_merchant_id', %s, true);", (test_merchant_id,))
        cur.execute("SELECT current_setting('app.current_merchant_id', true);")
        active_mid = cur.fetchone()[0]
        assert active_mid == test_merchant_id
        print("       [PASS] Transaction-local tenant context set_config verified.")

        # Roll back transaction immediately to guarantee zero persistent pollution
        app_conn.rollback()
        print("       [PASS] Transaction rolled back cleanly. Hosted database state preserved.")
        report_data["tests"]["rls_tenant_context_rollback"] = "PASS"
    except Exception as e:
        app_conn.rollback()
        print(f"       [FAIL] RLS context test failed: {e}")
        sys.exit(1)

    app_conn.close()

    # Step 5: Save audit evidence (strictly without password)
    evidence_path = REPO_ROOT / "docs" / ".phase3_1d_provision_evidence.json"
    evidence_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    print(f"\n[*] Verification evidence recorded to: {evidence_path.name}")

    print("\n===========================================================================")
    print("[SUCCESS] Phase 3.1D Secure Application Role Provisioning Complete!")
    print("          Password provisioned, permissions audited, 0 synthetic records written.")
    print("===========================================================================")


if __name__ == "__main__":
    provision_and_verify()
