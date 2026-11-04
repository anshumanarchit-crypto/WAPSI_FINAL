"""
Automated Test Suite for WAPSI Golden Path Execution & Determinism.
Razorpay AI Buildathon 2026 - Track 3
"""

import pytest
from examples.verify_golden_path import (
    GOLDEN_CASE,
    run_golden_path,
    WAPSIInferenceEngine,
    get_default_engine,
    WAPSIMockTEE,
    AuditLedger
)


@pytest.fixture(scope="module")
def shared_engine():
    return get_default_engine()


@pytest.fixture(scope="module")
def shared_tee(shared_engine):
    return WAPSIMockTEE(engine=shared_engine)


def test_golden_path_execution_completes(shared_engine, shared_tee):
    """Verifies that golden path case runs end-to-end through every layer."""
    ledger = AuditLedger()
    trace = run_golden_path(GOLDEN_CASE, shared_engine, shared_tee, ledger, run_label="TEST_RUN")

    assert trace["case_id"] == "CASE_GOLDEN_777"
    assert trace["best_action"] == "whatsapp_nudge"
    assert trace["uplift"] > 0.50
    assert trace["baseline_probability"] > 0.0
    assert trace["timing"]["recommended_window"] == "0-24h"
    assert len(trace["shap_reasons"]) > 0
    assert len(trace["precedents"]) > 0
    assert trace["network_prior"]["combined_uplift"] > 0.0
    assert trace["bandit"]["selected_action"] is not None
    assert trace["confidence"] > 0.80
    assert "attested" in trace["tee_status"]
    assert "allowed" in trace["policy_status"]
    assert trace["audit_id"].startswith("Block #1")


def test_golden_path_determinism(shared_engine, shared_tee):
    """Verifies 100% deterministic decisioning across consecutive runs on identical inputs."""
    ledger = AuditLedger()
    trace_1 = run_golden_path(GOLDEN_CASE, shared_engine, shared_tee, ledger, run_label="RUN_1")
    trace_2 = run_golden_path(GOLDEN_CASE, shared_engine, shared_tee, ledger, run_label="RUN_2")

    assert trace_1["best_action"] == trace_2["best_action"]
    assert trace_1["uplift"] == trace_2["uplift"]
    assert trace_1["baseline_probability"] == trace_2["baseline_probability"]
    assert trace_1["action_scores"] == trace_2["action_scores"]
    assert trace_1["timing"]["recommended_window"] == trace_2["timing"]["recommended_window"]
    assert trace_1["timing"]["hazard_by_window"] == trace_2["timing"]["hazard_by_window"]
    assert trace_1["confidence"] == trace_2["confidence"]
    assert len(trace_1["shap_reasons"]) == len(trace_2["shap_reasons"])
    assert trace_1["network_prior"]["combined_uplift"] == trace_2["network_prior"]["combined_uplift"]
    assert trace_1["policy_status"] == trace_2["policy_status"]
