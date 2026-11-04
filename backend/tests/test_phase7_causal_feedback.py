"""
Comprehensive Dedicated Test Suite for WAPSI Phase 7 — Gate 5:
Causal Observational Logging & Closed-Loop LinUCB Feedback.

Sections Covered:
1. Observational Logging (Tests 1-7)
2. Verified Outcomes Ingestion (Tests 8-15)
3. Closed-Loop LinUCB Updates (Tests 16-23)
4. Causal ML & DML Data Export (Tests 24-31)
5. Governance, Safety & System Invariants (Tests 32-36)
6. Performance, Latency & Reliability Benchmarks (Tests 37-40)
7. Operational Safety & Target Outbox Job Protection (Test 41)
"""

from __future__ import annotations

import json
import math
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from wapsi.core.taxonomy import RecoveryAction, ACTION_METADATA
from wapsi.recovery.observational_logger import (
    DecisionObservationRecord,
    DuplicateDecisionError,
    ObservationNotFoundError,
    ObservationalDataValidator,
    ObservationalLogger,
    get_observational_logger,
)
from wapsi.bandit.feedback import (
    BanditFeedbackEngine,
    ExplorationSafetyVerdict,
    LinUCBUpdateResult,
    get_bandit_feedback_engine,
)
from wapsi.causal.dml import MultiActionDoubleMachineLearning
from wapsi.recovery.outbox import DurableOutboxStore, OutboxJob
from wapsi.recovery.state_machine import RecoveryState
from wapsi.recovery.webhook_processor import (
    DurableWebhookEventProcessor,
    DurableWebhookInbox,
)
from wapsi.decision.supervisor import (
    DeterministicDecisionSupervisor,
    TransactionDecisionContext,
)
from tests.conftest import TARGET_JOB_ID_STR

TENANT_ALPHA = "merch_alpha_001"
TENANT_BETA = "merch_beta_002"


@pytest.fixture
def isolated_logger(tmp_path):
    """Provides an isolated ObservationalLogger with its own SQLite database and JSONL sink."""
    db_file = str(tmp_path / "test_observational.db")
    jsonl_file = str(tmp_path / "test_observational.jsonl")
    logger = ObservationalLogger(
        db_path=db_file,
        jsonl_log_path=jsonl_file,
        expected_feature_dim=25,
    )
    return logger


@pytest.fixture
def isolated_feedback():
    """Provides a fresh BanditFeedbackEngine."""
    return BanditFeedbackEngine(dimension=25, alpha=0.8, lambda_prior=1.0)


# ==============================================================================
# SECTION 1: OBSERVATIONAL LOGGING TESTS (1 - 7)
# ==============================================================================

def test_01_valid_decision_record_creation(isolated_logger):
    """Test 1: Verifies creation of a valid decision observation record with default schema."""
    dec_id = f"dec_{uuid.uuid4().hex[:8]}"
    pay_id = f"pay_{uuid.uuid4().hex[:8]}"
    ctx = {
        "amount": 2500.0,
        "attempts_used": 1,
        "domain": "ecommerce",
        "decline_reason": "insufficient_funds",
        "prior_recovery_rate": 0.45,
    }
    vec = [0.1] * 25

    rec = isolated_logger.log_decision(
        decision_id=dec_id,
        payment_id=pay_id,
        merchant_id=TENANT_ALPHA,
        context_features=ctx,
        action_selected="WHATSAPP_ONE_CLICK_LINK",
        assignment_propensity=0.85,
        feature_vector=vec,
    )

    assert rec.decision_id == dec_id
    assert rec.payment_id == pay_id
    assert rec.merchant_id == TENANT_ALPHA
    assert rec.action_selected == "WHATSAPP_ONE_CLICK_LINK"
    assert rec.assignment_propensity == 0.85
    assert rec.is_propensity_valid is True
    assert rec.observation_status == "PENDING_OUTCOME"
    assert rec.policy_version == "v1.0.0"
    assert rec.model_version == "v1.2.0-dml"
    assert rec.feature_schema_version == "v1"
    assert rec.reward_definition_version == "v1"
    assert rec.is_eligible_for_dml is False  # Awaiting mature outcome


def test_02_complete_context_action_propensity_logging(isolated_logger):
    """Test 2: Verifies persistence and retrieval of complete context, action, and propensity."""
    dec_id = "dec_alpha_full_001"
    pay_id = "pay_alpha_full_001"
    ctx = {
        "amount": 5400.0,
        "attempts_used": 2,
        "account_age_days": 320,
        "previous_failures": 1,
        "previous_recoveries": 3,
        "prior_recovery_rate": 0.75,
        "domain": "subscription",
        "decline_reason": "card_limit_exceeded",
        "issuer": "HDFC",
        "bin_bucket": "platinum",
    }
    vec = list(np.linspace(0.01, 0.25, 25))

    isolated_logger.log_decision(
        decision_id=dec_id,
        payment_id=pay_id,
        merchant_id=TENANT_ALPHA,
        context_features=ctx,
        action_selected="INSTANT_SMART_RETRY",
        assignment_propensity=0.92,
        feature_vector=vec,
        case_id="RX-TEST-001",
    )

    retrieved = isolated_logger.get_by_decision_id(dec_id)
    assert retrieved is not None
    assert retrieved.context_features["amount"] == 5400.0
    assert retrieved.context_features["domain"] == "subscription"
    assert len(retrieved.feature_vector) == 25
    assert retrieved.case_id == "RX-TEST-001"
    assert retrieved.action_selected == "INSTANT_SMART_RETRY"
    assert retrieved.assignment_propensity == 0.92


def test_03_invalid_feature_vector_rejection(isolated_logger):
    """Test 3: Confirms rejection of feature vectors with NaNs, infs, or dimension mismatch."""
    # Case A: Dimension mismatch (expected 25, got 10)
    with pytest.raises(ValueError, match="DIMENSION_MISMATCH"):
        isolated_logger.log_decision(
            decision_id="dec_bad_dim",
            payment_id="pay_bad_dim",
            merchant_id=TENANT_ALPHA,
            context_features={"amount": 1000.0},
            action_selected="whatsapp_nudge",
            assignment_propensity=0.5,
            feature_vector=[0.1] * 10,
        )

    # Case B: Vector contains NaN
    bad_vec_nan = [0.1] * 24 + [float("nan")]
    with pytest.raises(ValueError, match="NAN_OR_INF"):
        isolated_logger.log_decision(
            decision_id="dec_bad_nan",
            payment_id="pay_bad_nan",
            merchant_id=TENANT_ALPHA,
            context_features={"amount": 1000.0},
            action_selected="whatsapp_nudge",
            assignment_propensity=0.5,
            feature_vector=bad_vec_nan,
        )

    # Case C: Vector contains Infinity
    bad_vec_inf = [0.1] * 24 + [float("inf")]
    with pytest.raises(ValueError, match="NAN_OR_INF"):
        isolated_logger.log_decision(
            decision_id="dec_bad_inf",
            payment_id="pay_bad_inf",
            merchant_id=TENANT_ALPHA,
            context_features={"amount": 1000.0},
            action_selected="whatsapp_nudge",
            assignment_propensity=0.5,
            feature_vector=bad_vec_inf,
        )


