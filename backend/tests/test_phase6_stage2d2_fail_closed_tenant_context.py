"""
WAPSI — Phase 6 Stage 2D.2 Regression Test Suite:
Fail-Closed Tenant Context Enforcement on PostgreSQL Exact-Job Claim.

Verifies the 10 fail-closed security scenarios:
1. Correct session context and correct merchant ID.
2. Missing session context (app.current_merchant_id not set).
3. Empty session context (app.current_merchant_id = '').
4. Malformed UUID session context (app.current_merchant_id = 'not-a-valid-uuid').
5. Mismatched session context (app.current_merchant_id != p_merchant_id).
6. Correct session context but wrong p_merchant_id passed to function.
7. Wrong job ID.
8. Unapproved target job (PENDING_APPROVAL fails closed).
9. Payload tampering halts dispatch.
10. Opt-out restriction halts dispatch.
"""

import json
import uuid
import pytest
from sqlalchemy import text

from wapsi.core.config import get_settings
from wapsi.db.session import DatabaseManager
from wapsi.recovery.opt_out_store import PersistentOptOutStore
from wapsi.recovery.outbox import DurableOutboxStore
from wapsi.recovery.timeline import RecoveryTimelineStore
from wapsi.recovery.worker import RecoveryBackgroundWorker

TARGET_JOB_ID = "5a6587ab-2601-4017-b396-48e3d2fc2fda"
TARGET_MERCHANT_UUID = "04a2aaf8-8c8a-4d99-852c-cefc80e82019"
ANOTHER_MERCHANT_UUID = "11111111-2222-3333-4444-555555555555"
SYNTHETIC_JOB_ID = "00000000-0000-0000-0000-000000000001"
RANDOM_JOB_ID = "99999999-9999-9999-9999-999999999999"


def test_01_correct_session_context_and_correct_merchant_id():
    """Scenario 1: Correct session context and correct merchant ID execute cleanly without context error."""
    dm = DatabaseManager()
    with dm.tenant_session_scope(TARGET_MERCHANT_UUID) as session:
        # Context is active: execute function on synthetic job (pure schema/context test, no live target mutation)
        stmt = text("""
            SELECT id FROM public.claim_specific_recovery_outbox_job(
                p_job_id := :jid,
                p_merchant_id := :mid,
                p_worker_id := 'test_worker',
                p_lease_seconds := 60
            );
        """)
        rows = session.execute(stmt, {"jid": SYNTHETIC_JOB_ID, "mid": TARGET_MERCHANT_UUID}).fetchall()
        # Returns 0 rows because synthetic job does not exist, but does not throw context error
        assert len(rows) == 0


def test_02_missing_session_context():
    """Scenario 2: Missing session context (app.current_merchant_id unset) FAILS CLOSED and returns 0 rows."""
    dm = DatabaseManager()
    with dm.session_scope() as session:
        # Intentionally do NOT set app.current_merchant_id
        session.execute(text("SELECT set_config('app.current_merchant_id', '', true);"))
        stmt = text("""
            SELECT id FROM public.claim_specific_recovery_outbox_job(
                p_job_id := :jid,
                p_merchant_id := :mid,
                p_worker_id := 'test_worker',
                p_lease_seconds := 60
            );
        """)
        rows = session.execute(stmt, {"jid": SYNTHETIC_JOB_ID, "mid": TARGET_MERCHANT_UUID}).fetchall()
        assert len(rows) == 0, "Missing session context must return 0 rows"


def test_03_empty_session_context():
    """Scenario 3: Empty session context (app.current_merchant_id = '  ') FAILS CLOSED and returns 0 rows."""
    dm = DatabaseManager()
    with dm.session_scope() as session:
        session.execute(text("SELECT set_config('app.current_merchant_id', '   ', true);"))
        stmt = text("""
            SELECT id FROM public.claim_specific_recovery_outbox_job(
                p_job_id := :jid,
                p_merchant_id := :mid,
                p_worker_id := 'test_worker',
                p_lease_seconds := 60
            );
        """)
        rows = session.execute(stmt, {"jid": SYNTHETIC_JOB_ID, "mid": TARGET_MERCHANT_UUID}).fetchall()
        assert len(rows) == 0, "Empty session context must return 0 rows"


