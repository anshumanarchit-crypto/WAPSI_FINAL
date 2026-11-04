"""
Unit & Integration Tests for WAPSI End-to-End Simulation Engine.
Razorpay AI Buildathon 2026 - Track 3

Tests:
  - All 7 standard simulation scenarios
  - Recovered happy-path outcome
  - Hard decline non-recovery outcome
  - Duplicate event anti-replay deduplication
  - TRAI DND policy override
  - TEE attestation tampering fail-closed
  - Online Contextual Bandit posterior learning update
  - Append-only Audit Ledger cryptographic hash chaining
  - Machine-readable audit log persistence
"""

import pytest
import json
from pathlib import Path

from simulation.simulator import WAPSISimulator
from simulation.scenarios import (
    ALL_SCENARIOS,
    SCENARIO_RECOVERED,
    SCENARIO_NOT_RECOVERED,
    SCENARIO_DUPLICATE_EVENT,
    SCENARIO_POLICY_BLOCKED,
    SCENARIO_TEE_ATTESTATION_FAILURE,
    SCENARIO_LOW_CONFIDENCE,
    SCENARIO_HIGH_COUNTER_EVIDENCE
)
from simulation.runner import run_simulation


@pytest.fixture(scope="function")
def simulator():
    """Returns a fresh WAPSISimulator instance."""
    return WAPSISimulator()


def test_simulation_runs_all_7_scenarios():
    """Verifies that run_simulation() executes all 7 scenarios and produces logs."""
    results = run_simulation(save_logs=True)
    assert len(results) == 7

    # Verify log files exist
    log_path = Path("simulation") / "simulation_audit_log.json"
    assert log_path.exists()
    with open(log_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 7


def test_scenario_recovered_happy_path(simulator):
    """Verifies the recovered happy path scenario."""
    res = simulator.simulate_case(SCENARIO_RECOVERED)

    assert res["status"] != "DUPLICATE_IGNORED"
    assert res["simulated_outcome"] == "RECOVERED"
    assert res["recovered_amount"] == 4999.0
    assert res["recommended_action"] == "whatsapp_nudge"
    assert res["uplift"] > 0.0
    assert res["audit_block_index"] is not None


def test_scenario_not_recovered_hard_decline(simulator):
    """Verifies non-recovery on hard fraud/stolen decline."""
    res = simulator.simulate_case(SCENARIO_NOT_RECOVERED)

    assert res["simulated_outcome"] == "NOT_RECOVERED"
    assert res["recovered_amount"] == 0.0
    assert res["audit_block_index"] is not None


def test_scenario_duplicate_event_deduplication(simulator):
    """Verifies that duplicate webhook deliveries are ignored via anti-replay cache."""
    # First delivery
    res1 = simulator.simulate_case(SCENARIO_DUPLICATE_EVENT)
    assert res1["status"] == "DUPLICATE_IGNORED"


def test_scenario_dnd_policy_restriction(simulator):
    """Verifies that 23:00 IST transaction triggers DND restriction."""
    res = simulator.simulate_case(SCENARIO_POLICY_BLOCKED)

    assert "DND_RESTRICTED" in res["policy_status"]
    assert res["case_id"] == "CASE_DND_404"


def test_scenario_tee_attestation_failure_fails_closed(simulator):
    """Verifies that tampered TEE attestation document fails closed without execution."""
    res = simulator.simulate_case(SCENARIO_TEE_ATTESTATION_FAILURE)

    assert res["status"] == "TEE_ATTESTATION_FAILED"
    assert res["tee_status"] == "FAILED_CLOSED"
    assert "error" in res


def test_scenario_low_confidence_conformal_evaluated(simulator):
    """Verifies borderline scenario evaluates conformal calibration status."""
    res = simulator.simulate_case(SCENARIO_LOW_CONFIDENCE)

    assert res["conformal_status"] is not None
    assert isinstance(res["confidence"], float)


def test_bandit_posterior_updates_after_recovery(simulator):
    """Verifies that the contextual bandit updates merchant weights after simulated outcome."""
    merchant_id = SCENARIO_RECOVERED["case"]["merchant_id"]
    m_bandit = simulator.bandit.get_or_create_merchant_bandit(merchant_id)
    n_before = m_bandit.total_steps_

    simulator.simulate_case(SCENARIO_RECOVERED)

    n_after = m_bandit.total_steps_
    assert n_after == n_before + 1


def test_audit_ledger_cryptographic_chain_integrity(simulator):
    """Verifies that all simulation events are linked in a valid SHA-256 hash chain."""
    for sc in ALL_SCENARIOS:
        simulator.simulate_case(sc)

    integrity = simulator.audit_ledger.verify_integrity()
    assert integrity["is_valid"] is True
    assert integrity["total_blocks"] >= 5
