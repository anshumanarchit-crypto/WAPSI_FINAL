"""
Network Prior Engine (Multi-Merchant Collective Intelligence & Empirical Bayes Shrinkage).
Aggregates network-wide payment rail reliability and recovery distributions across Razorpay's merchant base,
stabilizing uplift estimates for cold-start or low-volume merchants.
"""

from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd
from wapsi.core.taxonomy import RecoveryAction, ErrorCategory


class NetworkPriorEngine:
    """
    Computes and provides empirical Bayesian network priors across payment rails,
    error taxonomies, and ticket buckets.
    """

    def __init__(self, shrinkage_strength: float = 15.0):
        self.shrinkage_strength = shrinkage_strength
        self.priors_: Dict[str, Dict[str, float]] = {}
        self.is_fitted = False

    def fit(self, df: pd.DataFrame):
        """
        Aggregates network-wide empirical recovery rates and baseline uplifts.
        """
        self.priors_.clear()
        
        # Segment by error_category and payment_method
        actions = [a.value for a in RecoveryAction]
        
        for (err_cat, pm), group in df.groupby(["error_category", "payment_method"]):
            key = f"{err_cat}_{pm}"
            self.priors_[key] = {}
            
            # Baseline control recovery rate
            ctrl_sub = group[group["assigned_action"] == RecoveryAction.NO_ACTION.value]
            p0 = float(ctrl_sub["recovered"].mean()) if len(ctrl_sub) > 0 else 0.15
            
            for act in actions:
                act_sub = group[group["assigned_action"] == act]
                p_act = float(act_sub["recovered"].mean()) if len(act_sub) > 0 else p0
                self.priors_[key][act] = round(p_act - p0, 4)

        # Global fallback prior
        self.global_prior_ = {}
        ctrl_all = df[df["assigned_action"] == RecoveryAction.NO_ACTION.value]
        p0_all = float(ctrl_all["recovered"].mean()) if len(ctrl_all) > 0 else 0.15
        for act in actions:
            act_all = df[df["assigned_action"] == act]
            p_act_all = float(act_all["recovered"].mean()) if len(act_all) > 0 else p0_all
            self.global_prior_[act] = round(p_act_all - p0_all, 4)

        self.is_fitted = True
        return self

    def get_network_prior(self, error_category: str, payment_method: str) -> Dict[str, float]:
        """
        Retrieves the network uplift prior for a given category and rail.
        """
        key = f"{error_category}_{payment_method}"
        if key in self.priors_:
            return self.priors_[key]
        return getattr(self, "global_prior_", {a.value: 0.05 for a in RecoveryAction})

    def apply_shrinkage(
        self,
        local_uplifts: Dict[str, float],
        error_category: str,
        payment_method: str,
        merchant_sample_count: int = 50
    ) -> Dict[str, float]:
        """
        Applies empirical Bayes shrinkage:
        tau_shrunk = w * tau_local + (1 - w) * tau_network
        """
        network_priors = self.get_network_prior(error_category, payment_method)
        w = merchant_sample_count / (merchant_sample_count + self.shrinkage_strength)
        
        shrunk_uplifts = {}
        for act, local_tau in local_uplifts.items():
            net_tau = network_priors.get(act, 0.0)
            shrunk_val = w * local_tau + (1.0 - w) * net_tau
            shrunk_uplifts[act] = round(float(shrunk_val), 4)

        return shrunk_uplifts
