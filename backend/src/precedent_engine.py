"""
WAPSI Precedent & Counter-Evidence Engine.
Razorpay AI Buildathon 2026 - Track 3

Retrieves similar historical transaction failure cases and exposes factual observed
outcomes to provide auditability, peer comparison, and counter-evidence detection.

Safety Constraint:
  This engine provides evidence and review signals only.
  It does NOT directly execute recovery interventions.
"""

from __future__ import annotations

import json
from typing import Dict, List, Any, Optional, Union, Tuple
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler, OneHotEncoder


SIMILARITY_NUMERICAL_FEATURES = [
    "amount",
    "prior_recovery_rate",
    "attempts_used",
    "fatigue_score",
    "account_age_days"
]

SIMILARITY_CATEGORICAL_FEATURES = [
    "domain",
    "decline_reason",
    "issuer"
]


def _to_json_safe(val: Any) -> Any:
    """Recursively converts numpy/pandas types to JSON-safe native Python types."""
    if isinstance(val, (np.bool_, bool)):
        return bool(val)
    elif isinstance(val, (np.integer, int)):
        return int(val)
    elif isinstance(val, (np.floating, float)):
        if np.isnan(val) or np.isinf(val):
            return None
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


class WAPSIPrecedentPreprocessor:
    """Preprocessor for scaling numerical and encoding categorical similarity features."""

    def __init__(self):
        self.num_scaler = StandardScaler()
        self.cat_encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
        self.num_cols = SIMILARITY_NUMERICAL_FEATURES
        self.cat_cols = SIMILARITY_CATEGORICAL_FEATURES
        self.is_fitted = False
        self.feature_names_: List[str] = []

    def fit(self, df: pd.DataFrame) -> "WAPSIPrecedentPreprocessor":
        X_num = df[self.num_cols].fillna(0.0).astype(float)
        X_cat = df[self.cat_cols].fillna("UNKNOWN").astype(str)

        self.num_scaler.fit(X_num)
        self.cat_encoder.fit(X_cat)

        cat_names = list(self.cat_encoder.get_feature_names_out(self.cat_cols))
        self.feature_names_ = list(self.num_cols) + cat_names
        self.is_fitted = True
        return self

    def transform(self, df_or_case: Union[pd.DataFrame, Dict[str, Any]]) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("Preprocessor must be fitted before transforming.")

        if isinstance(df_or_case, dict):
            df = pd.DataFrame([df_or_case])
        elif isinstance(df_or_case, pd.Series):
            df = pd.DataFrame([df_or_case.to_dict()])
        else:
            df = df_or_case.copy()

        # Handle missing columns gracefully
        for col in self.num_cols:
            if col not in df.columns:
                df[col] = 0.0
        for col in self.cat_cols:
            if col not in df.columns:
                df[col] = "UNKNOWN"

        X_num = df[self.num_cols].fillna(0.0).astype(float)
        X_cat = df[self.cat_cols].fillna("UNKNOWN").astype(str)

        X_num_scaled = self.num_scaler.transform(X_num)
        X_cat_encoded = self.cat_encoder.transform(X_cat)

        return np.hstack([X_num_scaled, X_cat_encoded])


