"""
WAPSI Mock Trusted Execution Environment (TEE) Provider.
Razorpay AI Buildathon 2026 - Track 3

Confidential Computing boundary implementation for local prototyping and hackathon verification.
Encloses all sensitive causal inference components and enforces:
  - Cryptographic attestation validation prior to execution
  - Model version integrity verification
  - Strict PII shielding and data minimization
  - Cryptographic signing of decision outputs
  - Fail-closed security architecture

DISCLOSURE:
This is a software-simulated Trusted Execution Environment (Mock TEE) designed to
model the exact attestation and signing flow of hardware enclaves (AWS Nitro / Intel SGX)
without requiring physical confidential hardware deployment during local evaluation.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
import numpy as np
import pandas as pd

from security.tee.interface import (
    AbstractTEEProvider,
    EnclaveSecurityException,
    AttestationVerificationError,
    ModelVersionMismatchError,
    EnclaveTamperingError
)
from security.tee.attestation import (
    AttestationDocument,
    AttestationVerifier,
    create_attestation_document
)
from security.tee.signer import EnclaveDecisionSigner, SignedDecisionProof
from src.inference import WAPSIInferenceEngine, get_default_engine


def _generate_component_pcr(component_name: str, version: str = "1.0.0") -> str:
    """Generates a reproducible SHA256 measurement hash for an enclave component."""
    seed = f"wapsi_core_{component_name}_{version}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


class WAPSIMockTEE(AbstractTEEProvider):
    """
    Production-Shaped Mock Trusted Execution Environment for WAPSI Causal Decisioning.
    """

    def __init__(
        self,
        enclave_id: str = "enclave_wapsi_core_01",
        expected_model_version: str = "1.0.0",
        engine: Optional[WAPSIInferenceEngine] = None,
        signing_secret: Optional[bytes] = None
    ):
        self.enclave_id = enclave_id
        self.expected_model_version = expected_model_version
        self.is_hardware_enclave = False  # Explicit disclosure: Mock TEE simulation
        self.signing_secret = signing_secret or b"wapsi_root_enclave_ca_secret_2026"
        self.enclave_private_key = b"wapsi_ephemeral_enclave_key_2026"

        # Hardware measurement registers (PCRs)
        self.pcr0 = _generate_component_pcr("inference_binary", expected_model_version)
        self.pcr1 = _generate_component_pcr("policy_rules", "1.0.0")
        self.pcr2 = _generate_component_pcr("model_weights", expected_model_version)
        self.public_key_hex = hashlib.sha256(self.enclave_private_key).hexdigest()

        # Enclave Security Verifier & Signer
        self.attestation_verifier = AttestationVerifier(
            expected_pcr0=self.pcr0,
            expected_pcr2=self.pcr2,
            signing_secret=self.signing_secret
        )
        self.decision_signer = EnclaveDecisionSigner(
            enclave_key=self.enclave_private_key,
            key_id=f"{enclave_id}_key",
            pcr0_measurement=self.pcr0
        )

        # Enclosed sensitive causal models
        self.engine = engine or get_default_engine()
        self.is_attested = False
        self._current_attestation: Optional[AttestationDocument] = None

        # Issue initial attestation document
        self.refresh_attestation()

    def refresh_attestation(self, nonce: Optional[str] = None) -> AttestationDocument:
        """Issues a fresh cryptographic attestation document."""
        self._current_attestation = create_attestation_document(
            enclave_id=self.enclave_id,
            pcr0=self.pcr0,
            pcr1=self.pcr1,
            pcr2=self.pcr2,
            public_key_hex=self.public_key_hex,
            nonce=nonce,
            signing_secret=self.signing_secret,
            is_hardware_enclave=self.is_hardware_enclave
        )
        self.is_attested = True
        return self._current_attestation

    def validate_attestation(self, attestation: Optional[AttestationDocument] = None) -> bool:
        """
        Validates the enclave cryptographic attestation document.
        FAILS CLOSED: Raises AttestationVerificationError if validation fails.
        """
        doc = attestation or self._current_attestation
        if doc is None:
            raise AttestationVerificationError("No attestation document present for enclave.")

        # Execute cryptographic verification
        self.attestation_verifier.verify(doc)
        self.is_attested = True
        return True

    def sign_decision_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Signs the minimal decision payload inside the enclave.
        """
        proof = self.decision_signer.sign(record)
        return proof.to_dict()

    def secure_score_case(
        self,
        case: Dict[str, Any],
        attestation: Optional[AttestationDocument] = None,
        model_version: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes sensitive causal scoring strictly inside the protected enclave boundary.

        Enforces:
          1. Cryptographic attestation validation (Fail-Closed)
          2. Model version verification (Fail-Closed)
          3. PII shielding / data minimization
          4. Output signing with enclave private key

        Returns:
            Minimal sanitized decision object with integrity proof.
        """
        # Step 1: Validate Attestation (Fail-Closed)
        try:
            self.validate_attestation(attestation)
        except Exception as e:
            self.is_attested = False
            raise AttestationVerificationError(f"TEE Attestation Validation Failed: {e}") from e

        # Step 2: Verify Model Version (Fail-Closed)
        version_to_check = model_version or self.expected_model_version
        if version_to_check != self.expected_model_version:
            raise ModelVersionMismatchError(
                f"TEE Model Version Mismatch! Expected: '{self.expected_model_version}', "
                f"Got: '{version_to_check}'. Execution halted (Fail-Closed)."
            )

        # Step 3: PII Shielding (Sanitize input within enclave boundary)
        raw_case_id = str(case.get("case_id", f"case_{uuid.uuid4().hex[:12]}"))
        shielded_case = dict(case)
        # Strip external PII handles before internal causal processing
        shielded_case.pop("customer_email", None)
        shielded_case.pop("customer_phone", None)
        shielded_case.pop("card_pan", None)
        shielded_case.pop("customer_name", None)

        # Step 4: Execute sensitive causal inference inside boundary
        raw_decision = self.engine.predict(shielded_case)

        # Step 5: Construct Reason Codes from SHAP and Conformal Gate
        reason_codes: List[str] = []
        conformal_status = raw_decision.get("policy_inputs", {}).get("conformal_gate", {}).get("calibration_status", "CALIBRATED")
        is_auto_approved = raw_decision.get("policy_inputs", {}).get("conformal_gate", {}).get("eligible_for_auto_action", False)
        
        if is_auto_approved:
            reason_codes.append("CONFORMAL_AUTO_ACTION_AUTHORIZED")
        else:
            reason_codes.append("CONFORMAL_HUMAN_REVIEW_ESCALATED")

        rec_win = raw_decision.get("timing", {}).get("recommended_window", "0-24h")
        reason_codes.append(f"TIMING_WINDOW_{rec_win.replace('-', '_').replace('+', '_PLUS')}")

        if raw_decision.get("counter_evidence", False):
            reason_codes.append("COUNTER_EVIDENCE_FLAGGED")

        # Top SHAP reasons into reason codes
        top_reasons = raw_decision.get("explanation", {}).get("top_reasons", [])
        for r in top_reasons[:2]:
            feat = str(r.get("feature", "feat")).upper()
            impact = float(r.get("impact", 0.0))
            direction = "POS" if impact >= 0 else "NEG"
            reason_codes.append(f"DRIVER_{feat}_{direction}")

        # Step 6: Extract Minimal Decision Record (Data Minimization)
        decision_id = f"dec_{uuid.uuid4().hex[:16]}"
        minimal_decision = {
            "case_id": raw_case_id,
            "recommended_action": raw_decision["recommended_action"],
            "uplift": raw_decision["uplift"],
            "confidence": raw_decision["confidence"],
            "reason_codes": reason_codes,
            "decision_id": decision_id,
            "model_version": self.expected_model_version,
            "execution_environment": "MOCK_TEE_SIMULATION" if not self.is_hardware_enclave else "HARDWARE_CONFIDENTIAL_ENCLAVE"
        }

        # Step 7: Cryptographically Sign Minimal Decision Record
        integrity_proof = self.sign_decision_record(minimal_decision)
        minimal_decision["integrity_proof"] = integrity_proof

        return minimal_decision
