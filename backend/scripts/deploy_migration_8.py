"""
Deploys Migration 8 to the hosted Supabase database.
"""

from __future__ import annotations

import dotenv
import psycopg2

def deploy():
    env = dotenv.dotenv_values(".env")
    admin_url = env["WAPSI_ADMIN_DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(admin_url)
    conn.autocommit = False

    with open("supabase/migrations/20261102000008_outbox_operator_authorization_gate.sql", "r", encoding="utf-8") as f:
        sql = f.read()

    with conn.cursor() as cur:
        print("Applying Migration 8 to hosted Supabase...")
        cur.execute(sql)
        cur.execute("INSERT INTO supabase_migrations.schema_migrations (version) VALUES ('20261102000008') ON CONFLICT DO NOTHING;")
        conn.commit()
        print("Migration 8 committed successfully!")

    conn.close()

if __name__ == "__main__":
    deploy()

