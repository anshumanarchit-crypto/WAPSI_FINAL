"""
WAPSI Network Prior Engine (Empirical Bayes Partial Pooling).
Razorpay AI Buildathon 2026 - Track 3

Solves the Merchant Cold-Start Problem:
New and low-volume merchants have insufficient empirical data to train high-confidence
causal uplift models. The Network Prior applies transparent empirical Bayes partial
pooling to blend network-wide collective intelligence with merchant-specific evidence:

  tau_combined = w(n) * tau_merchant + (1 - w(n)) * tau_network

Where:
  w(n) = n / (n + n_0)  (Hyperbolic shrinkage)
  - Small n (e.g. 10 cases)  -> w ~ 0.09 (Network Prior dominates)
  - Large n (e.g. 10,000)     -> w ~ 0.99 (Merchant Evidence dominates)

Privacy Architecture:
  - Cross-merchant aggregation strictly uses anonymized segment-level buckets (domain, decline_reason).
  - Raw customer identifiers and customer transaction histories are NEVER shared across merchants.

Design Note:
  This implementation provides a transparent, deterministic, and interpretable
  hackathon-grade partial pooling approximation of a full hierarchical Bayesian system.
"""

from __future__ import annotations

import json
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

from src.data_generator import TREATMENTS

ACTIVE_TREATMENTS = [t for t in TREATMENTS if t != "no_action"]


def _to_json_safe(val: Any) -> Any:
    """Recursively converts numpy/pandas types to JSON-safe native Python types."""
    if isinstance(val, (np.bool_, bool)):
        return bool(val)
    elif isinstance(val, (np.integer, int)):
        return int(val)
    elif isinstance(val, (np.floating, float)):
        if np.isnan(val) or np.isinf(val):
            return 0.0
        return round(float(val), 4)
    elif isinstance(val, np.ndarray):
        return [_to_json_safe(x) for x in val.tolist()]
    elif isinstance(val, dict):
        return {str(k): _to_json_safe(v) for k, v in val.items()}
    elif isinstance(val, (list, tuple)):
        return [_to_json_safe(x) for x in val]
    elif pd.isna(val):
        return None
    return str(val)


