"""
Unit tests for WAPSI Conformal Calibration Decision Gate.
Razorpay AI Buildathon 2026 - Track 3

Tests:
  - Split-conformal calibration on held-out data (D_calib)
  - evaluate_case schema conformity ({eligible_for_auto_action, confidence, calibration_status, reason})
  - Statistical decision gating (high confidence auto-action vs human escalation)
  - Empirical coverage verification on held-out test set
  - Policy Engine compliance (cannot bypass Policy Engine)
  - Persistence roundtrip (save and load via joblib)
  - Clean frontend JSON serializability
"""

import pytest
import json
import numpy as np
import pandas as pd
from pathlib import Path

from src.data_generator import WapsiDataGenerator, RecoveryDataConfig, TREATMENTS
from src.t_learner import WAPSIUpliftModel
from src.conformal_gate import WAPSIConformalGate
from wapsi.policy.policy_engine import PolicyEngine
from wapsi.core.taxonomy import RecoveryAction


@pytest.fixture(scope="module")
def conformal_dataset():
    """Generates train, calibration, and test partitions."""
    gen = WapsiDataGenerator(RecoveryDataConfig(n_samples=4000, random_seed=42))
    df_obs, _ = gen.generate()

    train_n = int(len(df_obs) * 0.5)
    calib_n = int(len(df_obs) * 0.75)

    df_train = df_obs.iloc[:train_n].copy()
    df_calib = df_obs.iloc[train_n:calib_n].copy()
    df_test = df_obs.iloc[calib_n:].copy()

    model = WAPSIUpliftModel(random_seed=42)
    model.fit(df_train)

    return df_train, df_calib, df_test, model


@pytest.fixture(scope="module")
def calibrated_gate(conformal_dataset):
    """Returns a pre-calibrated WAPSIConformalGate."""
    _, df_calib, _, model = conformal_dataset
    gate = WAPSIConformalGate(confidence_level=0.90, min_positive_lower_bound=0.02)
    gate.calibrate(model, df_calib)
    return gate


def test_conformal_gate_calibration(calibrated_gate):
    """Verifies that gate calibrates quantiles for all treatment arms."""
    assert calibrated_gate.is_calibrated is True
    for act in TREATMENTS:
        assert act in calibrated_gate.quantile_thresholds_
        q = calibrated_gate.quantile_thresholds_[act]
        assert isinstance(q, float)
        assert 0.0 < q <= 1.0


def test_evaluate_case_schema(calibrated_gate, conformal_dataset):
    """Tests the exact dictionary schema returned by evaluate_case."""
    _, _, df_test, model = conformal_dataset
    case = df_test.iloc[0].to_dict()
    uplifts = model.predict_uplift(case)
    top_act = max(uplifts.keys(), key=lambda k: uplifts[k])

    res = calibrated_gate.evaluate_case(case, action=top_act, predicted_uplift=uplifts[top_act])

    # Core required keys from specification
    assert "eligible_for_auto_action" in res
    assert "confidence" in res
    assert "calibration_status" in res
    assert "reason" in res
    assert "prediction_interval" in res
    assert "conformal_score" in res
    assert "conformal_threshold" in res

    assert isinstance(res["eligible_for_auto_action"], bool)
    assert isinstance(res["confidence"], float)
    assert isinstance(res["calibration_status"], str)
    assert isinstance(res["reason"], str)
    assert len(res["prediction_interval"]) == 2


def test_high_confidence_auto_action(calibrated_gate):
    """Verifies that large positive uplift produces eligible_for_auto_action == True."""
    case = {"amount": 2500.0, "domain": "ecommerce"}
    # Large positive uplift: +35%
    res = calibrated_gate.evaluate_case(case, action="whatsapp_nudge", predicted_uplift=0.35)

    assert res["eligible_for_auto_action"] is True
    assert "Autonomous execution authorized" in res["reason"]
    assert res["prediction_interval"][0] > 0.0


