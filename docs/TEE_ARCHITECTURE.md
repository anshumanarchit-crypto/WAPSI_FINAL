# WAPSI Trusted Execution Environment (TEE) Architecture
**Razorpay AI Buildathon 2026 | Track 3: Confidential Causal Recovery Router**

---

## 1. Executive Summary & Honest Disclosure

> [!IMPORTANT]
> **HACKATHON HONESTY DISCLOSURE**:
> During local evaluation and buildathon demonstration, WAPSI operates using a **Production-Shaped Mock TEE Simulation (`WAPSIMockTEE`)**.
> We **do not** falsely claim that this application currently executes inside physical cloud confidential hardware during local development.
> Instead, we have architected an **abstraction layer (`AbstractTEEProvider`)** that mirrors the exact PCR measurement, cryptographic attestation, signing, PII shielding, and fail-closed flows of production enclaves (AWS Nitro Enclaves, Intel SGX, or AMD SEV-SNP).

---

## 2. Enclosure Architecture: What Lives Inside the Boundary

To protect merchant privacy, proprietary causal uplift logic, and confidential payment outcomes, the following **6 sensitive components** are encapsulated strictly within the TEE enclave boundary:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                            UNTRUSTED EXTERNAL ENVIRONMENT                                   │
│  (Host OS / Kubernetes Pod / Public API Gateway / Observability / Logging)                  │
│                                                                                             │
│  Ingress Case Covariates (case_id, amount, domain, decline_reason, fatigue)                 │
│         │                                                                                   │
│         ▼                                                                                   │
│  ┌───────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                    CONFIDENTIAL TEE ENCLAVE BOUNDARY (`AbstractTEEProvider`)          │  │
│  │                                                                                       │  │
│  │   1. Attestation Check (PCR0 Binary Hash, PCR2 Weights Hash, Nonce, Anti-Replay)      │  │
│  │   2. Model Version Verification (Expected == Loaded)                                  │  │
│  │   3. PII Shielding (Tokenize/Redact customer_email, customer_phone, card_pan)         │  │
│  │                                                                                       │  │
│  │   [ ENCLOSED SENSITIVE ML COMPONENTS ]                                                │  │
│  │   ├── Network Prior (Empirical Bayes cross-merchant partial pooling)                  │  │
│  │   ├── Uplift Model (T-Learner CATE Estimators with potential outcome isolation)       │  │
│  │   ├── Timing Hazard Model (Discrete survival recovery probability)                    │  │
│  │   ├── Precedent Engine (k-NN Historical grounding & counter-evidence detection)       │  │
│  │   ├── TreeSHAP Explainer (Exact local feature attributions)                           │  │
│  │   └── Conformal Calibration Gate (Finite-sample valid decision safety bounds)         │  │
│  │                                                                                       │  │
│  │   4. Minimal Data Extraction (Data Minimization)                                      │  │
│  │   5. Enclave Cryptographic Signing (HMAC-SHA256 / Ed25519)                            │  │
│  └───────────────────────────────────────────────────────────────────────────────────────┘  │
│         │                                                                                   │
│         ▼                                                                                   │
│  Minimal Signed Decision Record + Cryptographic Integrity Proof                             │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Data Minimization & Privacy Guarantee

The TEE boundary strictly implements the **Principle of Data Minimization**:
- **What goes into the enclave**: Raw transaction failure event (including contextual covariates).
- **What is shielded inside the enclave**: User identifiers, contact handles, credit card PANs, and raw training features.
- **What leaves the enclave**: **ONLY** the minimal decision record:
  - `case_id`: Transaction reference
  - `recommended_action`: Optimal action (e.g. `"whatsapp_nudge"`)
  - `uplift`: Point estimate of incremental recovery
  - `confidence`: Calibrated statistical reliability score
  - `reason_codes`: High-level explanation codes (e.g. `["CONFORMAL_AUTO_ACTION_AUTHORIZED", "TIMING_WINDOW_0_24H"]`)
  - `decision_id`: Unique cryptographic UUID
  - `model_version`: Active model version
  - `integrity_proof`: Cryptographic signature + PCR0 measurement hash

---

## 4. "Mock TEE for Hackathon" vs "Production Hardware TEE Architecture"

| Architectural Property | Hackathon Implementation (`WAPSIMockTEE`) | Production Architecture (AWS Nitro / Intel SGX) |
| :--- | :--- | :--- |
| **Execution Environment** | Python software boundary (`security/tee/mock_tee.py`) | Hardware-isolated VM enclave with no persistent storage |
| **Enclave Communication** | In-process Python method call `secure_score_case()` | Secure AF_VSOCK Unix socket stream between host and enclave |
| **Measurement Registers** | SHA-256 hashes of Python codebase and model artifacts (`PCR0`, `PCR1`, `PCR2`) | Hardware-rooted TPM/SEV measurement registers computed by hypervisor |
| **Root of Trust** | Embedded Mock Root CA signing secret | Cloud hardware provider Root CA (e.g. AWS Nitro PKI / Intel Attestation Service) |
| **Signing Key** | Ephemeral enclave signing key initialized at enclave boot | Enclave-generated asymmetric key pair (Ed25519) never exposed to host |
| **Anti-Replay Protection** | Nonce challenge + 300s timestamp freshness verification | Cryptographic challenge nonce embedded into Signed Attestation Document |
| **Fail-Closed Behavior** | Raises `AttestationVerificationError` / `ModelVersionMismatchError` | Enclave terminates execution, halts VSOCK listener, refusing to release outputs |

---

## 5. Security & Fail-Closed Protocols

1. **Attestation Verification**:
   - Every inference call verifies the enclave's cryptographic attestation document.
   - If the code measurement (`PCR0`), model measurement (`PCR2`), signature, or nonce is altered, the enclave **fails closed** (`AttestationVerificationError`) and refuses to compute or release any recommendation.
2. **Model Version Verification**:
   - The enclave compares the requested model version against the attested version in memory.
   - Any mismatch immediately triggers `ModelVersionMismatchError` (fail-closed).
3. **Anti-Tampering Integrity Proof**:
   - All outgoing decisions are signed with the enclave's internal key.
   - Downstream payment services verify the signature before executing any recovery workflow. Any modification to `uplift` or `recommended_action` by a malicious actor immediately invalidates the cryptographic signature.
