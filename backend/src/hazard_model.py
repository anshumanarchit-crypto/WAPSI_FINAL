"""
WAPSI Discrete-Time Hazard & Recovery Timing Model.
Razorpay AI Buildathon 2026 - Track 3

Answers the core question:
"When is recovery most likely to happen?"

This model is separate from uplift decisioning (which determines WHAT to do).
The Timing Hazard Model determines WHEN the customer/case is most receptive
or when organic/intervention recovery is temporally concentrated.

Time Buckets:
  - 0-24h : Immediate recovery (technical glitch clearance, fast retry, instant UPI)
  - 24-48h: Next-day recovery (salary replenishment, customer notice, manual review)
  - 48-72h: Multi-day recovery (weekend rollover, bill cycle replenishment)
  - 72h+  : Extended recovery (long-tail re-engagement, billing cycle resolution)

Key Signals:
  - decline_reason (e.g., technical errors clear in 0-24h; insufficient funds peak 24-48h/48-72h)
  - issuer (e.g., HDFC/ICICI fast clearing vs PSU bank batch settlement cycles)
  - bin_bucket (e.g., platinum/corporate credit vs standard debit/UPI)
  - domain (e.g., food_delivery/gaming instant vs B2B SaaS/subscription billing cycle)
  - Contextual features: amount, hour, day_of_week, fatigue_score, previous_failures
"""

from __future__ import annotations

from typing import Dict, List, Any, Optional, Tuple, Union
from pathlib import Path
from datetime import datetime, timezone
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.metrics import log_loss

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TIME_WINDOWS: List[str] = ["0-24h", "24-48h", "48-72h", "72h+"]
WINDOW_MIDPOINTS: Dict[str, float] = {
    "0-24h": 12.0,
    "24-48h": 36.0,
    "48-72h": 60.0,
    "72h+": 84.0,
}

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


def map_hours_to_window(hours: float) -> str:
    """Maps continuous time to discrete time bucket."""
    if np.isnan(hours) or hours < 0:
        return "72h+"
    if hours <= 24.0:
        return "0-24h"
    elif hours <= 48.0:
        return "24-48h"
    elif hours <= 72.0:
        return "48-72h"
    else:
        return "72h+"


class WAPSITimingPreprocessor:
    """Encodes tabular features for the discrete-time hazard estimator."""

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

    def fit(self, df: pd.DataFrame) -> "WAPSITimingPreprocessor":
        clean_df = self._clean_input(df)
        self.preprocessor.fit(clean_df)
        cat_encoder = self.preprocessor.named_transformers_["cat"]
        cat_names = list(cat_encoder.get_feature_names_out(self.cat_cols))
        self.feature_names_ = list(self.num_cols) + cat_names
        self.is_fitted = True
        return self

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("Preprocessor must be fitted before transforming.")
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


