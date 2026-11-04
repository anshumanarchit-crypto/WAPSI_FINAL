"""
Causal & Uplift Evaluation Suite.
Calculates Qini curves, AUUC (Area Under Uplift Curve), cumulative incremental gain,
uplift deciles, and ground-truth ITE policy regret metrics.
"""

from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import pandas as pd
from scipy.stats import spearmanr


class UpliftEvaluator:
    """
    Evaluates causal uplift models both in observational/RCT test splits
    and against ground truth potential outcomes when available.
    """

    @classmethod
    def compute_qini_curve(
        cls,
        y_true: np.ndarray,
        treatment: np.ndarray,
        uplift_score: np.ndarray,
        n_bins: int = 100
    ) -> Dict[str, Any]:
        """
        Computes the Qini curve and Qini coefficient for binary treatment vs control.
        
        Args:
            y_true: Binary array (1 = recovered, 0 = failed)
            treatment: Binary array (1 = treated with action a, 0 = control/no action)
            uplift_score: Predicted continuous uplift scores tau_a(x)
            n_bins: Number of points on cumulative curve
            
        Returns:
            Dict containing population_fractions, qini_values, random_qini, and qini_score (normalized AUUC)
        """
        df = pd.DataFrame({
            "y": y_true,
            "t": treatment,
            "score": uplift_score
        }).sort_values("score", ascending=False).reset_index(drop=True)

        n_total = len(df)
        if n_total == 0:
            return {"population_fraction": [], "qini": [], "random_baseline": [], "qini_score": 0.0}

        # Cumulative counts
        df["cum_treat_rec"] = (df["y"] * df["t"]).cumsum()
        df["cum_ctrl_rec"] = (df["y"] * (1 - df["t"])).cumsum()
        df["cum_treat"] = df["t"].cumsum()
        df["cum_ctrl"] = (1 - df["t"]).cumsum()

        # Handle zero division
        ratio = df["cum_treat"] / np.maximum(df["cum_ctrl"], 1)
        qini_points = df["cum_treat_rec"] - df["cum_ctrl_rec"] * ratio

        # Downsample to n_bins points
        step = max(1, n_total // n_bins)
        indices = list(range(0, n_total, step))
        if indices[-1] != n_total - 1:
            indices.append(n_total - 1)

        pop_fractions = [float(i + 1) / n_total for i in indices]
        qini_curve = [float(qini_points.iloc[i]) for i in indices]
        
        total_treat_rec = float(df["cum_treat_rec"].iloc[-1])
        total_ctrl_rec = float(df["cum_ctrl_rec"].iloc[-1])
        total_treat = max(1, float(df["cum_treat"].iloc[-1]))
        total_ctrl = max(1, float(df["cum_ctrl"].iloc[-1]))
        
        max_qini = total_treat_rec - total_ctrl_rec * (total_treat / total_ctrl)
        random_curve = [frac * max_qini for frac in pop_fractions]

        # Calculate Area Under Curve
        trap_fn = getattr(np, "trapezoid", getattr(np, "trapz", None))
        area_qini = trap_fn(qini_curve, pop_fractions)
        area_random = trap_fn(random_curve, pop_fractions)
        qini_score = float(area_qini - area_random)

        return {
            "population_fraction": [round(f, 4) for f in pop_fractions],
            "qini": [round(q, 4) for q in qini_curve],
            "random_baseline": [round(r, 4) for r in random_curve],
            "qini_score": round(qini_score, 4),
            "normalized_qini": round(qini_score / (abs(area_random) + 1e-6), 4)
        }

    @classmethod
    def compute_uplift_deciles(
        cls,
        y_true: np.ndarray,
        treatment: np.ndarray,
        uplift_score: np.ndarray,
        amount_in_inr: Optional[np.ndarray] = None,
        n_deciles: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Groups users into deciles sorted by predicted uplift and calculates empirical uplift in each decile.
        """
        if amount_in_inr is None:
            amount_in_inr = np.ones(len(y_true)) * 1000.0

        df = pd.DataFrame({
            "y": y_true,
            "t": treatment,
            "score": uplift_score,
            "amount": amount_in_inr
        }).sort_values("score", ascending=False).reset_index(drop=True)

        df["decile"] = pd.qcut(df.index, q=n_deciles, labels=False) + 1
        deciles_data = []

        for d in range(1, n_deciles + 1):
            sub = df[df["decile"] == d]
            treat_sub = sub[sub["t"] == 1]
            ctrl_sub = sub[sub["t"] == 0]

            p_treat = treat_sub["y"].mean() if len(treat_sub) > 0 else 0.0
            p_ctrl = ctrl_sub["y"].mean() if len(ctrl_sub) > 0 else 0.0
            empirical_uplift = p_treat - p_ctrl
            mean_pred_uplift = sub["score"].mean()
            avg_amount = sub["amount"].mean()

            deciles_data.append({
                "decile": int(d),
                "sample_count": int(len(sub)),
                "treatment_count": int(len(treat_sub)),
                "control_count": int(len(ctrl_sub)),
                "predicted_uplift": round(float(mean_pred_uplift), 4),
                "treatment_recovery_rate": round(float(p_treat), 4),
                "control_recovery_rate": round(float(p_ctrl), 4),
                "empirical_uplift": round(float(empirical_uplift), 4),
                "estimated_net_recovery_value_inr": round(float(empirical_uplift * len(sub) * avg_amount), 2)
            })

        return deciles_data

    @classmethod
    def evaluate_ground_truth(
        cls,
        predicted_uplifts: Dict[str, np.ndarray],
        ground_truth_tau: np.ndarray,
        action_names: List[str]
    ) -> Dict[str, Any]:
        """
        Evaluates predicted uplift against exact ground truth potential outcome differences.
        """
        metrics = {}
        for idx, act in enumerate(action_names):
            if act not in predicted_uplifts or idx == 0:
                continue

            pred = predicted_uplifts[act]
            true_tau = ground_truth_tau[:, idx]

            mse = float(np.mean((pred - true_tau) ** 2))
            mae = float(np.mean(np.abs(pred - true_tau)))
            corr, _ = spearmanr(pred, true_tau)

            metrics[act] = {
                "action": act,
                "ite_mse": round(mse, 5),
                "ite_mae": round(mae, 5),
                "spearman_rank_correlation": round(float(corr) if not np.isnan(corr) else 0.0, 4)
            }

        # Policy Regret vs Oracle Policy
        # Oracle policy selects argmax true_tau
        oracle_action = np.argmax(ground_truth_tau, axis=1)
        
        # Learned policy selects argmax predicted utility / uplift
        pred_matrix = np.column_stack([predicted_uplifts[a] for a in action_names])
        learned_action = np.argmax(pred_matrix, axis=1)

        oracle_tau = ground_truth_tau[np.arange(len(ground_truth_tau)), oracle_action]
        learned_tau = ground_truth_tau[np.arange(len(ground_truth_tau)), learned_action]

        policy_regret = float(np.mean(oracle_tau - learned_tau))
        mean_learned_uplift = float(np.mean(learned_tau))

        metrics["policy_level"] = {
            "policy_regret": round(policy_regret, 4),
            "mean_achieved_uplift": round(mean_learned_uplift, 4),
            "oracle_optimal_match_rate": round(float(np.mean(oracle_action == learned_action)), 4)
        }

        return metrics
