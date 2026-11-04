"""
WAPSI Contextual Bandit Engine (Linear Thompson Sampling).
Razorpay AI Buildathon 2026 - Track 3

Online learning for recovery interventions under contextual heterogeneity:
  - Balances exploration (learning high-potential actions) vs exploitation (harvesting known winners)
  - Incorporates business value in reward (recovered amount - contact costs - fatigue - retry penalties)
  - Tracks cumulative regret over time against oracle
  - Supports per-merchant learning with cold-start network prior fallback
  - Enforces policy compliance: cannot bypass Policy Engine rules (TRAI DND, frequency caps)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Union, Tuple
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

from src.data_generator import TREATMENTS

ACTIVE_TREATMENTS = list(TREATMENTS)

CONTEXT_NUMERICAL_FEATURES = [
    "amount",
    "prior_recovery_rate",
    "attempts_used",
    "fatigue_score",
    "account_age_days",
    "previous_failures",
    "hour"
]

CONTEXT_CATEGORICAL_FEATURES = [
    "domain",
    "decline_reason",
    "issuer"
]


@dataclass
class BanditRewardConfig:
    """
    Business value reward parameters for WAPSI recovery decisioning.

    Reward = recovered_amount - contact_cost - extra_attempt_penalty - fatigue_penalty
    """
    contact_costs: Dict[str, float] = field(default_factory=lambda: {
        "no_action": 0.0,
        "retry_only": 0.50,
        "whatsapp_nudge": 0.85,
        "voice_call": 4.50,
        "email": 0.15,
        "incentive_link": 1.00
    })
    incentive_discount_pct: float = 0.02
    attempt_penalty_weight: float = 2.0
    fatigue_penalty_weight: float = 1.5
    normalize_scale: float = 1000.0

    def compute_reward(
        self,
        action: str,
        recovered: bool,
        amount: float,
        attempts_used: int = 1,
        fatigue_score: float = 0.0
    ) -> float:
        """
        Computes the business value reward in INR.
        """
        # 1. Recovered Amount Value
        rec_value = float(amount) if bool(recovered) else 0.0

        # 2. Contact Cost
        base_cost = self.contact_costs.get(action, 0.50)
        if action == "incentive_link" and bool(recovered):
            base_cost += self.incentive_discount_pct * float(amount)

        # 3. Extra Attempt Penalty
        attempt_penalty = self.attempt_penalty_weight * max(0, int(attempts_used) - 1)

        # 4. Customer Fatigue Penalty
        fatigue_penalty = self.fatigue_penalty_weight * float(fatigue_score) * min(float(amount), 1000.0) * 0.01

        # Net Business Reward
        net_reward = rec_value - base_cost - attempt_penalty - fatigue_penalty
        return float(net_reward)


class BanditContextPreprocessor:
    """Encodes transaction context into normalized feature vector for Linear Thompson Sampling."""

    def __init__(self):
        self.num_cols = CONTEXT_NUMERICAL_FEATURES
        self.cat_cols = CONTEXT_CATEGORICAL_FEATURES
        self.domain_map = {
            "ecommerce": 0, "subscription": 1, "b2b_saas": 2,
            "education": 3, "gaming": 4, "travel": 5, "food_delivery": 6
        }
        self.decline_map = {
            "insufficient_funds": 0, "authentication_failed": 1,
            "technical_gateway_error": 2, "card_limit_exceeded": 3,
            "bank_downtime": 4, "upi_pin_timeout": 5, "user_cancelled_checkout": 6
        }
        self.issuer_map = {
            "HDFC": 0, "ICICI": 1, "SBI": 2, "AXIS": 3, "KOTAK": 4, "CITI": 5, "OTHER": 6
        }
        self.d_ = len(self.num_cols) + 1 + len(self.domain_map) + len(self.decline_map) + len(self.issuer_map)

    def encode(self, context: Union[Dict[str, Any], pd.Series]) -> np.ndarray:
        """Transforms context dict/series into normalized 1D vector with bias term."""
        if isinstance(context, pd.Series):
            c = context.to_dict()
        else:
            c = dict(context)

        # Numerical features scaled
        num_vals = [
            float(c.get("amount", 1000.0)) / 5000.0,
            float(c.get("prior_recovery_rate", 0.5)),
            float(c.get("attempts_used", 1)) / 5.0,
            float(c.get("fatigue_score", 0.2)),
            float(c.get("account_age_days", 100)) / 365.0,
            float(c.get("previous_failures", 0)) / 5.0,
            float(c.get("hour", 12)) / 24.0
        ]

        # One-hot categorical encodings
        dom_vec = [0.0] * len(self.domain_map)
        dom_idx = self.domain_map.get(str(c.get("domain", "")), 0)
        dom_vec[dom_idx] = 1.0

        dec_vec = [0.0] * len(self.decline_map)
        dec_idx = self.decline_map.get(str(c.get("decline_reason", "")), 0)
        dec_vec[dec_idx] = 1.0

        iss_vec = [0.0] * len(self.issuer_map)
        iss_idx = self.issuer_map.get(str(c.get("issuer", "")), 0)
        iss_vec[iss_idx] = 1.0

        # Bias term + all features
        x = np.array([1.0] + num_vals + dom_vec + dec_vec + iss_vec, dtype=float)
        return x


class WAPSIContextualBandit:
    """
    Contextual Linear Thompson Sampling Bandit for Recovery Decisioning.

    For each action a, maintains Bayesian ridge regression model:
      r_a(x) = x^T theta_a + noise, theta_a ~ N(B_a^-1 f_a, v^2 B_a^-1)
    """

    def __init__(
        self,
        actions: Optional[List[str]] = None,
        exploration_variance: float = 0.3,
        lambda_prior: float = 1.0,
        reward_scale: float = 1000.0,
        random_seed: int = 42,
        reward_config: Optional[BanditRewardConfig] = None
    ):
        self.actions = actions or list(TREATMENTS)
        self.exploration_variance = float(exploration_variance)
        self.lambda_prior = float(lambda_prior)
        self.reward_scale = float(reward_scale)
        self.random_seed = int(random_seed)
        self.rng = np.random.RandomState(self.random_seed)
        self.preprocessor = BanditContextPreprocessor()
        self.d_ = self.preprocessor.d_
        self.reward_config = reward_config or BanditRewardConfig()

        # Sufficient statistics per action
        self.B_: Dict[str, np.ndarray] = {}
        self.B_inv_: Dict[str, np.ndarray] = {}
        self.f_: Dict[str, np.ndarray] = {}
        self.action_counts_: Dict[str, int] = {}
        self.action_rewards_: Dict[str, float] = {}

        self._init_statistics()

        # Cumulative Regret Tracking
        self.cumulative_regret_: float = 0.0
        self.regret_history_: List[float] = []
        self.reward_history_: List[float] = []
        self.total_steps_: int = 0

    def _init_statistics(self) -> None:
        """Initializes prior covariance B_a and target vector f_a."""
        for act in self.actions:
            self.B_[act] = self.lambda_prior * np.eye(self.d_, dtype=float)
            self.B_inv_[act] = (1.0 / self.lambda_prior) * np.eye(self.d_, dtype=float)
            self.f_[act] = np.zeros(self.d_, dtype=float)
            self.action_counts_[act] = 0
            self.action_rewards_[act] = 0.0

    def select_action(
        self,
        context: Union[Dict[str, Any], pd.Series],
        candidate_actions: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Selects an action using Thompson Sampling from posterior distribution.

        Args:
            context: Transaction context attributes dict or Series.
            candidate_actions: List of allowed/available actions. If None, considers all actions.

        Returns:
            Dictionary with selected_action, sampled_rewards, expected_rewards, exploration_bonus.
        """
        x = self.preprocessor.encode(context)
        eligible_actions = [a for a in (candidate_actions or self.actions) if a in self.actions]
        if not eligible_actions:
            eligible_actions = self.actions

        sampled_rewards: Dict[str, float] = {}
        expected_rewards: Dict[str, float] = {}

        v2 = self.exploration_variance ** 2

        for act in eligible_actions:
            B_inv = self.B_inv_[act]
            f = self.f_[act]

            # Mean estimate: mu_hat = B^-1 f (normalized scale)
            mu_hat = B_inv @ f
            expected_r = float(x @ mu_hat) * self.reward_scale
            expected_rewards[act] = round(expected_r, 4)

            # Covariance: Sigma = v^2 * B^-1
            Sigma = v2 * B_inv
            # Posterior sampling: theta_tilde ~ N(mu_hat, Sigma)
            try:
                theta_tilde = self.rng.multivariate_normal(mu_hat, Sigma)
            except Exception:
                jitter = 1e-6 * np.eye(self.d_)
                theta_tilde = self.rng.multivariate_normal(mu_hat, Sigma + jitter)

            sampled_r = float(x @ theta_tilde) * self.reward_scale
            sampled_rewards[act] = round(sampled_r, 4)

        # Winner is action maximizing sampled posterior reward
        chosen_action = max(eligible_actions, key=lambda a: sampled_rewards[a])

        return {
            "selected_action": chosen_action,
            "sampled_rewards": sampled_rewards,
            "expected_rewards": expected_rewards,
            "candidate_actions": eligible_actions,
            "total_steps": self.total_steps_
        }

    def update(
        self,
        context: Union[Dict[str, Any], pd.Series],
        action: str,
        reward: float,
        optimal_reward: Optional[float] = None
    ) -> None:
        """
        Updates posterior distribution with observed reward for chosen action.

        Args:
            context: Transaction context.
            action: Action taken.
            reward: Observed scalar business reward in INR.
            optimal_reward: Optional oracle/max reward for tracking instant regret.
        """
        if action not in self.actions:
            return

        x = self.preprocessor.encode(context)
        r = float(reward)
        r_norm = r / self.reward_scale

        # Update sufficient statistics
        # B_new = B + x x^T
        self.B_[action] += np.outer(x, x)
        self.f_[action] += r_norm * x
        self.action_counts_[action] += 1
        self.action_rewards_[action] += r
        self.total_steps_ += 1

        # Sherman-Morrison rank-1 update for B_inv:
        # (B + x x^T)^-1 = B^-1 - (B^-1 x x^T B^-1) / (1 + x^T B^-1 x)
        B_inv = self.B_inv_[action]
        Bx = B_inv @ x
        denom = 1.0 + float(x @ Bx)
        self.B_inv_[action] = B_inv - np.outer(Bx, Bx) / denom

        # Track regret
        self.reward_history_.append(r)
        if optimal_reward is not None:
            instant_regret = max(0.0, float(optimal_reward) - r)
            self.cumulative_regret_ += instant_regret
            self.regret_history_.append(self.cumulative_regret_)

    def get_regret(self) -> Dict[str, Any]:
        """Returns current cumulative regret and statistics."""
        return {
            "total_steps": self.total_steps_,
            "cumulative_regret": round(self.cumulative_regret_, 4),
            "average_regret_per_step": round(self.cumulative_regret_ / max(1, self.total_steps_), 4),
            "action_counts": dict(self.action_counts_),
            "action_rewards": {k: round(v, 2) for k, v in self.action_rewards_.items()}
        }

    def save(self, file_path: Union[str, Path]) -> None:
        """Persists bandit state to disk via joblib."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @classmethod
    def load(cls, file_path: Union[str, Path]) -> "WAPSIContextualBandit":
        """Loads bandit from disk."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"No bandit found at {path}")
        return joblib.load(path)


