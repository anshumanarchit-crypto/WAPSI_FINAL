"""
Feature preprocessing and encoding pipeline for WAPSI tabular models.
Ensures consistent numerical scaling, categorical encoding, and feature name preservation for SHAP.
"""

from typing import List, Tuple, Dict, Any
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer


NUMERICAL_COLS = [
    "amount_in_inr",
    "historical_orders_count",
    "historical_recovery_rate",
    "retry_attempt_number",
    "hour_of_day",
    "is_dnd_window",
]

CATEGORICAL_COLS = [
    "payment_method",
    "error_code",
    "error_category",
    "user_device_os",
    "user_network_type",
]


class PaymentFeaturePipeline(BaseEstimator, TransformerMixin):
    """
    Transforms raw payment failure records into standardized feature matrices.
    """

    def __init__(self):
        self.num_cols = NUMERICAL_COLS
        self.cat_cols = CATEGORICAL_COLS
        self.preprocessor = ColumnTransformer(
            transformers=[
                ("num", StandardScaler(), self.num_cols),
                ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), self.cat_cols),
            ],
            remainder="drop"
        )
        self.feature_names_: List[str] = []
        self.is_fitted = False

    def fit(self, X: pd.DataFrame, y=None):
        df = self._ensure_df(X)
        self.preprocessor.fit(df)
        self.is_fitted = True
        
        # Build feature names
        cat_encoder = self.preprocessor.named_transformers_["cat"]
        cat_features = list(cat_encoder.get_feature_names_out(self.cat_cols))
        self.feature_names_ = list(self.num_cols) + cat_features
        return self

    def transform(self, X: pd.DataFrame) -> np.ndarray:
        df = self._ensure_df(X)
        return self.preprocessor.transform(df)

    def fit_transform(self, X: pd.DataFrame, y=None) -> np.ndarray:
        return self.fit(X, y).transform(X)

    def _ensure_df(self, X: Any) -> pd.DataFrame:
        if isinstance(X, pd.DataFrame):
            df = X.copy()
        elif isinstance(X, dict):
            df = pd.DataFrame([X])
        elif isinstance(X, list):
            df = pd.DataFrame(X)
        else:
            raise ValueError(f"Unsupported input type for FeaturePipeline: {type(X)}")

        # Ensure all columns exist with defaults if missing
        for col in self.num_cols:
            if col not in df.columns:
                df[col] = 0.0
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

        for col in self.cat_cols:
            if col not in df.columns:
                df[col] = "UNKNOWN"
            else:
                df[col] = df[col].astype(str).fillna("UNKNOWN")

        return df

    def get_feature_names(self) -> List[str]:
        return self.feature_names_
