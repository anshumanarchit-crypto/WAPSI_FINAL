"""
Verifies Migration 8 live on hosted database:
1. Migration entry in supabase_migrations.schema_migrations
2. Job 5a6587ab status is PENDING_APPROVAL and requires_operator_approval is True
3. claim_recovery_outbox_jobs called by wapsi_app returns 0 rows (job is NOT claimable)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import dotenv
import psycopg2
from sqlalchemy import text
from wapsi.db.session import DatabaseManager

def verify():
    # 1. Admin check: migrations list
    env = dotenv.dotenv_values(".env")
    admin_url = env["WAPSI_ADMIN_DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(admin_url)
    with conn.cursor() as cur:
        cur.execute("SELECT version FROM supabase_migrations.schema_migrations ORDER BY version;")
        versions = [r[0] for r in cur.fetchall()]
        print("Applied migrations:", versions)
        assert "20261102000008" in versions, "Migration 8 not recorded in schema_migrations"
    conn.close()

    # 2. wapsi_app check: inspect job state
    dm = DatabaseManager()
    with dm.tenant_session_scope("04a2aaf8-8c8a-4d99-852c-cefc80e82019") as s:
        stmt = text(
            "SELECT id, status, requires_operator_approval, approved_by_operator_id, "
            "approved_at, approval_snapshot_hash "
            "FROM recovery_outbox WHERE id = :jid"
        )
        row = s.execute(stmt, {"jid": "5a6587ab-2601-4017-b396-48e3d2fc2fda"}).fetchone()
        print("Job 5a6587ab-2601-4017-b396-48e3d2fc2fda state in DB:")
        print(f"  Status: {row[1]}")
        print(f"  Requires Operator Approval: {row[2]}")
        print(f"  Approved By: {row[3]}")
        print(f"  Approved At: {row[4]}")
        print(f"  Approval Snapshot Hash: {row[5]}")
        assert row[1] == "PENDING_APPROVAL", f"Expected PENDING_APPROVAL, got {row[1]}"
        assert row[2] is True, "Expected requires_operator_approval to be True"
        assert row[3] is None, "Expected approved_by_operator_id to be None"

    # 3. wapsi_app check: call claim function
    with dm.session_scope() as s:
        claim_stmt = text(
            "SELECT * FROM public.claim_recovery_outbox_jobs(:w_id, :limit, :lease)"
        )
        claimed = s.execute(claim_stmt, {"w_id": "worker_safety_probe", "limit": 10, "lease": 60}).fetchall()
        print(f"Claim function returned {len(claimed)} claimed jobs (Worker probe cannot claim unapproved jobs).")
        assert len(claimed) == 0, f"Expected 0 claimed jobs, got {len(claimed)}"

    print("ALL LIVE DATABASE VERIFICATIONS PASSED!")

if __name__ == "__main__":
    verify()