class WAPSINetworkPrior:
    """
    Empirical Bayes Partial Pooling Network Prior for Causal Decisioning.

    Blends network-wide empirical uplift priors with merchant-specific signals.
    """

    def __init__(
        self,
        shrinkage_half_life: float = 100.0,
        shrinkage_rule: str = "hyperbolic",
        control_action: str = "no_action"
    ):
        """
        Args:
            shrinkage_half_life: n_0 parameter (sample size where merchant weight = 0.50).
            shrinkage_rule: Formula for weight w(n) - 'hyperbolic', 'exponential', or 'sigmoid'.
            control_action: Baseline control action name (default 'no_action').
        """
        self.shrinkage_half_life = float(shrinkage_half_life)
        self.shrinkage_rule = shrinkage_rule.lower()
        self.control_action = control_action

        # Learned priors
        self.global_network_uplifts_: Dict[str, float] = {}
        self.segment_network_uplifts_: Dict[str, Dict[str, float]] = {}
        self.merchant_sample_counts_: Dict[str, int] = {}
        self.merchant_empirical_uplifts_: Dict[str, Dict[str, float]] = {}
        self.is_fitted = False

    def compute_shrinkage_weight(self, n_observations: Union[int, float]) -> float:
        """
        Calculates shrinkage weight w(n) in [0.0, 1.0].
        w -> 0 as n -> 0 (network prior dominates)
        w -> 1 as n -> inf (merchant evidence dominates)
        """
        n = max(0.0, float(n_observations))
        n0 = max(1.0, self.shrinkage_half_life)

        if self.shrinkage_rule == "hyperbolic":
            # Standard Empirical Bayes / Conjugate Normal Shrinkage
            w = n / (n + n0)
        elif self.shrinkage_rule == "exponential":
            w = 1.0 - np.exp(-n / n0)
        elif self.shrinkage_rule == "sigmoid":
            scale = n0 / 2.0
            w = 1.0 / (1.0 + np.exp(-(n - n0) / scale))
        else:
            w = n / (n + n0)

        return float(np.clip(w, 0.0, 1.0))

    def fit(self, df_network: pd.DataFrame) -> "WAPSINetworkPrior":
        """
        Computes network-wide and segment-level empirical causal priors.
        Only consumes aggregated statistics to preserve cross-merchant privacy.
        """
        if len(df_network) == 0:
            raise ValueError("Cannot fit NetworkPrior on empty DataFrame.")

        # Determine treatment and recovery column names
        treatment_col = "treatment" if "treatment" in df_network.columns else "action"
        outcome_col = "recovered"

        # 1. Global Network Uplift Prior
        ctrl_mask = df_network[treatment_col] == self.control_action
        p0_global = float(df_network[ctrl_mask][outcome_col].mean()) if ctrl_mask.sum() > 0 else 0.15

        self.global_network_uplifts_.clear()
        for act in ACTIVE_TREATMENTS:
            act_mask = df_network[treatment_col] == act
            p_act = float(df_network[act_mask][outcome_col].mean()) if act_mask.sum() > 0 else p0_global
            self.global_network_uplifts_[act] = round(p_act - p0_global, 4)

        # 2. Segment-Level Network Priors (Domain & Decline Reason)
        self.segment_network_uplifts_.clear()
        segment_cols = [c for c in ["domain", "decline_reason"] if c in df_network.columns]

        if segment_cols:
            for seg_vals, group in df_network.groupby(segment_cols):
                seg_key = "_".join(str(v) for v in (seg_vals if isinstance(seg_vals, tuple) else [seg_vals]))
                ctrl_seg = group[group[treatment_col] == self.control_action]
                p0_seg = float(ctrl_seg[outcome_col].mean()) if len(ctrl_seg) > 0 else p0_global

                self.segment_network_uplifts_[seg_key] = {}
                for act in ACTIVE_TREATMENTS:
                    act_seg = group[group[treatment_col] == act]
                    p_act_seg = float(act_seg[outcome_col].mean()) if len(act_seg) > 0 else p0_seg
                    self.segment_network_uplifts_[seg_key][act] = round(p_act_seg - p0_seg, 4)

        # 3. Pre-compute Merchant Historical Counts & Empirical Uplifts (if merchant_id exists)
        self.merchant_sample_counts_.clear()
        self.merchant_empirical_uplifts_.clear()

        if "merchant_id" in df_network.columns:
            for merch_id, merch_group in df_network.groupby("merchant_id"):
                m_id = str(merch_id)
                n_merch = len(merch_group)
                self.merchant_sample_counts_[m_id] = n_merch

                # Calculate merchant empirical uplift
                ctrl_m = merch_group[merch_group[treatment_col] == self.control_action]
                p0_m = float(ctrl_m[outcome_col].mean()) if len(ctrl_m) > 0 else p0_global

                self.merchant_empirical_uplifts_[m_id] = {}
                for act in ACTIVE_TREATMENTS:
                    act_m = merch_group[merch_group[treatment_col] == act]
                    p_act_m = float(act_m[outcome_col].mean()) if len(act_m) > 0 else p0_m
                    self.merchant_empirical_uplifts_[m_id][act] = round(p_act_m - p0_m, 4)

        self.is_fitted = True
        return self

    def get_network_uplift(
        self,
        action: str,
        domain: Optional[str] = None,
        decline_reason: Optional[str] = None
    ) -> float:
        """
        Retrieves the appropriate network prior for an action, falling back gracefully.
        """
        if not self.is_fitted:
            # Safe heuristic defaults prior to fitting
            default_priors = {
                "retry_only": 0.20,
                "whatsapp_nudge": 0.25,
                "voice_call": 0.12,
                "email": 0.08,
                "incentive_link": 0.18
            }
            return default_priors.get(action, 0.10)

        # 1. Segment-level key match
        if domain and decline_reason:
            seg_key = f"{domain}_{decline_reason}"
            if seg_key in self.segment_network_uplifts_ and action in self.segment_network_uplifts_[seg_key]:
                return self.segment_network_uplifts_[seg_key][action]

        if domain and domain in self.segment_network_uplifts_ and action in self.segment_network_uplifts_[domain]:
            return self.segment_network_uplifts_[domain][action]

        # 2. Global network fallback
        return self.global_network_uplifts_.get(action, 0.10)

    def shrink_action_uplift(
        self,
        action: str,
        merchant_uplift: float,
        merchant_observations: int,
        domain: Optional[str] = None,
        decline_reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Performs partial pooling on a single action uplift estimate.

        Args:
            action: Treatment action being evaluated (e.g. 'whatsapp_nudge')
            merchant_uplift: Raw estimated uplift for this merchant/case
            merchant_observations: Number of historical transactions observed for this merchant
            domain: Optional merchant domain for segment prior
            decline_reason: Optional decline reason for segment prior

        Returns:
            JSON-safe dictionary matching the prompt contract:
            {
                "action": "whatsapp_nudge",
                "network_uplift": 0.24,
                "merchant_uplift": 0.19,
                "merchant_observations": 30,
                "merchant_weight": 0.2308,
                "combined_uplift": 0.2285
            }
        """
        net_uplift = self.get_network_uplift(action, domain=domain, decline_reason=decline_reason)
        m_weight = self.compute_shrinkage_weight(merchant_observations)
        comb_uplift = m_weight * float(merchant_uplift) + (1.0 - m_weight) * float(net_uplift)

        res = {
            "action": action,
            "network_uplift": round(float(net_uplift), 4),
            "merchant_uplift": round(float(merchant_uplift), 4),
            "merchant_observations": int(merchant_observations),
            "merchant_weight": round(float(m_weight), 4),
            "combined_uplift": round(float(comb_uplift), 4)
        }
        return _to_json_safe(res)

    def shrink_all_actions(
        self,
        merchant_uplifts: Dict[str, float],
        merchant_observations: int,
        domain: Optional[str] = None,
        decline_reason: Optional[str] = None,
        merchant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Applies empirical Bayes shrinkage across all candidate actions.

        Returns:
            Frontend-safe structured report with per-action shrunk uplifts and shrinkage summary.
        """
        action_results: Dict[str, Dict[str, Any]] = {}
        shrunk_uplifts: Dict[str, float] = {}

        for act, m_uplift in merchant_uplifts.items():
            if act == self.control_action:
                continue
            item = self.shrink_action_uplift(
                action=act,
                merchant_uplift=m_uplift,
                merchant_observations=merchant_observations,
                domain=domain,
                decline_reason=decline_reason
            )
            action_results[act] = item
            shrunk_uplifts[act] = item["combined_uplift"]

        weight = self.compute_shrinkage_weight(merchant_observations)

        response = {
            "merchant_id": str(merchant_id or "unregistered_cold_start"),
            "merchant_observations": int(merchant_observations),
            "shrinkage_half_life": float(self.shrinkage_half_life),
            "merchant_weight": round(float(weight), 4),
            "network_weight": round(float(1.0 - weight), 4),
            "shrunk_uplifts": shrunk_uplifts,
            "per_action_breakdown": action_results,
            "architecture_note": "Transparent partial pooling empirical Bayes approximation of hierarchical model."
        }
        return _to_json_safe(response)

    def get_merchant_sample_count(self, merchant_id: str) -> int:
        """Retrieves known historical observation count for a merchant, or 0 if cold-start."""
        return self.merchant_sample_counts_.get(str(merchant_id), 0)

    def save(self, file_path: Union[str, Path]) -> None:
        """Persists fitted NetworkPrior to disk via joblib."""
        if not self.is_fitted:
            raise RuntimeError("Cannot save unfitted NetworkPrior.")
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @classmethod
    def load(cls, file_path: Union[str, Path]) -> "WAPSINetworkPrior":
        """Loads a persisted NetworkPrior from disk."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"No saved NetworkPrior found at {path}")
        loaded = joblib.load(path)
        if not isinstance(loaded, cls):
            raise TypeError(f"Loaded object is not a {cls.__name__}")
        return loaded
