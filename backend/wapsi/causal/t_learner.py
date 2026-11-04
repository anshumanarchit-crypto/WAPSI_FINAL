"""
Multi-Action T-Learner (Two-Learner / Multi-Treatment Meta-Learner).
Estimates Conditional Average Treatment Effect (CATE) tau_a(x) = E[Y | X=x, A=a] - E[Y | X=x, A=0]
by training separate response estimators for control and each treatment arm.
"""

from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from wapsi.core.taxonomy import RecoveryAction
from wapsi.core.features import PaymentFeaturePipeline


class MultiActionTLearner:
    """
    Multi-Treatment T-Learner.
    Trains dedicated base classifiers mu_a(x) for each action a in Action Space.
    """

    def __init__(
        self,
        base_estimator_cls=GradientBoostingClassifier,
        estimator_kwargs: Optional[Dict[str, Any]] = None,
        random_seed: int = 42
    ):
        self.base_estimator_cls = base_estimator_cls
        self.estimator_kwargs = estimator_kwargs or {
            "n_estimators": 80,
            "max_depth": 4,
            "learning_rate": 0.08,
            "random_state": random_seed
        }
        self.random_seed = random_seed
        self.models_: Dict[str, Any] = {}
        self.feature_pipeline = PaymentFeaturePipeline()
        self.actions_ = [a.value for a in RecoveryAction]
        self.control_action_ = RecoveryAction.NO_ACTION.value
        self.is_fitted = False

    def fit(self, df: pd.DataFrame, action_col: str = "assigned_action", target_col: str = "recovered"):
        """
        Fits separate base estimators mu_a(x) for each action a.
        """
        # Fit feature pipeline on full dataset
        self.feature_pipeline.fit(df)
        X_mat = self.feature_pipeline.transform(df)
        
        actions_present = df[action_col].unique()
        
        for act in self.actions_:
            mask = (df[action_col] == act).values
            if not np.any(mask) or np.sum(mask) < 10:
                # If an action has too few records in observational sample, fit on all with lower weight
                # or fallback to global model
                y_sub = df[target_col].values
                X_sub = X_mat
            else:
                X_sub = X_mat[mask]
                y_sub = df[target_col].values[mask]

            # Check if single class in subgroup
            if len(np.unique(y_sub)) < 2:
                # Add synthetic anchor point to avoid single class failure
                anchor_y = 1 if y_sub[0] == 0 else 0
                X_sub = np.vstack([X_sub, X_sub[:1]])
                y_sub = np.append(y_sub, anchor_y)

            model = self.base_estimator_cls(**self.estimator_kwargs)
            model.fit(X_sub, y_sub)
            self.models_[act] = model

        self.is_fitted = True
        return self

    def predict_probabilities(self, X: pd.DataFrame) -> Dict[str, np.ndarray]:
        """
        Predicts absolute recovery probabilities mu_a(x) for all actions.
        Returns: Dict mapping action_name -> array of shape (n_samples,) with P(Y(a)=1 | x)
        """
        if not self.is_fitted:
            raise RuntimeError("TLearner is not fitted yet.")
        
        X_mat = self.feature_pipeline.transform(X)
        probs = {}
        for act, model in self.models_.items():
            if hasattr(model, "predict_proba"):
                # probability of class 1 (recovered)
                p = model.predict_proba(X_mat)[:, 1]
            else:
                p = model.predict(X_mat)
            probs[act] = np.clip(p, 0.001, 0.999)
        return probs

    def predict_uplift(self, X: pd.DataFrame) -> Dict[str, np.ndarray]:
        """
        Predicts incremental treatment effect (ITE / Uplift) for each action relative to control (NO_ACTION):
        tau_a(x) = mu_a(x) - mu_0(x)
        
        Returns: Dict mapping action_name -> array of uplift scores
        """
        probs = self.predict_probabilities(X)
        control_prob = probs[self.control_action_]
        
        uplifts = {}
        for act, p in probs.items():
            if act == self.control_action_:
                uplifts[act] = np.zeros_like(p)
            else:
                uplifts[act] = p - control_prob
        return uplifts

    def get_feature_names(self) -> List[str]:
        return self.feature_pipeline.get_feature_names()
