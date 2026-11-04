"""
Comprehensive Automated Security Audit Test Suite for WAPSI Decision Engine.
Razorpay AI Buildathon 2026 - Track 3

Covers:
  1. Basic Bugs & Boundary Defense (Nulls, negative amounts, invalid types, timeouts)
  2. OWASP Basics (Broken access control, safe error handling, no stack trace leaks)
  3. SQL Injection Negative Tests (SQLi payloads in identifiers & covariates)
  4. Cross-Site Scripting (XSS) Negative Tests (Script tags & event handlers in text/copy)
  5. Authentication & Tenant Authorization (API key check, Merchant isolation)
  6. Rate Limiting (Sliding window 429 response)
  7. Webhook Security (HMAC-SHA256 signature, freshness, replay & idempotency)
  8. Secrets Scan (Automated regex repository scan for leaked credentials)
  9. Fail-Closed Resilience (TEE attestation, policy failure, tamper detection)
"""

import pytest
import hmac
import hashlib
import time
import re
from pathlib import Path
from fastapi.testclient import TestClient

from api.app import app, api_rate_limiter, processed_webhook_nonces
from security.tee import WAPSIMockTEE, AttestationVerificationError, ModelVersionMismatchError
from wapsi.explain.llm_explainer import LLMDecisionExplainer
from src.inference import wapsi


