"""
Confidential Computing Attestation Verification.
Razorpay AI Buildathon 2026 - Track 3

Implements cryptographic attestation documents containing:
  - Enclave ID & Hardware Status (simulated vs hardware TEE)
  - PCR0 (Enclave Binary / Code Measurement Hash)
  - PCR1 (Enclave Configuration Measurement Hash)
  - PCR2 (Model Weights & State Measurement Hash)
  - Enclave Ephemeral Public Key
  - Nonce Challenge (Anti-Replay)
  - Enclave Signature over Canonical Measurement Payload
"""

from __future__ import annotations

import hmac
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict

from security.tee.interface import AttestationVerificationError


@dataclass
class AttestationDocument:
    """
    Cryptographic attestation certificate issued by the enclave environment.
    """
    enclave_id: str
    pcr0: str  # Code measurement
    pcr1: str  # Configuration measurement
    pcr2: str  # Model weights measurement
    public_key_hex: str
    nonce: str
    timestamp: str
    is_hardware_enclave: bool = False  # Explicit disclosure: False in hackathon mock mode
    enclave_mode: str = "MOCK_LOCAL_TEE"
    signature: str = ""

    def to_canonical_dict(self) -> Dict[str, Any]:
        """Returns unsigned canonical dictionary for signing/verifying."""
        d = asdict(self)
        d.pop("signature", None)
        return d

    def canonical_bytes(self) -> bytes:
        """Returns deterministic JSON bytes for cryptographic hashing."""
        return json.dumps(self.to_canonical_dict(), sort_keys=True).encode("utf-8")


class AttestationVerifier:
    """
    Verifies attestation documents against known root measurement hashes and public keys.
    """

    def __init__(
        self,
        expected_pcr0: str,
        expected_pcr2: Optional[str] = None,
        max_age_seconds: int = 300,
        signing_secret: Optional[bytes] = None
    ):
        self.expected_pcr0 = expected_pcr0
        self.expected_pcr2 = expected_pcr2
        self.max_age_seconds = max_age_seconds
        self.signing_secret = signing_secret or b"wapsi_root_enclave_ca_secret_2026"

    def verify(
        self,
        doc: AttestationDocument,
        expected_nonce: Optional[str] = None
    ) -> bool:
        """
        Validates an attestation document strictly. Fails closed if any check fails.

        Checks:
          1. Signature integrity over canonical payload
          2. PCR0 (code measurement) match
          3. PCR2 (model weights measurement) match (if specified)
          4. Nonce challenge match (anti-replay)
          5. Timestamp freshness (within max_age_seconds)

        Returns:
            True if verification passes.

        Raises:
            AttestationVerificationError if any check fails.
        """
        # 1. Verify Signature
        if not doc.signature:
            raise AttestationVerificationError("Attestation document missing signature.")

        expected_sig = hmac.new(
            self.signing_secret,
            doc.canonical_bytes(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(doc.signature, expected_sig):
            raise AttestationVerificationError(
                "Attestation signature verification failed: signature does not match root CA."
            )

        # 2. Verify PCR0 (Code Measurement)
        if doc.pcr0 != self.expected_pcr0:
            raise AttestationVerificationError(
                f"PCR0 code measurement mismatch! Expected: {self.expected_pcr0[:12]}..., "
                f"Got: {doc.pcr0[:12]}... (Possible binary tampering)"
            )

        # 3. Verify PCR2 (Model Weights Measurement)
        if self.expected_pcr2 is not None and doc.pcr2 != self.expected_pcr2:
            raise AttestationVerificationError(
                f"PCR2 model measurement mismatch! Expected: {self.expected_pcr2[:12]}..., "
                f"Got: {doc.pcr2[:12]}... (Model weights altered)"
            )

        # 4. Verify Nonce Challenge (Anti-Replay)
        if expected_nonce is not None and doc.nonce != expected_nonce:
            raise AttestationVerificationError(
                f"Attestation nonce challenge failed! Expected: {expected_nonce}, Got: {doc.nonce}"
            )

        # 5. Verify Timestamp Freshness
        try:
            doc_time = datetime.fromisoformat(doc.timestamp)
            now_time = datetime.now(timezone.utc)
            age = (now_time - doc_time).total_seconds()
            if age > self.max_age_seconds:
                raise AttestationVerificationError(
                    f"Attestation document expired! Age: {age:.1f}s > {self.max_age_seconds}s"
                )
        except Exception as e:
            if isinstance(e, AttestationVerificationError):
                raise
            raise AttestationVerificationError(f"Invalid attestation timestamp: {doc.timestamp}")

        return True


def create_attestation_document(
    enclave_id: str,
    pcr0: str,
    pcr1: str,
    pcr2: str,
    public_key_hex: str,
    nonce: Optional[str] = None,
    signing_secret: Optional[bytes] = None,
    is_hardware_enclave: bool = False
) -> AttestationDocument:
    """
    Factory function to issue a cryptographically signed attestation document.
    """
    secret = signing_secret or b"wapsi_root_enclave_ca_secret_2026"
    doc = AttestationDocument(
        enclave_id=enclave_id,
        pcr0=pcr0,
        pcr1=pcr1,
        pcr2=pcr2,
        public_key_hex=public_key_hex,
        nonce=nonce or uuid.uuid4().hex,
        timestamp=datetime.now(timezone.utc).isoformat(),
        is_hardware_enclave=is_hardware_enclave,
        enclave_mode="MOCK_LOCAL_TEE" if not is_hardware_enclave else "HARDWARE_CONFIDENTIAL_ENCLAVE",
        signature=""
    )
    # Sign document
    sig = hmac.new(secret, doc.canonical_bytes(), hashlib.sha256).hexdigest()
    doc.signature = sig
    return doc
