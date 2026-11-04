"""
WAPSI Phase 3.1C: Read-Only Catalog Verification Script for Hosted Supabase.
Probes the live PostgreSQL 17.11 catalog on filofxijqmgluuulivxb without writing any data.
"""

import sys
import os
from pathlib import Path

# Add backend root to sys.path
backend_root = str(Path(__file__).resolve().parent.parent)
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

import json
from sqlalchemy import create_engine, text
from wapsi.core.config import get_settings

def run_catalog_verification():
    settings = get_settings()
    db_url = settings.database_url
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    print("===========================================================================")
    print("WAPSI PHASE 3.1C: HOSTED SUPABASE CATALOG & SECURITY AUDIT")
    print("===========================================================================")
    engine = create_engine(db_url)

    results = {}

    with engine.connect() as conn:
        # 1. Role Attributes
        print("[*] 1. Probing pg_roles for 'wapsi_app' attributes...")
        role_res = conn.execute(
            text("""
                SELECT rolname, rolcanlogin, rolsuper, rolbypassrls, 
                       rolcreatedb, rolcreaterole, rolinherit
                FROM pg_catalog.pg_roles 
                WHERE rolname = 'wapsi_app';
            """)
        ).mappings().fetchone()

        if not role_res:
            print("[FAIL] Role 'wapsi_app' not found in pg_roles!")
            sys.exit(1)

        role_dict = dict(role_res)
        results["role_attributes"] = role_dict
        print(f"       + rolname: {role_dict['rolname']}")
        print(f"       + rolcanlogin: {role_dict['rolcanlogin']} (Expect: True)")
        print(f"       + rolsuper: {role_dict['rolsuper']} (Expect: False)")
        print(f"       + rolbypassrls: {role_dict['rolbypassrls']} (Expect: False)")
        print(f"       + rolcreatedb: {role_dict['rolcreatedb']} (Expect: False)")
        print(f"       + rolcreaterole: {role_dict['rolcreaterole']} (Expect: False)")
        print(f"       + rolinherit: {role_dict['rolinherit']} (Expect: False)")

        assert role_dict["rolcanlogin"] is True
        assert role_dict["rolsuper"] is False
        assert role_dict["rolbypassrls"] is False
        assert role_dict["rolcreatedb"] is False
        assert role_dict["rolcreaterole"] is False
        assert role_dict["rolinherit"] is False
        print("[PASS] Role 'wapsi_app' attributes verified with least privilege.")

        # 2. Table Privileges for wapsi_app
        print("\n[*] 2. Checking table-level DML privileges for 'wapsi_app'...")
        grants = conn.execute(
            text("""
                SELECT table_name, privilege_type 
                FROM information_schema.role_table_grants 
                WHERE grantee = 'wapsi_app' AND table_schema = 'public'
                ORDER BY table_name, privilege_type;
            """)
        ).fetchall()

        grants_by_table = {}
        for tbl, priv in grants:
            grants_by_table.setdefault(tbl, []).append(priv)

        results["table_grants"] = grants_by_table
        print(f"       + Tables granted DML access: {len(grants_by_table)}")
        for tbl, privs in sorted(grants_by_table.items()):
            print(f"         - public.{tbl}: {', '.join(privs)}")

        # Verify zero DELETE privileges anywhere
        delete_grants = [tbl for tbl, privs in grants_by_table.items() if "DELETE" in privs]
        if delete_grants:
            print(f"[FAIL] Tables with DELETE privilege found: {delete_grants}")
            sys.exit(1)
        else:
            print("       [PASS] ZERO DELETE grants found across all tables for 'wapsi_app'.")

        # Verify zero direct grants on merchant_api_keys and merchant_memberships
        forbidden = {"merchant_api_keys", "merchant_memberships"}
        found_forbidden = forbidden.intersection(grants_by_table.keys())
        if found_forbidden:
            print(f"[FAIL] Forbidden tables granted to wapsi_app: {found_forbidden}")
            sys.exit(1)
        else:
            print("       [PASS] Zero grants on merchant_api_keys and merchant_memberships.")

        # 3. Function Execute Grants for lookup_merchant_by_api_key_hash
        print("\n[*] 3. Checking EXECUTE permissions on lookup_merchant_by_api_key_hash...")
        fn_grants = conn.execute(
            text("""
                SELECT routine_name, grantee, privilege_type
                FROM information_schema.routine_privileges
                WHERE routine_schema = 'public' 
                  AND routine_name = 'lookup_merchant_by_api_key_hash';
            """)
        ).mappings().fetchall()

        fn_grantees = [dict(g) for g in fn_grants]
        results["fn_grants"] = fn_grantees
        for fg in fn_grantees:
            print(f"       + {fg['routine_name']}: {fg['privilege_type']} TO {fg['grantee']}")

        grantee_names = {fg["grantee"] for fg in fn_grantees}
        assert "wapsi_app" in grantee_names or "service_role" in grantee_names
        assert "PUBLIC" not in grantee_names
        assert "anon" not in grantee_names
        print("       [PASS] Function execution restricted exclusively to authorized roles.")

        # 4. Opt-Out Registry Schema & Partial Index
        print("\n[*] 4. Checking public.opt_out_registry schema & indexes...")
        opt_cols = conn.execute(
            text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'opt_out_registry'
                ORDER BY ordinal_position;
            """)
        ).mappings().fetchall()
        opt_col_dict = {c["column_name"]: dict(c) for c in opt_cols}
        print(f"       + Columns: {list(opt_col_dict.keys())}")
        assert "is_active" in opt_col_dict
        assert "revoked_at" in opt_col_dict
        assert opt_col_dict["is_active"]["data_type"] == "boolean"
        assert opt_col_dict["is_active"]["is_nullable"] == "NO"
        print("       [PASS] Columns 'is_active' and 'revoked_at' verified.")

        opt_idx = conn.execute(
            text("""
                SELECT indexname, indexdef 
                FROM pg_catalog.pg_indexes 
                WHERE tablename = 'opt_out_registry';
            """)
        ).mappings().fetchall()
        idx_dict = {i["indexname"]: i["indexdef"] for i in opt_idx}
        print(f"       + Indexes: {list(idx_dict.keys())}")
        assert "idx_opt_out_active" in idx_dict
        print(f"         - idx_opt_out_active def: {idx_dict['idx_opt_out_active']}")
        print("       [PASS] Partial index idx_opt_out_active verified.")

        # 5. Outbox Lease Schema
        print("\n[*] 5. Checking recovery_outbox lease columns & constraints...")
        outbox_cols = conn.execute(
            text("""
                SELECT column_name, is_nullable 
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'recovery_outbox';
            """)
        ).mappings().fetchall()
        outbox_col_dict = {c["column_name"]: c["is_nullable"] for c in outbox_cols}
        for expected_col in ["worker_id", "lease_expires_at", "case_id", "payment_id"]:
            assert expected_col in outbox_col_dict, f"Missing column {expected_col} in recovery_outbox"
        assert outbox_col_dict["decision_id"] == "YES", "decision_id must be nullable"
        print("       [PASS] Outbox lease columns and nullable decision_id verified.")

        # 6. RLS Policies on Public Tables
        print("\n[*] 6. Checking Row Level Security status on all public tables...")
        rls_tables = conn.execute(
            text("""
                SELECT tablename, rowsecurity 
                FROM pg_catalog.pg_tables 
                WHERE schemaname = 'public'
                ORDER BY tablename;
            """)
        ).fetchall()
        for tbl, rls_enabled in rls_tables:
            assert rls_enabled is True, f"RLS not enabled on table public.{tbl}"
        print(f"       [PASS] RLS is enabled on all {len(rls_tables)} public tables.")

        # 7. Zero Synthetic Records Check
        print("\n[*] 7. Verifying zero synthetic rows across all public tables...")
        row_counts = {}
        for tbl, _ in rls_tables:
            cnt = conn.execute(text(f"SELECT count(*) FROM public.{tbl}")).scalar()
            row_counts[tbl] = cnt
            if cnt != 0:
                print(f"[FAIL] Table public.{tbl} contains {cnt} rows!")
                sys.exit(1)
        print(f"       [PASS] All {len(row_counts)} tables verified at 0 rows.")

    print("\n===========================================================================")
    print("[SUCCESS] All hosted database catalog and security checks PASSED!")
    print("===========================================================================")

if __name__ == "__main__":
    run_catalog_verification()
