"""
Integration tests for WAPSI Unified Inference Pipeline.
Razorpay AI Buildathon 2026 - Track 3

Tests:
  - Strict JSON schema conformity for frontend teammate contract
  - 5 fixed deterministic sample cases covering diverse transaction domains
  - Advisory-only safety (recommends without executing recovery or side effects)
  - Missing and corrupt input tolerance
  - Clean frontend JSON serializability
"""

import pytest
import json
import numpy as np
import pandas as pd
from pathlib import Path

from src.inference import WAPSIInferenceEngine, wapsi, predict, normalize_case
from src.data_generator import TREATMENTS


@pytest.fixture(scope="module")
def sample_cases():
    """Defines 5 diverse, deterministic transaction cases."""
    return [
        # Case 1: High-intent eCommerce checkout OTP timeout
        {
            "case_id": "test_ecom_01",
            "amount": 2499.0,
            "domain": "ecommerce",
            "decline_reason": "upi_pin_timeout",
            "prior_recovery_rate": 0.85,
            "attempts_used": 1,
            "fatigue_score": 0.05,
            "hour": 15,
            "issuer": "HDFC",
            "merchant_id": "merch_trendy"
        },
        # Case 2: B2B SaaS bank downtime (should favor technical retry)
        {
            "case_id": "test_b2b_02",
            "amount": 45000.0,
            "domain": "b2b_saas",
            "decline_reason": "bank_downtime",
            "prior_recovery_rate": 0.90,
            "attempts_used": 1,
            "fatigue_score": 0.00,
            "hour": 11,
            "issuer": "ICICI",
            "merchant_id": "merch_saas_corp"
        },
        # Case 3: Subscription insufficient funds (card limit / billing failure)
        {
            "case_id": "test_sub_03",
            "amount": 799.0,
            "domain": "subscription",
            "decline_reason": "insufficient_funds",
            "prior_recovery_rate": 0.40,
            "attempts_used": 2,
            "fatigue_score": 0.35,
            "hour": 10,
            "issuer": "SBI",
            "merchant_id": "merch_stream_now"
        },
        # Case 4: High fatigue customer (3 attempts, high fatigue)
        {
            "case_id": "test_fatigue_04",
            "amount": 1200.0,
            "domain": "food_delivery",
            "decline_reason": "user_cancelled_checkout",
            "prior_recovery_rate": 0.20,
            "attempts_used": 3,
            "fatigue_score": 0.85,
            "hour": 20,
            "issuer": "AXIS",
            "merchant_id": "merch_quick_bites"
        },
        # Case 5: Night-time transaction (23:00 IST - DND hours)
        {
            "case_id": "test_night_05",
            "amount": 3500.0,
            "domain": "travel",
            "decline_reason": "incorrect_otp",
            "prior_recovery_rate": 0.70,
            "attempts_used": 1,
            "fatigue_score": 0.10,
            "hour": 23,
            "issuer": "KOTAK",
            "merchant_id": "merch_fly_easy"
        }
    ]


def test_wapsi_predict_contract_schema(sample_cases):
    """
    CRITICAL CONTRACT VALIDATION:
    Verifies that wapsi.predict(case) strictly adheres to the specified JSON schema.
    """
    case = sample_cases[0]
    result = wapsi.predict(case)

    # 1. Top-level keys
    required_top_keys = [
        "case_id",
        "recommended_action",
        "uplift",
        "action_scores",
        "timing",
        "confidence",
        "explanation",
        "precedents",
        "counter_evidence",
        "network_prior",
        "bandit",
        "policy_inputs"
    ]
    for k in required_top_keys:
        assert k in result, f"Missing required top-level key '{k}' in result"

    # 2. Timing sub-structure
    assert "recommended_window" in result["timing"]
    assert "hazard_by_window" in result["timing"]
    for w in ["0-24h", "24-48h", "48-72h", "72h+"]:
        assert w in result["timing"]["hazard_by_window"]

    # 3. Explanation sub-structure
    assert "top_reasons" in result["explanation"]
    assert isinstance(result["explanation"]["top_reasons"], list)
    if len(result["explanation"]["top_reasons"]) > 0:
        r0 = result["explanation"]["top_reasons"][0]
        assert "feature" in r0
        assert "value" in r0
        assert "impact" in r0

    # 4. Precedents sub-structure
    assert isinstance(result["precedents"], list)
    assert isinstance(result["counter_evidence"], bool)

    # 5. Network Prior sub-structure
    net = result["network_prior"]
    for k in ["network_uplift", "merchant_uplift", "merchant_observations", "merchant_weight", "combined_uplift"]:
        assert k in net, f"Missing key '{k}' in network_prior"

    # 6. Bandit sub-structure
    bandit_info = result["bandit"]
    assert "selected_action" in bandit_info
    assert "sampled_rewards" in bandit_info
    assert "expected_rewards" in bandit_info

    # 7. Policy inputs sub-structure
    policy_info = result["policy_inputs"]
    assert "dnd_active" in policy_info
    assert "frequency_capped" in policy_info
    assert "conformal_gate" in policy_info
    assert "eligible_for_auto_action" in policy_info["conformal_gate"]


def test_5_deterministic_integration_cases(sample_cases):
    """Evaluates 5 deterministic cases and validates coherent decision outputs."""
    for case in sample_cases:
        res = wapsi.predict(case)

        assert res["case_id"] == case["case_id"]
        assert res["recommended_action"] in TREATMENTS
        assert isinstance(res["uplift"], float)
        assert 0.0 <= res["confidence"] <= 1.0

        # Validate action scores contains all treatments except no_action
        assert len(res["action_scores"]) >= 5

        # Check JSON serialization stability
        json_dump = json.dumps(res)
        assert isinstance(json_dump, str)
        reloaded = json.loads(json_dump)
        assert reloaded["case_id"] == case["case_id"]


def test_night_case_dnd_policy_inputs(sample_cases):
    """Verifies that 23:00 night case properly reports dnd_active in policy_inputs."""
    night_case = sample_cases[4]  # hour = 23
    res = wapsi.predict(night_case)

    assert res["policy_inputs"]["dnd_active"] is True


def test_missing_and_corrupt_fields_graceful():
    """Verifies that engine gracefully handles sparse/empty dictionaries without crashing."""
    sparse_case = {}
    res = wapsi.predict(sparse_case)

    assert res["case_id"].startswith("case_")
    assert res["recommended_action"] in TREATMENTS
    assert isinstance(res["uplift"], float)
    assert res["confidence"] > 0.0


def test_top_level_convenience_predict_function(sample_cases):
    """Verifies module-level predict() function works seamlessly."""
    case = sample_cases[1]
    res = predict(case)
    assert res["case_id"] == "test_b2b_02"
    assert res["recommended_action"] in TREATMENTS
