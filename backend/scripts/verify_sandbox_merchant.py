#!/usr/bin/env python3
"""
Inspect and verify the hosted sandbox merchant in WAPSI-DEV-MUMBAI under both admin and wapsi_app role.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

from sqlalchemy import create_engine, text
from wapsi.db.session import get_db_manager

def inspect_merchants():
    admin_url = os.environ.get("WAPSI_ADMIN_DATABASE_URL")
    merchants = []
    if admin_url:
        admin_engine = create_engine(admin_url)
        with admin_engine.connect() as conn:
            print("=== ADMIN INSPECTION ===")
            print("Admin user:", conn.execute(text("SELECT current_user;")).scalar())
            merchants = conn.execute(text("SELECT * FROM public.merchants;")).fetchall()
            print(f"Total merchants in DB: {len(merchants)}")
            for m in merchants:
                print("Merchant row:", dict(m._mapping))
            
            policies = conn.execute(text(
                "SELECT schemaname, tablename, policyname, roles, cmd, qual, with_check "
                "FROM pg_policies WHERE tablename = 'merchants';"
            )).fetchall()
            print("\nMerchants RLS policies:")
            for p in policies:
                print("Policy:", dict(p._mapping))

            api_keys = conn.execute(text("SELECT * FROM public.merchant_api_keys;")).fetchall()
            print(f"\nAPI keys count: {len(api_keys)}")
            for k in api_keys:
                d = dict(k._mapping)
                d["key_hash"] = d["key_hash"][:10] + "..." if d.get("key_hash") else None
                print("API key row:", d)

            memberships = conn.execute(text("SELECT * FROM public.merchant_memberships;")).fetchall()
            print(f"\nMemberships count: {len(memberships)}")
            for mb in memberships:
                print("Membership row:", dict(mb._mapping))

            func_def = conn.execute(text("SELECT pg_get_functiondef(oid) FROM pg_proc WHERE proname = 'has_merchant_role';")).scalar()
            print("\nhas_merchant_role def:\n", func_def)

    print("\n=== WAPSI_APP INSPECTION ===")
    mgr = get_db_manager()
    with mgr.session_scope() as session:
        user = session.execute(text("SELECT current_user;")).scalar()
        print("wapsi_app user:", user)
        if merchants:
            first_m = merchants[0]
            m_id = str(first_m.id)
            print(f"Testing setting tenant context to: {m_id}")
            session.execute(text(f"SELECT set_config('app.current_merchant_id', '{m_id}', true);"))
            rows = session.execute(text("SELECT id, merchant_code, name, status FROM public.merchants;")).fetchall()
            print(f"Rows found for {m_id}: {len(rows)}")
            for r in rows:
                print("Found merchant:", r)

if __name__ == "__main__":
    inspect_merchants()