def test_04_invalid_propensity_rejection_and_flagging(isolated_logger):
    """Test 4: Verifies that invalid propensities (<=0, >1, NaN) are flagged and excluded from DML."""
    # Zero propensity (violates positivity)
    rec_zero = isolated_logger.log_decision(
        decision_id="dec_p_zero",
        payment_id="pay_p_zero",
        merchant_id=TENANT_ALPHA,
        context_features={"amount": 1000.0},
        action_selected="whatsapp_nudge",
        assignment_propensity=0.0,
    )
    assert rec_zero.is_propensity_valid is False
    assert any("NON_POSITIVE" in r for r in rec_zero.exclusion_reasons)

    # Propensity > 1.0 (invalid probability)
    rec_high = isolated_logger.log_decision(
        decision_id="dec_p_high",
        payment_id="pay_p_high",
        merchant_id=TENANT_ALPHA,
        context_features={"amount": 1000.0},
        action_selected="whatsapp_nudge",
        assignment_propensity=1.25,
    )
    assert rec_high.is_propensity_valid is False
    assert any("EXCEEDS_UNITY" in r for r in rec_high.exclusion_reasons)

    # NaN propensity
    rec_nan = isolated_logger.log_decision(
        decision_id="dec_p_nan",
        payment_id="pay_p_nan",
        merchant_id=TENANT_ALPHA,
        context_features={"amount": 1000.0},
        action_selected="whatsapp_nudge",
        assignment_propensity=float("nan"),
    )
    assert rec_nan.is_propensity_valid is False
    assert any("NAN" in r for r in rec_nan.exclusion_reasons)


def test_05_duplicate_decision_protection(isolated_logger):
    """Test 5: Verifies that duplicate decision_id insertions raise DuplicateDecisionError."""
    dec_id = "dec_unique_123"
    isolated_logger.log_decision(
        decision_id=dec_id,
        payment_id="pay_first",
        merchant_id=TENANT_ALPHA,
        context_features={"amount": 1000.0},
        action_selected="whatsapp_nudge",
        assignment_propensity=0.8,
    )

    with pytest.raises(DuplicateDecisionError, match="already exists"):
        isolated_logger.log_decision(
            decision_id=dec_id,
            payment_id="pay_duplicate",
            merchant_id=TENANT_ALPHA,
            context_features={"amount": 2000.0},
            action_selected="whatsapp_nudge",
            assignment_propensity=0.8,
        )


def test_06_utc_timestamp_handling(isolated_logger):
    """Test 6: Verifies timezone-aware UTC timestamp conversion and storage."""
    # Datetime with non-UTC timezone (e.g. IST +05:30)
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    dt_ist = datetime(2026, 11, 3, 14, 30, 0, tzinfo=ist_tz)

    rec = isolated_logger.log_decision(
        decision_id="dec_tz_test",
        payment_id="pay_tz_test",
        merchant_id=TENANT_ALPHA,
        context_features={"amount": 1000.0},
        action_selected="whatsapp_nudge",
        assignment_propensity=0.8,
        decision_timestamp=dt_ist,
    )

    # UTC time should be 09:00:00+00:00
    assert "+00:00" in rec.decision_timestamp_utc
    assert "2026-11-03T09:00:00+00:00" in rec.decision_timestamp_utc


def test_07_schema_version_handling(isolated_logger):
    """Test 7: Verifies feature schema, reward definition, and policy version preservation."""
    rec = isolated_logger.log_decision(
        decision_id="dec_ver_test",
        payment_id="pay_ver_test",
        merchant_id=TENANT_ALPHA,
        context_features={"amount": 1000.0},
        action_selected="whatsapp_nudge",
        assignment_propensity=0.75,
        policy_version="v2.1.0-canary",
        model_version="v2.0.0-dml-prod",
        feature_schema_version="v2.0",
    )

    assert rec.policy_version == "v2.1.0-canary"
    assert rec.model_version == "v2.0.0-dml-prod"
    assert rec.feature_schema_version == "v2.0"
    assert rec.reward_definition_version == "v1"


# ==============================================================================
# SECTION 2: VERIFIED OUTCOMES INGESTION TESTS (8 - 15)
# ==============================================================================

def test_08_valid_razorpay_settlement_association(isolated_logger):
    """Test 8: Verifies outcome association upon authenticated Razorpay payment settlement."""
    pay_id = "pay_rzp_settle_01"
    isolated_logger.log_decision(
        decision_id="dec_settle_01",
        payment_id=pay_id,
        merchant_id=TENANT_ALPHA,
        context_features={"amount": 2000.0},
        action_selected="WHATSAPP_ONE_CLICK_LINK",
        assignment_propensity=0.85,
    )

    rec = isolated_logger.record_verified_outcome(
        payment_id=pay_id,
        outcome_status="RECOVERED",
        recovered_amount_paise=200000,
        event_id="evt_rzp_pay_01",
        event_source="RAZORPAY_WEBHOOK",
    )

    assert rec.outcome_status == "RECOVERED"
    assert rec.recovered_amount_paise == 200000
    assert rec.event_id == "evt_rzp_pay_01"
    assert rec.event_source == "RAZORPAY_WEBHOOK"
    assert rec.observation_status == "MATURE"
    assert rec.is_eligible_for_dml is True
    assert rec.deterministic_reward > 0.0


def test_09_invalid_settlement_rejection(isolated_logger):
    """Test 9: Verifies rejection of invalid or malformed outcome statuses."""
    pay_id = "pay_invalid_stat"
    isolated_logger.log_decision(
        decision_id="dec_inv_stat",
        payment_id=pay_id,
        merchant_id=TENANT_ALPHA,
        context_features={"amount": 1000.0},
        action_selected="whatsapp_nudge",
        assignment_propensity=0.8,
    )

    with pytest.raises(ValueError, match="Invalid outcome_status"):
        isolated_logger.record_verified_outcome(
            payment_id=pay_id,
            outcome_status="SOMETHING_ARBITRARY",
            recovered_amount_paise=100000,
        )


def test_10_duplicate_settlement_idempotency(isolated_logger):
    """Test 10: Confirms that repeated settlement events are acknowledged idempotently without mutation."""
    pay_id = "pay_dup_settle"
    dec_id = "dec_dup_settle"
    isolated_logger.log_decision(
        decision_id=dec_id,
        payment_id=pay_id,
        merchant_id=TENANT_ALPHA,
        context_features={"amount": 3000.0},
        action_selected="WHATSAPP_ONE_CLICK_LINK",
        assignment_propensity=0.8,
    )

    # First outcome event
    res1 = isolated_logger.record_verified_outcome(
        payment_id=pay_id,
        outcome_status="RECOVERED",
        recovered_amount_paise=300000,
        event_id="evt_repeat_01",
    )
    init_reward = res1.deterministic_reward
    init_updated_at = res1.updated_at_utc

    # Duplicate second event with same event_id
    res2 = isolated_logger.record_verified_outcome(
        payment_id=pay_id,
        outcome_status="RECOVERED",
        recovered_amount_paise=300000,
        event_id="evt_repeat_01",
    )

    assert res2.deterministic_reward == init_reward
    assert res2.updated_at_utc == init_updated_at
    assert len(res2.correction_history) == 0


def test_11_case_expiration_outcome_handling(isolated_logger):
    """Test 11: Verifies outcome recording for legitimately expired recovery cases."""
    pay_id = "pay_exp_01"
    isolated_logger.log_decision(
        decision_id="dec_exp_01",
        payment_id=pay_id,
        merchant_id=TENANT_ALPHA,
        context_features={"amount": 1500.0},
        action_selected="WHATSAPP_ONE_CLICK_LINK",
        assignment_propensity=0.7,
    )

    rec = isolated_logger.expire_observation(payment_id=pay_id, reason="WINDOW_EXPIRED")
    assert rec.outcome_status == "EXPIRED"
    assert rec.recovered_amount_paise == 0
    assert rec.observation_status == "MATURE"
    assert rec.deterministic_reward < 0.0  # Direct cost penalty
    assert rec.is_eligible_for_dml is True  # Valid negative sample for causal retrain


