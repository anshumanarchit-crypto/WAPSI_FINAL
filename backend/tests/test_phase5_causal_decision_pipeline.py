"""
Unit & Integration Test Suite for WAPSI Phase 5:
Causal Learning and Deterministic Decision Intelligence Pipeline.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from wapsi.causal.dml import MultiActionDoubleMachineLearning
from wapsi.bandit.feedback import BanditFeedbackEngine, ExplorationSafetyVerdict
from wapsi.decision.supervisor import (
    DeterministicDecisionSupervisor,
    TransactionDecisionContext,
    DEFAULT_HIGH_VALUE_THRESHOLD_INR,
)
from wapsi.api.app import app
from wapsi.db.service import PersistenceService
from wapsi.db.session import DatabaseManager


@pytest.fixture(autouse=True)
def isolate_persistence(monkeypatch):
    """Protects hosted database by using isolated in-memory persistence during tests."""
    test_db = DatabaseManager(database_url="sqlite:///:memory:")
    test_service = PersistenceService(db_manager=test_db)
    monkeypatch.setattr("wapsi.api.app.get_persistence_service", lambda: test_service)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def sample_training_data():
    """Generates synthetic tabular data for quick unit-level model validation."""
    np.random.seed(42)
    n = 300
    df = pd.DataFrame({
        "amount": np.random.uniform(500, 10000, n),
        "attempts_used": np.random.randint(1, 4, n),
        "account_age_days": np.random.randint(30, 700, n),
        "previous_failures": np.random.randint(0, 5, n),
        "previous_recoveries": np.random.randint(0, 3, n),
        "prior_recovery_rate": np.random.uniform(0.1, 0.9, n),
        "day_of_week": np.random.randint(0, 7, n),
        "hour": np.random.randint(0, 24, n),
        "fatigue_score": np.random.uniform(0.0, 1.0, n),
        "domain": np.random.choice(["ecommerce", "subscription", "b2b_saas"], n),
        "decline_reason": np.random.choice(["insufficient_funds", "bank_downtime", "upi_pin_timeout"], n),
        "issuer": np.random.choice(["HDFC", "ICICI", "SBI"], n),
        "bin_bucket": np.random.choice(["classic", "platinum"], n),
        "treatment": np.random.choice(["no_action", "whatsapp_nudge", "retry_only"], n),
        "recovered": np.random.choice([0, 1], n, p=[0.7, 0.3]),
    })
    return df


# ==============================================================================
# STAGE 3 TESTS: DOUBLE MACHINE LEARNING & CAUSAL ESTIMATION
# ==============================================================================

def test_dml_fit_predict_and_diagnostics(sample_training_data):
    """Verifies DML fitting with K-fold cross-fitting and overlap diagnostics."""
    dml = MultiActionDoubleMachineLearning(n_splits=3, random_seed=42)
    dml.fit(sample_training_data)

    assert dml.is_fitted is True
    assert "whatsapp_nudge" in dml.active_treatments_
    assert "retry_only" in dml.active_treatments_
    assert dml.control_action == "no_action"

    # Test overlap diagnostics
    diagnostics = dml.get_overlap_diagnostics()
    assert "whatsapp_nudge" in diagnostics
    assert "min_propensity" in diagnostics["whatsapp_nudge"]
    assert "max_propensity" in diagnostics["whatsapp_nudge"]
    assert diagnostics["whatsapp_nudge"]["min_propensity"] > 0.0
    assert diagnostics["whatsapp_nudge"]["max_propensity"] < 1.0

    # Test predictions
    sample = sample_training_data.head(5)
    uplifts, uncertainties = dml.predict_uplift(sample, return_uncertainty=True)
    outcomes = dml.predict_action_outcomes(sample)

    assert "whatsapp_nudge" in uplifts
    assert len(uplifts["whatsapp_nudge"]) == 5
    assert len(uncertainties["whatsapp_nudge"]) == 5
    assert "no_action" in outcomes
    assert "whatsapp_nudge" in outcomes

    # Probabilities must be within valid probability range [0, 1]
    for act, probs in outcomes.items():
        assert np.all(probs >= 0.0)
        assert np.all(probs <= 1.0)


def test_dml_potential_outcomes_leakage_guard():
    """Confirms that DML strictly rejects data with counterfactual leakage columns."""
    dml = MultiActionDoubleMachineLearning()
    leaky_df = pd.DataFrame({
        "treatment": ["no_action", "whatsapp_nudge"],
        "recovered": [0, 1],
        "y_no_action": [0, 0],  # Forbidden counterfactual column
    })
    with pytest.raises(ValueError, match="Potential outcome leakage detected"):
        dml.fit(leaky_df)


# ==============================================================================
# STAGE 4 TESTS: CONTEXTUAL BANDIT FEEDBACK ENGINE
# ==============================================================================

def test_bandit_safe_exploration_gates():
    """Verifies all hard safety constraints on exploratory assignments."""
    engine = BanditFeedbackEngine()

    # Opted-out user must be suppressed
    v_opt = engine.evaluate_safe_exploration(
        context={"error_code": "bank_downtime"},
        proposed_action="WHATSAPP_ONE_CLICK_LINK",
        is_opted_out=True,
    )
    assert not v_opt.is_safe
    assert v_opt.reason_code == "EXPLORATION_SUPPRESSED_OPT_OUT"

    # DND quiet hours must be deferred
    v_dnd = engine.evaluate_safe_exploration(
        context={"error_code": "bank_downtime"},
        proposed_action="WHATSAPP_ONE_CLICK_LINK",
        is_dnd_window=True,
    )
    assert not v_dnd.is_safe
    assert v_dnd.reason_code == "EXPLORATION_BLOCKED_DND"

    # Irreversible stolen card must be blocked
    v_stolen = engine.evaluate_safe_exploration(
        context={"error_code": "CARD_REPORTED_STOLEN"},
        proposed_action="WHATSAPP_ONE_CLICK_LINK",
    )
    assert not v_stolen.is_safe
    assert v_stolen.reason_code == "EXPLORATION_BLOCKED_IRREVERSIBLE_RISK"

    # Merchant disallowed action must be blocked
    v_disallow = engine.evaluate_safe_exploration(
        context={"error_code": "bank_downtime"},
        proposed_action="CALL_ASSIST_IVR",
        merchant_disallowed_actions=["CALL_ASSIST_IVR"],
    )
    assert not v_disallow.is_safe
    assert v_disallow.reason_code == "EXPLORATION_BLOCKED_MERCHANT_POLICY"

    # Safe case passes
    v_safe = engine.evaluate_safe_exploration(
        context={"error_code": "bank_downtime"},
        proposed_action="WHATSAPP_ONE_CLICK_LINK",
    )
    assert v_safe.is_safe
    assert v_safe.reason_code == "EXPLORATION_PERMITTED"


def test_bandit_reward_and_window_expiry():
    """Verifies deterministic reward computation and observation window expiration."""
    engine = BanditFeedbackEngine()

    # Recovered outcome yields positive economic reward
    r_rec = engine.compute_deterministic_reward("RECOVERED", 3000.0, "WHATSAPP_ONE_CLICK_LINK")
    assert r_rec > 0.0

    # Failed outcome yields negative cost penalty
    r_fail = engine.compute_deterministic_reward("FAILED", 3000.0, "WHATSAPP_ONE_CLICK_LINK")
    assert r_fail < 0.0

    now = datetime.now(timezone.utc)
    # Inside 24h window -> reward applied
    res_valid = engine.process_verified_outcome(
        payment_id="pay_001",
        outcome_status="RECOVERED",
        recovered_amount_inr=2000.0,
        action_taken="WHATSAPP_ONE_CLICK_LINK",
        context={},
        dispatched_at=now - timedelta(hours=4),
        resolved_at=now,
    )
    assert res_valid["reward_applied"] is True

    # Beyond 72h max window -> reward rejected
    res_expired = engine.process_verified_outcome(
        payment_id="pay_002",
        outcome_status="RECOVERED",
        recovered_amount_inr=2000.0,
        action_taken="WHATSAPP_ONE_CLICK_LINK",
        context={},
        dispatched_at=now - timedelta(days=4),
        resolved_at=now,
    )
    assert res_expired["reward_applied"] is False
    assert res_expired["reason"] == "OBSERVATION_WINDOW_EXPIRED"


# ==============================================================================
# STAGE 5 TESTS: DETERMINISTIC DECISION SUPERVISOR
# ==============================================================================

def test_supervisor_recoverable_flow():
    """Verifies sequential 6-engine evaluation and benchmark advisory deployment gate."""
    supervisor = DeterministicDecisionSupervisor()
    ctx = TransactionDecisionContext(
        payment_id="pay_rec_001",
        amount_in_inr=1500.0,
        error_code="technical_gateway_error",
        customer_phone="+919876543210",
    )
    snapshot = supervisor.evaluate_decision(ctx)

    assert snapshot.payment_id == "pay_rec_001"
    assert snapshot.amount_in_inr == 1500.0
    # In ADVISORY_HUMAN_REVIEW mode, benchmark models cannot autonomously dispatch customer contact
    assert snapshot.model_readiness_status == "BENCHMARK_VALIDATED_AWAITING_PRODUCTION_LOGS"
    assert snapshot.deployment_mode == "ADVISORY_HUMAN_REVIEW"
    assert snapshot.requires_human_approval is True
    assert snapshot.execution_status == "PENDING_APPROVAL"
    assert snapshot.authorized_action == "NO_ACTION"
    assert "Model deployment boundary" in snapshot.human_approval_reason
    assert len(snapshot.snapshot_hash) == 64
    assert "risk_score" in snapshot.risk_assessment
    assert "conformal_uplift_interval" in snapshot.causal_metrics

    # When explicitly pre-approved by merchant operator, authorization passes cleanly
    ctx_approved = TransactionDecisionContext(
        payment_id="pay_rec_001_app",
        amount_in_inr=1500.0,
        error_code="technical_gateway_error",
        customer_phone="+919876543210",
        is_pre_approved_by_operator=True,
    )
    snapshot_approved = supervisor.evaluate_decision(ctx_approved)
    assert snapshot_approved.execution_status in ("AUTHORIZED", "SCHEDULED_DND")
    assert snapshot_approved.requires_human_approval is False
    assert snapshot_approved.authorized_action == snapshot_approved.recommended_action


def test_supervisor_high_value_human_approval_gate():
    """Verifies that high-value transactions (>= 50,000 INR) trigger mandatory human approval."""
    supervisor = DeterministicDecisionSupervisor(high_value_threshold_inr=50000.0)
    ctx = TransactionDecisionContext(
        payment_id="pay_high_val_999",
        amount_in_inr=85000.0,
        error_code="insufficient_funds",
        customer_phone="+919876543210",
    )
    snapshot = supervisor.evaluate_decision(ctx)

    assert snapshot.requires_human_approval is True
    assert snapshot.execution_status == "PENDING_APPROVAL"
    assert snapshot.authorized_action == "NO_ACTION"  # Held until human approved
    assert "exceeds high-value threshold" in snapshot.human_approval_reason


def test_supervisor_irreversible_risk_rejection():
    """Verifies that non-recoverable error codes are rejected deterministically."""
    supervisor = DeterministicDecisionSupervisor()
    ctx = TransactionDecisionContext(
        payment_id="pay_fraud_001",
        amount_in_inr=2000.0,
        error_code="CARD_REPORTED_STOLEN",
        customer_phone="+919876543210",
    )
    snapshot = supervisor.evaluate_decision(ctx)

    assert snapshot.execution_status == "REJECTED"
    assert snapshot.authorized_action == "NO_ACTION"
    assert snapshot.risk_assessment["is_fraud_or_irreversible"] is True


# ==============================================================================
# STAGE 6 TESTS: CANONICAL API ENDPOINT & FRONTEND CONTRACT
# ==============================================================================

def test_api_causal_decision_endpoint(client):
    """Verifies POST /api/v1/causal/decision contract adherence and metric separation."""
    payload = {
        "payment_id": "pay_api_test_501",
        "merchant_id": "merch_acme",
        "amount_in_inr": 4500.0,
        "error_code": "bank_downtime",
        "customer_phone": "+919876543210",
        "model_choice": "dml",
    }
    response = client.post("/api/v1/causal/decision", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["payment_id"] == "pay_api_test_501"
    assert data["merchant_id"] == "merch_acme"
    assert "decision_id" in data
    assert "model_version" in data
    assert data["model_readiness_status"] == "BENCHMARK_VALIDATED_AWAITING_PRODUCTION_LOGS"
    assert data["deployment_mode"] == "ADVISORY_HUMAN_REVIEW"
    assert "risk_score" in data
    assert "recommended_action" in data
    assert "authorized_action" in data
    assert "execution_status" in data
    assert "requires_human_approval" in data
    assert "estimated_treatment_uplift" in data
    assert "expected_recovered_value_inr" in data
    assert "net_expected_economic_value_inr" in data
    assert "uncertainty_information" in data
    assert "policy_decisions" in data
    assert "action_rankings" in data
    assert "plain_english_rationale" in data
    assert "snapshot_hash" in data
    assert "audit_hash" in data

    # Strict Metric Distinction Check:
    # Uplift tau (fraction) != Expected Recovered Value (INR) != Net Expected Utility (INR)
    tau = data["estimated_treatment_uplift"]
    recovered_val = data["expected_recovered_value_inr"]
    net_val = data["net_expected_economic_value_inr"]

    assert isinstance(tau, float)
    assert isinstance(recovered_val, float)
    assert isinstance(net_val, float)
    # Recovered value is scaled by amount (4500 * tau)
    assert abs(recovered_val - round(4500.0 * tau, 2)) < 0.10


def test_api_causal_decision_high_value_routing(client):
    """Verifies that transactions >= 50,000 INR route to PENDING_APPROVAL over HTTP."""
    payload = {
        "payment_id": "pay_api_high_val_502",
        "amount_in_inr": 72000.0,
        "error_code": "insufficient_funds",
        "customer_phone": "+919876543210",
        "model_choice": "dml",
    }
    response = client.post("/api/v1/causal/decision", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["requires_human_approval"] is True
    assert data["execution_status"] == "PENDING_APPROVAL"
    assert data["human_approval_reason"] is not None
    assert "exceeds high-value threshold" in data["human_approval_reason"]


def test_api_causal_decision_invalid_api_key_rejected(client):
    """Verifies that an unauthorized API key is rejected with HTTP 401."""
    payload = {
        "payment_id": "pay_api_auth_test",
        "amount_in_inr": 1000.0,
        "error_code": "bank_downtime",
    }
    response = client.post(
        "/api/v1/causal/decision",
        json=payload,
        headers={"X-API-Key": "invalid_unregistered_key_999"},
    )
    assert response.status_code == 401

