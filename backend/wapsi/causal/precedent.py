"""
Counter-Evidence & Precedent Engine for Causal Decision Verification.
Uses Nearest Neighbors over normalized failure representations to retrieve historical precedent cases,
empirical action recovery rates, and counter-factual evidence.
"""

from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from wapsi.core.features import PaymentFeaturePipeline
from wapsi.core.taxonomy import RecoveryAction


class PrecedentEngine:
    """
    Retrieves nearest historical failure precedents to validate causal recommendations
    against empirical real-world past cases.
    """

    def __init__(self, n_neighbors: int = 40, random_seed: int = 42):
        self.n_neighbors = n_neighbors
        self.random_seed = random_seed
        self.feature_pipeline = PaymentFeaturePipeline()
        self.nn_model = NearestNeighbors(n_neighbors=n_neighbors, metric="euclidean")
        self.history_df: Optional[pd.DataFrame] = None
        self.is_fitted = False

    def fit(self, history_df: pd.DataFrame):
        """
        Indexes historical failure cases.
        """
        self.history_df = history_df.copy().reset_index(drop=True)
        self.feature_pipeline.fit(self.history_df)
        X_mat = self.feature_pipeline.transform(self.history_df)
        
        n_samples = len(self.history_df)
        k = min(self.n_neighbors, n_samples)
        self.nn_model = NearestNeighbors(n_neighbors=k, metric="euclidean")
        self.nn_model.fit(X_mat)
        self.is_fitted = True
        return self

    def query_precedents(
        self,
        event_dict: Dict[str, Any],
        candidate_action: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieves similar historical cases and calculates empirical action performance.
        """
        if not self.is_fitted or self.history_df is None:
            return {
                "precedent_count": 0,
                "empirical_recovery_rates": {},
                "counter_evidence_summary": "Precedent engine not initialized.",
                "nearest_neighbor_distance": 0.0
            }

        df = pd.DataFrame([event_dict])
        X_query = self.feature_pipeline.transform(df)
        distances, indices = self.nn_model.kneighbors(X_query)

        neighbor_indices = indices[0]
        neighbor_distances = distances[0]
        neighbor_cases = self.history_df.iloc[neighbor_indices]

        # Calculate empirical recovery rate per action among neighbors
        empirical_rates = {}
        action_counts = {}
        for act in [a.value for a in RecoveryAction]:
            act_sub = neighbor_cases[neighbor_cases["assigned_action"] == act]
            cnt = len(act_sub)
            action_counts[act] = cnt
            if cnt > 0:
                rec_rate = float(act_sub["recovered"].mean())
                empirical_rates[act] = round(rec_rate, 3)
            else:
                empirical_rates[act] = None

        # Build human-readable counter-evidence narrative
        best_empirical_action = max(
            [a for a, r in empirical_rates.items() if r is not None and action_counts[a] >= 2],
            key=lambda a: empirical_rates[a],
            default=None
        )

        counter_narrative = self._generate_counter_evidence(
            empirical_rates,
            action_counts,
            candidate_action,
            len(neighbor_cases)
        )

        return {
            "precedent_count": len(neighbor_cases),
            "nearest_neighbor_distance": round(float(np.mean(neighbor_distances[:5])), 4),
            "empirical_recovery_rates": empirical_rates,
            "precedent_action_distribution": action_counts,
            "best_empirical_action": best_empirical_action,
            "counter_evidence_summary": counter_narrative
        }

    def _generate_counter_evidence(
        self,
        rates: Dict[str, Optional[float]],
        counts: Dict[str, int],
        candidate: Optional[str],
        total_k: int
    ) -> str:
        valid_items = [(act, rates[act], counts[act]) for act in rates if rates[act] is not None and counts[act] >= 2]
        if not valid_items:
            return f"Retrieved {total_k} similar failure records across historical cohort."

        valid_items.sort(key=lambda x: x[1], reverse=True)
        top_act, top_rate, top_count = valid_items[0]
        
        control_rate = rates.get(RecoveryAction.NO_ACTION.value)
        ctrl_str = f" vs {round(control_rate * 100, 1)}% organic recovery" if control_rate is not None else ""

        if candidate and candidate == top_act:
            return (
                f"Historical Precedent: Across {total_k} nearest failure cases, '{candidate}' achieved the highest "
                f"empirical recovery rate of {round(top_rate * 100, 1)}% (n={top_count}){ctrl_str}."
            )
        elif candidate and rates.get(candidate) is not None:
            cand_rate = rates[candidate]
            return (
                f"Historical Precedent: In {total_k} nearest cases, '{candidate}' yielded {round(cand_rate * 100, 1)}% "
                f"success (n={counts[candidate]}), while '{top_act}' yielded {round(top_rate * 100, 1)}% (n={top_count})."
            )
        else:
            return (
                f"Historical Precedent: Across {total_k} similar failures, top observed recovery was '{top_act}' "
                f"at {round(top_rate * 100, 1)}% (n={top_count}){ctrl_str}."
            )