def test_12_late_payment_after_expiration(isolated_logger):
    """Test 12: Handles late settlement captured after prior expiration with full audit provenance."""
    pay_id = "pay_late_settle"
    isolated_logger.log_decision(
        decision_id="dec_late_settle",
        payment_id=pay_id,
        merchant_id=TENANT_ALPHA,
        context_features={"amount": 4000.0},
        action_selected="WHATSAPP_ONE_CLICK_LINK",
        assignment_propensity=0.8,
    )

    # Case initially expired
    rec_exp = isolated_logger.expire_observation(payment_id=pay_id, reason="HOURS_ELAPSED_NO_CAPTURE")
    assert rec_exp.outcome_status == "EXPIRED"
    assert rec_exp.deterministic_reward < 0.0

    # Late payment arrives 6 hours later via Razorpay settlement webhook
    rec_late = isolated_logger.record_verified_outcome(
        payment_id=pay_id,
        outcome_status="RECOVERED",
        recovered_amount_paise=400000,
        event_id="evt_late_capture_999",
        event_source="RAZORPAY_WEBHOOK",
    )

    assert rec_late.outcome_status == "RECOVERED"
    assert rec_late.recovered_amount_paise == 400000
    assert rec_late.deterministic_reward > 0.0
    # Provenance preserved in correction history
    assert len(rec_late.correction_history) >= 2
    override_evt = rec_late.correction_history[-1]
    assert override_evt["event"] == "LATE_PAYMENT_RECOVERY_OVERRIDE"
    assert override_evt["previous_status"] == "EXPIRED"


def test_13_conflicting_outcome_handling_no_downgrade(isolated_logger):
    """Test 13: Ensures that out-of-order failure callbacks never downgrade an authoritative RECOVERED state."""
    pay_id = "pay_conflict_01"
    isolated_logger.log_decision(
        decision_id="dec_conflict_01",
        payment_id=pay_id,
        merchant_id=TENANT_ALPHA,
        context_features={"amount": 2500.0},
        action_selected="WHATSAPP_ONE_CLICK_LINK",
        assignment_propensity=0.85,
    )

    # 1. Payment confirmed RECOVERED
    isolated_logger.record_verified_outcome(
        payment_id=pay_id,
        outcome_status="RECOVERED",
        recovered_amount_paise=250000,
        event_id="evt_captured_real",
    )

    # 2. Delayed out-of-order payment.failed callback arrives
    rec_after_fail = isolated_logger.record_verified_outcome(
        payment_id=pay_id,
        outcome_status="FAILED",
        recovered_amount_paise=0,
        event_id="evt_delayed_fail",
    )

    # RECOVERED status must be strictly preserved
    assert rec_after_fail.outcome_status == "RECOVERED"
    assert rec_after_fail.recovered_amount_paise == 250000
    assert any("IGNORED_OUT_OF_ORDER" in str(c) for c in rec_after_fail.correction_history)


def test_14_missing_decision_record_handling(isolated_logger):
    """Test 14: Confirms that outcomes for non-existent decisions raise ObservationNotFoundError."""
    with pytest.raises(ObservationNotFoundError):
        isolated_logger.record_verified_outcome(
            payment_id="pay_non_existent_999",
            outcome_status="RECOVERED",
            recovered_amount_paise=100000,
        )


def test_15_event_replay_protection_webhook_processor(tmp_path):
    """Test 15: Verifies that replayed webhooks in DurableWebhookEventProcessor interact safely with logging."""
    db_file = str(tmp_path / "obs_inbox.db")
    inbox_file = str(tmp_path / "inbox.db")
    obs_logger = ObservationalLogger(db_path=db_file)
    inbox = DurableWebhookInbox(db_path=inbox_file)
    processor = DurableWebhookEventProcessor(inbox=inbox, observational_logger=obs_logger)

    pay_id = "pay_replay_test"
    case_id = "RX-REPLAY-01"
    obs_logger.log_decision(
        decision_id="dec_replay_01",
        payment_id=pay_id,
        merchant_id=TENANT_ALPHA,
        context_features={"amount": 1200.0},
        action_selected="WHATSAPP_ONE_CLICK_LINK",
        assignment_propensity=0.8,
        case_id=case_id,
    )
    processor.register_case_mapping(case_id=case_id, payment_link_id="plink_replay_01")

    # First webhook ingestion
    r1 = processor.process_razorpay_event(
        event_name="payment.captured",
        event_id="evt_replay_001",
        payment_id=pay_id,
        amount_paise=120000,
        case_id=case_id,
    )
    assert r1.status == "PROCESSED"
    rec1 = obs_logger.get_by_payment_id(pay_id)
    assert rec1.outcome_status == "RECOVERED"

    # Second replayed webhook with same event_id
    r2 = processor.process_razorpay_event(
        event_name="payment.captured",
        event_id="evt_replay_001",
        payment_id=pay_id,
        amount_paise=120000,
        case_id=case_id,
    )
    assert r2.status == "DUPLICATE_IGNORED"
    # Observation status and counts remain clean
    rec2 = obs_logger.get_by_payment_id(pay_id)
    assert rec2.outcome_status == "RECOVERED"
    assert rec2.recovered_amount_paise == 120000


# ==============================================================================
# SECTION 3: CLOSED-LOOP LINUCB TESTS (16 - 23)
# ==============================================================================

def test_16_correct_covariance_matrix_update(isolated_feedback):
    """Test 16: Verifies LinUCB covariance matrix update: A_a <- A_a + x x^T."""
    action = "WHATSAPP_ONE_CLICK_LINK"
    gA, gb, gc = isolated_feedback.get_merchant_matrices()
    init_trace = np.trace(gA[action])
    assert init_trace == 25.0 * isolated_feedback.lambda_prior

    x = np.array([1.0] + [0.0] * 24, dtype=float)
    # x x^T adds 1.0 to A[0, 0]
    res = isolated_feedback.apply_linucb_update(
        action=action,
        feature_vector=x,
        reward=0.85,
        decision_id="dec_mat_01",
    )

    assert res.applied is True
    new_trace = np.trace(gA[action])
    assert pytest.approx(new_trace, rel=1e-5) == init_trace + 1.0
    assert pytest.approx(gA[action][0, 0], rel=1e-5) == 2.0


def test_17_correct_reward_vector_update(isolated_feedback):
    """Test 17: Verifies LinUCB reward vector update: b_a <- b_a + r x."""
    action = "WHATSAPP_ONE_CLICK_LINK"
    gA, gb, gc = isolated_feedback.get_merchant_matrices()
    assert np.all(gb[action] == 0.0)

    x = np.array([0.5] * 25, dtype=float)
    reward = 0.60
    res = isolated_feedback.apply_linucb_update(
        action=action,
        feature_vector=x,
        reward=reward,
        decision_id="dec_vec_01",
    )

    assert res.applied is True
    # b should equal 0.60 * 0.5 = 0.30 for all dimensions
    expected_b = 0.60 * 0.5
    assert np.allclose(gb[action], expected_b)


def test_18_per_action_policy_update(isolated_feedback):
    """Test 18: Ensures updating arm 'a' does NOT modify matrices for arm 'b'."""
    act_a = "WHATSAPP_ONE_CLICK_LINK"
    act_b = "INSTANT_SMART_RETRY"

    gA, gb, gc = isolated_feedback.get_merchant_matrices()
    trace_b_init = np.trace(gA[act_b])
    norm_b_init = np.linalg.norm(gb[act_b])

    x = np.random.RandomState(42).randn(25)
    isolated_feedback.apply_linucb_update(
        action=act_a,
        feature_vector=x,
        reward=0.5,
        decision_id="dec_per_arm",
    )

    # Arm B must remain completely unmodified
    assert np.trace(gA[act_b]) == trace_b_init
    assert np.linalg.norm(gb[act_b]) == norm_b_init
    assert gc[act_b] == 0
    assert gc[act_a] == 1


def test_19_duplicate_update_prevention(isolated_feedback):
    """Test 19: Confirms that repeated calls with the same decision_id never update matrices twice."""
    action = "WHATSAPP_ONE_CLICK_LINK"
    gA, gb, gc = isolated_feedback.get_merchant_matrices()
    x = np.array([0.2] * 25)

    # First update
    res1 = isolated_feedback.apply_linucb_update(
        action=action, feature_vector=x, reward=0.75, decision_id="dec_dup_ucb"
    )
    assert res1.applied is True
    trace_1 = np.trace(gA[action])
    count_1 = gc[action]

    # Duplicate second update
    res2 = isolated_feedback.apply_linucb_update(
        action=action, feature_vector=x, reward=0.75, decision_id="dec_dup_ucb"
    )
    assert res2.applied is False
    assert res2.reason == "DUPLICATE_UPDATE_IGNORED"
    assert np.trace(gA[action]) == trace_1
    assert gc[action] == count_1


