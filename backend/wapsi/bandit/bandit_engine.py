"""
Contextual Bandit Engine (LinUCB & Thompson Sampling with Safe Exploration).
Enables continuous online learning and recovery policy adaptation from real-world payment outcomes.
"""

from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd
from wapsi.core.taxonomy import RecoveryAction
from wapsi.core.features import PaymentFeaturePipeline


class ContextualBanditEngine:
    """
    LinUCB Contextual Bandit with safety constraints and epsilon-controlled exploration.
    """

    def __init__(
        self,
        alpha: float = 0.8,
        exploration_prob: float = 0.05,
        dimension: int = 25,
        random_seed: int = 42
    ):
        self.alpha = alpha
        self.exploration_prob = exploration_prob
        self.d = dimension
        self.random_seed = random_seed
        self.rng = np.random.default_rng(random_seed)
        
        self.actions = [a.value for a in RecoveryAction]
        self.feature_pipeline = PaymentFeaturePipeline()
        
        # LinUCB state per arm: A_a (d x d matrix), b_a (d x 1 vector)
        self.A_matrices: Dict[str, np.ndarray] = {}
        self.b_vectors: Dict[str, np.ndarray] = {}
        self.is_initialized = False

    def initialize(self, fitted_pipeline: PaymentFeaturePipeline):
        """
        Initializes matrices for each arm matching the feature pipeline dimensionality.
        """
        self.feature_pipeline = fitted_pipeline
        self.d = len(fitted_pipeline.get_feature_names())
        
        for act in self.actions:
            self.A_matrices[act] = np.identity(self.d)
            self.b_vectors[act] = np.zeros(self.d)

        self.is_initialized = True
        return self

    def select_action(
        self,
        event_dict: Dict[str, Any],
        causal_recommended_action: str
    ) -> Dict[str, Any]:
        """
        Selects an action using LinUCB exploration-exploitation balancing.
        Falls back to causal recommendation unless exploration condition triggers.
        """
        if not self.is_initialized:
            return {
                "bandit_action": causal_recommended_action,
                "is_exploration": False,
                "ucb_scores": {},
                "assignment_propensity": 1.0,
                "feature_vector": None,
            }

        df = pd.DataFrame([event_dict])
        x = self.feature_pipeline.transform(df)[0]  # shape (d,)

        # Compute UCB score for each arm
        ucb_scores = {}
        for act in self.actions:
            A_inv = np.linalg.inv(self.A_matrices[act])
            theta = A_inv @ self.b_vectors[act]
            mean_reward = np.dot(x, theta)
            confidence_bound = self.alpha * np.sqrt(x @ A_inv @ x)
            ucb_scores[act] = float(mean_reward + confidence_bound)

        best_bandit_arm = max(ucb_scores, key=ucb_scores.get)
        # Decide whether to explore or exploit
        if self.rng.uniform() < self.exploration_prob:
            # Safe exploration: Choose highest UCB arm
            is_exploration = (best_bandit_arm != causal_recommended_action)
            chosen_action = best_bandit_arm if is_exploration else causal_recommended_action
        else:
            # Exploit causal ML recommendation
            chosen_action = causal_recommended_action
            is_exploration = False

        if chosen_action == causal_recommended_action:
            if best_bandit_arm == causal_recommended_action:
                propensity = 1.0
            else:
                propensity = round(1.0 - self.exploration_prob, 4)
        else:
            propensity = round(self.exploration_prob, 4)

        return {
            "bandit_action": chosen_action,
            "is_exploration": is_exploration,
            "ucb_scores": {k: round(v, 4) for k, v in ucb_scores.items()},
            "assignment_propensity": propensity,
            "feature_vector": x.tolist(),
        }

    def update(self, event_dict: Dict[str, Any], action: str, reward: float):
        """
        Updates LinUCB online state when a payment outcome is observed.
        Reward is binary recovery (1/0) or net revenue contribution.
        """
        if not self.is_initialized or action not in self.A_matrices:
            return

        df = pd.DataFrame([event_dict])
        x = self.feature_pipeline.transform(df)[0]

        # Update A_a = A_a + x * x^T
        self.A_matrices[action] += np.outer(x, x)
        # Update b_a = b_a + r * x
        self.b_vectors[action] += reward * x
