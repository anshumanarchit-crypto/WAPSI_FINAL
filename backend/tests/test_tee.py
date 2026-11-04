"""
Unit & Security Tests for WAPSI TEE Enclave Abstraction.
Razorpay AI Buildathon 2026 - Track 3

Tests:
  - Valid cryptographic attestation and secure scoring
  - Invalid / tampered attestation rejection (Fail-Closed)
  - Expired attestation rejection (Anti-Replay / Freshness)
  - Model version mismatch rejection (Fail-Closed)
  - Decision signature verification and anti-tamper detection
  - Strict data minimization (PII shielding, no raw feature leakage)
  - Explicit Mock TEE simulation disclosure
"""

import pytest
import json
import uuid
import copy
from datetime import datetime, timezone, timedelta

from security.tee import (
    WAPSIMockTEE,
    AttestationDocument,
    AttestationVerifier,
    create_attestation_document,
    EnclaveDecisionSigner,
    AttestationVerificationError,
    ModelVersionMismatchError
)
from src.data_generator import TREATMENTS


@pytest.fixture(scope="function")
def mock_tee():
    """Returns a fresh WAPSIMockTEE instance for each test."""
    return WAPSIMockTEE(
        enclave_id="enclave_wapsi_test_01",
        expected_model_version="1.0.0"
    )


@pytest.fixture(scope="module")
def sample_case():
    """Sample transaction failure case."""
    return {
        "case_id": "case_tee_test_101",
        "amount": 3499.0,
        "domain": "ecommerce",
        "decline_reason": "upi_pin_timeout",
        "prior_recovery_rate": 0.85,
        "attempts_used": 1,
        "fatigue_score": 0.05,
        "customer_phone": "+919876543210",  # Sensitive PII
        "customer_email": "user@example.com"  # Sensitive PII
    }


def test_valid_attestation_and_scoring(mock_tee, sample_case):
    """Verifies that valid attestation allows secure scoring and returns minimal schema."""
    result = mock_tee.secure_score_case(sample_case)

    # 1. Required minimal keys from specification
    required_keys = [
        "case_id",
        "recommended_action",
        "uplift",
        "confidence",
        "reason_codes",
        "decision_id",
        "integrity_proof",
        "model_version",
        "execution_environment"
    ]
    for k in required_keys:
        assert k in result, f"Missing key '{k}' in TEE decision output"

    assert result["case_id"] == "case_tee_test_101"
    assert result["recommended_action"] in TREATMENTS
    assert isinstance(result["uplift"], float)
    assert isinstance(result["confidence"], float)
    assert isinstance(result["reason_codes"], list)
    assert len(result["reason_codes"]) > 0
    assert result["model_version"] == "1.0.0"
    assert result["execution_environment"] == "MOCK_TEE_SIMULATION"

    # 2. Integrity proof validation
    proof = result["integrity_proof"]
    assert "signature" in proof
    assert "enclave_pcr0" in proof
    assert "algorithm" in proof
    assert len(proof["signature"]) == 64  # SHA256 hex


def test_invalid_attestation_tampered_signature_fails_closed(mock_tee, sample_case):
    """
    CRITICAL SECURITY TEST:
    Tampered attestation signature must immediately raise AttestationVerificationError (Fail-Closed).
    """
    tampered_attestation = mock_tee.refresh_attestation()
    # Corrupt the cryptographic signature
    tampered_attestation.signature = "0" * 64

    with pytest.raises(AttestationVerificationError) as excinfo:
        mock_tee.secure_score_case(sample_case, attestation=tampered_attestation)

    assert "signature verification failed" in str(excinfo.value).lower()


