"""
WAPSI Multi-Action Recovery Router.
Causal Decision Engine for Intelligent Payment Recovery.
Razorpay AI Buildathon 2026 - Track 3

Selects the optimal recovery intervention by maximizing true incremental causal uplift (CATE),
filtering domain/case ineligibility constraints, and enforcing fallback to no_action
when interventions provide zero or negative incremental value.
"""

from typing import Dict, List, Any, Optional, Tuple, Union
import json
import numpy as np
import pandas as pd

from src.t_learner import WAPSIUpliftModel
from src.data_generator import TREATMENTS


class WAPSIRecoveryRouter:
    """
    Causal Decision Engine for Payment Recovery Routing.
    Evaluates incremental treatment uplift tau_a(X) across available actions,
    applies business & compliance feasibility filters, and returns ranked recommendations.
    """

    def __init__(
        self,
        model: WAPSIUpliftModel,
        enable_eligibility_rules: bool = True,
        min_uplift_threshold: float = 0.0
    ):
        self.model = model
        self.enable_eligibility_rules = enable_eligibility_rules
        self.min_uplift_threshold = min_uplift_threshold
        self.control_action = "no_action"
        self.active_treatments = [t for t in TREATMENTS if t != self.control_action]

    def route(
        self,
        case: Dict[str, Any],
        merchant_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Routes a single payment failure case to the optimal recovery action.

        Args:
            case: Dict containing transaction covariates (domain, amount, decline_reason, etc.)
            merchant_config: Optional merchant-specific overrides (disallowed_actions, max_budget, etc.)

        Returns:
            Dict containing recommended_action, uplift, action_scores, complete rankings,
            and separated outcome probabilities.
        """
        merchant_config = merchant_config or {}
        case_id = case.get("case_id", "case_unassigned")

        # 1. Compute Action Outcome Probabilities & Incremental Uplift via T-Learner
        all_probs = self.model.predict_action_outcomes(case)
        all_uplifts = self.model.predict_uplift(case)

        baseline_prob = float(all_probs[self.control_action])

        # 2. Check Action Eligibility / Feasibility Constraints
        eligible_actions, ineligibility_reasons = self._filter_eligible_actions(case, merchant_config)

        # 3. Build Action Score Map (all active actions)
        action_scores = {act: float(all_uplifts.get(act, 0.0)) for act in self.active_treatments}

        # 4. Rank Actions by Incremental Uplift
        ranking_items = []
        for act in self.active_treatments:
            tau = float(all_uplifts.get(act, 0.0))
            pred_prob = float(all_probs.get(act, baseline_prob))
            is_elig = act in eligible_actions
            reasons = ineligibility_reasons.get(act, [])

            ranking_items.append({
                "action": act,
                "incremental_uplift": round(tau, 4),
                "predicted_outcome_probability": round(pred_prob, 4),
                "baseline_outcome_probability": round(baseline_prob, 4),
                "is_eligible": is_elig,
                "ineligibility_reasons": reasons
            })

        # Sort by incremental uplift descending
        ranking_items.sort(key=lambda x: x["incremental_uplift"], reverse=True)
        for rank_idx, item in enumerate(ranking_items, start=1):
            item["rank"] = rank_idx

        # 5. Select Winner: Highest positive uplift among ELIGIBLE actions
        eligible_candidates = [
            item for item in ranking_items
            if item["is_eligible"] and item["incremental_uplift"] > self.min_uplift_threshold
        ]

        if eligible_candidates:
            winner = eligible_candidates[0]
            recommended_action = winner["action"]
            recommended_uplift = winner["incremental_uplift"]
            recommended_prob = winner["predicted_outcome_probability"]
            decision_type = "INTERVENTION_AUTHORIZED"
        else:
            # Fallback to no_action: All uplifts <= 0 or all eligible actions produce no net benefit
            recommended_action = self.control_action
            recommended_uplift = 0.0
            recommended_prob = baseline_prob
            decision_type = "ORGANIC_NO_ACTION"

        # 6. Generate Plain-English Decision Rationale
        rationale = self._generate_rationale(
            recommended_action=recommended_action,
            recommended_uplift=recommended_uplift,
            baseline_prob=baseline_prob,
            recommended_prob=recommended_prob,
            case=case
        )

        return {
            "case_id": case_id,
            "recommended_action": recommended_action,
            "uplift": round(recommended_uplift, 4),
            "action_scores": action_scores,
            "decision_type": decision_type,
            "baseline_outcome_probability": round(baseline_prob, 4),
            "predicted_outcome_probability": round(recommended_prob, 4),
            "action_rankings": ranking_items,
            "eligible_actions": eligible_actions,
            "rationale": rationale
        }

    def batch_route(
        self,
        df_cases: pd.DataFrame,
        merchant_config: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Routes a batch DataFrame of cases."""
        records = df_cases.to_dict(orient="records")
        return [self.route(c, merchant_config) for c in records]

    def _filter_eligible_actions(
        self,
        case: Dict[str, Any],
        merchant_config: Dict[str, Any]
    ) -> Tuple[List[str], Dict[str, List[str]]]:
        """
        Applies domain and case feasibility rules.
        """
        eligible = list(self.active_treatments)
        reasons: Dict[str, List[str]] = {act: [] for act in self.active_treatments}

        if not self.enable_eligibility_rules:
            return eligible, reasons

        hour = int(case.get("hour", 14))
        amount = float(case.get("amount", 1000.0))
        decline_reason = str(case.get("decline_reason", ""))
        domain = str(case.get("domain", ""))
        disallowed = merchant_config.get("disallowed_actions", [])

        # Rule 1: Merchant disallowed actions
        for act in disallowed:
            if act in eligible:
                eligible.remove(act)
                reasons[act].append(f"Disabled by merchant configuration.")

        # Rule 2: Voice calls restricted during night hours (21:00 - 09:00 IST)
        if (hour >= 21 or hour < 9) and "voice_call" in eligible:
            eligible.remove("voice_call")
            reasons["voice_call"].append("Voice IVR restricted during night hours (21:00-09:00 IST).")

        # Rule 3: Voice calls restricted on micro amounts (< ₹500) due to customer annoyance
        if amount < 500.0 and "voice_call" in eligible:
            eligible.remove("voice_call")
            reasons["voice_call"].append(f"Order amount (₹{amount:.2f}) below minimum voice call threshold (₹500).")

        # Rule 4: Retry only not feasible on explicit user cancellation
        if decline_reason == "user_cancelled_checkout" and "retry_only" in eligible:
            eligible.remove("retry_only")
            reasons["retry_only"].append("Cannot silently retry when user explicitly cancelled checkout.")

        # Rule 5: Incentive links not suitable on pure bank outages
        if decline_reason == "bank_downtime" and "incentive_link" in eligible:
            eligible.remove("incentive_link")
            reasons["incentive_link"].append("Discounts cannot resolve acquiring bank infrastructure downtime.")

        # Rule 6: Email not suitable for instant food delivery checkout
        if domain == "food_delivery" and "email" in eligible:
            eligible.remove("email")
            reasons["email"].append("Email delivery latency exceeds food delivery checkout timeout.")

        return eligible, reasons

    def _generate_rationale(
        self,
        recommended_action: str,
        recommended_uplift: float,
        baseline_prob: float,
        recommended_prob: float,
        case: Dict[str, Any]
    ) -> str:
        if recommended_action == self.control_action:
            return (
                f"Recommended NO_ACTION: Customer has baseline organic recovery probability of {baseline_prob*100:.1f}%. "
                f"No active intervention provides positive incremental uplift (all tau <= 0). "
                f"Intervening would waste dispatch cost and risk customer friction."
            )
        else:
            return (
                f"Recommended '{recommended_action}': Achieves highest estimated incremental uplift of +{recommended_uplift*100:.1f}% "
                f"(boosting recovery probability from {baseline_prob*100:.1f}% baseline to {recommended_prob*100:.1f}%). "
                f"Selected as the most effective causal intervention for {case.get('domain', 'ecommerce')} / {case.get('decline_reason', 'failure')}."
            )


def get_deterministic_example_cases() -> List[Dict[str, Any]]:
    """
    Returns 5 canonical benchmark payment failure cases demonstrating different optimal actions,
    specifically including Case 5 where high raw payment probability != high intervention uplift.
    """
    return [
        # Case 1: UPI App Timeout on Mobile Ecommerce -> WhatsApp Nudge
        {
            "case_id": "case_ex1_upi_timeout",
            "domain": "ecommerce",
            "amount": 2499.0,
            "decline_reason": "upi_pin_timeout",
            "attempts_used": 1,
            "account_age_days": 120,
            "previous_failures": 1,
            "previous_recoveries": 1,
            "prior_recovery_rate": 0.50,
            "day_of_week": 2,
            "hour": 14,
            "issuer": "HDFC",
            "bin_bucket": "classic",
            "fatigue_score": 0.10,
            "expected_optimal_action": "whatsapp_nudge",
            "scenario_description": "Mobile UPI PIN timeout on ecommerce cart: 1-click WhatsApp deep link unblocks authentication drop."
        },
        # Case 2: Technical Gateway Switch Error -> Retry Only
        {
            "case_id": "case_ex2_tech_gateway",
            "domain": "travel",
            "amount": 6500.0,
            "decline_reason": "technical_gateway_error",
            "attempts_used": 1,
            "account_age_days": 45,
            "previous_failures": 0,
            "previous_recoveries": 0,
            "prior_recovery_rate": 0.0,
            "day_of_week": 1,
            "hour": 11,
            "issuer": "ICICI",
            "bin_bucket": "platinum",
            "fatigue_score": 0.05,
            "expected_optimal_action": "retry_only",
            "scenario_description": "Intermittent bank gateway socket disconnect: Instant background switch reroute succeeds without user contact."
        },
        # Case 3: High-Ticket B2B SaaS Renewal -> Voice Call
        {
            "case_id": "case_ex3_b2b_voice",
            "domain": "b2b_saas",
            "amount": 42000.0,
            "decline_reason": "card_limit_exceeded",
            "attempts_used": 2,
            "account_age_days": 360,
            "previous_failures": 1,
            "previous_recoveries": 2,
            "prior_recovery_rate": 0.6667,
            "day_of_week": 3,
            "hour": 15,
            "issuer": "HDFC",
            "bin_bucket": "corporate",
            "fatigue_score": 0.15,
            "expected_optimal_action": "voice_call",
            "scenario_description": "High-value B2B SaaS invoice: Outbound voice assist / account manager callback provides highest conversion."
        },
        # Case 4: Checkout Cancellation / Price Hesitation -> Incentive Link
        {
            "case_id": "case_ex4_cart_abandon",
            "domain": "ecommerce",
            "amount": 3499.0,
            "decline_reason": "user_cancelled_checkout",
            "attempts_used": 1,
            "account_age_days": 60,
            "previous_failures": 2,
            "previous_recoveries": 0,
            "prior_recovery_rate": 0.0,
            "day_of_week": 6,
            "hour": 20,
            "issuer": "SBI",
            "bin_bucket": "classic",
            "fatigue_score": 0.20,
            "expected_optimal_action": "incentive_link",
            "scenario_description": "User cancelled checkout due to price hesitation: 5% recovery discount link revives purchase intent."
        },
        # Case 5: Loyal Self-Curer (High Raw Payment Probability != High Uplift) -> No Action
        {
            "case_id": "case_ex5_organic_self_curer",
            "domain": "education",
            "amount": 2200.0,
            "decline_reason": "authentication_failed",
            "attempts_used": 1,
            "account_age_days": 365,
            "previous_failures": 0,
            "previous_recoveries": 4,
            "prior_recovery_rate": 1.0,
            "day_of_week": 2,
            "hour": 10,
            "issuer": "HDFC",
            "bin_bucket": "signature",
            "fatigue_score": 0.02,
            "expected_optimal_action": "no_action",
            "scenario_description": "CRITICAL WAPSI THESIS CASE: Loyal repeat payer with 87% organic recovery probability. Interventions produce negative/zero incremental uplift (all tau <= 0). Standard propensity models waste budget messaging them; WAPSI correctly assigns NO_ACTION."
        }
    ]
