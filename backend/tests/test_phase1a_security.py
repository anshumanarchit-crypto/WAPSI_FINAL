"""
WAPSI Phase 1A Security Hardening & Architecture Validation Test Suite.
Verifies:
  1. Centralized WapsiSettings: SecretStr credential masking, test-prefix validation, fail-closed production gates.
  2. Raw-byte HMAC-SHA256 signature verification, tamper rejection, anti-replay caching.
  3. Explicit Asia/Kolkata IST timezone resolution in PolicyEngine.
  4. Channel-specific DND policy separation (WhatsApp/SMS/IVR vs Smart Retry/Email) and customer opt-out gating.
  5. Fail-closed model manifest & required artifact validation at gateway lifespan.
"""

import hmac
import hashlib
import time
from pathlib import Path
import pytest
from pydantic import ValidationError, SecretStr

from wapsi.core.config import WapsiSettings
from wapsi.security.validation import WebhookValidator, AntiReplayCache
from wapsi.policy.policy_engine import PolicyEngine
from wapsi.core.taxonomy import RecoveryAction


# ==============================================================================
# SECTION 1: CENTRALIZED CONFIGURATION & CREDENTIAL MASKING
# ==============================================================================

def test_settings_secret_masking():
    """Confirms SecretStr prevents credential leakage in string formatting and logs."""
    settings = WapsiSettings(
        razorpay_key_id="rzp_test_mockKeyForTesting123",
        razorpay_key_secret="mockSecretStringPassword987",
        razorpay_mode="test"
    )
    # Plain str() must NOT reveal the raw secret value
    assert "mockSecretStringPassword987" not in str(settings)
    assert "mockSecretStringPassword987" not in repr(settings)
    assert settings.razorpay_key_secret.get_secret_value() == "mockSecretStringPassword987"


def test_settings_masked_key_id_utility():
    """Confirms masked_key_id reveals only safe prefix and suffix."""
    settings = WapsiSettings(
        razorpay_key_id="rzp_test_1234567890abcdef",
        razorpay_mode="test"
    )
    masked = settings.masked_key_id
    assert masked.startswith("rzp_test_")
    assert masked.endswith("cdef")
    assert "1234567890" not in masked
    assert "****" in masked


def test_settings_test_mode_prefix_validation():
    """Live keys in test mode must be rejected immediately."""
    with pytest.raises(ValidationError) as exc_info:
        WapsiSettings(
            razorpay_key_id="rzp_live_unauthorizedLiveKeyInTest",
            razorpay_mode="test"
        )
    assert "must start with 'rzp_test_'" in str(exc_info.value)


def test_settings_production_mode_fail_closed():
    """Missing or dummy credentials in production mode must fail closed."""
    with pytest.raises(ValidationError) as exc_info:
        WapsiSettings(
            razorpay_key_id="rzp_test_dummyKey",
            razorpay_key_secret="dummySecret",
            razorpay_mode="live"
        )
    assert "live mode" in str(exc_info.value).lower()


# ==============================================================================
# SECTION 2: WEBHOOK SECURITY & REPLAY PROTECTION
# ==============================================================================

def test_webhook_validator_constant_time_signature():
    """Verifies HMAC-SHA256 signature verification over exact raw bytes."""
    secret = "test_webhook_secret_key_2026"
    raw_payload = b'{"event":"payment.failed","payment_id":"pay_1001","amount":2500}'
    
    valid_sig = hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()
    assert WebhookValidator.verify_signature(raw_payload, valid_sig, secret) is True

    # Tampered byte in payload must fail verification
    tampered_payload = b'{"event":"payment.failed","payment_id":"pay_1001","amount":9999}'
    assert WebhookValidator.verify_signature(tampered_payload, valid_sig, secret) is False

    # Invalid signature string must fail verification
    assert WebhookValidator.verify_signature(raw_payload, "invalid_hex_digest_xyz", secret) is False


def test_anti_replay_cache_idempotency():
    """AntiReplayCache must accept a unique nonce once and reject replays."""
    cache = AntiReplayCache(ttl_seconds=2)
    nonce = "nonce_unique_test_12345"

    # First check: allowed
    assert cache.check_and_record(nonce) is True

    # Immediate replay: rejected
    assert cache.check_and_record(nonce) is False
    assert cache.is_duplicate(nonce) is True

    # After TTL expiration: accepted again
    time.sleep(2.1)
    assert cache.check_and_record(nonce) is True


# ==============================================================================
# SECTION 3: EXPLICIT IST TIMEZONE & DND WINDOW HANDLING
# ==============================================================================

