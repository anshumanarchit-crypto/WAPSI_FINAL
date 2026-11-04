"""
Cryptographic Decision Record Signer.
Razorpay AI Buildathon 2026 - Track 3

Signs confidential decision records inside the TEE enclave boundary, generating
cryptographic integrity proofs verified by external downstream microservices.
"""

from __future__ import annotations

import hmac
import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class SignedDecisionProof:
    """
    Integrity proof accompanying a confidential TEE recovery decision.
    """
    signature: str
    enclave_pcr0: str
    algorithm: str = "HMAC-SHA256-MOCK-TEE"
    key_id: str = "enclave_wapsi_key_01"
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EnclaveDecisionSigner:
    """
    Signer and verifier for decision records produced inside the TEE boundary.
    """

    def __init__(
        self,
        enclave_key: Optional[bytes] = None,
        key_id: str = "enclave_wapsi_key_01",
        pcr0_measurement: str = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ):
        self.enclave_key = enclave_key or b"wapsi_ephemeral_enclave_signing_key_2026"
        self.key_id = key_id
        self.pcr0_measurement = pcr0_measurement

    def sign(self, decision_payload: Dict[str, Any]) -> SignedDecisionProof:
        """
        Signs a canonicalized decision payload dictionary.
        """
        # Canonicalize payload without existing proof
        clean_payload = {k: v for k, v in decision_payload.items() if k != "integrity_proof"}
        canonical_bytes = json.dumps(clean_payload, sort_keys=True).encode("utf-8")

        ts = datetime.now(timezone.utc).isoformat()
        signable_message = canonical_bytes + b"|" + self.pcr0_measurement.encode("utf-8") + b"|" + ts.encode("utf-8")

        signature = hmac.new(
            self.enclave_key,
            signable_message,
            hashlib.sha256
        ).hexdigest()

        return SignedDecisionProof(
            signature=signature,
            enclave_pcr0=self.pcr0_measurement,
            algorithm="HMAC-SHA256-MOCK-TEE",
            key_id=self.key_id,
            timestamp=ts
        )

    def verify(
        self,
        decision_payload: Dict[str, Any],
        proof: SignedDecisionProof
    ) -> bool:
        """
        Verifies the cryptographic signature of a decision record.
        """
        clean_payload = {k: v for k, v in decision_payload.items() if k != "integrity_proof"}
        canonical_bytes = json.dumps(clean_payload, sort_keys=True).encode("utf-8")

        signable_message = canonical_bytes + b"|" + proof.enclave_pcr0.encode("utf-8") + b"|" + proof.timestamp.encode("utf-8")

        expected_sig = hmac.new(
            self.enclave_key,
            signable_message,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(proof.signature, expected_sig)