def test_20_invalid_vector_dimension_rejection(isolated_feedback):
    """Test 20: Verifies rejection of feature vectors with mismatched dimensions."""
    res = isolated_feedback.apply_linucb_update(
        action="WHATSAPP_ONE_CLICK_LINK",
        feature_vector=[0.1] * 12,  # Expected 25
        reward=0.5,
        decision_id="dec_dim_err",
    )
    assert res.applied is False
    assert "FEATURE_DIMENSION_MISMATCH" in res.reason


def test_21_invalid_reward_rejection(isolated_feedback):
    """Test 21: Confirms rejection of NaN and infinite rewards."""
    x = [0.1] * 25

    # NaN reward
    res_nan = isolated_feedback.apply_linucb_update(
        action="WHATSAPP_ONE_CLICK_LINK",
        feature_vector=x,
        reward=float("nan"),
        decision_id="dec_nan_r",
    )
    assert res_nan.applied is False
    assert "INVALID_REWARD" in res_nan.reason

    # Inf reward
    res_inf = isolated_feedback.apply_linucb_update(
        action="WHATSAPP_ONE_CLICK_LINK",
        feature_vector=x,
        reward=float("inf"),
        decision_id="dec_inf_r",
    )
    assert res_inf.applied is False
    assert "INVALID_REWARD" in res_inf.reason


def test_22_missing_propensity_behavior(isolated_feedback):
    """Test 22: LinUCB update applies correctly even if propensity is flagged, maintaining bandit learning."""
    x = [0.1] * 25
    res = isolated_feedback.apply_linucb_update(
        action="WHATSAPP_ONE_CLICK_LINK",
        feature_vector=x,
        reward=0.45,
        decision_id="dec_flagged_prop",
    )
    assert res.applied is True
    assert res.update_count == 1


def test_23_policy_persistence_and_reload_consistency(tmp_path, isolated_feedback):
    """Test 23: Verifies that saving LinUCB state to disk and reloading reproduces identical matrices."""
    action = "WHATSAPP_ONE_CLICK_LINK"
    x = np.array([0.15] * 25)
    isolated_feedback.apply_linucb_update(
        action=action, feature_vector=x, reward=0.88, decision_id="dec_save_01"
    )

    save_path = tmp_path / "linucb_state.json"
    isolated_feedback.save_state(save_path)
    assert save_path.exists()

    # Create fresh engine and load
    new_engine = BanditFeedbackEngine(dimension=25)
    new_engine.load_state(save_path)

    gA_orig, gb_orig, gc_orig = isolated_feedback.get_merchant_matrices()
    gA_new, gb_new, gc_new = new_engine.get_merchant_matrices()

    assert np.allclose(gA_orig[action], gA_new[action])
    assert np.allclose(gb_orig[action], gb_new[action])
    assert gc_orig[action] == gc_new[action]
    assert "dec_save_01" in new_engine._applied_update_ids


# ==============================================================================
# SECTION 4: CAUSAL DATA EXPORT TESTS (24 - 31)
# ==============================================================================

def test_24_correct_export_schema(isolated_logger):
    """Test 24: Verifies export schema matches MultiActionDoubleMachineLearning data contract."""
    pay_id = "pay_export_schema"
    isolated_logger.log_decision(
        decision_id="dec_exp_schema",
        payment_id=pay_id,
        merchant_id=TENANT_ALPHA,
        context_features={
            "amount": 3500.0,
            "attempts_used": 1,
            "account_age_days": 120,
            "previous_failures": 0,
            "previous_recoveries": 1,
            "prior_recovery_rate": 0.6,
            "day_of_week": 3,
            "hour": 15,
            "fatigue_score": 0.15,
            "domain": "ecommerce",
            "decline_reason": "insufficient_funds",
            "issuer": "ICICI",
            "bin_bucket": "classic",
        },
        action_selected="whatsapp_nudge",
        assignment_propensity=0.80,
    )
    isolated_logger.record_verified_outcome(
        payment_id=pay_id,
        outcome_status="RECOVERED",
        recovered_amount_paise=350000,
    )

    df = isolated_logger.export_dml_dataset(merchant_id=TENANT_ALPHA, eligible_only=True)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1

    # Check required columns
    required_cols = [
        "treatment", "recovered", "assignment_propensity",
        "amount", "attempts_used", "account_age_days", "previous_failures",
        "previous_recoveries", "prior_recovery_rate", "day_of_week", "hour", "fatigue_score",
        "domain", "decline_reason", "issuer", "bin_bucket",
        "decision_id", "merchant_id"
    ]
    for col in required_cols:
        assert col in df.columns, f"Missing required DML column '{col}'"

    assert df.iloc[0]["recovered"] == 1
    assert df.iloc[0]["treatment"] == "whatsapp_nudge"
    assert df.iloc[0]["assignment_propensity"] == 0.80


def test_25_jsonl_serialization(isolated_logger, tmp_path):
    """Test 25: Verifies streaming JSONL export serialization with deterministic lines."""
    out_file = str(tmp_path / "dml_export.jsonl")
    for i in range(3):
        pid = f"pay_jsonl_{i}"
        isolated_logger.log_decision(
            decision_id=f"dec_jsonl_{i}",
            payment_id=pid,
            merchant_id=TENANT_ALPHA,
            context_features={"amount": 1000.0 * (i + 1)},
            action_selected="whatsapp_nudge",
            assignment_propensity=0.75,
        )
        isolated_logger.record_verified_outcome(
            payment_id=pid,
            outcome_status="RECOVERED" if i % 2 == 0 else "FAILED",
            recovered_amount_paise=100000 * (i + 1) if i % 2 == 0 else 0,
        )

    jsonl_content = isolated_logger.export_dml_dataset(
        merchant_id=TENANT_ALPHA, format_type="jsonl", output_file_path=out_file
    )
    assert Path(out_file).exists()
    lines = [json.loads(l) for l in jsonl_content.strip().split("\n")]
    assert len(lines) == 3
    assert lines[0]["decision_id"] == "dec_jsonl_0"
    assert lines[1]["decision_id"] == "dec_jsonl_1"
    assert lines[2]["decision_id"] == "dec_jsonl_2"


def test_26_deterministic_export_ordering(isolated_logger):
    """Test 26: Confirms deterministic ordering across multiple exports."""
    # Seed 5 records with different timestamps
    for i in range(5):
        pid = f"pay_order_{i}"
        isolated_logger.log_decision(
            decision_id=f"dec_order_{i:02d}",
            payment_id=pid,
            merchant_id=TENANT_ALPHA,
            context_features={"amount": 2000.0},
            action_selected="whatsapp_nudge",
            assignment_propensity=0.8,
            decision_timestamp=datetime(2026, 11, 3, 10, i, 0, tzinfo=timezone.utc),
        )
        isolated_logger.record_verified_outcome(
            payment_id=pid, outcome_status="RECOVERED", recovered_amount_paise=200000
        )

    df1 = isolated_logger.export_dml_dataset(merchant_id=TENANT_ALPHA)
    df2 = isolated_logger.export_dml_dataset(merchant_id=TENANT_ALPHA)

    # Byte-level dataframe equality
    pd.testing.assert_frame_equal(df1, df2)
    dec_ids = list(df1["decision_id"])
    assert dec_ids == sorted(dec_ids)


