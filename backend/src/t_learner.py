"""
WAPSI T-Learner Baseline Causal Uplift Estimator.
Razorpay AI Buildathon 2026 - Track 3

Implements the multi-action T-Learner meta-algorithm. Fits separate response models
mu_a(x) = P(Y=1 | A=a, X=x) for control (no_action) and each active treatment arm,
and computes individual incremental treatment effects (CATE):
tau_a(x) = mu_a(x) - mu_0(x).
"""

from typing import Dict, List, Any, Optional, Union
from pathlib import Path
from datetime import datetime, timezone
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.ensemble import GradientBoostingClassifier, HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.metrics import roc_auc_score, log_loss

from src.data_generator import TREATMENTS


NUMERICAL_FEATURES: List[str] = [
    "amount",
    "attempts_used",
    "account_age_days",
    "previous_failures",
    "previous_recoveries",
    "prior_recovery_rate",
    "day_of_week",
    "hour",
    "fatigue_score",
]

CATEGORICAL_FEATURES: List[str] = [
    "domain",
    "decline_reason",
    "issuer",
    "bin_bucket",
]

IDENTIFIER_COLS: List[str] = ["case_id", "merchant_id", "customer_id"]
TARGET_COL: str = "recovered"
TREATMENT_COL: str = "treatment"


class WAPSIFeaturePreprocessor:
    """
    Standard tabular preprocessor with consistent one-hot encoding, scaling,
    and column tracking for tabular gradient boosting models.
    """

    def __init__(self):
        self.num_cols = NUMERICAL_FEATURES
        self.cat_cols = CATEGORICAL_FEATURES
        self.preprocessor = ColumnTransformer(
            transformers=[
                ("num", StandardScaler(), self.num_cols),
                ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), self.cat_cols),
            ],
            remainder="drop"
        )
        self.feature_names_: List[str] = []
        self.is_fitted = False

    def fit(self, df: pd.DataFrame):
        clean_df = self._clean_input(df)
        self.preprocessor.fit(clean_df)
        
        # Build human-readable feature names
        cat_encoder = self.preprocessor.named_transformers_["cat"]
        cat_names = list(cat_encoder.get_feature_names_out(self.cat_cols))
        self.feature_names_ = list(self.num_cols) + cat_names
        self.is_fitted = True
        return self

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("Feature preprocessor must be fitted before transforming.")
        clean_df = self._clean_input(df)
        return self.preprocessor.transform(clean_df)

    def _clean_input(self, X: Union[pd.DataFrame, Dict[str, Any], List[Dict[str, Any]]]) -> pd.DataFrame:
        if isinstance(X, dict):
            df = pd.DataFrame([X])
        elif isinstance(X, list):
            df = pd.DataFrame(X)
        elif isinstance(X, pd.DataFrame):
            df = X.copy()
        else:
            raise ValueError(f"Unsupported input type for preprocessor: {type(X)}")

        # Ensure all numerical columns exist
        for col in self.num_cols:
            if col not in df.columns:
                df[col] = 0.0
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

        # Ensure all categorical columns exist
        for col in self.cat_cols:
            if col not in df.columns:
                df[col] = "UNKNOWN"
            else:
                df[col] = df[col].astype(str).fillna("UNKNOWN")

        return df