def test_low_confidence_human_escalation(calibrated_gate):
    """Verifies that borderline/uncertain uplift triggers human escalation."""
    case = {"amount": 1000.0, "domain": "food_delivery"}
    # Small borderline uplift: +2% (interval will span below 0)
    res = calibrated_gate.evaluate_case(case, action="voice_call", predicted_uplift=0.02)

    assert res["eligible_for_auto_action"] is False
    assert "Escalated for human review" in res["reason"] or "Negative" in res["reason"]


def test_no_action_safe_handling(calibrated_gate):
    """Verifies that control action (no_action) is always safely eligible."""
    case = {"amount": 500.0}
    res = calibrated_gate.evaluate_case(case, action="no_action", predicted_uplift=0.0)

    assert res["eligible_for_auto_action"] is True
    assert "no_action" in res["reason"]


def test_empirical_coverage_validity_audit(calibrated_gate, conformal_dataset):
    """Audits empirical coverage on held-out test set without fabricating guarantees."""
    _, _, df_test, model = conformal_dataset
    coverage_report = calibrated_gate.evaluate_test_coverage(model, df_test)

    assert "overall_empirical_coverage" in coverage_report
    assert "target_nominal_coverage" in coverage_report
    assert "coverage_guarantee_met" in coverage_report
    assert "per_action_coverage" in coverage_report

    emp_cov = coverage_report["overall_empirical_coverage"]
    target_cov = coverage_report["target_nominal_coverage"]

    # Empirical coverage should be close to nominal (90% target -> realized ~88-92%)
    assert abs(emp_cov - target_cov) < 0.08, f"Empirical coverage {emp_cov} should be close to target {target_cov}"


def test_policy_engine_guardrail_integration(calibrated_gate):
    """
    CRITICAL SAFETY CONSTRAINT:
    Conformal Gate signals safety, but CANNOT bypass Policy Engine rules.
    """
    policy = PolicyEngine(dnd_start_hour=21, dnd_end_hour=9)

    # High confidence case during DND hours (23:00)
    night_case = {
        "user_id": "usr_conformal_test",
        "amount_in_inr": 5000.0,
        "hour_of_day": 23
    }

    # Conformal Gate reports high confidence
    conformal_eval = calibrated_gate.evaluate_case(night_case, action="whatsapp_nudge", predicted_uplift=0.40)
    assert conformal_eval["eligible_for_auto_action"] is True

    # But Policy Engine enforces DND override
    policy_eval = policy.evaluate(
        night_case,
        proposed_action=RecoveryAction.WHATSAPP_ONE_CLICK_LINK.value,
        causal_net_utility=200.0
    )

    # Policy overrides to instant smart retry / non-contact channel
    assert policy_eval["dnd_active"] is True
    assert policy_eval["override_applied"] is True
    assert policy_eval["authorized_action"] != RecoveryAction.WHATSAPP_ONE_CLICK_LINK.value


def test_persistence_roundtrip(calibrated_gate, conformal_dataset, tmp_path):
    """Verifies save and load persistence via joblib."""
    save_path = tmp_path / "conformal_gate.joblib"
    calibrated_gate.save(save_path)
    assert save_path.exists()

    loaded = WAPSIConformalGate.load(save_path)
    assert loaded.is_calibrated is True
    assert loaded.quantile_thresholds_ == calibrated_gate.quantile_thresholds_

    case = {"amount": 2000.0}
    orig_res = calibrated_gate.evaluate_case(case, "retry_only", 0.20)
    loaded_res = loaded.evaluate_case(case, "retry_only", 0.20)
    assert orig_res == loaded_res


def test_frontend_safe_json_serialization(calibrated_gate):
    """Verifies that the entire conformal evaluation payload serializes cleanly to standard JSON."""
    case = {"amount": 3000.0}
    res = calibrated_gate.evaluate_case(case, "whatsapp_nudge", 0.25)
    json_str = json.dumps(res)
    assert isinstance(json_str, str)
    loaded = json.loads(json_str)
    assert loaded["action"] == "whatsapp_nudge"
