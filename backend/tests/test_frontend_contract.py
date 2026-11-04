"""
WAPSI Frontend API Contract Verification Suite.
Razorpay AI Buildathon 2026 - Track 3

Tests POST /api/v1/recovery/predict across 8 required diverse cases:
  1. Normal subscription case
  2. Checkout case (eCommerce)
  3. B2B SaaS case
  4. High raw probability / low uplift case (diminishing return on rich user)
  5. Low raw probability / high uplift case (PIN timeout / recoverable friction)
  6. Policy-blocked case (Late night DND window at 23:00 IST)
  7. Low-confidence case (conformal gate flags borderline case)
  8. TEE-attestation-failure case (Enclave tampering fail-closed)
"""

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.schemas import RecoveryPredictResponse


@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient with model state loaded."""
    with TestClient(app) as test_client:
        yield test_client


def _assert_contract_fields(data: dict):
    """Verifies that all 14 canonical contract fields are present and valid."""
    required_fields = [
        "case_id",
        "decision_id",
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
        "tee_status",
        "policy_status"
    ]
    for field in required_fields:
        assert field in data, f"Missing required field: '{field}' in response: {data}"

    # Verify timing sub-fields
    assert "recommended_window" in data["timing"]
    assert "hazard_by_window" in data["timing"]

    # Verify explanation sub-fields
    assert "top_reasons" in data["explanation"]

    # Verify network prior sub-fields
    assert "network_uplift" in data["network_prior"]
    assert "merchant_weight" in data["network_prior"]
    assert "combined_uplift" in data["network_prior"]

    # Verify bandit sub-fields
    assert "selected_action" in data["bandit"]
    assert "sampled_rewards" in data["bandit"]


# --- Case 1: Normal Subscription Case ---
def test_case_1_normal_subscription(client):
    payload = {
        "case_id": "CASE_SUB_001",
        "merchant_id": "merch_stream_pass",
        "domain": "subscription",
        "amount": 999.0,
        "decline_reason": "insufficient_funds",
        "attempts_used": 1,
        "account_age_days": 365,
        "previous_failures": 2,
        "previous_recoveries": 3,
        "prior_recovery_rate": 0.60,
        "day_of_week": 1,
        "hour": 11,
        "issuer": "HDFC",
        "bin_bucket": "classic",
        "fatigue_score": 0.15
    }
    res = client.post(
        "/api/v1/recovery/predict",
        json=payload,
        headers={"X-API-Key": "rzp_live_wapsi_key_demo", "X-Merchant-ID": "merch_stream_pass"}
    )
    assert res.status_code == 200
    data = res.json()
    _assert_contract_fields(data)
    assert data["case_id"] == "CASE_SUB_001"
    assert data["policy_status"] == "allowed"
    assert data["tee_status"] == "attested"


# --- Case 2: Checkout Case (eCommerce) ---
def test_case_2_checkout_ecommerce(client):
    payload = {
        "case_id": "CASE_ECOM_002",
        "merchant_id": "merch_trendy_wear",
        "domain": "ecommerce",
        "amount": 3499.0,
        "decline_reason": "upi_pin_timeout",
        "attempts_used": 1,
        "account_age_days": 180,
        "previous_failures": 1,
        "previous_recoveries": 2,
        "prior_recovery_rate": 0.75,
        "day_of_week": 3,
        "hour": 15,
        "issuer": "ICICI",
        "bin_bucket": "platinum",
        "fatigue_score": 0.05
    }
    res = client.post(
        "/api/v1/recovery/predict",
        json=payload,
        headers={"X-API-Key": "rzp_live_wapsi_key_demo", "X-Merchant-ID": "merch_trendy_wear"}
    )
    assert res.status_code == 200
    data = res.json()
    _assert_contract_fields(data)
    assert data["recommended_action"] == "whatsapp_nudge"
    assert data["uplift"] > 0.0


# --- Case 3: B2B SaaS Case ---
def test_case_3_b2b_saas(client):
    payload = {
        "case_id": "CASE_B2B_003",
        "merchant_id": "merch_cloud_scale",
        "domain": "b2b_saas",
        "amount": 45000.0,
        "decline_reason": "card_limit_exceeded",
        "attempts_used": 1,
        "account_age_days": 730,
        "previous_failures": 0,
        "previous_recoveries": 5,
        "prior_recovery_rate": 0.95,
        "day_of_week": 2,
        "hour": 10,
        "issuer": "HDFC",
        "bin_bucket": "corporate",
        "fatigue_score": 0.00
    }
    res = client.post(
        "/api/v1/recovery/predict",
        json=payload,
        headers={"X-API-Key": "rzp_live_wapsi_key_demo", "X-Merchant-ID": "merch_cloud_scale"}
    )
    assert res.status_code == 200
    data = res.json()
    _assert_contract_fields(data)
    assert data["timing"]["recommended_window"] in ["0-24h", "24-48h"]


# --- Case 4: High Raw Probability / Low Uplift Case ---
def test_case_4_high_probability_low_uplift(client):
    payload = {
        "case_id": "CASE_HIPROB_004",
        "merchant_id": "merch_prime_luxe",
        "domain": "ecommerce",
        "amount": 15000.0,
        "decline_reason": "technical_gateway_error",
        "attempts_used": 1,
        "account_age_days": 1200,
        "previous_failures": 0,
        "previous_recoveries": 15,
        "prior_recovery_rate": 0.98,
        "day_of_week": 4,
        "hour": 12,
        "issuer": "CITI",
        "bin_bucket": "signature",
        "fatigue_score": 0.00
    }
    res = client.post(
        "/api/v1/recovery/predict",
        json=payload,
        headers={"X-API-Key": "rzp_live_wapsi_key_demo", "X-Merchant-ID": "merch_prime_luxe"}
    )
    assert res.status_code == 200
    data = res.json()
    _assert_contract_fields(data)
    # Action scores and probabilities exist
    assert "retry_only" in data["action_scores"]


# --- Case 5: Low Raw Probability / High Uplift Case ---
def test_case_5_low_probability_high_uplift(client):
    payload = {
        "case_id": "CASE_LOWPROB_005",
        "merchant_id": "merch_flash_deals",
        "domain": "ecommerce",
        "amount": 1999.0,
        "decline_reason": "upi_pin_timeout",
        "attempts_used": 1,
        "account_age_days": 60,
        "previous_failures": 3,
        "previous_recoveries": 0,
        "prior_recovery_rate": 0.10,
        "day_of_week": 5,
        "hour": 16,
        "issuer": "SBI",
        "bin_bucket": "classic",
        "fatigue_score": 0.10
    }
    res = client.post(
        "/api/v1/recovery/predict",
        json=payload,
        headers={"X-API-Key": "rzp_live_wapsi_key_demo", "X-Merchant-ID": "merch_flash_deals"}
    )
    assert res.status_code == 200
    data = res.json()
    _assert_contract_fields(data)
    # High uplift from WhatsApp nudge intervention
    assert data["uplift"] > 0.10


# --- Case 6: Policy-Blocked Case (Late Night 23:00 IST) ---
def test_case_6_policy_blocked_night_window(client):
    payload = {
        "case_id": "CASE_DND_006",
        "merchant_id": "merch_quick_bite",
        "domain": "food_delivery",
        "amount": 450.0,
        "decline_reason": "insufficient_funds",
        "attempts_used": 1,
        "account_age_days": 180,
        "prior_recovery_rate": 0.50,
        "day_of_week": 6,
        "hour": 23,  # 23:00 IST -> TRAI DND Window
        "issuer": "KOTAK",
        "fatigue_score": 0.20
    }
    res = client.post(
        "/api/v1/recovery/predict",
        json=payload,
        headers={"X-API-Key": "rzp_live_wapsi_key_demo", "X-Merchant-ID": "merch_quick_bite"}
    )
    assert res.status_code == 200
    data = res.json()
    _assert_contract_fields(data)
    assert data["policy_status"] == "dnd_restricted"
    assert data["policy_inputs"]["dnd_active"] is True


# --- Case 7: Low-Confidence Case ---
def test_case_7_low_confidence_conformal_gate(client):
    payload = {
        "case_id": "CASE_LOWCONF_007",
        "merchant_id": "merch_travel_exp",
        "domain": "travel",
        "amount": 85000.0,
        "decline_reason": "authentication_failed",
        "attempts_used": 3,
        "account_age_days": 10,
        "previous_failures": 6,
        "previous_recoveries": 0,
        "prior_recovery_rate": 0.05,
        "day_of_week": 0,
        "hour": 17,
        "issuer": "OTHER",
        "bin_bucket": "corporate",
        "fatigue_score": 0.85
    }
    res = client.post(
        "/api/v1/recovery/predict",
        json=payload,
        headers={"X-API-Key": "rzp_live_wapsi_key_demo", "X-Merchant-ID": "merch_travel_exp"}
    )
    assert res.status_code == 200
    data = res.json()
    _assert_contract_fields(data)
    assert data["confidence"] is not None
    assert "conformal_gate" in data["policy_inputs"]


# --- Case 8: TEE-Attestation-Failure Case (Fail-Closed) ---
def test_case_8_tee_attestation_failure(client):
    payload = {
        "case_id": "CASE_TEE_008",
        "merchant_id": "merch_fin_corp",
        "domain": "b2b_saas",
        "amount": 100000.0,
        "decline_reason": "bank_downtime",
        "attempts_used": 1,
        "prior_recovery_rate": 0.90,
        "hour": 14,
        "issuer": "HDFC",
        "fatigue_score": 0.00
    }
    # Tampered attestation header triggers fail-closed security boundary
    res = client.post(
        "/api/v1/recovery/predict",
        json=payload,
        headers={
            "X-API-Key": "rzp_live_wapsi_key_demo",
            "X-Merchant-ID": "merch_fin_corp",
            "X-Enclave-Attestation": "tampered"
        }
    )
    assert res.status_code == 403
    data = res.json()
    assert "TEE Attestation Verification Failed" in data["detail"]
    assert data["error"] == "HTTP Error"
