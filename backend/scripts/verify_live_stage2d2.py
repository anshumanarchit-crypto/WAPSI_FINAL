"""
Read-only live verification script for Phase 6 Stage 2D.2.
"""

from wapsi.db.session import DatabaseManager
from sqlalchemy import text

def verify():
    dm = DatabaseManager()
    print("=== 1. LIVE FUNCTION CATALOG ===")
    with dm.session_scope() as session:
        func = session.execute(text("""
            SELECT 
                p.proname,
                pg_get_function_identity_arguments(p.oid) as args,
                r.rolname as owner,
                r.rolbypassrls as bypass_rls,
                p.prosecdef as is_security_definer,
                p.proacl
            FROM pg_proc p
            JOIN pg_roles r ON p.proowner = r.oid
            WHERE p.proname = 'claim_specific_recovery_outbox_job';
        """)).mappings().one()
        print("Signature & Ownership:", dict(func))

    print("\n=== 2. TENANT JOB VISIBILITY & CLAIMS ===")
    target_job = "5a6587ab-2601-4017-b396-48e3d2fc2fda"
    target_merchant = "04a2aaf8-8c8a-4d99-852c-cefc80e82019"
    wrong_merchant = "11111111-2222-3333-4444-555555555555"

    # A. Correct tenant can see its own job
    with dm.tenant_session_scope(target_merchant) as session:
        row = session.execute(
            text("SELECT id, status, requires_operator_approval, approved_by_operator_id, approved_at, approval_snapshot_hash, worker_id, retry_count FROM public.recovery_outbox WHERE id = :jid;"),
            {"jid": target_job}
        ).mappings().one()
        print("A. Target job under correct tenant scope:", dict(row))

    # B. Wrong tenant cannot see it (RLS)
    with dm.tenant_session_scope(wrong_merchant) as session:
        rows = session.execute(
            text("SELECT id FROM public.recovery_outbox WHERE id = :jid;"),
            {"jid": target_job}
        ).fetchall()
        print("B. Target job visible under wrong tenant scope:", len(rows), "rows")

    # C. Missing context cannot claim it
    with dm.session_scope() as session:
        session.execute(text("SELECT set_config('app.current_merchant_id', '', true);"))
        c_rows = session.execute(
            text("SELECT id FROM public.claim_specific_recovery_outbox_job(:jid, :mid, :wid);"),
            {"jid": target_job, "mid": target_merchant, "wid": "test"}
        ).fetchall()
        print("C. Claim with missing context returned:", len(c_rows), "rows")

    # D. Malformed context cannot claim it
    with dm.session_scope() as session:
        session.execute(text("SELECT set_config('app.current_merchant_id', 'not-a-valid-uuid', true);"))
        d_rows = session.execute(
            text("SELECT id FROM public.claim_specific_recovery_outbox_job(:jid, :mid, :wid);"),
            {"jid": target_job, "mid": target_merchant, "wid": "test"}
        ).fetchall()
        print("D. Claim with malformed context returned:", len(d_rows), "rows")

    # E. Mismatched context cannot claim it
    with dm.tenant_session_scope(wrong_merchant) as session:
        e_rows = session.execute(
            text("SELECT id FROM public.claim_specific_recovery_outbox_job(:jid, :mid, :wid);"),
            {"jid": target_job, "mid": target_merchant, "wid": "test"}
        ).fetchall()
        print("E. Claim with mismatched context returned:", len(e_rows), "rows")

if __name__ == "__main__":
    verify()