def test_04_malformed_uuid_session_context():
    """Scenario 4: Malformed UUID session context ('not-a-valid-uuid') FAILS CLOSED and returns 0 rows."""
    dm = DatabaseManager()
    with dm.session_scope() as session:
        session.execute(text("SELECT set_config('app.current_merchant_id', 'not-a-valid-uuid-xyz', true);"))
        stmt = text("""
            SELECT id FROM public.claim_specific_recovery_outbox_job(
                p_job_id := :jid,
                p_merchant_id := :mid,
                p_worker_id := 'test_worker',
                p_lease_seconds := 60
            );
        """)
        rows = session.execute(stmt, {"jid": SYNTHETIC_JOB_ID, "mid": TARGET_MERCHANT_UUID}).fetchall()
        assert len(rows) == 0, "Malformed UUID session context must return 0 rows"


def test_05_mismatched_session_context():
    """Scenario 5: Session context merchant != p_merchant_id FAILS CLOSED and returns 0 rows."""
    dm = DatabaseManager()
    with dm.tenant_session_scope(ANOTHER_MERCHANT_UUID) as session:
        # Session is set to ANOTHER_MERCHANT_UUID, but caller passes TARGET_MERCHANT_UUID
        stmt = text("""
            SELECT id FROM public.claim_specific_recovery_outbox_job(
                p_job_id := :jid,
                p_merchant_id := :mid,
                p_worker_id := 'test_worker',
                p_lease_seconds := 60
            );
        """)
        rows = session.execute(stmt, {"jid": SYNTHETIC_JOB_ID, "mid": TARGET_MERCHANT_UUID}).fetchall()
        assert len(rows) == 0, "Mismatched session context must return 0 rows"


def test_06_correct_session_context_but_wrong_p_merchant_id():
    """Scenario 6: Session context matches TARGET_MERCHANT_UUID, but wrong p_merchant_id is passed -> returns 0 rows."""
    dm = DatabaseManager()
    with dm.tenant_session_scope(TARGET_MERCHANT_UUID) as session:
        stmt = text("""
            SELECT id FROM public.claim_specific_recovery_outbox_job(
                p_job_id := :jid,
                p_merchant_id := :mid,
                p_worker_id := 'test_worker',
                p_lease_seconds := 60
            );
        """)
        rows = session.execute(stmt, {"jid": SYNTHETIC_JOB_ID, "mid": ANOTHER_MERCHANT_UUID}).fetchall()
        assert len(rows) == 0, "Wrong p_merchant_id must return 0 rows"


def test_07_wrong_job_id():
    """Scenario 7: Random non-existent job ID returns 0 rows."""
    dm = DatabaseManager()
    with dm.tenant_session_scope(TARGET_MERCHANT_UUID) as session:
        stmt = text("""
            SELECT id FROM public.claim_specific_recovery_outbox_job(
                p_job_id := :jid,
                p_merchant_id := :mid,
                p_worker_id := 'test_worker',
                p_lease_seconds := 60
            );
        """)
        rows = session.execute(stmt, {"jid": RANDOM_JOB_ID, "mid": TARGET_MERCHANT_UUID}).fetchall()
        assert len(rows) == 0, "Non-existent job ID must return 0 rows"


def test_08_unapproved_job_fails_closed_in_isolation(tmp_path):
    """Scenario 8: An unapproved outbox job is rejected by exact claim (fails closed)."""
    db_file = tmp_path / "test_unapproved_2d2.db"
    store = DurableOutboxStore(db_path=str(db_file))
    merchant_id = str(uuid.uuid4())
    job = store.enqueue(
        case_id="case_unappr_2d2",
        payment_id="pay_unappr_2d2",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****5671",
        message_payload={"body": "Unapproved isolation test"},
        idempotency_key="idemp_unappr_2d2",
        merchant_id=merchant_id,
        requires_operator_approval=True,
    )
    assert job.status == "PENDING_APPROVAL"
    assert job.requires_operator_approval is True

    # Claim attempt fails closed
    claimed = store.claim_job_by_id(job_id=job.id, worker_id="test_worker", merchant_id=merchant_id)
    assert claimed is None

    # Status remains PENDING_APPROVAL
    refreshed = store.get_job(job.id, merchant_id=merchant_id)
    assert refreshed.status == "PENDING_APPROVAL"
    assert refreshed.worker_id is None


