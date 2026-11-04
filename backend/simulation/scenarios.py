"""
Standard Simulation Scenarios for WAPSI End-to-End Decisioning.
Razorpay AI Buildathon 2026 - Track 3

Defines deterministic, reproducible test scenarios covering:
  - Happy Path (High uplift -> Recovery success)
  - Hard Decline (Non-recoverable failure -> Not recovered)
  - Duplicate Webhook Event (Deduplication idempotency)
  - Policy Blocked / DND Override (Night window TRAI restriction)
  - TEE Attestation Failure (Enclave tampering -> Fail-closed)
  - Low Confidence / Borderline (Conformal escalation for human review)
  - High Counter-Evidence (Historical negative precedent alert)
"""

from __future__ import annotations
from typing import Dict, Any, List

SCENARIO_RECOVERED: Dict[str, Any] = {
    "scenario_id": "SCENARIO_01_RECOVERED",
    "name": "eCommerce UPI PIN Timeout (High Uplift & Recovery)",
    "case": {
        "case_id": "CASE_REC_101",
        "merchant_id": "merch_trendy_wear",
        "domain": "ecommerce",
        "amount": 4999.0,
        "decline_reason": "upi_pin_timeout",
        "attempts_used": 1,
        "account_age_days": 420,
        "previous_failures": 1,
        "previous_recoveries": 2,
        "prior_recovery_rate": 0.85,
        "day_of_week": 2,
        "hour": 14,
        "issuer": "HDFC",
        "bin_bucket": "platinum",
        "fatigue_score": 0.05
    },
    "expected_action": "whatsapp_nudge",
    "simulate_attestation_failure": False,
    "is_duplicate": False,
    "seed": 42
}

SCENARIO_NOT_RECOVERED: Dict[str, Any] = {
    "scenario_id": "SCENARIO_02_NOT_RECOVERED",
    "name": "Stolen Card / Expired Mandate (Hard Decline Non-Recovery)",
    "case": {
        "case_id": "CASE_FAIL_202",
        "merchant_id": "merch_gadget_hub",
        "domain": "ecommerce",
        "amount": 28500.0,
        "decline_reason": "stolen_card",
        "attempts_used": 3,
        "account_age_days": 30,
        "previous_failures": 5,
        "previous_recoveries": 0,
        "prior_recovery_rate": 0.00,
        "day_of_week": 5,
        "hour": 16,
        "issuer": "SBI",
        "bin_bucket": "classic",
        "fatigue_score": 0.90
    },
    "expected_action": "no_action",
    "simulate_attestation_failure": False,
    "is_duplicate": False,
    "seed": 101
}

SCENARIO_DUPLICATE_EVENT: Dict[str, Any] = {
    "scenario_id": "SCENARIO_03_DUPLICATE_EVENT",
    "name": "Duplicate Webhook Delivery (Anti-Replay Idempotency)",
    "case": {
        "case_id": "CASE_DUP_303",
        "merchant_id": "merch_cloud_suite",
        "domain": "b2b_saas",
        "amount": 12000.0,
        "decline_reason": "bank_downtime",
        "attempts_used": 1,
        "account_age_days": 600,
        "prior_recovery_rate": 0.90,
        "hour": 11,
        "issuer": "ICICI",
        "fatigue_score": 0.00
    },
    "expected_action": "voice_call",
    "simulate_attestation_failure": False,
    "is_duplicate": True,
    "seed": 42
}

SCENARIO_POLICY_BLOCKED: Dict[str, Any] = {
    "scenario_id": "SCENARIO_04_POLICY_BLOCKED",
    "name": "Late Night Transaction (TRAI DND Policy Override)",
    "case": {
        "case_id": "CASE_DND_404",
        "merchant_id": "merch_quick_bite",
        "domain": "food_delivery",
        "amount": 650.0,
        "decline_reason": "insufficient_funds",
        "attempts_used": 1,
        "account_age_days": 180,
        "prior_recovery_rate": 0.60,
        "day_of_week": 6,
        "hour": 23,  # 23:00 IST -> Night Window Active
        "issuer": "KOTAK",
        "fatigue_score": 0.20
    },
    "expected_action": "retry_only",
    "simulate_attestation_failure": False,
    "is_duplicate": False,
    "seed": 42
}

SCENARIO_TEE_ATTESTATION_FAILURE: Dict[str, Any] = {
    "scenario_id": "SCENARIO_05_TEE_FAILURE",
    "name": "Tampered Enclave State (Fail-Closed Security Rejection)",
    "case": {
        "case_id": "CASE_TEE_505",
        "merchant_id": "merch_fin_corp",
        "domain": "b2b_saas",
        "amount": 75000.0,
        "decline_reason": "bank_downtime",
        "attempts_used": 1,
        "prior_recovery_rate": 0.95,
        "hour": 10,
        "issuer": "HDFC",
        "fatigue_score": 0.00
    },
    "expected_action": None,
    "simulate_attestation_failure": True,  # Simulates corrupted PCR0 / signature
    "is_duplicate": False,
    "seed": 42
}

SCENARIO_LOW_CONFIDENCE: Dict[str, Any] = {
    "scenario_id": "SCENARIO_06_LOW_CONFIDENCE",
    "name": "Borderline / High Noise Case (Conformal Human Review Escalation)",
    "case": {
        "case_id": "CASE_LOWCONF_606",
        "merchant_id": "merch_travel_exp",
        "domain": "travel",
        "amount": 42000.0,
        "decline_reason": "card_declined",
        "attempts_used": 2,
        "account_age_days": 15,
        "previous_failures": 4,
        "previous_recoveries": 1,
        "prior_recovery_rate": 0.20,
        "hour": 18,
        "issuer": "AXIS",
        "fatigue_score": 0.75
    },
    "expected_action": "voice_call",
    "simulate_attestation_failure": False,
    "is_duplicate": False,
    "seed": 88
}

SCENARIO_HIGH_COUNTER_EVIDENCE: Dict[str, Any] = {
    "scenario_id": "SCENARIO_07_COUNTER_EVIDENCE",
    "name": "High Fatigue Repeated Failure (Historical Failure Alert)",
    "case": {
        "case_id": "CASE_COUNTER_707",
        "merchant_id": "merch_stream_ott",
        "domain": "subscription",
        "amount": 999.0,
        "decline_reason": "insufficient_funds",
        "attempts_used": 3,
        "account_age_days": 240,
        "previous_failures": 6,
        "previous_recoveries": 0,
        "prior_recovery_rate": 0.10,
        "hour": 12,
        "issuer": "SBI",
        "fatigue_score": 0.85
    },
    "expected_action": "incentive_link",
    "simulate_attestation_failure": False,
    "is_duplicate": False,
    "seed": 77
}

ALL_SCENARIOS: List[Dict[str, Any]] = [
    SCENARIO_RECOVERED,
    SCENARIO_NOT_RECOVERED,
    SCENARIO_DUPLICATE_EVENT,
    SCENARIO_POLICY_BLOCKED,
    SCENARIO_TEE_ATTESTATION_FAILURE,
    SCENARIO_LOW_CONFIDENCE,
    SCENARIO_HIGH_COUNTER_EVIDENCE
]
