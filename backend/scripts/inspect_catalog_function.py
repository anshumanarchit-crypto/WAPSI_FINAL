import os
import sys
import psycopg2
from dotenv import load_dotenv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

url = os.environ.get("DATABASE_URL")
if not url:
    print("DATABASE_URL not found")
    sys.exit(1)

if url.startswith("postgresql+psycopg2://"):
    url = url.replace("postgresql+psycopg2://", "postgresql://", 1)

conn = psycopg2.connect(url)
cur = conn.cursor()

print("=== COLUMNS OF public.merchants ===")
cur.execute("""
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'merchants'
    ORDER BY ordinal_position;
""")
for row in cur.fetchall():
    print(f"  {row[0]:<25} {row[1]:<20} nullable={row[2]}")

print("\n=== COLUMNS OF public.merchant_api_keys ===")
cur.execute("""
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'merchant_api_keys'
    ORDER BY ordinal_position;
""")
for row in cur.fetchall():
    print(f"  {row[0]:<25} {row[1]:<20} nullable={row[2]}")

print("\n=== DEFINITION OF public.lookup_merchant_by_api_key_hash ===")
cur.execute("""
    SELECT p.proname, pg_get_functiondef(p.oid)
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname = 'lookup_merchant_by_api_key_hash';
""")
for row in cur.fetchall():
    print(f"Function Name: {row[0]}")
    print(row[1])

print("\n=== FUNCTION OWNER AND ATTRIBUTES ===")
cur.execute("""
    SELECT p.proname, r.rolname, p.prosecdef, p.proconfig
    FROM pg_proc p
    JOIN pg_roles r ON r.oid = p.proowner
    WHERE p.proname = 'lookup_merchant_by_api_key_hash';
""")
for row in cur.fetchall():
    print(f"  Name: {row[0]}, Owner: {row[1]}, SecurityDefiner: {row[2]}, ProConfig (search_path): {row[3]}")

print("\n=== PERMISSIONS / GRANTS ON FUNCTION ===")
cur.execute("""
    SELECT grantee, privilege_type
    FROM information_schema.routine_privileges
    WHERE routine_schema = 'public' AND routine_name = 'lookup_merchant_by_api_key_hash';
""")
for row in cur.fetchall():
    print(f"  Grantee: {row[0]:<20} Privilege: {row[1]}")

conn.close()
