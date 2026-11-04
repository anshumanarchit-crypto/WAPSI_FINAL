"""
WAPSI Multi-Action X-Learner Causal Uplift Estimator.
Razorpay AI Buildathon 2026 - Track 3

Implements the multi-action X-Learner meta-algorithm (Künzel et al., PNAS 2019:
"Metalearners for estimating heterogeneous treatment effects using machine learning").

The X-Learner is designed for heterogeneous treatment effect estimation, particularly
excelling in settings with unbalanced treatment group sizes and complex treatment effects:

Architecture:
  Stage 1: Response Models (Base Learners)
    - mu_0(x) = P(Y=1 | A=no_action, X=x) fitted on control units
    - mu_a(x) = P(Y=1 | A=a, X=x) fitted on treated units for each active action a

  Stage 2: Counterfactual Imputation & Residual Computation
    - For treated units (A=a):  D_{a, 1} = Y_a - mu_0(X_a)    [Imputed treatment effect on treated]
    - For control units (A=0):  D_{a, 0} = mu_a(X_0) - Y_0    [Imputed treatment effect on control]

  Stage 3: Second-Stage Treatment Effect Regressors
    - tau_{a, 1}(x) fitted on (X_a, D_{a, 1})
    - tau_{a, 0}(x) fitted on (X_0, D_{a, 0})

  Stage 4: Propensity Score Weighting
    - e_a(x) = P(A=a | A in {no_action, a}, X=x)
    - CATE estimate: tau_a(x) = e_a(x) * tau_{a, 0}(x) + (1 - e_a(x)) * tau_{a, 1}(x)

KEY ISOLATION RULE:
  Strictly no access to hidden synthetic potential outcomes (y_*, p_*, tau_*).
  Trained exclusively on observed factual data.
"""

from __future__ import annotations

from typing import Dict, List, Any, Optional, Union
from pathlib import Path
from datetime import datetime, timezone
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.ensemble import (
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor
)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, log_loss, mean_squared_error

from src.data_generator import TREATMENTS
from src.t_learner import (
    WAPSIFeaturePreprocessor,
    NUMERICAL_FEATURES,
    CATEGORICAL_FEATURES,
    IDENTIFIER_COLS,
    TARGET_COL,
    TREATMENT_COL
)