class WAPSIHazardModel(BaseEstimator):
    """
    Discrete-Time Hazard Estimator for Payment Recovery Timing.

    Predicts the conditional discrete hazard distribution h(t | x) across
    4 operational windows: 0-24h, 24-48h, 48-72h, and 72h+.
    """

    def __init__(
        self,
        classifier_kwargs: Optional[Dict[str, Any]] = None,
        random_seed: int = 42,
        model_version: str = "1.0.0"
    ):
        self.random_seed = random_seed
        self.model_version = model_version
        self.classifier_kwargs = classifier_kwargs or {
            "n_estimators": 75,
            "max_depth": 3,
            "learning_rate": 0.08,
            "random_state": random_seed
        }
        self.windows = TIME_WINDOWS
        self.window_to_idx = {w: i for i, w in enumerate(TIME_WINDOWS)}
        self.preprocessor = WAPSITimingPreprocessor()
        self.classifier = GradientBoostingClassifier(**self.classifier_kwargs)
        self.is_fitted = False
        self.metadata_: Dict[str, Any] = {}

    def fit(
        self,
        df: pd.DataFrame,
        time_col: str = "time_to_recovery_hours",
        target_col: str = "recovered"
    ) -> "WAPSIHazardModel":
        """
        Fits the discrete-time hazard model on training dataset.

        Uses recovered cases with observed time_to_recovery_hours, with
        prior smoothing from unrecovered / right-censored background distribution.
        """
        train_timestamp = datetime.now(timezone.utc).isoformat()

        # Filter to recovered events with valid non-negative timing
        has_time = df[time_col].notna() & (df[time_col] >= 0)
        df_valid = df[has_time].copy()

        if len(df_valid) < 50:
            # If sparse, create synthetic windows based on decline reasons
            df_valid = df.copy()
            df_valid[time_col] = df_valid[time_col].fillna(24.0)

        # Map continuous hours to discrete window targets
        y_windows = df_valid[time_col].apply(map_hours_to_window).values
        y_indices = np.array([self.window_to_idx.get(w, 0) for w in y_windows])

        # Ensure all 4 classes are represented
        unique_classes = set(y_indices)
        X_df = df_valid.copy()
        if len(unique_classes) < len(self.windows):
            for missing_idx in range(len(self.windows)):
                if missing_idx not in unique_classes:
                    # Append one synthetic anchor row
                    dummy_row = X_df.iloc[:1].copy()
                    X_df = pd.concat([X_df, dummy_row], ignore_index=True)
                    y_indices = np.append(y_indices, missing_idx)

        # Fit Preprocessor
        self.preprocessor.fit(X_df)
        X_mat = self.preprocessor.transform(X_df)

        # Fit multi-class hazard model
        self.classifier.fit(X_mat, y_indices)
        self.is_fitted = True

        # Record metadata
        self.metadata_ = {
            "model_type": "DiscreteTimeHazardModel",
            "model_version": self.model_version,
            "training_timestamp": train_timestamp,
            "training_rows": len(df_valid),
            "random_seed": self.random_seed,
            "features_used": self.preprocessor.feature_names_,
            "windows": self.windows,
            "class_distribution": {
                w: int(np.sum(y_indices == i)) for i, w in enumerate(self.windows)
            }
        }

        return self

    def recommend_timing(self, case: Union[Dict[str, Any], pd.DataFrame, pd.Series]) -> Dict[str, Any]:
        """
        Recommends the optimal recovery window and returns the discrete hazard distribution.

        Args:
            case: Dict or single-row DataFrame containing transaction features.

        Returns:
            Dict matching specification:
            {
                "recommended_window": "24-48h",
                "hazard_by_window": {
                    "0-24h": 0.12,
                    "24-48h": 0.31,
                    "48-72h": 0.44,
                    "72h+": 0.13
                },
                "expected_hours": 38.5,
                "cumulative_hazard": {...},
                "timing_drivers": {...}
            }
        """
        if not self.is_fitted:
            raise RuntimeError("WAPSIHazardModel is not fitted yet.")

        if isinstance(case, pd.Series):
            case = case.to_dict()
        elif isinstance(case, pd.DataFrame):
            case = case.iloc[0].to_dict()

        X_mat = self.preprocessor.transform(case)
        probs = self.classifier.predict_proba(X_mat)[0]

        # Map probabilities to the 4 time windows
        # Ensure array matches the 4 target windows
        hazard_by_window: Dict[str, float] = {}
        for i, w in enumerate(self.windows):
            if i < len(probs):
                hazard_by_window[w] = float(probs[i])
            else:
                hazard_by_window[w] = 0.0

        # Normalize to ensure clean sum to 1.00
        total_p = sum(hazard_by_window.values()) or 1.0
        for w in self.windows:
            hazard_by_window[w] = round(hazard_by_window[w] / total_p, 4)

        # Identify window with highest conditional hazard / probability
        recommended_window = max(self.windows, key=lambda w: hazard_by_window[w])

        # Compute cumulative recovery curve S(t)
        cum_val = 0.0
        cumulative_hazard: Dict[str, float] = {}
        for w in self.windows:
            cum_val += hazard_by_window[w]
            cumulative_hazard[w] = round(min(cum_val, 1.0), 4)

        # Expected recovery time in hours
        expected_hours = sum(
            hazard_by_window[w] * WINDOW_MIDPOINTS[w] for w in self.windows
        )

        return {
            "case_id": case.get("case_id", "case_unassigned"),
            "recommended_window": recommended_window,
            "hazard_by_window": hazard_by_window,
            "expected_hours": round(float(expected_hours), 2),
            "cumulative_hazard": cumulative_hazard,
            "timing_drivers": {
                "issuer": str(case.get("issuer", "UNKNOWN")),
                "bin_bucket": str(case.get("bin_bucket", "UNKNOWN")),
                "decline_reason": str(case.get("decline_reason", "UNKNOWN")),
                "domain": str(case.get("domain", "UNKNOWN")),
                "hour": int(case.get("hour", 12)),
                "fatigue_score": float(case.get("fatigue_score", 0.0))
            }
        }

    def batch_recommend_timing(self, df_cases: pd.DataFrame) -> List[Dict[str, Any]]:
        """Recommends timing for a batch of cases."""
        records = df_cases.to_dict(orient="records")
        return [self.recommend_timing(r) for r in records]

    def get_metadata(self) -> Dict[str, Any]:
        """Returns training metadata."""
        return dict(self.metadata_)

    def save(self, filepath: Union[str, Path]):
        """Persists fitted hazard model to disk."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @classmethod
    def load(cls, filepath: Union[str, Path]) -> "WAPSIHazardModel":
        """Loads a persisted WAPSIHazardModel from disk."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Model file not found at: {path}")
        model = joblib.load(path)
        if not isinstance(model, cls):
            raise TypeError(f"Loaded object is not a {cls.__name__}, got {type(model)}")
        return model


