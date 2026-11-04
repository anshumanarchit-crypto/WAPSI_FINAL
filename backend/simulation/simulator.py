"""
WAPSI End-to-End Simulation Engine.
Razorpay AI Buildathon 2026 - Track 3

Orchestrates the complete 12-stage causal recovery lifecycle:
  Event -> Validation -> Root Cause -> Causal Uplift -> Timing -> SHAP ->
  Conformal Policy Gate -> Simulated Dispatch -> Customer Response ->
  Cryptographic Audit Ledger -> Contextual Bandit Learning Update.

DISCLOSURE:
Operates entirely in local simulation mode without real currency, real dispatches,
or production Razorpay API integration.
"""

from __future__ import annotations

import time
import uuid
import numpy as np
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set

from src.inference import WAPSIInferenceEngine, get_default_engine
from security.tee import WAPSIMockTEE, AttestationVerificationError, create_attestation_document
from wapsi.security.audit_ledger import AuditLedger
from src.bandit import WAPSIMultiMerchantBandit, BanditRewardConfig
from wapsi.core.root_cause import RootCauseClassifier


class WAPSISimulator:
    """
    End-to-End Simulator for WAPSI Autonomous & Advisory Recovery Router.
    """

    def __init__(
        self,
        engine: Optional[WAPSIInferenceEngine] = None,
        mock_tee: Optional[WAPSIMockTEE] = None,
        bandit: Optional[WAPSIMultiMerchantBandit] = None,
        audit_ledger: Optional[AuditLedger] = None
    ):
        self.engine = engine or get_default_engine()
        self.mock_tee = mock_tee or WAPSIMockTEE(engine=self.engine)
        self.bandit = bandit or WAPSIMultiMerchantBandit()
        self.audit_ledger = audit_ledger or AuditLedger()
        self.reward_config = BanditRewardConfig()

        # Idempotency deduplication memory
        self.seen_event_ids: Set[str] = set()

        # Execution event history
        self.execution_history: List[Dict[str, Any]] = []

    def simulate_customer_response(
        self,
        case: Dict[str, Any],
        action: str,
        uplift: float,
        seed: int = 42
    ) -> Dict[str, Any]:
        """
        Simulates realistic customer payment response based on causal potential outcomes.
        """
        rng = np.random.RandomState(seed)
        prior_rate = float(case.get("prior_recovery_rate", 0.50))
        fatigue = float(case.get("fatigue_score", 0.10))
        amount = float(case.get("amount", 1000.0))

        # Base organic recovery probability
        p_organic = np.clip(0.20 * prior_rate * (1.0 - fatigue * 0.5), 0.02, 0.40)

        if action == "no_action":
            p_effective = p_organic
        else:
            p_effective = np.clip(p_organic + uplift, 0.05, 0.98)

        # Draw stochastic outcome
        rand_val = rng.uniform(0.0, 1.0)
        recovered = bool(rand_val < p_effective)
        recovered_amount = amount if recovered else 0.0

        # Delay in hours
        if recovered:
            time_hours = round(float(rng.exponential(scale=1.5 if action == "whatsapp_nudge" else 12.0)), 2)
        else:
            time_hours = None

        return {
            "recovered": recovered,
            "recovered_amount": recovered_amount,
            "p_effective": round(float(p_effective), 4),
            "time_to_recovery_hours": time_hours
        }

    def simulate_case(self, scenario: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a single end-to-end scenario through the complete WAPSI lifecycle.
        """
        scenario_id = scenario.get("scenario_id", f"SCENARIO_{uuid.uuid4().hex[:8]}")
        case = scenario["case"]
        case_id = case.get("case_id", f"CASE_{uuid.uuid4().hex[:8]}")
        merchant_id = case.get("merchant_id", "merch_default")
        amount = float(case.get("amount", 1000.0))
        seed = scenario.get("seed", 42)

        start_time = time.time()
        timestamp_iso = datetime.now(timezone.utc).isoformat()

        # Step 1: Idempotency & Duplicate Check
        if scenario.get("is_duplicate", False) or case_id in self.seen_event_ids:
            record = {
                "scenario_id": scenario_id,
                "case_id": case_id,
                "status": "DUPLICATE_IGNORED",
                "message": f"Duplicate event for case {case_id} ignored via anti-replay cache.",
                "timestamp": timestamp_iso
            }
            self.execution_history.append(record)
            return record

        self.seen_event_ids.add(case_id)

        # Step 2: Root-Cause Classification
        root_cause_info = RootCauseClassifier.classify(
            error_code=case.get("decline_reason", "generic_decline"),
            error_description=str(case.get("decline_reason", ""))
        )
        category_val = root_cause_info.get("error_category", "TECHNICAL_GATEWAY")

        # Step 3: TEE Attestation & Fail-Closed Security Boundary
        tee_status = "attested"
        if scenario.get("simulate_attestation_failure", False):
            # Simulate corrupted attestation
            bad_doc = create_attestation_document(
                enclave_id=self.mock_tee.enclave_id,
                pcr0="tampered_unverified_pcr0_measurement",
                pcr1=self.mock_tee.pcr1,
                pcr2=self.mock_tee.pcr2,
                public_key_hex=self.mock_tee.public_key_hex,
                signing_secret=self.mock_tee.signing_secret
            )
            try:
                self.mock_tee.validate_attestation(bad_doc)
            except AttestationVerificationError as e:
                tee_status = "attestation_failed"
                record = {
                    "scenario_id": scenario_id,
                    "case_id": case_id,
                    "status": "TEE_ATTESTATION_FAILED",
                    "tee_status": "FAILED_CLOSED",
                    "error": str(e),
                    "message": "Enclave measurement mismatch. Execution halted in fail-closed state.",
                    "timestamp": timestamp_iso
                }
                # Log security alert in audit ledger
                self.audit_ledger.append("TEE_SECURITY_ALERT", {
                    "case_id": case_id,
                    "scenario_id": scenario_id,
                    "error": str(e)
                })
                self.execution_history.append(record)
                return record

        # Step 4: Causal Decision & Timing Inference
        decision = self.engine.predict(case)
        recommended_action = decision["recommended_action"]
        uplift = float(decision["uplift"])
        confidence = float(decision["confidence"])
        timing = decision["timing"]
        timing_window = timing["recommended_window"]
        explanation = decision["explanation"]
        precedents = decision.get("precedents", [])
        counter_evidence = decision.get("counter_evidence", False)
        policy_inputs = decision.get("policy_inputs", {})
        conformal_gate = policy_inputs.get("conformal_gate", {})
        dnd_active = policy_inputs.get("dnd_active", False)

        # Precedent summary calculation
        rec_precedents = [p for p in precedents if p.get("action") == recommended_action]
        recovered_precedents = sum(1 for p in rec_precedents if p.get("recovered", False))
        precedent_str = f"{recovered_precedents}/{len(rec_precedents)} similar cases recovered" if rec_precedents else "No identical precedents"

        # Step 5: Policy Gate Evaluation
        is_auto_action = conformal_gate.get("eligible_for_auto_action", True)
        if dnd_active:
            policy_status = "DND_RESTRICTED (Silent retry only)"
        elif not is_auto_action:
            policy_status = "ESCALATED_FOR_HUMAN_REVIEW"
        else:
            policy_status = "ALLOWED (Auto-Action Approved)"

        # Step 6: Simulated Dispatch Execution
        dispatch_record = {
            "dispatch_id": f"disp_{uuid.uuid4().hex[:12]}",
            "action": recommended_action,
            "channel": "whatsapp" if "whatsapp" in recommended_action else "system_retry",
            "mock_dispatched": True,
            "timestamp": timestamp_iso
        }

        # Step 7: Simulated Customer Outcome
        customer_outcome = self.simulate_customer_response(case, recommended_action, uplift, seed=seed)
        is_recovered = customer_outcome["recovered"]
        recovered_amount = customer_outcome["recovered_amount"]

        # Step 8: Contextual Bandit Posterior Learning Update
        reward = self.reward_config.compute_reward(
            recovered=is_recovered,
            amount=amount,
            action=recommended_action,
            fatigue_score=float(case.get("fatigue_score", 0.10))
        )
        self.bandit.update(
            merchant_id=merchant_id,
            context=case,
            action=recommended_action,
            reward=reward
        )

        # Step 9: Cryptographic Append-Only Audit Ledger
        audit_block = self.audit_ledger.append("RECOVERY_DECISION_AND_OUTCOME", {
            "scenario_id": scenario_id,
            "case_id": case_id,
            "merchant_id": merchant_id,
            "amount": amount,
            "root_cause": category_val,
            "recommended_action": recommended_action,
            "uplift": uplift,
            "confidence": confidence,
            "timing_window": timing_window,
            "policy_status": policy_status,
            "outcome": "RECOVERED" if is_recovered else "NOT_RECOVERED",
            "recovered_amount": recovered_amount,
            "reward_earned": reward,
            "tee_pcr0": self.mock_tee.pcr0
        })

        duration_ms = round((time.time() - start_time) * 1000, 2)

        # Step 10: Complete Structured Record
        record = {
            "scenario_id": scenario_id,
            "case_id": case_id,
            "merchant_id": merchant_id,
            "status": "PROCESSED",
            "amount": amount,
            "decline_reason": case.get("decline_reason"),
            "root_cause_category": category_val,
            "recommended_action": recommended_action,
            "uplift": uplift,
            "timing_window": timing_window,
            "confidence": confidence,
            "precedent_summary": precedent_str,
            "counter_evidence": counter_evidence,
            "tee_status": tee_status,
            "policy_status": policy_status,
            "conformal_status": conformal_gate.get("calibration_status", "CALIBRATED"),
            "simulated_outcome": "RECOVERED" if is_recovered else "NOT_RECOVERED",
            "recovered_amount": recovered_amount,
            "net_reward_inr": reward,
            "audit_block_index": audit_block.index,
            "audit_block_hash": audit_block.block_hash,
            "execution_duration_ms": duration_ms,
            "timestamp": timestamp_iso
        }

        self.execution_history.append(record)
        return record