class WAPSIXLearner(BaseEstimator):
    """
    Multi-Action X-Learner Uplift Estimator for Payment Recovery.

    Estimates individual treatment effects (CATE) tau_a(x) across recovery interventions
    using crossover residual modeling with propensity score weighting.
    """

    def __init__(
        self,
        classifier_cls=GradientBoostingClassifier,
        regressor_cls=GradientBoostingRegressor,
        classifier_kwargs: Optional[Dict[str, Any]] = None,
        regressor_kwargs: Optional[Dict[str, Any]] = None,
        propensity_kwargs: Optional[Dict[str, Any]] = None,
        random_seed: int = 42,
        model_version: str = "1.0.0"
    ):
        self.classifier_cls = classifier_cls
        self.regressor_cls = regressor_cls
        self.random_seed = random_seed
        self.model_version = model_version

        self.classifier_kwargs = classifier_kwargs or {
            "n_estimators": 75,
            "max_depth": 4,
            "learning_rate": 0.08,
            "random_state": random_seed
        }
        self.regressor_kwargs = regressor_kwargs or {
            "n_estimators": 75,
            "max_depth": 4,
            "learning_rate": 0.08,
            "random_state": random_seed
        }
        self.propensity_kwargs = propensity_kwargs or {
            "max_iter": 500,
            "random_state": random_seed,
            "C": 1.0
        }

        self.treatments = TREATMENTS
        self.control_action = "no_action"
        self.active_treatments = [t for t in TREATMENTS if t != self.control_action]

        self.preprocessor = WAPSIFeaturePreprocessor()

        # Stage 1: First-stage outcome response models: mu_0 and mu_a
        self.mu_models_: Dict[str, Any] = {}
        # Stage 3: Second-stage effect models: tau_{a, 0} and tau_{a, 1}
        self.tau_models_: Dict[str, Dict[str, Any]] = {}
        # Stage 4: Propensity models: e_a(x)
        self.propensity_models_: Dict[str, Any] = {}

        self.is_fitted = False
        self.metadata_: Dict[str, Any] = {}

    def fit(
        self,
        df_train: pd.DataFrame,
        treatment_col: str = TREATMENT_COL,
        target_col: str = TARGET_COL,
        df_val: Optional[pd.DataFrame] = None
    ) -> "WAPSIXLearner":
        """
        Fits the multi-action X-Learner pipeline on observed training data.

        Strictly enforces data isolation (no potential outcomes allowed).
        """
        # Strict isolation check: Verify no hidden potential outcome columns
        forbidden_cols = [
            c for c in df_train.columns
            if c.startswith("y_") or c.startswith("p_") or c.startswith("tau_")
        ]
        if forbidden_cols:
            raise ValueError(
                f"Strict isolation violation: df_train contains potential outcome columns: {forbidden_cols}"
            )

        train_timestamp = datetime.now(timezone.utc).isoformat()

        # 1. Fit Preprocessor on Training Split Features
        self.preprocessor.fit(df_train)
        X_train_mat = self.preprocessor.transform(df_train)
        y_train = df_train[target_col].values.astype(float)
        t_train = df_train[treatment_col].values

        control_mask = (t_train == self.control_action)
        X_0 = X_train_mat[control_mask]
        y_0 = y_train[control_mask]

        if len(y_0) < 5:
            raise ValueError(f"Insufficient control samples: {len(y_0)} rows for {self.control_action}")

        # -------------------------------------------------------------------
        # Stage 1: Fit Response Models mu_0(x) and mu_a(x)
        # -------------------------------------------------------------------
        # Fit mu_0 on control units
        mu_0_model = self._fit_binary_classifier(X_0, y_0)
        self.mu_models_[self.control_action] = mu_0_model

        # Fit mu_a on treated units for each active action
        for action in self.active_treatments:
            mask_a = (t_train == action)
            X_a = X_train_mat[mask_a]
            y_a = y_train[mask_a]

            if len(y_a) < 5:
                # Fallback to all data if action is extremely sparse
                mu_a_model = self._fit_binary_classifier(X_train_mat, y_train)
            else:
                mu_a_model = self._fit_binary_classifier(X_a, y_a)

            self.mu_models_[action] = mu_a_model

        # -------------------------------------------------------------------
        # Stage 2 & 3: Impute Residuals and Fit Effect Regressors tau_{a, 0} & tau_{a, 1}
        # -------------------------------------------------------------------
        for action in self.active_treatments:
            mask_a = (t_train == action)
            X_a = X_train_mat[mask_a]
            y_a = y_train[mask_a]

            if len(y_a) < 5:
                X_a = X_train_mat
                y_a = y_train

            # Imputed counterfactuals
            # D_{a, 1} = Y_a - mu_0(X_a) for treated units
            y_0_hat_on_a = mu_0_model.predict_proba(X_a)[:, 1]
            D_a_1 = y_a - y_0_hat_on_a

            # D_{a, 0} = mu_a(X_0) - Y_0 for control units
            mu_a_model = self.mu_models_[action]
            y_a_hat_on_0 = mu_a_model.predict_proba(X_0)[:, 1]
            D_a_0 = y_a_hat_on_0 - y_0

            # Fit second-stage effect regressors
            tau_1_model = self._fit_regressor(X_a, D_a_1)
            tau_0_model = self._fit_regressor(X_0, D_a_0)

            self.tau_models_[action] = {
                "tau_1": tau_1_model,
                "tau_0": tau_0_model
            }

            # ---------------------------------------------------------------
            # Stage 4: Fit Propensity Model e_a(x) = P(A=a | A in {control, a}, X)
            # ---------------------------------------------------------------
            pair_mask = (t_train == self.control_action) | (t_train == action)
            X_pair = X_train_mat[pair_mask]
            w_pair = (t_train[pair_mask] == action).astype(int)

            prop_model = self._fit_propensity_model(X_pair, w_pair)
            self.propensity_models_[action] = prop_model

        # -------------------------------------------------------------------
        # Validation Metrics (Optional)
        # -------------------------------------------------------------------
        val_metrics = {}
        if df_val is not None and len(df_val) > 0:
            val_metrics = self._compute_validation_metrics(df_val, treatment_col, target_col)

        self.is_fitted = True

        # Store metadata
        self.metadata_ = {
            "model_type": "MultiActionXLearner",
            "model_version": self.model_version,
            "training_timestamp": train_timestamp,
            "training_rows": len(df_train),
            "random_seed": self.random_seed,
            "features_used": self.preprocessor.feature_names_,
            "treatments": self.treatments,
            "control_action": self.control_action,
            "active_treatments": self.active_treatments,
            "validation_metrics": val_metrics
        }

        return self

    def _fit_binary_classifier(self, X: np.ndarray, y: np.ndarray) -> Any:
        """Fits a binary classifier with handling for single-class subsets."""
        y_int = y.astype(int)
        if len(np.unique(y_int)) < 2:
            anchor_y = 1 if y_int[0] == 0 else 0
            X = np.vstack([X, X[:1]])
            y_int = np.append(y_int, anchor_y)

        model = self.classifier_cls(**self.classifier_kwargs)
        model.fit(X, y_int)
        return model

    def _fit_regressor(self, X: np.ndarray, y: np.ndarray) -> Any:
        """Fits a continuous regressor for second-stage CATE estimation."""
        model = self.regressor_cls(**self.regressor_kwargs)
        model.fit(X, y)
        return model

    def _fit_propensity_model(self, X: np.ndarray, w: np.ndarray) -> Any:
        """Fits propensity score model e_a(X) = P(W=1|X)."""
        if len(np.unique(w)) < 2:
            anchor_w = 1 if w[0] == 0 else 0
            X = np.vstack([X, X[:1]])
            w = np.append(w, anchor_w)

        prop_model = LogisticRegression(**self.propensity_kwargs)
        prop_model.fit(X, w)
        return prop_model

    def _compute_validation_metrics(
        self,
        df_val: pd.DataFrame,
        treatment_col: str,
        target_col: str
    ) -> Dict[str, Any]:
        """Computes stage 1 AUC and log loss on validation split."""
        val_metrics: Dict[str, Any] = {}
        X_val_mat = self.preprocessor.transform(df_val)
        y_val = df_val[target_col].values.astype(int)
        t_val = df_val[treatment_col].values

        for action in self.treatments:
            val_mask = (t_val == action)
            if np.sum(val_mask) >= 10 and len(np.unique(y_val[val_mask])) >= 2:
                p_val = self.mu_models_[action].predict_proba(X_val_mat[val_mask])[:, 1]
                auc = float(roc_auc_score(y_val[val_mask], p_val))
                ll = float(log_loss(y_val[val_mask], p_val))
                val_metrics[action] = {
                    "val_auc": round(auc, 4),
                    "val_log_loss": round(ll, 4)
                }
        return val_metrics

    def predict_uplift(
        self,
        X: Union[pd.DataFrame, Dict[str, Any], List[Dict[str, Any]]]
    ) -> Dict[str, Union[np.ndarray, float]]:
        """
        Predicts individual treatment effect uplift for each intervention vs no_action:
          tau_a(x) = e_a(x) * tau_{a, 0}(x) + (1 - e_a(x)) * tau_{a, 1}(x)

        Args:
            X: Input DataFrame, dict (single case), or list of dicts.

        Returns:
            Dict mapping active treatment name -> estimated CATE uplift (float or 1D np.ndarray).
        """
        if not self.is_fitted:
            raise RuntimeError("WAPSIXLearner is not fitted yet.")

        is_single = isinstance(X, dict) or (isinstance(X, pd.DataFrame) and len(X) == 1)
        X_mat = self.preprocessor.transform(X)

        uplifts: Dict[str, Any] = {}

        for action in self.active_treatments:
            # 1. Propensity score e_a(x) = P(A=a | A in {control, a}, X)
            prop_model = self.propensity_models_[action]
            e_a = prop_model.predict_proba(X_mat)[:, 1]
            # Clip propensity scores to prevent extreme weighting artifacts
            e_a = np.clip(e_a, 0.01, 0.99)

            # 2. Predict second-stage effect models
            tau_0_model = self.tau_models_[action]["tau_0"]
            tau_1_model = self.tau_models_[action]["tau_1"]

            tau_0_hat = tau_0_model.predict(X_mat)
            tau_1_hat = tau_1_model.predict(X_mat)

            # 3. Propensity-weighted crossover combination (Künzel et al. 2019)
            cate = e_a * tau_0_hat + (1.0 - e_a) * tau_1_hat

            if is_single:
                uplifts[action] = round(float(cate[0]), 4)
            else:
                uplifts[action] = np.round(cate, 4)

        return uplifts

    def predict_action_outcomes(
        self,
        X: Union[pd.DataFrame, Dict[str, Any], List[Dict[str, Any]]]
    ) -> Dict[str, Union[np.ndarray, float]]:
        """
        Predicts expected recovery probability for all actions:
          P(Y=1 | no_action, X) = mu_0(X)
          P(Y=1 | a, X) = clip(mu_0(X) + tau_a(X), 0.001, 0.999)

        Guarantees consistency: P(Y=1 | a, X) - P(Y=1 | no_action, X) == tau_a(X) (up to clipping).
        """
        if not self.is_fitted:
            raise RuntimeError("WAPSIXLearner is not fitted yet.")

        is_single = isinstance(X, dict) or (isinstance(X, pd.DataFrame) and len(X) == 1)
        X_mat = self.preprocessor.transform(X)

        # Baseline probability under control
        p0 = self.mu_models_[self.control_action].predict_proba(X_mat)[:, 1]
        p0 = np.clip(p0, 0.001, 0.999)

        # Uplifts for active actions
        uplifts = self.predict_uplift(X)

        probs: Dict[str, Any] = {}
        if is_single:
            probs[self.control_action] = round(float(p0[0]), 4)
            for action in self.active_treatments:
                p_act = np.clip(p0[0] + uplifts[action], 0.001, 0.999)
                probs[action] = round(float(p_act), 4)
        else:
            probs[self.control_action] = np.round(p0, 4)
            for action in self.active_treatments:
                p_act = np.clip(p0 + uplifts[action], 0.001, 0.999)
                probs[action] = np.round(p_act, 4)

        return probs

    def get_metadata(self) -> Dict[str, Any]:
        """Returns training metadata and feature schema."""
        return dict(self.metadata_)

    def save(self, filepath: Union[str, Path]):
        """Persists the fitted X-Learner model bundle to disk using joblib."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @classmethod
    def load(cls, filepath: Union[str, Path]) -> "WAPSIXLearner":
        """Loads a persisted WAPSIXLearner from disk."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Model file not found at: {path}")
        model = joblib.load(path)
        if not isinstance(model, cls):
            raise TypeError(f"Loaded object is not a {cls.__name__}, got {type(model)}")
        return model