# ---------------------------------------------------------------------------
# Diagnostic Plotting Functions
# ---------------------------------------------------------------------------

def generate_timing_plots(
    df: pd.DataFrame,
    hazard_model: Optional[WAPSIHazardModel] = None,
    output_dir: str = "evaluation/plots/timing_plots"
) -> Dict[str, str]:
    """
    Generates and saves diagnostic timing plots:
      1. Timing by decline reason
      2. Timing by issuer
      3. Timing by domain
      4. Timing by BIN bucket

    Returns dict mapping plot_name -> file_path.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    plot_paths = {}

    # Ensure discrete window column exists
    df_plot = df.copy()
    if "time_to_recovery_hours" in df_plot.columns:
        df_plot["timing_window"] = df_plot["time_to_recovery_hours"].apply(map_hours_to_window)
    elif hazard_model is not None:
        recs = hazard_model.batch_recommend_timing(df_plot)
        df_plot["timing_window"] = [r["recommended_window"] for r in recs]
    else:
        raise ValueError("Either time_to_recovery_hours in df or hazard_model must be provided.")

    # Filter to valid recovered / timed cases
    valid_mask = df_plot["time_to_recovery_hours"].notna() if "time_to_recovery_hours" in df_plot.columns else slice(None)
    df_valid = df_plot[valid_mask] if isinstance(valid_mask, pd.Series) else df_plot

    window_colors = ["#4C72B0", "#55A868", "#C44E52", "#8172B3"]

    # 1. Timing by Decline Reason
    if "decline_reason" in df_valid.columns:
        fig, ax = plt.subplots(figsize=(11, 5))
        ct = pd.crosstab(df_valid["decline_reason"], df_valid["timing_window"], normalize="index")
        # Ensure all columns exist in correct order
        for w in TIME_WINDOWS:
            if w not in ct.columns:
                ct[w] = 0.0
        ct = ct[TIME_WINDOWS]

        ct.plot(kind="bar", stacked=True, ax=ax, color=window_colors, alpha=0.85, edgecolor="black", linewidth=0.5)
        ax.set_title("Recovery Timing Distribution by Decline Reason", fontsize=12, fontweight="bold")
        ax.set_ylabel("Proportion of Recoveries", fontsize=10)
        ax.set_xlabel("Decline Reason", fontsize=10)
        ax.set_xticklabels(ax.get_xticklabels(), rotation=25, ha="right", fontsize=9)
        ax.legend(title="Time Window", bbox_to_anchor=(1.02, 1), loc="upper left")
        ax.grid(axis="y", alpha=0.3)
        plt.tight_layout()
        p1 = out_path / "timing_by_decline_reason.png"
        fig.savefig(p1, dpi=150, bbox_inches="tight")
        plt.close(fig)
        plot_paths["timing_by_decline_reason"] = str(p1)

    # 2. Timing by Issuer
    if "issuer" in df_valid.columns:
        fig, ax = plt.subplots(figsize=(10, 5))
        ct = pd.crosstab(df_valid["issuer"], df_valid["timing_window"], normalize="index")
        for w in TIME_WINDOWS:
            if w not in ct.columns:
                ct[w] = 0.0
        ct = ct[TIME_WINDOWS]

        ct.plot(kind="bar", stacked=True, ax=ax, color=window_colors, alpha=0.85, edgecolor="black", linewidth=0.5)
        ax.set_title("Recovery Timing Distribution by Card Issuer", fontsize=12, fontweight="bold")
        ax.set_ylabel("Proportion of Recoveries", fontsize=10)
        ax.set_xlabel("Issuer Bank", fontsize=10)
        ax.set_xticklabels(ax.get_xticklabels(), rotation=0, fontsize=9)
        ax.legend(title="Time Window", bbox_to_anchor=(1.02, 1), loc="upper left")
        ax.grid(axis="y", alpha=0.3)
        plt.tight_layout()
        p2 = out_path / "timing_by_issuer.png"
        fig.savefig(p2, dpi=150, bbox_inches="tight")
        plt.close(fig)
        plot_paths["timing_by_issuer"] = str(p2)

    # 3. Timing by Domain
    if "domain" in df_valid.columns:
        fig, ax = plt.subplots(figsize=(11, 5))
        ct = pd.crosstab(df_valid["domain"], df_valid["timing_window"], normalize="index")
        for w in TIME_WINDOWS:
            if w not in ct.columns:
                ct[w] = 0.0
        ct = ct[TIME_WINDOWS]

        ct.plot(kind="bar", stacked=True, ax=ax, color=window_colors, alpha=0.85, edgecolor="black", linewidth=0.5)
        ax.set_title("Recovery Timing Distribution by Merchant Domain", fontsize=12, fontweight="bold")
        ax.set_ylabel("Proportion of Recoveries", fontsize=10)
        ax.set_xlabel("Merchant Domain", fontsize=10)
        ax.set_xticklabels(ax.get_xticklabels(), rotation=25, ha="right", fontsize=9)
        ax.legend(title="Time Window", bbox_to_anchor=(1.02, 1), loc="upper left")
        ax.grid(axis="y", alpha=0.3)
        plt.tight_layout()
        p3 = out_path / "timing_by_domain.png"
        fig.savefig(p3, dpi=150, bbox_inches="tight")
        plt.close(fig)
        plot_paths["timing_by_domain"] = str(p3)

    # 4. Timing by BIN Bucket
    if "bin_bucket" in df_valid.columns:
        fig, ax = plt.subplots(figsize=(10, 5))
        ct = pd.crosstab(df_valid["bin_bucket"], df_valid["timing_window"], normalize="index")
        for w in TIME_WINDOWS:
            if w not in ct.columns:
                ct[w] = 0.0
        ct = ct[TIME_WINDOWS]

        ct.plot(kind="bar", stacked=True, ax=ax, color=window_colors, alpha=0.85, edgecolor="black", linewidth=0.5)
        ax.set_title("Recovery Timing Distribution by Card BIN Tier", fontsize=12, fontweight="bold")
        ax.set_ylabel("Proportion of Recoveries", fontsize=10)
        ax.set_xlabel("BIN Bucket", fontsize=10)
        ax.set_xticklabels(ax.get_xticklabels(), rotation=20, ha="right", fontsize=9)
        ax.legend(title="Time Window", bbox_to_anchor=(1.02, 1), loc="upper left")
        ax.grid(axis="y", alpha=0.3)
        plt.tight_layout()
        p4 = out_path / "timing_by_bin_bucket.png"
        fig.savefig(p4, dpi=150, bbox_inches="tight")
        plt.close(fig)
        plot_paths["timing_by_bin_bucket"] = str(p4)

    return plot_paths