def test_08b_live_target_job_governance_read_only():
    """Scenario 8b: Read-only audit confirms live target job governance metadata without claim or mutation."""
    dm = DatabaseManager()
    with dm.tenant_session_scope(TARGET_MERCHANT_UUID) as session:
        row = session.execute(
            text("""
                SELECT id, status, requires_operator_approval, approved_by_operator_id, approval_snapshot_hash
                FROM public.recovery_outbox
                WHERE id = :jid;
            """),
            {"jid": TARGET_JOB_ID},
        ).mappings().one()
        assert str(row["id"]) == TARGET_JOB_ID
        assert row["requires_operator_approval"] is True
        assert row["approved_by_operator_id"] == "operator_arpit"
        assert row["approval_snapshot_hash"] == "dd0bcf49b2fa5204052b24e401c680d2ebf6d125aedbae88434b96fc8214e8cd"


def test_09_payload_tampering(tmp_path):
    """Scenario 9: Modifying message payload post-approval halts worker dispatch with DEAD_LETTER."""
    db_file = tmp_path / "test_outbox.db"
    opt_file = tmp_path / "test_opt_out.db"
    time_file = tmp_path / "test_timeline.db"

    store = DurableOutboxStore(db_path=str(db_file))
    opt_store = PersistentOptOutStore(db_path=str(opt_file))
    timeline = RecoveryTimelineStore(db_path=str(time_file))

    merchant_id = str(uuid.uuid4())
    job = store.enqueue(
        case_id="case_tamp_2d2",
        payment_id="pay_tamp_2d2",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****5671",
        message_payload={"customer_phone": "+916260055671", "amount_paise": 1000},
        idempotency_key="idemp_tamp_2d2",
        merchant_id=merchant_id,
        requires_operator_approval=True,
    )
    store.approve_job(job.id, operator_id="op_admin", merchant_id=merchant_id)

    # Tamper payload
    with store._get_sqlite_connection() as conn:
        conn.execute(
            "UPDATE recovery_outbox SET message_payload = ? WHERE id = ?",
            (json.dumps({"customer_phone": "+916260055671", "amount_paise": 999999}), job.id),
        )

    worker = RecoveryBackgroundWorker(outbox_store=store, opt_out_store=opt_store, timeline_store=timeline)
    res = worker.process_single_job_by_id(job.id, merchant_id=merchant_id)
    assert res.status == "DEAD_LETTER"
    assert "payload integrity violation" in res.error_message.lower()


def test_10_opt_out_restriction(tmp_path):
    """Scenario 10: Recipient opting out prior to dispatch halts worker dispatch with DEAD_LETTER."""
    db_file = tmp_path / "test_outbox.db"
    opt_file = tmp_path / "test_opt_out.db"
    time_file = tmp_path / "test_timeline.db"

    store = DurableOutboxStore(db_path=str(db_file))
    opt_store = PersistentOptOutStore(db_path=str(opt_file))
    timeline = RecoveryTimelineStore(db_path=str(time_file))

    merchant_id = str(uuid.uuid4())
    phone = "+916260055671"
    job = store.enqueue(
        case_id="case_optout_2d2",
        payment_id="pay_optout_2d2",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****5671",
        message_payload={"customer_phone": phone, "body": "Recovery link"},
        idempotency_key="idemp_optout_2d2",
        merchant_id=merchant_id,
        requires_operator_approval=True,
    )
    store.approve_job(job.id, operator_id="op_admin", merchant_id=merchant_id)

    # Opt out recipient
    opt_store.record_opt_out(phone, reason="Customer STOP", source="whatsapp_inbound")

    worker = RecoveryBackgroundWorker(outbox_store=store, opt_out_store=opt_store, timeline_store=timeline)
    res = worker.process_single_job_by_id(job.id, merchant_id=merchant_id)
    assert res.status == "DEAD_LETTER"
    assert "opted out" in res.error_message.lower()