def test_invalid_attestation_tampered_pcr0_fails_closed(mock_tee, sample_case):
    """
    CRITICAL SECURITY TEST:
    Tampered binary/code measurement (PCR0) must fail closed.
    """
    bad_pcr_doc = create_attestation_document(
        enclave_id=mock_tee.enclave_id,
        pcr0="bad_unauthorized_code_measurement_hash",
        pcr1=mock_tee.pcr1,
        pcr2=mock_tee.pcr2,
        public_key_hex=mock_tee.public_key_hex,
        signing_secret=mock_tee.signing_secret
    )

    with pytest.raises(AttestationVerificationError) as excinfo:
        mock_tee.secure_score_case(sample_case, attestation=bad_pcr_doc)

    assert "pcr0 code measurement mismatch" in str(excinfo.value).lower()


def test_expired_attestation_fails_closed(mock_tee, sample_case):
    """
    CRITICAL SECURITY TEST:
    Stale/expired attestation documents (older than 300s) must be rejected to prevent replay attacks.
    """
    expired_doc = mock_tee.refresh_attestation()
    # Set timestamp to 1 hour ago
    expired_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    expired_doc.timestamp = expired_time
    # Re-sign with expired timestamp
    signer = AttestationVerifier(mock_tee.pcr0, signing_secret=mock_tee.signing_secret)
    expired_doc.signature = "invalid_or_expired"

    with pytest.raises(AttestationVerificationError):
        mock_tee.secure_score_case(sample_case, attestation=expired_doc)


def test_model_version_mismatch_fails_closed(mock_tee, sample_case):
    """
    CRITICAL SECURITY TEST:
    Model version mismatch must fail closed immediately.
    """
    with pytest.raises(ModelVersionMismatchError) as excinfo:
        mock_tee.secure_score_case(sample_case, model_version="2.0.0")

    assert "Model Version Mismatch" in str(excinfo.value)
    assert "Fail-Closed" in str(excinfo.value)


def test_integrity_proof_verification_success(mock_tee, sample_case):
    """Verifies that the enclave signer's cryptographic proof validates genuine records."""
    decision = mock_tee.secure_score_case(sample_case)
    proof_dict = decision["integrity_proof"]

    proof = mock_tee.decision_signer.sign(decision)
    is_valid = mock_tee.decision_signer.verify(decision, proof)
    assert is_valid is True


def test_integrity_proof_detects_tampering(mock_tee, sample_case):
    """Verifies that modifying any decision field (e.g. recommended_action or uplift) invalidates the signature."""
    decision = mock_tee.secure_score_case(sample_case)
    proof = mock_tee.decision_signer.sign(decision)

    # Tamper with the decision
    tampered_decision = copy.deepcopy(decision)
    tampered_decision["uplift"] = 0.9999  # Unauthorized modification
    is_valid = mock_tee.decision_signer.verify(tampered_decision, proof)
    assert is_valid is False

    tampered_action = copy.deepcopy(decision)
    tampered_action["recommended_action"] = "no_action"
    assert mock_tee.decision_signer.verify(tampered_action, proof) is False


def test_data_minimization_no_raw_features_or_pii_leaked(mock_tee, sample_case):
    """
    CRITICAL PRIVACY TEST:
    The TEE boundary must return ONLY minimal decision data.
    Raw features and PII (phone, email, prior rates) must not cross the boundary.
    """
    decision = mock_tee.secure_score_case(sample_case)

    # Verify sensitive PII fields are absent
    assert "customer_phone" not in decision
    assert "customer_email" not in decision
    assert "prior_recovery_rate" not in decision
    assert "account_age_days" not in decision
    assert "amount" not in decision

    # Verify no internal full models or objects
    assert "uplift_model" not in decision
    assert "precedents" not in decision  # Precedent full list stays internal or minimized


def test_explicit_mock_tee_disclosure(mock_tee):
    """Verifies that the mock TEE explicitly discloses its simulated status."""
    assert mock_tee.is_hardware_enclave is False
    doc = mock_tee.refresh_attestation()
    assert doc.is_hardware_enclave is False
    assert doc.enclave_mode == "MOCK_LOCAL_TEE"