class WAPSIUpliftModel(BaseEstimator):
    """
    Multi-Action T-Learner Uplift Estimator for Payment Recovery.
    Estimates action-specific recovery probabilities and counterfactual treatment uplift vs no_action.
    """

    def __init__(
        self,
        base_estimator_cls=GradientBoostingClassifier,
        estimator_kwargs: Optional[Dict[str, Any]] = None,
        random_seed: int = 42,
        model_version: str = "1.0.0"
    ):
        self.base_estimator_cls = base_estimator_cls
        self.estimator_kwargs = estimator_kwargs or {
            "n_estimators": 75,
            "max_depth": 4,
            "learning_rate": 0.08,
            "random_state": random_seed
        }
        self.random_seed = random_seed
        self.model_version = model_version
        
        self.treatments = TREATMENTS
        self.control_action = "no_action"
        self.active_treatments = [t for t in TREATMENTS if t != self.control_action]
        
        self.preprocessor = WAPSIFeaturePreprocessor()
        self.models_: Dict[str, Any] = {}
        self.is_fitted = False
        self.metadata_: Dict[str, Any] = {}

    def fit(
        self,
        df_train: pd.DataFrame,
        treatment_col: str = TREATMENT_COL,
        target_col: str = TARGET_COL,
        df_val: Optional[pd.DataFrame] = None
    ) -> "WAPSIUpliftModel":
        """
        Fits multi-action T-Learner models on training dataset.
        Guarantees strictly no access to hidden potential outcomes.
        """
        # Strict isolation check: Verify no hidden potential outcomes are in df_train
        forbidden_cols = [c for c in df_train.columns if c.startswith("y_") or c.startswith("p_") or c.startswith("tau_")]
        if forbidden_cols:
            raise ValueError(f"Strict isolation violation: df_train contains potential outcome columns: {forbidden_cols}")

        train_timestamp = datetime.now(timezone.utc).isoformat()
        
        # 1. Fit Preprocessor on Training Split Features
        self.preprocessor.fit(df_train)
        X_train_mat = self.preprocessor.transform(df_train)
        y_train = df_train[target_col].values.astype(int)
        t_train = df_train[treatment_col].values

        # 2. Fit dedicated response model mu_a(x) for each action
        val_metrics = {}
        for action in self.treatments:
            mask = (t_train == action)
            n_sub = np.sum(mask)

            if n_sub < 15:
                # Fallback on all data if action is sparse
                X_sub = X_train_mat
                y_sub = y_train
            else:
                X_sub = X_train_mat[mask]
                y_sub = y_train[mask]

            # Ensure both positive and negative classes exist
            if len(np.unique(y_sub)) < 2:
                anchor_y = 1 if y_sub[0] == 0 else 0
                X_sub = np.vstack([X_sub, X_sub[:1]])
                y_sub = np.append(y_sub, anchor_y)

            # Fit base classifier
            model = self.base_estimator_cls(**self.estimator_kwargs)
            model.fit(X_sub, y_sub)
            self.models_[action] = model

        # 3. Compute validation metrics if validation set provided
        if df_val is not None and len(df_val) > 0:
            X_val_mat = self.preprocessor.transform(df_val)
            y_val = df_val[target_col].values.astype(int)
            t_val = df_val[treatment_col].values

            for action in self.treatments:
                val_mask = (t_val == action)
                if np.sum(val_mask) >= 10 and len(np.unique(y_val[val_mask])) >= 2:
                    p_val = self.models_[action].predict_proba(X_val_mat[val_mask])[:, 1]
                    auc = float(roc_auc_score(y_val[val_mask], p_val))
                    ll = float(log_loss(y_val[val_mask], p_val))
                    val_metrics[action] = {"val_auc": round(auc, 4), "val_log_loss": round(ll, 4)}

        self.is_fitted = True

        # Save metadata
        self.metadata_ = {
            "model_type": "MultiActionTLearner",
            "model_version": self.model_version,
            "training_timestamp": train_timestamp,
            "training_rows": len(df_train),
            "random_seed": self.random_seed,
            "features_used": self.preprocessor.feature_names_,
            "treatments": self.treatments,
            "control_action": self.control_action,
            "validation_metrics": val_metrics
        }

        return self

    def predict_action_outcomes(
        self,
        X: Union[pd.DataFrame, Dict[str, Any], List[Dict[str, Any]]]
    ) -> Dict[str, Union[np.ndarray, float]]:
        """
        Predicts recovery probability mu_a(x) = P(Y=1 | A=a, X=x) for all treatment arms.
        """
        if not self.is_fitted:
            raise RuntimeError("WAPSIUpliftModel is not fitted yet.")

        is_single = isinstance(X, dict) or (isinstance(X, pd.DataFrame) and len(X) == 1)
        X_mat = self.preprocessor.transform(X)

        probs: Dict[str, Any] = {}
        for action in self.treatments:
            model = self.models_[action]
            p = model.predict_proba(X_mat)[:, 1]
            p = np.clip(p, 0.001, 0.999)
            if is_single:
                probs[action] = round(float(p[0]), 4)
            else:
                probs[action] = p

        return probs

    def predict_uplift(
        self,
        X: Union[pd.DataFrame, Dict[str, Any], List[Dict[str, Any]]]
    ) -> Dict[str, Union[np.ndarray, float]]:
        """
        Predicts individual treatment effect uplift for each intervention versus no_action:
        uplift_action = P(Y=1 | action, X) - P(Y=1 | no_action, X)

        Returns dictionary mapping active treatment names to estimated uplift values.
        """
        probs = self.predict_action_outcomes(X)
        is_single = isinstance(probs[self.control_action], (float, int))
        p0 = probs[self.control_action]

        uplifts: Dict[str, Any] = {}
        for action in self.active_treatments:
            p_act = probs[action]
            if is_single:
                uplifts[action] = round(float(p_act - p0), 4)
            else:
                uplifts[action] = np.round(p_act - p0, 4)

        return uplifts

    def get_metadata(self) -> Dict[str, Any]:
        """Returns training metadata and feature schema."""
        return dict(self.metadata_)

    def save(self, filepath: Union[str, Path]):
        """Persists the fitted uplift model bundle to disk using joblib."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @classmethod
    def load(cls, filepath: Union[str, Path]) -> "WAPSIUpliftModel":
        """Loads a persisted WAPSIUpliftModel from disk."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Model file not found at: {path}")
        model = joblib.load(path)
        if not isinstance(model, cls):
            raise TypeError(f"Loaded object is not a {cls.__name__}, got {type(model)}")
        return model
