"""
Unified Causal Decisioning Core for WAPSI.
Orchestrates Meta-Learner uplift estimation, empirical Bayes Network Priors,
Conformal Uncertainty calibration, Survival Timing optimization, and Net Revenue Utility maximization.
"""

from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd
from wapsi.core.taxonomy import RecoveryAction, ACTION_METADATA, ErrorCategory
from wapsi.causal.t_learner import MultiActionTLearner
from wapsi.causal.x_learner import MultiActionXLearner
from wapsi.causal.network_prior import NetworkPriorEngine
from wapsi.causal.timing import RecoveryTimingModel
from wapsi.causal.conformal import ConformalUpliftCalibrator


class CausalDecisionEngine:
    """
    Unified Causal Decision Core.
    Calculates causal uplift tau_a(x), applies network priors and conformal bounds,
    and maximizes Net Expected Utility to determine the optimal recovery strategy.
    """

    def __init__(
        self,
        model_type: str = "t_learner",
        merchant_default_margin: float = 0.20,
        random_seed: int = 42
    ):
        self.model_type = model_type
        self.default_margin = merchant_default_margin
        self.random_seed = random_seed
        
        self.t_learner = MultiActionTLearner(random_seed=random_seed)
        self.x_learner = MultiActionXLearner(random_seed=random_seed)
        self.network_prior = NetworkPriorEngine()
        self.timing_model = RecoveryTimingModel(random_seed=random_seed)
        self.conformal_calibrator = ConformalUpliftCalibrator(confidence_level=0.90)
        self.is_trained = False

    def train_pipeline(self, train_df: pd.DataFrame, val_df: Optional[pd.DataFrame] = None):
        """
        Trains all causal decisioning sub-components on training and validation splits.
        """
        # 1. Train Meta-Learners
        self.t_learner.fit(train_df)
        self.x_learner.fit(train_df)

        # 2. Train Network Prior
        self.network_prior.fit(train_df)

        # 3. Train Timing Model
        self.timing_model.fit(train_df)

        # 4. Calibrate Conformal Bounds on Validation Split
        if val_df is not None and len(val_df) > 0:
            val_uplifts = self.t_learner.predict_uplift(val_df)
            val_probs = self.t_learner.predict_probabilities(val_df)
            
            residuals = {}
            for act in [a.value for a in RecoveryAction]:
                act_mask = (val_df["assigned_action"] == act).values
                if np.any(act_mask):
                    emp_y = val_df["recovered"].values[act_mask]
                    pred_p = val_probs[act][act_mask]
                    residuals[act] = emp_y - pred_p
                else:
                    residuals[act] = np.array([0.05])
            self.conformal_calibrator.calibrate(val_uplifts, residuals)
        else:
            # Synthetic calibration anchor
            self.conformal_calibrator.calibrate({}, {})

        self.is_trained = True
        return self

    def decide(
        self,
        event_dict: Dict[str, Any],
        merchant_margin: Optional[float] = None,
        use_x_learner: bool = False
    ) -> Dict[str, Any]:
        """
        Evaluates a single payment failure event and produces a comprehensive causal decision.
        """
        if not self.is_trained:
            raise RuntimeError("CausalDecisionEngine must be trained before inference.")

        df = pd.DataFrame([event_dict])
        margin = merchant_margin if merchant_margin is not None else self.default_margin
        amount = float(event_dict.get("amount_in_inr", 1000.0))
        err_cat = event_dict.get("error_category", ErrorCategory.TECHNICAL_GATEWAY.value)
        pay_method = event_dict.get("payment_method", "upi")

        # 1. Predict Raw Uplifts & Probabilities
        meta_learner = self.x_learner if use_x_learner else self.t_learner
        raw_uplifts = meta_learner.predict_uplift(df)
        raw_probs = meta_learner.predict_probabilities(df)

        # 2. Apply Network Prior Empirical Bayes Shrinkage
        local_uplift_map = {act: float(raw_uplifts[act][0]) for act in raw_uplifts}
        shrunk_uplifts = self.network_prior.apply_shrinkage(
            local_uplifts=local_uplift_map,
            error_category=err_cat,
            payment_method=pay_method,
            merchant_sample_count=int(event_dict.get("historical_orders_count", 10))
        )

        # 3. Calculate Net Expected Utility for all actions:
        # Net Utility = tau_a * Amount * Margin - DispatchCost - FrictionCost
        action_evaluations = []
        for act_enum in RecoveryAction:
            act = act_enum.value
            tau = shrunk_uplifts.get(act, 0.0)
            prob = float(raw_probs[act][0])
            meta = ACTION_METADATA[act_enum]
            dispatch_cost = meta["dispatch_cost_inr"]
            friction_cost = meta["friction_cost_inr"]
            total_cost = dispatch_cost + friction_cost

            if act == RecoveryAction.NO_ACTION.value:
                net_utility = 0.0
                tau = 0.0
            else:
                # Expected incremental revenue minus direct costs
                net_utility = round((tau * amount * margin) - total_cost, 2)

            lower_ci, upper_ci, conf_tier = self.conformal_calibrator.predict_intervals(tau, act)

            action_evaluations.append({
                "action": act,
                "action_name": meta["name"],
                "channel": meta["channel"],
                "predicted_recovery_probability": round(prob, 4),
                "causal_uplift_tau": round(tau, 4),
                "conformal_interval": [lower_ci, upper_ci],
                "confidence_tier": conf_tier,
                "dispatch_cost_inr": dispatch_cost,
                "friction_cost_inr": friction_cost,
                "net_expected_utility_inr": net_utility
            })

        # Sort actions descending by Net Expected Utility
        action_evaluations.sort(key=lambda x: x["net_expected_utility_inr"], reverse=True)
        best_candidate = action_evaluations[0]

        # If best action has negative net utility, fall back to NO_ACTION
        if best_candidate["net_expected_utility_inr"] < 0:
            chosen_action = RecoveryAction.NO_ACTION.value
        else:
            chosen_action = best_candidate["action"]

        # 4. Compute Optimal Timing Delay
        timing_info = self.timing_model.predict_optimal_delay(event_dict, chosen_action)

        # Base control organic probability
        control_prob = round(float(raw_probs[RecoveryAction.NO_ACTION.value][0]), 4)
        chosen_eval = next(item for item in action_evaluations if item["action"] == chosen_action)

        return {
            "recommended_action": chosen_action,
            "recommended_action_name": chosen_eval["action_name"],
            "recommended_channel": chosen_eval["channel"],
            "baseline_organic_recovery_prob": control_prob,
            "expected_action_recovery_prob": chosen_eval["predicted_recovery_probability"],
            "individual_treatment_effect_uplift": chosen_eval["causal_uplift_tau"],
            "conformal_uplift_interval": chosen_eval["conformal_interval"],
            "confidence_tier": chosen_eval["confidence_tier"],
            "net_expected_utility_inr": chosen_eval["net_expected_utility_inr"],
            "total_action_cost_inr": round(chosen_eval["dispatch_cost_inr"] + chosen_eval["friction_cost_inr"], 2),
            "timing": timing_info,
            "all_action_rankings": action_evaluations,
            "learner_used": "X-Learner" if use_x_learner else "T-Learner"
        }