@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient instance."""
    with TestClient(app) as test_client:
        yield test_client


# ==============================================================================
# SECTION 1: BASIC BUGS & BOUNDARY DEFENSE
# ==============================================================================

def test_basic_bugs_negative_amount_rejected(client):
    """Negative and zero transaction amounts must be rejected with 422."""
    payload = {"amount": -100.0, "domain": "ecommerce"}
    res = client.post("/api/v1/recovery/predict", json=payload)
    assert res.status_code == 422
    assert res.json()["status_code"] == 422


def test_basic_bugs_invalid_data_types_rejected(client):
    """Invalid data types (e.g. string for amount, string for fatigue) must be rejected with 422."""
    payload = {"amount": "five_hundred", "fatigue_score": "high", "domain": "ecommerce"}
    res = client.post("/api/v1/recovery/predict", json=payload)
    assert res.status_code == 422


def test_basic_bugs_null_and_empty_payload_graceful(client):
    """Empty or missing fields receive structured validation errors without crashing."""
    res = client.post("/api/v1/recovery/predict", json={})
    assert res.status_code == 422
    assert "detail" in res.json()


def test_basic_bugs_extreme_covariates_bounded():
    """Extreme and out-of-range numerical inputs must be gracefully handled/bounded."""
    case = {
        "amount": 999999999.0,
        "attempts_used": 100,
        "fatigue_score": 1.0,
        "prior_recovery_rate": 0.0,
        "account_age_days": 10000
    }
    res = wapsi.predict(case)
    assert 0.0 <= res["uplift"] <= 1.0
    assert 0.0 <= res["confidence"] <= 1.0


# ==============================================================================
# SECTION 2: OWASP BASICS & ERROR HANDLING
# ==============================================================================

def test_owasp_no_stack_trace_leakage_on_404(client):
    """404 errors must return sanitized JSON without internal tracebacks."""
    res = client.get("/invalid_endpoint_path_xyz")
    assert res.status_code == 404
    assert "Traceback" not in res.text
    assert "File \"" not in res.text


def test_owasp_no_stack_trace_leakage_on_422(client):
    """422 validation errors must never leak stack traces."""
    res = client.post("/api/v1/recovery/predict", json={"amount": -1})
    assert res.status_code == 422
    assert "Traceback" not in res.text


def test_owasp_no_filesystem_paths_leaked(client):
    """Responses must never expose server filesystem paths or joblib filenames."""
    payload = {"amount": 2500.0, "domain": "ecommerce"}
    res = client.post("/api/v1/recovery/predict", json=payload)
    assert res.status_code == 200
    text = res.text
    assert "C:\\" not in text
    assert "/Users/" not in text
    assert ".joblib" not in text


# ==============================================================================
# SECTION 3: SQL INJECTION NEGATIVE TESTS
# ==============================================================================

@pytest.mark.parametrize("sqli_payload", [
    "' OR '1'='1",
    "'; DROP TABLE transactions; --",
    "1' UNION SELECT null, null, null--",
    "admin'--",
    "' OR 1=1 #",
    "\" OR \"\"=\""
])
def test_sqli_payloads_safely_handled_as_literal_strings(client, sqli_payload):
    """
    SQL injection attack payloads in case_id, merchant_id, and decline_reason
    must be treated strictly as literal string values without causing DB crashes or syntax errors.
    """
    payload = {
        "case_id": f"CASE_{sqli_payload}",
        "merchant_id": f"MERCH_{sqli_payload}",
        "domain": "subscription",
        "amount": 2999.0,
        "decline_reason": sqli_payload,
        "issuer": sqli_payload
    }
    res = client.post("/api/v1/recovery/predict", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["case_id"] == f"CASE_{sqli_payload}"
    assert "recommended_action" in data


# ==============================================================================
# SECTION 4: CROSS-SITE SCRIPTING (XSS) NEGATIVE TESTS
# ==============================================================================

@pytest.mark.parametrize("xss_payload", [
    "<script>alert('XSS')</script>",
    "<img src=x onerror=alert(1)>",
    "<svg/onload=alert(document.domain)>",
    "javascript:alert(1)",
    "'\"><script>prompt(1)</script>"
])
def test_xss_payloads_sanitized_in_llm_and_notification_copy(xss_payload):
    """
    XSS payloads embedded in merchant_id, error_code, or payment_id must be
    properly escaped via html.escape so they cannot execute in web interfaces.
    """
    event = {
        "merchant_id": f"merch_{xss_payload}",
        "error_code": f"ERR_{xss_payload}",
        "payment_id": f"pay_{xss_payload}",
        "amount_in_inr": 1500.0
    }
    copy = LLMDecisionExplainer.generate_customer_copy(
        event,
        selected_action="whatsapp_one_click_link"
    )
    body = copy["body_text"]

    # Assert raw unescaped script tag is not present
    assert "<script>" not in body
    assert "<img" not in body
    assert "<svg" not in body


# ==============================================================================
# SECTION 5: AUTHENTICATION & TENANT AUTHORIZATION
# ==============================================================================

def test_auth_invalid_api_key_rejected(client):
    """Requests with invalid X-API-Key header must receive 401 Unauthorized."""
    payload = {"amount": 1000.0, "domain": "ecommerce"}
    headers = {"X-API-Key": "invalid_forged_key_123"}
    res = client.post("/api/v1/recovery/predict", json=payload, headers=headers)
    assert res.status_code == 401
    assert "Invalid API Key" in res.json()["detail"]


def test_auth_valid_api_key_accepted(client):
    """Requests with valid X-API-Key header must succeed with 200 OK."""
    payload = {"amount": 1000.0, "domain": "ecommerce"}
    headers = {"X-API-Key": "rzp_live_wapsi_key_demo"}
    res = client.post("/api/v1/recovery/predict", json=payload, headers=headers)
    assert res.status_code == 200


def test_tenant_isolation_cross_merchant_access_denied(client):
    """
    CRITICAL ACCESS CONTROL TEST:
    If Merchant A (X-Merchant-ID: M001) tries to predict/access data for Merchant B (merchant_id: M002),
    it must be strictly denied with 403 Forbidden.
    """
    payload = {
        "merchant_id": "merchant_beta_002",
        "amount": 5000.0,
        "domain": "ecommerce"
    }
    headers = {
        "X-Merchant-ID": "merchant_alpha_001"  # Mismatch!
    }
    res = client.post("/api/v1/recovery/predict", json=payload, headers=headers)
    assert res.status_code == 403
    assert "Tenant authorization failure" in res.json()["detail"]


def test_tenant_isolation_matching_merchant_allowed(client):
    """When X-Merchant-ID matches request merchant_id, request is authorized."""
    payload = {
        "merchant_id": "merchant_alpha_001",
        "amount": 5000.0,
        "domain": "ecommerce"
    }
    headers = {
        "X-Merchant-ID": "merchant_alpha_001"
    }
    res = client.post("/api/v1/recovery/predict", json=payload, headers=headers)
    assert res.status_code == 200


# ==============================================================================
# SECTION 6: RATE LIMITING
# ==============================================================================

def test_rate_limiting_enforcement(client):
    """
    Simulates rapid bursts to verify that the rate limiter halts requests with HTTP 429.
    """
    # Temporarily set max requests to 5 for test validation
    original_rpm = api_rate_limiter.max_rpm
    api_rate_limiter.max_rpm = 5
    api_rate_limiter.request_timestamps.clear()

    try:
        # First 5 should succeed
        for _ in range(5):
            res = client.get("/health")
            assert res.status_code == 200

        # 6th request must trigger 429 Too Many Requests
        res_blocked = client.get("/health")
        assert res_blocked.status_code == 429
        assert "Rate limit exceeded" in res_blocked.json()["detail"]
    finally:
        # Restore rate limiter capacity
        api_rate_limiter.max_rpm = original_rpm
        api_rate_limiter.request_timestamps.clear()


# ==============================================================================
# SECTION 7: WEBHOOK SECURITY
# ==============================================================================

def test_webhook_missing_signature_rejected(client):
    """Webhooks without X-Razorpay-Signature must be rejected with 401."""
    payload = {
        "event": "payment.recovered",
        "payment_id": "pay_test_001",
        "merchant_id": "M001",
        "amount": 2500.0,
        "status": "captured",
        "timestamp": int(time.time()),
        "nonce": "nonce_123"
    }
    res = client.post("/api/v1/webhook", json=payload)
    assert res.status_code == 401
    assert "Missing X-Razorpay-Signature" in res.json()["detail"]


def test_webhook_invalid_signature_rejected(client):
    """Webhooks with an invalid signature must be rejected with 401."""
    payload = {
        "event": "payment.recovered",
        "payment_id": "pay_test_001",
        "merchant_id": "M001",
        "amount": 2500.0,
        "status": "captured",
        "timestamp": int(time.time()),
        "nonce": "nonce_123"
    }
    headers = {"X-Razorpay-Signature": "bad_forged_signature_hex"}
    res = client.post("/api/v1/webhook", json=payload, headers=headers)
    assert res.status_code == 401


def test_webhook_valid_signature_and_freshness_success(client):
    """Webhooks with valid HMAC-SHA256 signature and fresh timestamp must succeed."""
    from wapsi.core.config import get_settings
    settings = get_settings()
    secret = settings.razorpay_webhook_secret.get_secret_value() if settings.razorpay_webhook_secret else "rzp_webhook_secret_dev_demo"
    payload = {
        "event": "payment.recovered",
        "payment_id": "pay_test_999",
        "merchant_id": "M001",
        "amount": 2500.0,
        "status": "captured",
        "timestamp": int(time.time()),
        "nonce": "nonce_unique_101"
    }
    import json
    body_bytes = json.dumps(payload).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

    headers = {
        "X-Razorpay-Signature": sig,
        "Content-Type": "application/json"
    }
    res = client.post("/api/v1/webhook", content=body_bytes, headers=headers)
    assert res.status_code == 200
    assert res.json()["signature_verified"] is True
    assert res.json()["idempotency_status"] == "processed"


def test_webhook_expired_timestamp_rejected(client):
    """Webhooks with stale timestamps (>300s old) must be rejected to prevent replay attacks."""
    from wapsi.core.config import get_settings
    settings = get_settings()
    secret = settings.razorpay_webhook_secret.get_secret_value() if settings.razorpay_webhook_secret else "rzp_webhook_secret_dev_demo"
    payload = {
        "event": "payment.recovered",
        "payment_id": "pay_test_old",
        "merchant_id": "M001",
        "amount": 2500.0,
        "status": "captured",
        "timestamp": int(time.time()) - 600,  # 10 minutes ago
        "nonce": "nonce_old_001"
    }
    import json
    body_bytes = json.dumps(payload).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

    headers = {"X-Razorpay-Signature": sig, "Content-Type": "application/json"}
    res = client.post("/api/v1/webhook", content=body_bytes, headers=headers)
    assert res.status_code == 400
    assert "timestamp expired" in res.json()["detail"]


def test_webhook_replay_protection_idempotency(client):
    """Duplicate webhooks with the same nonce must be recognized and return duplicate_ignored."""
    from wapsi.core.config import get_settings
    settings = get_settings()
    secret = settings.razorpay_webhook_secret.get_secret_value() if settings.razorpay_webhook_secret else "rzp_webhook_secret_dev_demo"
    payload = {
        "event": "payment.recovered",
        "payment_id": "pay_test_idempotent",
        "merchant_id": "M001",
        "amount": 2500.0,
        "status": "captured",
        "timestamp": int(time.time()),
        "nonce": "nonce_idempotent_test_99"
    }
    import json
    body_bytes = json.dumps(payload).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

    headers = {"X-Razorpay-Signature": sig, "Content-Type": "application/json"}

    # First delivery: processed
    res1 = client.post("/api/v1/webhook", content=body_bytes, headers=headers)
    assert res1.status_code == 200
    assert res1.json()["idempotency_status"] == "processed"

    # Replayed delivery: duplicate_ignored
    res2 = client.post("/api/v1/webhook", content=body_bytes, headers=headers)
    assert res2.status_code == 200
    assert res2.json()["idempotency_status"] == "duplicate_ignored"


# ==============================================================================
# SECTION 8: SECRETS AUDIT SCAN
# ==============================================================================

def test_secrets_audit_no_live_credentials_in_source():
    """
    Scans Python source files to ensure no real production AWS, Razorpay live secrets,
    private RSA keys, or database passwords are hardcoded.
    """
    repo_root = Path(__file__).resolve().parent.parent
    py_files = list(repo_root.glob("**/*.py"))

    # Patterns for real secrets (excluding test/demo strings)
    forbidden_patterns = [
        re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS Access Key
        re.compile(r"-----BEGIN RSA PRIVATE KEY-----"),
        re.compile(r"-----BEGIN OPENSSH PRIVATE KEY-----"),
        re.compile(r"rzp_live_[a-zA-Z0-9]{20,}"),  # Real Live Razorpay keys
        re.compile(r"postgres://\w+:\w+@"),  # DB connection URI with credentials
    ]

    violations = []
    for f in py_files:
        if ".pytest_cache" in str(f) or "test_" in str(f) or ".venv" in str(f) or "site-packages" in str(f):
            continue
        try:
            content = f.read_text(encoding="utf-8")
            for pat in forbidden_patterns:
                if pat.search(content):
                    violations.append(f"Secret detected in {f.name} matching {pat.pattern}")
        except Exception:
            pass

    assert len(violations) == 0, f"Hardcoded secrets detected: {violations}"


# ==============================================================================
# SECTION 9: FAIL-CLOSED RESILIENCE
# ==============================================================================

def test_fail_closed_tampered_tee_attestation():
    """
    CRITICAL FAIL-CLOSED TEST:
    If TEE attestation fails validation, the system MUST refuse autonomous action and fail closed.
    """
    mock_tee = WAPSIMockTEE()
    bad_attestation = mock_tee.refresh_attestation()
    bad_attestation.signature = "0" * 64  # Tamper signature

    with pytest.raises(AttestationVerificationError):
        mock_tee.secure_score_case({"amount": 1000.0}, attestation=bad_attestation)


def test_fail_closed_model_version_mismatch():
    """
    CRITICAL FAIL-CLOSED TEST:
    If model version mismatches expected enclave version, inference must fail closed.
    """
    mock_tee = WAPSIMockTEE(expected_model_version="1.0.0")
    with pytest.raises(ModelVersionMismatchError):
        mock_tee.secure_score_case({"amount": 1000.0}, model_version="9.9.9")