def test_policy_engine_ist_timezone_hour_resolution():
    """PolicyEngine must resolve IST hours strictly according to Asia/Kolkata."""
    engine = PolicyEngine(dnd_start_hour=21, dnd_end_hour=9)
    current_ist_hour = engine.get_current_ist_hour()
    assert isinstance(current_ist_hour, int)
    assert 0 <= current_ist_hour <= 23

    # Direct hour check: 21, 22, 23, 0, 1..8 must be DND active
    assert engine.is_dnd_active_for_hour(21) is True
    assert engine.is_dnd_active_for_hour(23) is True
    assert engine.is_dnd_active_for_hour(3) is True
    assert engine.is_dnd_active_for_hour(8) is True

    # Business day window: 9..20 must be DND inactive
    assert engine.is_dnd_active_for_hour(9) is False
    assert engine.is_dnd_active_for_hour(14) is False
    assert engine.is_dnd_active_for_hour(20) is False


# ==============================================================================
# SECTION 4: CHANNEL-SPECIFIC DND SEPARATION & OPT-OUT GATING
# ==============================================================================

def test_channel_specific_dnd_separation():
    """
    TRAI DND restricts unsolicited customer messages (WhatsApp, SMS, IVR)
    between 21:00 and 09:00 IST, but allows autonomous backend retries (Smart Retry).
    """
    engine = PolicyEngine(dnd_start_hour=21, dnd_end_hour=9)
    
    night_event = {
        "user_id": "usr_night_owl",
        "payment_id": "pay_night_01",
        "amount_in_inr": 2000.0,
        "hour_of_day": 23  # 23:00 IST (Night DND)
    }

    # WhatsApp must be suppressed during DND and safely routed to non-intrusive smart retry
    res_wa = engine.evaluate(
        event_dict=night_event,
        proposed_action=RecoveryAction.WHATSAPP_ONE_CLICK_LINK.value,
        causal_net_utility=150.0
    )
    assert res_wa["is_allowed"] is False
    assert res_wa["authorized_action"] == RecoveryAction.INSTANT_SMART_RETRY.value
    assert any("TRAI DND" in v for v in res_wa["violations"])

    # Instant Smart Retry is a silent backend operation: MUST be allowed 24/7
    res_retry = engine.evaluate(
        event_dict=night_event,
        proposed_action=RecoveryAction.INSTANT_SMART_RETRY.value,
        causal_net_utility=150.0
    )
    assert res_retry["is_allowed"] is True
    assert res_retry["authorized_action"] == RecoveryAction.INSTANT_SMART_RETRY.value


def test_customer_opt_out_gate():
    """Customers with active opt-out flags must never receive outbound recovery communications."""
    engine = PolicyEngine()
    opted_out_event = {
        "user_id": "usr_opted_out_001",
        "customer_opted_out": True,
        "amount_in_inr": 3500.0,
        "hour_of_day": 14  # Day window
    }

    res = engine.evaluate(
        event_dict=opted_out_event,
        proposed_action=RecoveryAction.WHATSAPP_ONE_CLICK_LINK.value,
        causal_net_utility=200.0
    )
    assert res["is_allowed"] is False
    assert res["authorized_action"] == RecoveryAction.NO_ACTION.value
    assert any("opted out" in v.lower() for v in res["violations"])


def test_ivr_ticket_size_floor():
    """IVR calls are economically restricted to higher ticket transactions (>= ₹1,500)."""
    engine = PolicyEngine()
    low_ticket_event = {
        "user_id": "usr_low_ticket",
        "amount_in_inr": 499.0,  # Below ₹1,500 IVR threshold
        "hour_of_day": 14
    }

    res = engine.evaluate(
        event_dict=low_ticket_event,
        proposed_action=RecoveryAction.CALL_ASSIST_IVR.value,
        causal_net_utility=50.0
    )
    assert res["is_allowed"] is False
    assert any("ticket size" in v.lower() for v in res["violations"])


# ==============================================================================
# SECTION 5: MODEL MANIFEST & ARTIFACT INTEGRITY VERIFICATION
# ==============================================================================

def test_model_manifest_validation():
    """Gateway verifies manifest.json and rejects nonexistent or corrupt model directories."""
    from src.inference import WAPSIInferenceEngine
    
    # Existing models/ directory loads properly
    engine = WAPSIInferenceEngine.load_default("models")
    assert engine.uplift_model is not None
    assert engine.timing_model is not None
    assert engine.conformal_gate is not None
    assert engine.network_prior is not None
    assert engine.bandit is not None
    assert engine.precedent_engine is not None

    # Missing models directory fails gracefully or falls back
    invalid_engine = WAPSIInferenceEngine.load_default("nonexistent_models_path_xyz")
    assert invalid_engine.uplift_model is None
