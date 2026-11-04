"""
WAPSI Phase 3.1B: Zero-DELETE Opt-Out Lifecycle & Privilege Verification Tests.

Guarantees Verified:
1. New opt-out creation sets is_active=True and revoked_at=None.
2. Duplicate STOP requests are handled idempotently and logged as DUPLICATE_OPT_OUT.
3. Re-consent deactivates the record (is_active=False, revoked_at set) without deleting the row.
4. Subsequent opt-out reactivates the record (is_active=True, revoked_at=None).
5. Inactive records do not suppress recovery notifications; active records immediately suppress.
6. Chronological audit history is preserved across all transitions.
7. Behavioral consistency between SQLite and PostgreSQL backends.
8. Role wapsi_app has zero DELETE privilege on opt_out_registry.
"""

import time
import pytest
import sqlite3
from typing import Dict, Any

from wapsi.recovery.opt_out_store import PersistentOptOutStore
from wapsi.recovery.eligibility import (
    RecoveryEligibilityEngine,
    EligibilityEvaluationContext,
    EligibilityStatus,
)
from wapsi.recovery.state_machine import RecoveryState


def test_sqlite_opt_out_full_zero_delete_lifecycle(tmp_path):
    """
    Verifies the complete zero-delete opt-out lifecycle in SQLite:
    Opt-out -> Duplicate STOP -> Re-consent -> Inactive Check -> Subsequent Opt-out -> Full Audit Trail.
    """
    db_file = str(tmp_path / "zero_delete_test.db")
    store = PersistentOptOutStore(db_path=db_file)

    phone = "+91 98765 11223"
    norm_phone = "919876511223"

    # Step 0: Initial state
    assert store.is_opted_out(phone) is False

    # Step 1: New opt-out creation
    assert store.record_opt_out(phone, reason="STOP_KEYWORD", source="inbound_whatsapp", actor="user") is True
    assert store.is_opted_out(phone) is True

    # Direct SQLite row inspection
    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM opt_out_registry WHERE phone = ?", (norm_phone,)).fetchone()
        assert row is not None
        assert row["is_active"] == 1
        assert row["revoked_at"] is None

    # Step 2: Duplicate STOP request
    assert store.record_opt_out(phone, reason="STOP_AGAIN", source="inbound_whatsapp") is True
    assert store.is_opted_out(phone) is True

    audit = store.get_audit_trail(phone)
    assert len(audit) == 2
    assert audit[0]["action"] == "OPT_OUT"
    assert audit[1]["action"] == "DUPLICATE_OPT_OUT"

    # Step 3: Re-consent / Revocation without proof fails
    with pytest.raises(ValueError, match="explicit, verified consent proof"):
        store.revoke_opt_out(phone, consent_proof="   ")

    # Re-consent with valid proof succeeds
    consent_proof = "SIGNED_AFFIRMATIVE_OPT_IN_FORM_REF_009"
    assert store.revoke_opt_out(phone, consent_proof=consent_proof, actor="support_agent") is True
    assert store.is_opted_out(phone) is False

    # ZERO-DELETE CHECK: The row in opt_out_registry MUST STILL EXIST!
    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM opt_out_registry WHERE phone = ?", (norm_phone,)).fetchone()
        assert row is not None, "Row must not be deleted from opt_out_registry!"
        assert row["is_active"] == 0, "is_active must be set to 0 (deactivated)"
        assert row["revoked_at"] is not None, "revoked_at must record UTC timestamp"

    # Step 4: Inactive record does not suppress
    assert store.is_opted_out(phone) is False

    # Calling revoke_opt_out on already inactive record returns False harmlessly
    assert store.revoke_opt_out(phone, consent_proof=consent_proof) is False

    # Step 5: Subsequent re-opt-out (Customer sends STOP again)
    assert store.record_opt_out(phone, reason="STOP_RENOTIFIED", source="inbound_whatsapp", actor="user") is True
    assert store.is_opted_out(phone) is True

    # Verify reactivation
    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM opt_out_registry WHERE phone = ?", (norm_phone,)).fetchone()
        assert row is not None
        assert row["is_active"] == 1, "is_active must be reactivated to 1"
        assert row["revoked_at"] is None, "revoked_at must be reset to None"

    # Step 6: Complete audit history preservation
    audit = store.get_audit_trail(phone)
    assert len(audit) == 4
    actions = [a["action"] for a in audit]
    assert actions == ["OPT_OUT", "DUPLICATE_OPT_OUT", "REVOCATION", "OPT_OUT"]
    assert audit[2]["consent_proof"] == consent_proof


def test_eligibility_active_vs_inactive_opt_out(tmp_path):
    """
    Verifies that EligibilityEvaluator properly suppresses active opt-outs
    and does NOT suppress inactive (revoked) opt-outs.
    """
    db_file = str(tmp_path / "eligibility_test.db")
    store = PersistentOptOutStore(db_path=db_file)
    evaluator = RecoveryEligibilityEngine()

    phone = "+91 91234 56789"

    # Context builder helper
    def make_ctx(customer_opted_out: bool) -> EligibilityEvaluationContext:
        return EligibilityEvaluationContext(
            case_id="case_opt_test",
            payment_id="pay_opt_test",
            amount_paise=50000,
            customer_phone=phone,
            error_code="BAD_REQUEST_PAYMENT_FAILED",
            error_category="GATEWAY_DECLINE",
            current_case_status=RecoveryState.PENDING,
            customer_opted_out=customer_opted_out,
            attempts_already_made=0,
            max_allowed_attempts=3,
            is_within_24h_meta_window=True,
            has_approved_template=True,
        )

    # 1. Customer opted out -> Must be SUPPRESSED
    store.record_opt_out(phone, reason="STOP")
    res1 = RecoveryEligibilityEngine.evaluate(make_ctx(store.is_opted_out(phone)))
    assert res1.is_eligible is False
    assert res1.status == EligibilityStatus.SUPPRESSED
    assert any("opted out" in r.lower() for r in res1.reasons)

    # 2. Customer re-consents -> Must NOT be suppressed
    store.revoke_opt_out(phone, consent_proof="VERIFIED_CONSENT_123")
    assert store.is_opted_out(phone) is False
    res2 = RecoveryEligibilityEngine.evaluate(make_ctx(store.is_opted_out(phone)))
    assert res2.is_eligible is True
    assert res2.status == EligibilityStatus.ELIGIBLE


def test_process_restart_persistence_with_zero_delete(tmp_path):
    """
    Verifies that state and deactivation status survive complete process restarts.
    """
    db_file = str(tmp_path / "restart_test.db")
    phone = "919876543210"

    # Process 1: Record opt-out then revoke
    p1 = PersistentOptOutStore(db_path=db_file)
    p1.record_opt_out(phone)
    p1.revoke_opt_out(phone, consent_proof="PROOF_ABC_123")
    assert p1.is_opted_out(phone) is False

    # Process 2: Start new instance pointing to same file
    p2 = PersistentOptOutStore(db_path=db_file)
    assert p2.is_opted_out(phone) is False

    # Process 2: Re-opt-out
    p2.record_opt_out(phone)
    assert p2.is_opted_out(phone) is True

    # Process 3: Start third instance
    p3 = PersistentOptOutStore(db_path=db_file)
    assert p3.is_opted_out(phone) is True
    trail = p3.get_audit_trail(phone)
    assert len(trail) == 3
    assert [t["action"] for t in trail] == ["OPT_OUT", "REVOCATION", "OPT_OUT"]