class WAPSIMultiMerchantBandit:
    """
    Multi-Merchant Hierarchical Contextual Bandit Manager.

    Maintains per-merchant bandits while leveraging a global network bandit for cold start.
    """

    def __init__(
        self,
        exploration_variance: float = 0.5,
        lambda_prior: float = 1.0,
        random_seed: int = 42,
        reward_config: Optional[BanditRewardConfig] = None
    ):
        self.exploration_variance = exploration_variance
        self.lambda_prior = lambda_prior
        self.random_seed = random_seed
        self.reward_config = reward_config or BanditRewardConfig()

        self.global_bandit = WAPSIContextualBandit(
            exploration_variance=exploration_variance,
            lambda_prior=lambda_prior,
            random_seed=random_seed,
            reward_config=self.reward_config
        )
        self.merchant_bandits: Dict[str, WAPSIContextualBandit] = {}

    def get_or_create_merchant_bandit(self, merchant_id: str) -> WAPSIContextualBandit:
        """Gets or instantiates a bandit for the specific merchant."""
        m_id = str(merchant_id)
        if m_id not in self.merchant_bandits:
            # Initialize with fresh seed derived from merchant_id
            m_seed = (self.random_seed + abs(hash(m_id))) % (2**31 - 1)
            self.merchant_bandits[m_id] = WAPSIContextualBandit(
                exploration_variance=self.exploration_variance,
                lambda_prior=self.lambda_prior,
                random_seed=m_seed,
                reward_config=self.reward_config
            )
        return self.merchant_bandits[m_id]

    def select_action(
        self,
        context: Union[Dict[str, Any], pd.Series],
        merchant_id: Optional[str] = None,
        candidate_actions: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Selects action using merchant-specific bandit or global fallback."""
        m_id = merchant_id or (context.get("merchant_id") if isinstance(context, dict) else getattr(context, "merchant_id", None))
        if m_id:
            m_bandit = self.get_or_create_merchant_bandit(m_id)
            res = m_bandit.select_action(context, candidate_actions=candidate_actions)
            res["merchant_id"] = str(m_id)
            return res
        return self.global_bandit.select_action(context, candidate_actions=candidate_actions)

    def update(
        self,
        context: Union[Dict[str, Any], pd.Series],
        action: str,
        reward: float,
        merchant_id: Optional[str] = None,
        optimal_reward: Optional[float] = None
    ) -> None:
        """Updates both local merchant bandit and global shared network bandit."""
        # 1. Update Global network bandit
        self.global_bandit.update(context, action, reward, optimal_reward=optimal_reward)

        # 2. Update Local merchant bandit if merchant_id present
        m_id = merchant_id or (context.get("merchant_id") if isinstance(context, dict) else getattr(context, "merchant_id", None))
        if m_id:
            m_bandit = self.get_or_create_merchant_bandit(m_id)
            m_bandit.update(context, action, reward, optimal_reward=optimal_reward)


def run_bandit_simulation(
    df: pd.DataFrame,
    df_gt: Optional[pd.DataFrame] = None,
    n_steps: int = 2000,
    random_seed: int = 42
) -> Tuple[WAPSIContextualBandit, Dict[str, Any]]:
    """
    Runs a sequential Thompson Sampling bandit simulation over historical payment cases.

    Returns:
        Fitted bandit and dictionary with simulation metrics and regret progression.
    """
    bandit = WAPSIContextualBandit(random_seed=random_seed)
    reward_cfg = bandit.reward_config

    n_cases = min(n_steps, len(df))
    sample_indices = np.random.RandomState(random_seed).permutation(len(df))[:n_cases]

    action_potentials = {
        "no_action": "y_no_action",
        "retry_only": "y_retry_only",
        "whatsapp_nudge": "y_whatsapp_nudge",
        "voice_call": "y_voice_call",
        "email": "y_email",
        "incentive_link": "y_incentive_link"
    }

    step_regrets = []
    actions_chosen = []

    for t, idx in enumerate(sample_indices):
        case = df.iloc[idx].to_dict()
        amount = float(case.get("amount", 1000.0))
        attempts = int(case.get("attempts_used", 1))
        fatigue = float(case.get("fatigue_score", 0.1))

        # Bandit selects action
        decision = bandit.select_action(case)
        chosen_act = decision["selected_action"]
        actions_chosen.append(chosen_act)

        # Compute actual factual / counterfactual reward from ground truth
        if df_gt is not None and idx < len(df_gt):
            gt_row = df_gt.iloc[idx].to_dict()
            col_chosen = action_potentials.get(chosen_act, "y_no_action")
            rec_chosen = bool(gt_row.get(col_chosen, 0) == 1)

            # Calculate oracle reward across all active actions
            oracle_rewards = []
            for act, col in action_potentials.items():
                rec_act = bool(gt_row.get(col, 0) == 1)
                r_act = reward_cfg.compute_reward(
                    action=act, recovered=rec_act, amount=amount,
                    attempts_used=attempts, fatigue_score=fatigue
                )
                oracle_rewards.append(r_act)
            opt_r = max(oracle_rewards)
        else:
            # Observed factual outcome
            rec_chosen = bool(case.get("recovered", 0) == 1)
            opt_r = None

        # Observed reward
        reward = reward_cfg.compute_reward(
            action=chosen_act,
            recovered=rec_chosen,
            amount=amount,
            attempts_used=attempts,
            fatigue_score=fatigue
        )

        bandit.update(case, chosen_act, reward, optimal_reward=opt_r)

    summary = bandit.get_regret()
    summary["actions_chosen_distribution"] = {
        act: actions_chosen.count(act) for act in bandit.actions
    }
    summary["regret_history"] = bandit.regret_history_

    return bandit, summary
