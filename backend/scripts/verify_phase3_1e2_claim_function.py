#!/usr/bin/env python3
"""
WAPSI — Phase 3.1E.2: Hosted Function & Security Verification Utility
Target: WAPSI-DEV-MUMBAI (filofxijqmgluuulivxb)
Role: wapsi_app & Function public.claim_recovery_outbox_jobs

Validates:
1. Function existence, owner, and signature in pg_proc.
2. SECURITY DEFINER attribute and empty search_path configuration.
3. Strict EXECUTE privileges (granted to wapsi_app and service_role; revoked from PUBLIC, anon, authenticated).
4. Execution on empty outbox queue returns zero rows with correct schema.
5. wapsi_app role attributes (NOBYPASSRLS, NOSUPERUSER).
6. Zero DELETE privileges across all operational tables for wapsi_app.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Ensure repository root in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

import psycopg2


def run_hosted_verification() -> Dict[str, bool]:
    admin_url = os.environ.get("DATABASE_URL")
    if not admin_url:
        print("[FAIL] DATABASE_URL not set in .env")
        sys.exit(1)

    raw_url = admin_url.replace("postgresql+psycopg2://", "postgresql://", 1)
    conn = psycopg2.connect(raw_url)
    cur = conn.cursor()

    results: Dict[str, bool] = {}

    print("=" * 75)
    print("WAPSI PHASE 3.1E.2: HOSTED FUNCTION & SECURITY PRIVILEGE VERIFICATION")
    print("Target: WAPSI-DEV-MUMBAI (filofxijqmgluuulivxb, PostgreSQL 17.11)")
    print("=" * 75)

    # 1. Verify function existence and signature
    print("\n[*] 1. Inspecting function existence and metadata in pg_proc...")
    cur.execute("""
        SELECT 
            p.proname,
            pg_get_function_identity_arguments(p.oid) AS args,
            p.prosecdef AS is_secdef,
            p.proconfig AS config,
            r.rolname AS owner
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        JOIN pg_roles r ON r.oid = p.proowner
        WHERE n.nspname = 'public' AND p.proname = 'claim_recovery_outbox_jobs';
    """)
    fn_row = cur.fetchone()
    if not fn_row:
        print("[FAIL] Function public.claim_recovery_outbox_jobs not found in catalog!")
        results["function_exists"] = False
        sys.exit(1)

    proname, args, is_secdef, proconfig, owner = fn_row
    print(f"       + Function Name: {proname}")
    print(f"       + Arguments: {args}")
    print(f"       + Owner: {owner}")
    print(f"       + SECURITY DEFINER: {is_secdef}")
    print(f"       + Runtime Config (search_path): {proconfig}")

    results["function_exists"] = (proname == "claim_recovery_outbox_jobs")
    results["security_definer"] = (is_secdef is True)
    results["empty_search_path"] = ("search_path=\"\"" in (proconfig or []) or 'search_path=""' in str(proconfig))
    results["trusted_owner"] = (owner == "postgres")

    assert results["function_exists"], "Function name mismatch"
    assert results["security_definer"], "Function must be SECURITY DEFINER"
    assert results["empty_search_path"], "search_path must be pinned to empty string"
    assert results["trusted_owner"], "Function must be owned by administrative postgres role"
    print("[PASS] Function existence, ownership, and SECURITY DEFINER attributes verified.")

    # 2. Verify EXECUTE privileges
    print("\n[*] 2. Verifying EXECUTE privileges across database roles...")
    cur.execute("""
        SELECT 
            has_function_privilege('wapsi_app', 'public.claim_recovery_outbox_jobs(character varying, integer, integer)', 'EXECUTE') AS wapsi_app_exec,
            has_function_privilege('service_role', 'public.claim_recovery_outbox_jobs(character varying, integer, integer)', 'EXECUTE') AS service_role_exec,
            has_function_privilege('anon', 'public.claim_recovery_outbox_jobs(character varying, integer, integer)', 'EXECUTE') AS anon_exec,
            has_function_privilege('authenticated', 'public.claim_recovery_outbox_jobs(character varying, integer, integer)', 'EXECUTE') AS authenticated_exec,
            has_function_privilege('public', 'public.claim_recovery_outbox_jobs(character varying, integer, integer)', 'EXECUTE') AS public_exec;
    """)
    wapsi_app_exec, service_role_exec, anon_exec, auth_exec, pub_exec = cur.fetchone()
    print(f"       + wapsi_app EXECUTE: {wapsi_app_exec}")
    print(f"       + service_role EXECUTE: {service_role_exec}")
    print(f"       + anon EXECUTE: {anon_exec}")
    print(f"       + authenticated EXECUTE: {auth_exec}")
    print(f"       + PUBLIC EXECUTE: {pub_exec}")

    results["wapsi_app_can_execute"] = (wapsi_app_exec is True)
    results["service_role_can_execute"] = (service_role_exec is True)
    results["anon_denied"] = (anon_exec is False)
    results["authenticated_denied"] = (auth_exec is False)
    results["public_denied"] = (pub_exec is False)

    assert results["wapsi_app_can_execute"], "wapsi_app must have EXECUTE privilege"
    assert results["service_role_can_execute"], "service_role must have EXECUTE privilege"
    assert results["anon_denied"], "anon must NOT have EXECUTE privilege"
    assert results["authenticated_denied"], "authenticated must NOT have EXECUTE privilege"
    assert results["public_denied"], "PUBLIC must NOT have EXECUTE privilege"
    print("[PASS] Function privilege isolation strictly enforced.")

    # 3. Test execution on empty queue
    print("\n[*] 3. Testing function execution on empty outbox queue...")
    cur.execute("SELECT * FROM public.claim_recovery_outbox_jobs('verify_worker_preflight_test', 10, 60);")
    rows = cur.fetchall()
    col_names = [d[0] for d in cur.description]
    print(f"       + Claimed Jobs Count: {len(rows)}")
    print(f"       + Output Column Count: {len(col_names)}")
    print(f"       + Output Schema: {col_names}")

    expected_cols = [
        "id", "case_id", "payment_id", "merchant_id", "idempotency_key",
        "action", "channel", "recipient_masked", "message_payload",
        "status", "retry_count", "max_retries", "next_attempt_at",
        "lease_expires_at", "worker_id", "last_error", "created_at", "updated_at"
    ]
    results["empty_queue_zero_rows"] = (len(rows) == 0)
    results["schema_columns_match"] = (col_names == expected_cols)

    assert results["empty_queue_zero_rows"], f"Expected 0 rows on empty queue, got {len(rows)}"
    assert results["schema_columns_match"], "Output columns do not match expected outbox schema"
    print("[PASS] Function executed successfully on empty queue, returning 0 rows with full 18-column schema.")

    # 4. Verify wapsi_app role attributes
    print("\n[*] 4. Inspecting wapsi_app role attributes in pg_roles...")
    cur.execute("""
        SELECT rolname, rolsuper, rolbypassrls, rolinherit, rolcanlogin
        FROM pg_roles
        WHERE rolname = 'wapsi_app';
    """)
    r_name, r_super, r_bypassrls, r_inherit, r_canlogin = cur.fetchone()
    print(f"       + Role Name: {r_name}")
    print(f"       + Superuser (rolsuper): {r_super}")
    print(f"       + RLS Bypass (rolbypassrls): {r_bypassrls}")
    print(f"       + Inherit (rolinherit): {r_inherit}")
    print(f"       + Can Login (rolcanlogin): {r_canlogin}")

    results["wapsi_app_nosuperuser"] = (r_super is False)
    results["wapsi_app_nobypassrls"] = (r_bypassrls is False)
    results["wapsi_app_canlogin"] = (r_canlogin is True)

    assert results["wapsi_app_nosuperuser"], "wapsi_app must NOT be a superuser"
    assert results["wapsi_app_nobypassrls"], "wapsi_app must NOT have BYPASSRLS"
    assert results["wapsi_app_canlogin"], "wapsi_app must be permitted to log in"
    print("[PASS] wapsi_app role security constraints verified (NOSUPERUSER, NOBYPASSRLS).")

    # 5. Confirm zero DELETE privileges on all operational tables
    print("\n[*] 5. Verifying ZERO DELETE privileges on public operational tables...")
    tables_to_check = [
        "merchants",
        "customers",
        "transactions",
        "recovery_outbox",
        "recovery_dispatches",
        "payment_outcomes",
        "opt_out_registry",
        "webhook_inbox",
        "audit_ledger_blocks",
        "bandit_weights",
        "model_versions",
    ]
    zero_delete_all = True
    for tbl in tables_to_check:
        cur.execute(f"SELECT has_table_privilege('wapsi_app', 'public.{tbl}', 'DELETE');")
        del_priv = cur.fetchone()[0]
        print(f"       + public.{tbl}: DELETE privilege = {del_priv}")
        if del_priv:
            zero_delete_all = False

    results["zero_delete_privileges"] = zero_delete_all
    assert results["zero_delete_privileges"], "wapsi_app MUST have ZERO DELETE privileges!"
    print("[PASS] Zero-DELETE privilege invariant confirmed across all operational tables.")

    conn.close()

    print("\n" + "=" * 75)
    print("[SUCCESS] ALL PHASE 3.1E.2 VERIFICATION CHECKS PASSED!")
    print("=" * 75)
    return results


if __name__ == "__main__":
    run_hosted_verification()

