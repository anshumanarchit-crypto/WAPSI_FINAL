"""
Multi-Action X-Learner (Crossover Meta-Learner for Unbalanced / Heterogeneous Uplift).
Implements the 5-stage X-Learner algorithm (Künzel et al., 2019) extended to multi-treatment action spaces
with propensity-score weighted crossover residual modeling.
"""

from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from wapsi.core.taxonomy import RecoveryAction
from wapsi.core.features import PaymentFeaturePipeline


class MultiActionXLearner:
    """
    Multi-Action X-Learner.
    Provides superior sample-efficiency and robustness under observational selection bias.
    """

    def __init__(
        self,
        classifier_kwargs: Optional[Dict[str, Any]] = None,
        regressor_kwargs: Optional[Dict[str, Any]] = None,
        random_seed: int = 42
    ):
        self.random_seed = random_seed
        self.classifier_kwargs = classifier_kwargs or {
            "n_estimators": 70,
            "max_depth": 3,
            "learning_rate": 0.08,
            "random_state": random_seed
        }
        self.regressor_kwargs = regressor_kwargs or {
            "n_estimators": 70,
            "max_depth": 3,
            "learning_rate": 0.08,
            "random_state": random_seed
        }
        self.feature_pipeline = PaymentFeaturePipeline()
        self.actions_ = [a.value for a in RecoveryAction]
        self.control_action_ = RecoveryAction.NO_ACTION.value
        
        # Stage 1 response models: mu_0 and mu_a
        self.mu_models_: Dict[str, Any] = {}
        # Stage 3 effect models: tau_0_a and tau_1_a
        self.tau_models_: Dict[str, Dict[str, Any]] = {}
        # Propensity models e_a(x)
        self.propensity_models_: Dict[str, Any] = {}
        self.is_fitted = False

    def fit(self, df: pd.DataFrame, action_col: str = "assigned_action", target_col: str = "recovered"):
        """
        Fits multi-treatment X-Learner stages across all actions.
        """
        self.feature_pipeline.fit(df)
        X_mat = self.feature_pipeline.transform(df)
        y = df[target_col].values.astype(float)
        actions = df[action_col].values

        # Stage 1: Fit base response model for control
        ctrl_mask = (actions == self.control_action_)
        if not np.any(ctrl_mask) or np.sum(ctrl_mask) < 5:
            # Fallback if no control samples
            ctrl_mask = np.ones(len(df), dtype=bool)

        X_ctrl = X_mat[ctrl_mask]
        y_ctrl = y[ctrl_mask]
        
        mu_0 = GradientBoostingClassifier(**self.classifier_kwargs)
        if len(np.unique(y_ctrl)) < 2:
            y_ctrl = np.append(y_ctrl, 1 if y_ctrl[0] == 0 else 0)
            X_ctrl = np.vstack([X_ctrl, X_ctrl[:1]])
        mu_0.fit(X_ctrl, y_ctrl)
        self.mu_models_[self.control_action_] = mu_0

        # Stage 1 & 2 & 3 for each treatment arm
        for act in self.actions_:
            if act == self.control_action_:
                continue

            treat_mask = (actions == act)
            if not np.any(treat_mask) or np.sum(treat_mask) < 5:
                # Fallback to full set
                treat_mask = np.ones(len(df), dtype=bool)

            X_treat = X_mat[treat_mask]
            y_treat = y[treat_mask]

            # Fit mu_a
            mu_a = GradientBoostingClassifier(**self.classifier_kwargs)
            if len(np.unique(y_treat)) < 2:
                y_treat = np.append(y_treat, 1 if y_treat[0] == 0 else 0)
                X_treat = np.vstack([X_treat, X_treat[:1]])
            mu_a.fit(X_treat, y_treat)
            self.mu_models_[act] = mu_a

            # Stage 2: Calculate imputed counterfactual treatment effects
            # For treatment group: D1 = Y1 - mu_0(X1)
            pred_mu_0_on_treat = mu_0.predict_proba(X_treat)[:, 1]
            D1 = y_treat - pred_mu_0_on_treat

            # For control group: D0 = mu_a(X0) - Y0
            pred_mu_a_on_ctrl = mu_a.predict_proba(X_ctrl)[:, 1]
            D0 = pred_mu_a_on_ctrl - y_ctrl

            # Stage 3: Fit effect models
            tau_1 = GradientBoostingRegressor(**self.regressor_kwargs)
            tau_1.fit(X_treat, D1)

            tau_0 = GradientBoostingRegressor(**self.regressor_kwargs)
            tau_0.fit(X_ctrl, D0)

            self.tau_models_[act] = {"tau_0": tau_0, "tau_1": tau_1}

            # Stage 4: Propensity model e_a(x) = P(A=a | X=x)
            prop_y = treat_mask.astype(int)
            prop_model = LogisticRegression(max_iter=500, random_state=self.random_seed)
            prop_model.fit(X_mat, prop_y)
            self.propensity_models_[act] = prop_model

        self.is_fitted = True
        return self

    def predict_uplift(self, X: pd.DataFrame) -> Dict[str, np.ndarray]:
        """
        Predicts propensity-weighted crossover uplift tau_a(x):
        tau_a(x) = e_a(x) * tau_0(x) + (1 - e_a(x)) * tau_1(x)
        """
        if not self.is_fitted:
            raise RuntimeError("XLearner is not fitted yet.")

        X_mat = self.feature_pipeline.transform(X)
        uplifts = {}
        uplifts[self.control_action_] = np.zeros(len(X_mat))

        for act in self.actions_:
            if act == self.control_action_:
                continue

            tau_0_model = self.tau_models_[act]["tau_0"]
            tau_1_model = self.tau_models_[act]["tau_1"]
            prop_model = self.propensity_models_[act]

            tau_0_pred = tau_0_model.predict(X_mat)
            tau_1_pred = tau_1_model.predict(X_mat)
            e_a = prop_model.predict_proba(X_mat)[:, 1]
            e_a = np.clip(e_a, 0.05, 0.95)

            # Crossover weighted average
            tau_x = e_a * tau_0_pred + (1.0 - e_a) * tau_1_pred
            uplifts[act] = tau_x

        return uplifts

    def predict_probabilities(self, X: pd.DataFrame) -> Dict[str, np.ndarray]:
        """
        Calculates absolute probabilities: mu_0(x) for control, and mu_0(x) + tau_a(x) for treatments.
        """
        if not self.is_fitted:
            raise RuntimeError("XLearner is not fitted yet.")

        X_mat = self.feature_pipeline.transform(X)
        mu_0_model = self.mu_models_[self.control_action_]
        p0 = mu_0_model.predict_proba(X_mat)[:, 1]

        uplifts = self.predict_uplift(X)
        probs = {self.control_action_: np.clip(p0, 0.01, 0.99)}

        for act in self.actions_:
            if act == self.control_action_:
                continue
            probs[act] = np.clip(p0 + uplifts[act], 0.01, 0.99)

        return probs

    def get_feature_names(self) -> List[str]:
        return self.feature_pipeline.get_feature_names()