class WAPSIPrecedentEngine:
    """
    WAPSI Precedent & Counter-Evidence Retrieval Engine.

    Finds Nearest Historical Neighbors based on case context, computes empirical recovery
    rates for each action in the peer group, and flags strong counter-evidence.
    """

    def __init__(
        self,
        n_neighbors: int = 15,
        metric: str = "euclidean",
        counter_evidence_threshold: float = 0.25,
        min_evidence_cases: int = 3
    ):
        self.n_neighbors = n_neighbors
        self.metric = metric
        self.counter_evidence_threshold = counter_evidence_threshold
        self.min_evidence_cases = min_evidence_cases
        self.preprocessor = WAPSIPrecedentPreprocessor()
        self.nn_model = NearestNeighbors(n_neighbors=n_neighbors, metric=metric)
        self.historical_records_: Optional[pd.DataFrame] = None
        self.is_fitted = False

    def fit(self, df_history: pd.DataFrame) -> "WAPSIPrecedentEngine":
        """
        Fits the similarity space only on historical / training data.
        Never expose future / test set rows to this engine.
        """
        if len(df_history) == 0:
            raise ValueError("Cannot fit precedent engine on empty historical DataFrame.")

        # Fit preprocessor
        self.preprocessor.fit(df_history)
        X_mat = self.preprocessor.transform(df_history)

        # Fit nearest neighbors
        self.nn_model.fit(X_mat)

        # Store essential historical metadata
        cols_to_keep = [
            col for col in [
                "case_id", "treatment", "action", "recovered", "time_to_recovery_hours",
                "amount", "domain", "decline_reason", "issuer", "fatigue_score", "prior_recovery_rate"
            ] if col in df_history.columns
        ]

        # Standardize treatment column name to 'action'
        df_stored = df_history[cols_to_keep].copy()
        if "action" not in df_stored.columns and "treatment" in df_stored.columns:
            df_stored["action"] = df_stored["treatment"]

        # Ensure boolean recovered
        if "recovered" in df_stored.columns:
            df_stored["recovered"] = df_stored["recovered"].astype(bool)

        self.historical_records_ = df_stored.reset_index(drop=True)
        self.is_fitted = True
        return self

    def retrieve_similar_cases(
        self,
        case: Union[Dict[str, Any], pd.Series, pd.DataFrame],
        k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves top-k most similar historical cases.
        """
        if not self.is_fitted or self.historical_records_ is None:
            raise RuntimeError("WAPSIPrecedentEngine must be fitted before retrieval.")

        k = k or self.n_neighbors
        k = min(k, len(self.historical_records_))

        X_query = self.preprocessor.transform(case)
        distances, indices = self.nn_model.kneighbors(X_query, n_neighbors=k)

        dist_row = distances[0]
        idx_row = indices[0]

        similar_cases = []
        for d, idx in zip(dist_row, idx_row):
            record = self.historical_records_.iloc[idx].to_dict()
            # Bounded similarity score: s = 1 / (1 + distance)
            sim_score = float(1.0 / (1.0 + float(d)))

            case_item = {
                "case_id": str(record.get("case_id", f"hist_{idx}")),
                "action": str(record.get("action", record.get("treatment", "unknown"))),
                "recovered": bool(record.get("recovered", False)),
                "similarity": round(sim_score, 4),
                "time_to_recovery_hours": _to_json_safe(record.get("time_to_recovery_hours")),
                "domain": str(record.get("domain", "")),
                "decline_reason": str(record.get("decline_reason", "")),
                "issuer": str(record.get("issuer", "")),
                "amount": _to_json_safe(record.get("amount"))
            }
            similar_cases.append(case_item)

        return similar_cases

    def query(
        self,
        case: Union[Dict[str, Any], pd.Series, pd.DataFrame],
        recommended_action: Optional[str] = None,
        k: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Executes a precedent query, computes empirical recovery rates per action,
        and checks for counter-evidence.

        Args:
            case: Dict or Series of transaction attributes.
            recommended_action: The recovery action recommended by the causal model (e.g. 'whatsapp_nudge').
            k: Number of historical neighbors to evaluate (default: n_neighbors).

        Returns:
            Frontend-safe JSON dict with precedents, empirical statistics, and counter-evidence flags.
        """
        similar_cases = self.retrieve_similar_cases(case, k=k)
        count = len(similar_cases)

        # Compute empirical recovery rates by action across the neighborhood
        action_stats: Dict[str, Dict[str, Any]] = {}
        for c in similar_cases:
            act = c["action"]
            if act not in action_stats:
                action_stats[act] = {"attempts": 0, "recoveries": 0}
            action_stats[act]["attempts"] += 1
            if c["recovered"]:
                action_stats[act]["recoveries"] += 1

        action_recovery_rates: Dict[str, Optional[float]] = {}
        action_counts: Dict[str, int] = {}
        for act, stats in action_stats.items():
            action_counts[act] = stats["attempts"]
            action_recovery_rates[act] = round(stats["recoveries"] / stats["attempts"], 4)

        # Recommended action statistics
        rec_recovery_rate: Optional[float] = None
        rec_sample_size: int = 0
        if recommended_action and recommended_action in action_stats:
            rec_sample_size = action_stats[recommended_action]["attempts"]
            rec_recovery_rate = action_recovery_rates[recommended_action]

        # Counter-evidence detection logic
        counter_evidence = False
        discrepancy_reason: Optional[str] = None

        if recommended_action and rec_sample_size >= self.min_evidence_cases:
            # Check if recommended action failed consistently in similar cases
            if rec_recovery_rate is not None and rec_recovery_rate < self.counter_evidence_threshold:
                # Find best performing alternative action in neighborhood
                best_alt_act = None
                best_alt_rate = -1.0
                for act, rate in action_recovery_rates.items():
                    if act != recommended_action and rate is not None and action_counts[act] >= 2:
                        if rate > best_alt_rate:
                            best_alt_rate = rate
                            best_alt_act = act

                if best_alt_rate >= 0.50 and best_alt_act:
                    counter_evidence = True
                    discrepancy_reason = (
                        f"Historical Discrepancy: Model recommended '{recommended_action}' (recovery rate: {rec_recovery_rate:.1%} "
                        f"over {rec_sample_size} cases), but historical peer cases achieved {best_alt_rate:.1%} "
                        f"recovery rate under '{best_alt_act}' ({action_stats[best_alt_act]['recoveries']}/{action_counts[best_alt_act]})."
                    )
                elif rec_recovery_rate == 0.0 and rec_sample_size >= self.min_evidence_cases:
                    counter_evidence = True
                    discrepancy_reason = (
                        f"Strong Counter-Evidence: Recommended action '{recommended_action}' has a 0.0% recovery rate "
                        f"across {rec_sample_size} highly similar historical cases in this segment."
                    )

        result = {
            "similar_cases": similar_cases,
            "similar_case_count": count,
            "recommended_action": recommended_action,
            "recommended_action_recovery_rate": rec_recovery_rate,
            "recommended_action_sample_size": rec_sample_size,
            "action_recovery_rates": action_recovery_rates,
            "action_counts": action_counts,
            "counter_evidence": counter_evidence,
            "discrepancy_reason": discrepancy_reason,
            "execution_permitted": False,
            "advisory_note": "Evidence only - this engine does not directly execute recovery interventions."
        }

        return _to_json_safe(result)

    def save(self, file_path: Union[str, Path]) -> None:
        """Persists fitted precedent engine to disk via joblib."""
        if not self.is_fitted:
            raise RuntimeError("Cannot save unfitted Precedent Engine.")
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @classmethod
    def load(cls, file_path: Union[str, Path]) -> "WAPSIPrecedentEngine":
        """Loads a persisted Precedent Engine from disk."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"No saved Precedent Engine found at {path}")
        loaded = joblib.load(path)
        if not isinstance(loaded, cls):
            raise TypeError(f"Loaded object is not a {cls.__name__}")
        return loaded