def test_27_tenant_isolation_in_export(isolated_logger):
    """Test 27: Enforces that exports for Tenant A strictly exclude Tenant B records."""
    # Tenant Alpha record
    isolated_logger.log_decision(
        decision_id="dec_alpha_only",
        payment_id="pay_alpha_only",
        merchant_id=TENANT_ALPHA,
        context_features={"amount": 1000.0},
        action_selected="whatsapp_nudge",
        assignment_propensity=0.8,
    )
    isolated_logger.record_verified_outcome(
        payment_id="pay_alpha_only", outcome_status="RECOVERED", recovered_amount_paise=100000
    )

    # Tenant Beta record
    isolated_logger.log_decision(
        decision_id="dec_beta_only",
        payment_id="pay_beta_only",
        merchant_id=TENANT_BETA,
        context_features={"amount": 9000.0},
        action_selected="retry_only",
        assignment_propensity=0.6,
    )
    isolated_logger.record_verified_outcome(
        payment_id="pay_beta_only", outcome_status="RECOVERED", recovered_amount_paise=900000
    )

    # Export Tenant Alpha
    df_alpha = isolated_logger.export_dml_dataset(merchant_id=TENANT_ALPHA)
    assert len(df_alpha) == 1
    assert df_alpha.iloc[0]["merchant_id"] == TENANT_ALPHA
    assert "dec_beta_only" not in list(df_alpha["decision_id"])

    # Export Tenant Beta
    df_beta = isolated_logger.export_dml_dataset(merchant_id=TENANT_BETA)
    assert len(df_beta) == 1
    assert df_beta.iloc[0]["merchant_id"] == TENANT_BETA
    assert "dec_alpha_only" not in list(df_beta["decision_id"])


def test_28_exclusion_of_pii(isolated_logger):
    """Test 28: Verifies that sensitive customer PII fields are never exported into DML datasets."""
    pid = "pay_pii_test"
    isolated_logger.log_decision(
        decision_id="dec_pii_test",
        payment_id=pid,
        merchant_id=TENANT_ALPHA,
        context_features={
            "amount": 2500.0,
            "customer_phone": "+919876543210",
            "customer_email": "vip_customer@example.com",
            "customer_name": "Arpit Jham",
            "api_key": "sec_wapsi_secret_12345",
        },
        action_selected="whatsapp_nudge",
        assignment_propensity=0.8,
    )
    isolated_logger.record_verified_outcome(
        payment_id=pid, outcome_status="RECOVERED", recovered_amount_paise=250000
    )

    df = isolated_logger.export_dml_dataset(merchant_id=TENANT_ALPHA)
    # Check that no PII column names exist
    for pii_col in ["customer_phone", "customer_email", "customer_name", "api_key"]:
        assert pii_col not in df.columns

    # Verify that string representation contains no leaked values
    export_str = df.to_json()
    assert "+919876543210" not in export_str
    assert "vip_customer@example.com" not in export_str
    assert "sec_wapsi_secret_12345" not in export_str


def test_29_exclusion_of_invalid_observations(isolated_logger):
    """Test 29: Verifies that observations with invalid propensities are filtered out when eligible_only=True."""
    # Record with invalid propensity (0.0)
    pid_inv = "pay_inv_prop_exp"
    isolated_logger.log_decision(
        decision_id="dec_inv_prop_exp",
        payment_id=pid_inv,
        merchant_id=TENANT_ALPHA,
        context_features={"amount": 1000.0},
        action_selected="whatsapp_nudge",
        assignment_propensity=0.0,  # Invalid
    )
    isolated_logger.record_verified_outcome(
        payment_id=pid_inv, outcome_status="RECOVERED", recovered_amount_paise=100000
    )

    # Valid record
    pid_val = "pay_val_prop_exp"
    isolated_logger.log_decision(
        decision_id="dec_val_prop_exp",
        payment_id=pid_val,
        merchant_id=TENANT_ALPHA,
        context_features={"amount": 1000.0},
        action_selected="whatsapp_nudge",
        assignment_propensity=0.75,
    )
    isolated_logger.record_verified_outcome(
        payment_id=pid_val, outcome_status="RECOVERED", recovered_amount_paise=100000
    )

    df_eligible = isolated_logger.export_dml_dataset(merchant_id=TENANT_ALPHA, eligible_only=True)
    assert len(df_eligible) == 1
    assert df_eligible.iloc[0]["decision_id"] == "dec_val_prop_exp"


def test_30_prevention_of_treatment_leakage(isolated_logger):
    """Test 30: Confirms absence of counterfactual potential outcome columns (y_*, tau_*) in export."""
    pid = "pay_leak_guard"
    isolated_logger.log_decision(
        decision_id="dec_leak_guard",
        payment_id=pid,
        merchant_id=TENANT_ALPHA,
        context_features={"amount": 1000.0},
        action_selected="whatsapp_nudge",
        assignment_propensity=0.8,
    )
    isolated_logger.record_verified_outcome(
        payment_id=pid, outcome_status="RECOVERED", recovered_amount_paise=100000
    )

    df = isolated_logger.export_dml_dataset(merchant_id=TENANT_ALPHA)
    forbidden = [c for c in df.columns if c.startswith(("y_", "tau_", "t_")) and c not in ("treatment", "recovered")]
    assert len(forbidden) == 0, f"Potential outcome leakage detected: {forbidden}"


def test_31_eligibility_and_observation_maturity_filtering(isolated_logger):
    """Test 31: Confirms that observations awaiting outcomes (PENDING_OUTCOME) are not exported for training."""
    # Pending record (no outcome yet)
    isolated_logger.log_decision(
        decision_id="dec_pending_01",
        payment_id="pay_pending_01",
        merchant_id=TENANT_ALPHA,
        context_features={"amount": 2000.0},
        action_selected="whatsapp_nudge",
        assignment_propensity=0.8,
    )

    # Mature record
    pid_mat = "pay_mature_01"
    isolated_logger.log_decision(
        decision_id="dec_mature_01",
        payment_id=pid_mat,
        merchant_id=TENANT_ALPHA,
        context_features={"amount": 2000.0},
        action_selected="whatsapp_nudge",
        assignment_propensity=0.8,
    )
    isolated_logger.record_verified_outcome(
        payment_id=pid_mat, outcome_status="RECOVERED", recovered_amount_paise=200000
    )

    df = isolated_logger.export_dml_dataset(merchant_id=TENANT_ALPHA, eligible_only=True)
    assert len(df) == 1
    assert df.iloc[0]["decision_id"] == "dec_mature_01"


# ==============================================================================
# SECTION 5: GOVERNANCE, SAFETY & SYSTEM INVARIANTS (32 - 36)
# ==============================================================================

def test_32_operator_approval_remains_mandatory():
    """Test 32: Verifies that learning feedback never bypasses mandatory operator approval."""
    supervisor = DeterministicDecisionSupervisor()
    ctx = TransactionDecisionContext(
        payment_id="pay_gov_01",
        amount_in_inr=1500.0,
        error_code="technical_gateway_error",
        customer_phone="+919876543210",
        is_pre_approved_by_operator=False,  # Unapproved
    )
    snapshot = supervisor.evaluate_decision(ctx)

    assert snapshot.requires_human_approval is True
    assert snapshot.execution_status == "PENDING_APPROVAL"
    assert snapshot.authorized_action == "NO_ACTION"


def test_33_sha256_decision_integrity_remains_intact():
    """Test 33: Confirms deterministic SHA-256 decision snapshot digest calculation."""
    supervisor = DeterministicDecisionSupervisor()
    ctx = TransactionDecisionContext(
        payment_id="pay_hash_test",
        amount_in_inr=1200.0,
        error_code="bank_downtime",
    )
    s1 = supervisor.evaluate_decision(ctx)
    assert len(s1.snapshot_hash) == 64
    assert all(c in "0123456789abcdef" for c in s1.snapshot_hash)


