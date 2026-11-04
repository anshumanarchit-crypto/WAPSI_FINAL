"""
WAPSI Confidential Computing & TEE Security Package.
Razorpay AI Buildathon 2026 - Track 3
"""

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
from security.tee.mock_tee import WAPSIMockTEE

__all__ = [
    "AbstractTEEProvider",
    "EnclaveSecurityException",
    "AttestationVerificationError",
    "ModelVersionMismatchError",
    "EnclaveTamperingError",
    "AttestationDocument",
    "AttestationVerifier",
    "create_attestation_document",
    "EnclaveDecisionSigner",
    "SignedDecisionProof",
    "WAPSIMockTEE"
]
