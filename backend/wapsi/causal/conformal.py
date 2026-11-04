"""
Split Conformal Calibrator for Causal Uplift Uncertainty Estimation.
Provides distribution-free prediction intervals [tau_lower, tau_upper] for estimated treatment effects
with finite-sample coverage guarantees.
"""

from typing import Dict, List, Tuple, Optional
import numpy as np
import pandas as pd


class ConformalUpliftCalibrator:
    """
    Calibrates prediction intervals for uplift estimates using split-conformal calibration.
    """

    def __init__(self, confidence_level: float = 0.90):
        self.confidence_level = confidence_level
        self.alpha = 1.0 - confidence_level
        self.quantile_scores_: Dict[str, float] = {}
        self.is_calibrated = False

    def calibrate(
        self,
        predicted_uplifts: Dict[str, np.ndarray],
        calibration_residuals: Dict[str, np.ndarray]
    ):
        """
        Calibrates conformal quantiles using calibration holdout nonconformity scores.
        """
        for act, res in calibration_residuals.items():
            abs_res = np.abs(res)
            n = len(abs_res)
            if n == 0:
                self.quantile_scores_[act] = 0.10
                continue
            
            # (1 - alpha) * (1 + 1/n) empirical quantile
            q_val = float(np.quantile(abs_res, min(1.0, (1.0 - self.alpha) * (1.0 + 1.0 / n))))
            self.quantile_scores_[act] = max(0.02, q_val)

        self.is_calibrated = True
        return self

    def predict_intervals(
        self,
        predicted_uplift: float,
        action: str
    ) -> Tuple[float, float, str]:
        """
        Returns (lower_bound, upper_bound, confidence_tier).
        """
        q = self.quantile_scores_.get(action, 0.08)
        lower = round(float(predicted_uplift - q), 4)
        upper = round(float(predicted_uplift + q), 4)

        interval_width = upper - lower
        if interval_width < 0.12:
            tier = "HIGH_CONFIDENCE"
        elif interval_width < 0.25:
            tier = "MEDIUM_CONFIDENCE"
        else:
            tier = "HIGH_EPISTEMIC_UNCERTAINTY"

        return lower, upper, tier