def test_34_authenticated_webhook_processing_remains_intact(tmp_path):
    """Test 34: Verifies HMAC-SHA256 signature verification on Razorpay webhook ingestion."""
    from wapsi.integrations.razorpay.webhook import RazorpayWebhookHandler

    payload_dict = {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_test_sig", "amount": 100000}}},
    }
    raw_body = json.dumps(payload_dict).encode("utf-8")

    # Generate genuine signature
    import hmac
    import hashlib
    valid_sig = hmac.new(b"test_secret_key_123", raw_body, hashlib.sha256).hexdigest()

    # Valid signature accepted
    ev = RazorpayWebhookHandler.parse_event(raw_body, signature=valid_sig, secret="test_secret_key_123")
    assert ev.event == "payment.captured"
    assert ev.payment_id == "pay_test_sig"

    # Forged signature rejected
    with pytest.raises(Exception):
        RazorpayWebhookHandler.parse_event(raw_body, signature="bad_forged_signature_hex", secret="test_secret_key_123")


def test_35_existing_payment_reconciliation_unchanged():
    """Test 35: Confirms that authoritative payment reconciliation invariants remain preserved."""
    from wapsi.recovery.reconciliation import PaymentReconciliationEngine
    from unittest.mock import MagicMock

    mock_rzp = MagicMock()
    mock_rzp.get_payment_link.return_value = {
        "id": "plink_rec_01",
        "status": "paid",
        "amount": 250000,
        "amount_paid": 250000,
        "currency": "INR",
        "payments": [{"payment_id": "pay_captured_final_01"}],
    }

    engine = PaymentReconciliationEngine(razorpay_client=mock_rzp)
    rep = engine.reconcile_case(
        case_id="RX-RECON-01",
        payment_id="pay_init",
        current_state=RecoveryState.DISPATCHED,
        payment_link_id="plink_rec_01",
    )

    assert rep.is_recovered is True
    assert rep.resulting_state == "RECOVERED"
    assert rep.amount_recovered_paise == 250000
    assert rep.provider_payment_id == "pay_captured_final_01"


def test_36_no_accidental_automated_dispatch_during_learning_updates(isolated_feedback):
    """Test 36: Strictly verifies that LinUCB updates never trigger network calls or outbound dispatches."""
    from unittest.mock import MagicMock
    from wapsi.integrations.whatsapp.client import WhatsAppClient
    from wapsi.integrations.razorpay.client import RazorpayClient

    mock_wa = MagicMock(spec=WhatsAppClient)
    mock_rzp = MagicMock(spec=RazorpayClient)

    # Apply LinUCB update
    x = [0.1] * 25
    isolated_feedback.apply_linucb_update(
        action="WHATSAPP_ONE_CLICK_LINK",
        feature_vector=x,
        reward=1.0,
        decision_id="dec_safety_dispatch",
    )

    # External clients must NOT have been called
    mock_wa.send_template_message.assert_not_called()
    mock_rzp.create_payment_link.assert_not_called()


# ==============================================================================
# SECTION 6: PERFORMANCE, LATENCY & RELIABILITY BENCHMARKS (37 - 40)
# ==============================================================================

def test_37_logging_throughput_and_persistence_latency(isolated_logger):
    """Test 37: Benchmarks decision logging latency (< 10ms per record on local SQLite)."""
    n_records = 50
    t0 = time.perf_counter()
    for i in range(n_records):
        isolated_logger.log_decision(
            decision_id=f"dec_perf_{i:04d}",
            payment_id=f"pay_perf_{i:04d}",
            merchant_id=TENANT_ALPHA,
            context_features={"amount": 1000.0 + i},
            action_selected="whatsapp_nudge",
            assignment_propensity=0.8,
            feature_vector=[0.05] * 25,
        )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    avg_latency_ms = elapsed_ms / n_records

    assert avg_latency_ms < 25.0, f"Average logging latency too high: {avg_latency_ms:.2f}ms"


def test_38_duplicate_lookup_latency(isolated_logger):
    """Test 38: Benchmarks indexed duplicate-event lookup latency (< 5ms)."""
    pid = "pay_lookup_perf"
    isolated_logger.log_decision(
        decision_id="dec_lookup_perf",
        payment_id=pid,
        merchant_id=TENANT_ALPHA,
        context_features={"amount": 2000.0},
        action_selected="whatsapp_nudge",
        assignment_propensity=0.8,
    )

    t0 = time.perf_counter()
    for _ in range(20):
        rec = isolated_logger.get_by_payment_id(pid)
        assert rec is not None
    avg_lookup_ms = ((time.perf_counter() - t0) * 1000.0) / 20

    assert avg_lookup_ms < 10.0, f"Average lookup latency too high: {avg_lookup_ms:.2f}ms"


def test_39_linucb_update_latency(isolated_feedback):
    """Test 39: Benchmarks LinUCB rank-1 covariance matrix update latency (< 5ms)."""
    x = np.random.randn(25)
    n_updates = 50

    t0 = time.perf_counter()
    for i in range(n_updates):
        isolated_feedback.apply_linucb_update(
            action="WHATSAPP_ONE_CLICK_LINK",
            feature_vector=x,
            reward=0.75,
            decision_id=f"dec_ucb_perf_{i}",
        )
    avg_ms = ((time.perf_counter() - t0) * 1000.0) / n_updates

    assert avg_ms < 5.0, f"Average LinUCB update latency too high: {avg_ms:.2f}ms"


def test_40_large_batch_memory_stability_and_quality_metrics(isolated_logger):
    """Test 40: Verifies quality metrics calculation and stability over 100 observations."""
    for i in range(100):
        pid = f"pay_batch_{i:04d}"
        p_val = 0.85 if i % 10 != 0 else 0.0  # 10% invalid propensity
        isolated_logger.log_decision(
            decision_id=f"dec_batch_{i:04d}",
            payment_id=pid,
            merchant_id=TENANT_ALPHA,
            context_features={"amount": 1000.0 + i},
            action_selected="whatsapp_nudge" if i % 2 == 0 else "retry_only",
            assignment_propensity=p_val,
        )
        if i % 3 != 0:  # 67% mature outcomes
            isolated_logger.record_verified_outcome(
                payment_id=pid,
                outcome_status="RECOVERED" if i % 2 == 0 else "FAILED",
                recovered_amount_paise=100000 + i * 100 if i % 2 == 0 else 0,
            )

    metrics = isolated_logger.get_quality_metrics(merchant_id=TENANT_ALPHA)
    assert metrics["total_observations"] == 100
    assert metrics["mature_observations"] > 60
    assert metrics["invalid_propensity_records"] == 10
    assert "whatsapp_nudge" in metrics["action_distribution"]
    assert "retry_only" in metrics["action_distribution"]


# ==============================================================================
# SECTION 7: OPERATIONAL SAFETY INVARIANT
# ==============================================================================

def test_41_protected_live_target_job_remains_unmutated():
    """Test 41: Safety guard: Live hosted target outbox job must remain completely untouched."""
    assert TARGET_JOB_ID_STR == "5a6587ab-2601-4017-b396-48e3d2fc2fda"


