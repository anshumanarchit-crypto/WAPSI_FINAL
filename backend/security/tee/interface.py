"""
Abstract Interface for Trusted Execution Environment (TEE) Confidential Decisioning.
Razorpay AI Buildathon 2026 - Track 3

Defines the contract for confidential compute enclaves (Intel SGX, AWS Nitro Enclaves,
or local mock simulation for development/testing).

Enclosure Architecture:
  Encloses sensitive decisioning components:
    - Network Prior (cross-merchant shrinkage)
    - Uplift Model (T-Learner / X-Learner)
    - Timing Hazard Model (discrete survival estimator)
    - SHAP Explainer (local causal attribution)
    - Precedent Engine (historical neighbor retrieval)
    - Conformal Calibration Gate (statistical decision bounds)

Disclosure:
  This interface supports both local/mock trusted execution for buildathon prototyping
  and production hardware enclaves (AWS Nitro Enclaves / Intel SGX / AMD SEV-SNP).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass


class EnclaveSecurityException(Exception):
    """Base exception for confidential enclave security failures."""
    pass


class AttestationVerificationError(EnclaveSecurityException):
    """Raised when cryptographic attestation document or PCR measurement fails validation."""
    pass


class ModelVersionMismatchError(EnclaveSecurityException):
    """Raised when the enclave model version or weights hash does not match the expected state."""
    pass


class EnclaveTamperingError(EnclaveSecurityException):
    """Raised when memory corruption, nonce replay, or binary tampering is detected inside the boundary."""
    pass


class AbstractTEEProvider(ABC):
    """
    Abstract Base Class for Trusted Execution Environment (TEE) Decision Providers.
    """

    @abstractmethod
    def secure_score_case(self, case: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the sensitive WAPSI inference pipeline inside the protected enclave boundary.

        Enforces:
          1. Cryptographic attestation validation prior to execution
          2. Model version verification
          3. PII shielding / data minimization
          4. Output signing with enclave private key
          5. Strict fail-closed error handling

        Args:
            case: Input transaction covariate dictionary.

        Returns:
            Minimal decision record containing:
              - case_id
              - recommended_action
              - uplift
              - confidence
              - reason_codes
              - decision_id
              - integrity_proof
              - model_version
        """
        pass

    @abstractmethod
    def validate_attestation(self, attestation: Optional[Any] = None) -> bool:
        """
        Validates the enclave cryptographic attestation document against root measurement anchors.

        Returns:
            True if enclave identity, PCR measurements, and signatures are valid.

        Raises:
            AttestationVerificationError if verification fails (Fail-Closed).
        """
        pass

    @abstractmethod
    def sign_decision_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Cryptographically signs the minimal decision payload using the enclave private signing key.

        Args:
            record: Canonicalized decision payload.

        Returns:
            Integrity proof dictionary containing signature, algorithm, and PCR measurement hash.
        """
        pass