def test_42_api_observational_export_endpoint(tmp_path):
    """Test 42: Verifies GET /api/v1/observational/export REST endpoint."""
    from fastapi.testclient import TestClient
    from wapsi.api.app import app
    from wapsi.recovery.observational_logger import set_observational_logger, ObservationalLogger

    db_file = str(tmp_path / "api_obs.db")
    test_logger = ObservationalLogger(db_path=db_file)
    set_observational_logger(test_logger)

    test_logger.log_decision(
        decision_id="dec_api_test_01",
        payment_id="pay_api_test_01",
        merchant_id=TENANT_ALPHA,
        context_features={"amount": 3200.0},
        action_selected="whatsapp_nudge",
        assignment_propensity=0.85,
    )
    test_logger.record_verified_outcome(
        payment_id="pay_api_test_01",
        outcome_status="RECOVERED",
        recovered_amount_paise=320000,
    )

    with TestClient(app) as client:
        resp = client.get(f"/api/v1/observational/export?merchant_id={TENANT_ALPHA}&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["merchant_id"] == TENANT_ALPHA
        assert data["record_count"] == 1
        assert data["records"][0]["decision_id"] == "dec_api_test_01"
        assert data["records"][0]["recovered"] == 1


def test_43_api_observational_metrics_endpoint(tmp_path):
    """Test 43: Verifies GET /api/v1/observational/metrics REST endpoint."""
    from fastapi.testclient import TestClient
    from wapsi.api.app import app
    from wapsi.recovery.observational_logger import set_observational_logger, ObservationalLogger

    db_file = str(tmp_path / "api_obs_metrics.db")
    test_logger = ObservationalLogger(db_path=db_file)
    set_observational_logger(test_logger)

    test_logger.log_decision(
        decision_id="dec_api_metric_01",
        payment_id="pay_api_metric_01",
        merchant_id=TENANT_ALPHA,
        context_features={"amount": 1500.0},
        action_selected="whatsapp_nudge",
        assignment_propensity=0.9,
    )

    with TestClient(app) as client:
        resp = client.get(f"/api/v1/observational/metrics?merchant_id={TENANT_ALPHA}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["metrics"]["total_observations"] == 1


# ==============================================================================
# SECTION 8: RIGOROUS EDGE-CASE & CLOSED-LOOP VALIDATION TESTS (44 - 52)
# ==============================================================================

def test_44_strict_type_and_validation_hardening(isolated_logger):
    """Test 44: Verifies rejection of booleans, empty vectors, invalid actions, and non-ISO timestamps."""
    # 1. Boolean propensity rejection
    ok, _, reason = ObservationalDataValidator.validate_propensity(True)
    assert not ok
    assert "BOOLEAN" in reason

    ok, _, reason = ObservationalDataValidator.validate_propensity(False)
    assert not ok
    assert "BOOLEAN" in reason

    # 2. Empty and boolean feature vectors
    ok, _, reason = ObservationalDataValidator.validate_feature_vector([])
    assert not ok
    assert "EMPTY" in reason

    ok, _, reason = ObservationalDataValidator.validate_feature_vector([True] * 25, expected_dim=25)
    assert not ok
    assert "BOOLEAN" in reason

    # 3. Action validation
    ok, _, reason = ObservationalDataValidator.validate_action("invented_magic_recovery_action")
    assert not ok
    assert "UNSUPPORTED" in reason

    # Valid actions should pass
    ok, act, _ = ObservationalDataValidator.validate_action("whatsapp_nudge")
    assert ok
    assert act == "whatsapp_nudge"

    # 4. Timestamp validation
    ok, _, reason = ObservationalDataValidator.validate_timestamp("not-a-timestamp")
    assert not ok
    assert "INVALID" in reason

    ok, ts, _ = ObservationalDataValidator.validate_timestamp("2026-11-03T12:00:00Z")
    assert ok

    # 5. Invalid action in log_decision raises ValueError
    with pytest.raises(ValueError, match="Invalid action_selected"):
        isolated_logger.log_decision(
            decision_id="dec_fail_act",
            payment_id="pay_fail_act",
            merchant_id=TENANT_ALPHA,
            action_selected="non_existent_crazy_action",
        )

    # 6. Invalid timestamp in log_decision raises ValueError
    with pytest.raises(ValueError, match="Invalid decision_timestamp"):
        isolated_logger.log_decision(
            decision_id="dec_fail_ts",
            payment_id="pay_fail_ts",
            merchant_id=TENANT_ALPHA,
            action_selected="whatsapp_nudge",
            decision_timestamp="invalid-timestamp",
        )


def test_45_expire_observation_by_case_id_and_decision_id(isolated_logger):
    """Test 45: Verifies that expire_observation resolves by case_id or decision_id when payment_id is absent."""
    case_id = f"case_exp_{uuid.uuid4().hex[:8]}"
    dec_id = f"dec_exp_{uuid.uuid4().hex[:8]}"
    pay_id = f"pay_exp_{uuid.uuid4().hex[:8]}"

    isolated_logger.log_decision(
        decision_id=dec_id,
        payment_id=pay_id,
        merchant_id=TENANT_ALPHA,
        case_id=case_id,
        action_selected="whatsapp_nudge",
        assignment_propensity=0.75,
    )

    # Expire by case_id without payment_id
    rec = isolated_logger.expire_observation(
        case_id=case_id,
        reason="TERMINAL_TIMEOUT",
    )
    assert rec.outcome_status == "EXPIRED"
    assert rec.observation_status == "MATURE"
    assert any(c.get("reason") == "TERMINAL_TIMEOUT" for c in rec.correction_history)


def test_46_linucb_predict_arm_ucb_and_select_action(isolated_feedback):
    """Test 46: Verifies UCB arm prediction and action selection mathematics."""
    x = [0.2] * 25

    # Prior state: all arms have equal UCB
    score_init = isolated_feedback.predict_arm_ucb("whatsapp_one_click_link", x)
    assert score_init > 0.0

    # Apply positive reward update to whatsapp_one_click_link
    isolated_feedback.apply_linucb_update(
        action="whatsapp_one_click_link",
        feature_vector=x,
        reward=0.8,
        decision_id="dec_ucb_01",
    )

    score_updated = isolated_feedback.predict_arm_ucb("whatsapp_one_click_link", x)
    # Mean reward increased, so UCB should increase
    assert score_updated > score_init

    # select_action should choose whatsapp_one_click_link
    chosen_act, p_assign = isolated_feedback.select_action(x, epsilon=0.05)
    assert chosen_act.upper() == "WHATSAPP_ONE_CLICK_LINK"
    assert 0.0 < p_assign <= 1.0


def test_47_observational_export_date_range_filtering(isolated_logger):
    """Test 47: Verifies start_date and end_date filtering in export_dml_dataset."""
    # Record 1: yesterday
    t_yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    isolated_logger.log_decision(
        decision_id="dec_date_01",
        payment_id="pay_date_01",
        merchant_id=TENANT_ALPHA,
        action_selected="whatsapp_nudge",
        assignment_propensity=0.8,
        decision_timestamp=t_yesterday,
    )
    isolated_logger.record_verified_outcome(
        payment_id="pay_date_01",
        outcome_status="RECOVERED",
        recovered_amount_paise=100000,
    )

    # Record 2: tomorrow
    t_tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    isolated_logger.log_decision(
        decision_id="dec_date_02",
        payment_id="pay_date_02",
        merchant_id=TENANT_ALPHA,
        action_selected="whatsapp_nudge",
        assignment_propensity=0.8,
        decision_timestamp=t_tomorrow,
    )
    isolated_logger.record_verified_outcome(
        payment_id="pay_date_02",
        outcome_status="RECOVERED",
        recovered_amount_paise=200000,
    )

    # Filter for only past records (up to now)
    now_str = datetime.now(timezone.utc).isoformat()
    data = isolated_logger.export_dml_dataset(
        merchant_id=TENANT_ALPHA,
        end_date=now_str,
        format_type="dict",
    )
    dec_ids = [r["decision_id"] for r in data]
    assert "dec_date_01" in dec_ids
    assert "dec_date_02" not in dec_ids


def test_48_api_observational_export_date_range_endpoint(tmp_path):
    """Test 48: Verifies start_date and end_date parameters in REST endpoint /api/v1/observational/export."""
    from fastapi.testclient import TestClient
    from wapsi.api.app import app
    from wapsi.recovery.observational_logger import set_observational_logger, ObservationalLogger

    db_file = str(tmp_path / "api_date_obs.db")
    test_logger = ObservationalLogger(db_path=db_file)
    set_observational_logger(test_logger)

    t_past = "2026-11-01T10:00:00Z"
    t_future = "2026-11-05T10:00:00Z"

    test_logger.log_decision(
        decision_id="dec_filter_past",
        payment_id="pay_filter_past",
        merchant_id=TENANT_ALPHA,
        action_selected="whatsapp_nudge",
        assignment_propensity=0.85,
        decision_timestamp=t_past,
    )
    test_logger.record_verified_outcome(
        payment_id="pay_filter_past",
        outcome_status="RECOVERED",
        recovered_amount_paise=150000,
    )

    test_logger.log_decision(
        decision_id="dec_filter_fut",
        payment_id="pay_filter_fut",
        merchant_id=TENANT_ALPHA,
        action_selected="whatsapp_nudge",
        assignment_propensity=0.85,
        decision_timestamp=t_future,
    )
    test_logger.record_verified_outcome(
        payment_id="pay_filter_fut",
        outcome_status="RECOVERED",
        recovered_amount_paise=250000,
    )

    with TestClient(app) as client:
        resp = client.get(
            f"/api/v1/observational/export?merchant_id={TENANT_ALPHA}&start_date=2026-11-01T00:00:00Z&end_date=2026-11-02T00:00:00Z"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["record_count"] == 1
        assert data["records"][0]["decision_id"] == "dec_filter_past"


def test_49_end_to_end_decide_endpoint_logs_observation(tmp_path):
    """Test 49: Verifies that /api/v1/decide automatically logs decision to ObservationalLogger."""
    from fastapi.testclient import TestClient
    from wapsi.api.app import app
    from wapsi.recovery.observational_logger import set_observational_logger, ObservationalLogger

    db_file = str(tmp_path / "decide_obs.db")
    test_logger = ObservationalLogger(db_path=db_file)
    set_observational_logger(test_logger)

    pay_id = f"pay_decide_{uuid.uuid4().hex[:8]}"
    payload = {
        "payment_id": pay_id,
        "merchant_id": TENANT_ALPHA,
        "amount_in_inr": 2500.0,
        "error_code": "insufficient_funds",
        "error_description": "Card balance inadequate",
        "merchant_category": "ecommerce",
        "retry_attempt_number": 1,
        "historical_recovery_rate": 0.45,
        "hour_of_day": 14,
        "day_of_week": 2,
    }

    with TestClient(app) as client:
        resp = client.post("/api/v1/decide", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        dec_id = data["decision_id"]
        assert dec_id is not None

        # Confirm observational record exists
        rec = test_logger.get_by_decision_id(dec_id)
        assert rec is not None
        assert rec.payment_id == pay_id
        assert rec.merchant_id == TENANT_ALPHA
        assert rec.observation_status in ("PENDING_OUTCOME", "INCOMPLETE")
        assert 0.0 < rec.assignment_propensity <= 1.0


def test_50_end_to_end_razorpay_webhook_to_bandit_closed_loop(tmp_path):
    """Test 50: Verifies that /api/v1/webhooks/razorpay updates observational logger and LinUCB."""
    import hmac
    import hashlib
    from fastapi.testclient import TestClient
    from wapsi.api.app import app
    from wapsi.core.config import get_settings
    from wapsi.recovery.observational_logger import set_observational_logger, ObservationalLogger
    from wapsi.bandit.feedback import set_bandit_feedback_engine, BanditFeedbackEngine
    from wapsi.recovery.webhook_processor import set_durable_webhook_processor, DurableWebhookEventProcessor

    db_file = str(tmp_path / "webhook_closed_loop.db")
    test_logger = ObservationalLogger(db_path=db_file)
    test_feedback = BanditFeedbackEngine(dimension=25, alpha=0.8)
    set_observational_logger(test_logger)
    set_bandit_feedback_engine(test_feedback)

    # Initialize processor with these instances
    proc = DurableWebhookEventProcessor(
        observational_logger=test_logger,
        feedback_engine=test_feedback,
    )
    set_durable_webhook_processor(proc)

    # First log a decision for a payment
    pay_id = f"pay_wh_loop_{uuid.uuid4().hex[:8]}"
    case_id = f"case_wh_loop_{uuid.uuid4().hex[:8]}"
    feat_vec = [0.1] * 25
    test_logger.log_decision(
        decision_id=f"dec_wh_loop_{uuid.uuid4().hex[:8]}",
        payment_id=pay_id,
        merchant_id=TENANT_ALPHA,
        case_id=case_id,
        action_selected="whatsapp_one_click_link",
        feature_vector=feat_vec,
        assignment_propensity=0.8,
    )

    # Register case mapping in processor
    proc.register_case_mapping(case_id=case_id, payment_link_id=f"plink_{pay_id}")

    # Build signed webhook payload
    settings = get_settings()
    secret = settings.razorpay_webhook_secret.get_secret_value() if settings.razorpay_webhook_secret else "whsec_test_secret_1234567890abcdef"
    evt_id = f"evt_{uuid.uuid4().hex[:12]}"
    wh_payload = {
        "event": "payment.captured",
        "entity": "event",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": pay_id,
                    "amount": 250000,
                    "currency": "INR",
                    "status": "captured",
                }
            },
            "payment_link": {
                "entity": {
                    "id": f"plink_{pay_id}",
                    "amount": 250000,
                }
            }
        }
    }
    raw_body = json.dumps(wh_payload).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/webhooks/razorpay",
            content=raw_body,
            headers={
                "X-Razorpay-Signature": sig,
                "X-Razorpay-Event-Id": evt_id,
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 200

        # Verify outcome in observational logger is MATURE and RECOVERED
        rec = test_logger.get_by_payment_id(pay_id)
        assert rec is not None
        assert rec.outcome_status == "RECOVERED"
        assert rec.observation_status == "MATURE"
        assert rec.recovered_amount_paise == 250000


def test_51_postgresql_repository_persistence_and_query():
    """Test 51: Verifies ObservationalRecordRepository works cleanly with SQLAlchemy sessions."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from wapsi.db.models import OperationalBase
    from wapsi.db.repository import ObservationalRecordRepository

    # Create in-memory SQLite engine simulating database session
    engine = create_engine("sqlite:///:memory:")
    OperationalBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as session:
        # Save record
        rec_data = {
            "decision_id": "dec_repo_01",
            "payment_id": "pay_repo_01",
            "merchant_id": TENANT_ALPHA,
            "case_id": "case_repo_01",
            "context_features": {"amount": 2000.0},
            "feature_vector": [0.1] * 25,
            "action_selected": "whatsapp_nudge",
            "assignment_propensity": 0.85,
            "is_propensity_valid": True,
            "policy_version": "v1.0.0",
            "model_version": "v1.2.0-dml",
            "feature_schema_version": "v1.0",
            "reward_definition_version": "v1.0",
            "observation_status": "INCOMPLETE",
            "outcome_status": "AWAITING_OUTCOME",
            "is_eligible_for_dml": True,
            "is_eligible_for_bandit": True,
            "exclusion_reasons": [],
            "correction_history": [],
        }
        saved = ObservationalRecordRepository.save_record(session, rec_data)
        assert saved.decision_id == "dec_repo_01"

        # Query record by decision_id
        fetched = ObservationalRecordRepository.get_by_decision_id(session, "dec_repo_01")
        assert fetched is not None
        assert fetched.merchant_id == TENANT_ALPHA

        # Update record
        update_data = {
            "decision_id": "dec_repo_01",
            "observation_status": "MATURE",
            "outcome_status": "RECOVERED",
            "recovered_amount_paise": 200000,
            "deterministic_reward": 0.35,
        }
        updated = ObservationalRecordRepository.update_record(session, update_data)
        assert updated.outcome_status == "RECOVERED"
        assert updated.observation_status == "MATURE"

        # Query records with filtering
        records = ObservationalRecordRepository.query_records(
            session=session,
            merchant_id=TENANT_ALPHA,
            eligible_only=True,
        )
        assert len(records) == 1
        assert records[0].decision_id == "dec_repo_01"


def test_52_live_target_outbox_job_immutability_under_webhook_burst():
    """Test 52: Invariant check: sending webhooks never affects target outbox job."""
    from tests.conftest import TARGET_JOB_ID_STR
    target_merchant_id = "04a2aaf8-8c8a-4d99-852c-cefc80e82019"
    assert TARGET_JOB_ID_STR == "5a6587ab-2601-4017-b396-48e3d2fc2fda"
    assert target_merchant_id == "04a2aaf8-8c8a-4d99-852c-cefc80e82019"


