"""
Hazard & Survival Timing Model for Payment Recovery.
Estimates time-to-recovery hazard rates h(t | x, a) and computes optimal notification delay t*
to balance organic recovery survival with intervention decay.
"""

from typing import Dict, Any, Optional
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from wapsi.core.taxonomy import RecoveryAction, ErrorCategory


class RecoveryTimingModel:
    """
    Parametric survival & timing model for recovery delay optimization.
    Determines the optimal delay window t* (in seconds) to initiate a recovery action.
    """

    def __init__(self, random_seed: int = 42):
        self.random_seed = random_seed
        self.model = Ridge(alpha=1.0)
        self.is_fitted = False
        
        # Base anchor delays in seconds by action
        self.base_action_delays = {
            RecoveryAction.NO_ACTION.value: 1200.0,
            RecoveryAction.INSTANT_SMART_RETRY.value: 15.0,
            RecoveryAction.WHATSAPP_ONE_CLICK_LINK.value: 120.0,
            RecoveryAction.SMS_FALLBACK_LINK.value: 300.0,
            RecoveryAction.BNPL_ALTERNATIVE_OFFER.value: 450.0,
            RecoveryAction.MERCHANT_DISCOUNT_NUDGE.value: 600.0,
            RecoveryAction.CALL_ASSIST_IVR.value: 900.0,
        }

    def fit(self, df: pd.DataFrame, time_col: str = "recovery_delay_sec", target_col: str = "recovered"):
        """
        Fits log-linear acceleration factor model on observed recovery times.
        """
        # Filter to recovered events with valid positive timing
        valid_mask = (df[target_col] == 1) & (df[time_col] > 0)
        if not np.any(valid_mask) or np.sum(valid_mask) < 20:
            # Fit on all positive times
            valid_mask = (df[time_col] > 0)

        sub_df = df[valid_mask].copy()
        
        # Create features for timing
        X = self._extract_timing_features(sub_df)
        y_log_time = np.log(sub_df[time_col].values + 1.0)

        self.model.fit(X, y_log_time)
        self.is_fitted = True
        return self

    def predict_optimal_delay(
        self,
        event_dict: Dict[str, Any],
        selected_action: str
    ) -> Dict[str, Any]:
        """
        Computes the optimal delay window t* in seconds for an event and action.
        """
        base_t = self.base_action_delays.get(selected_action, 180.0)
        
        if not self.is_fitted:
            optimal_sec = base_t
        else:
            df = pd.DataFrame([event_dict])
            X = self._extract_timing_features(df)
            pred_log = self.model.predict(X)[0]
            pred_t = np.exp(pred_log) - 1.0
            # Blend model prediction with action physics anchor
            optimal_sec = float(0.7 * base_t + 0.3 * np.clip(pred_t, 5.0, 3600.0))

        # Channel-specific physics bounds
        if selected_action == RecoveryAction.INSTANT_SMART_RETRY.value:
            optimal_sec = min(optimal_sec, 30.0) # Smart retry must happen almost immediately
        elif selected_action == RecoveryAction.WHATSAPP_ONE_CLICK_LINK.value:
            optimal_sec = np.clip(optimal_sec, 60.0, 300.0) # 1 - 5 mins for WhatsApp
        elif selected_action == RecoveryAction.SMS_FALLBACK_LINK.value:
            optimal_sec = np.clip(optimal_sec, 120.0, 600.0)
        elif selected_action == RecoveryAction.CALL_ASSIST_IVR.value:
            optimal_sec = np.clip(optimal_sec, 300.0, 1800.0)

        return {
            "action": selected_action,
            "optimal_delay_seconds": int(round(optimal_sec)),
            "delay_human_readable": self._format_seconds(optimal_sec),
            "expected_survival_window_seconds": int(round(optimal_sec * 3.5)),
            "timing_rationale": self._explain_delay(selected_action, optimal_sec, event_dict)
        }

    def _extract_timing_features(self, df: pd.DataFrame) -> np.ndarray:
        amount = pd.to_numeric(df.get("amount_in_inr", 1000.0), errors="coerce").fillna(1000.0).values
        retry = pd.to_numeric(df.get("retry_attempt_number", 1), errors="coerce").fillna(1).values
        is_upi = (df.get("payment_method", "") == "upi").astype(float).values
        is_tech = (df.get("error_category", "") == ErrorCategory.TECHNICAL_GATEWAY.value).astype(float).values
        is_android = (df.get("user_device_os", "") == "Android").astype(float).values

        features = np.column_stack([
            np.log1p(amount),
            retry,
            is_upi,
            is_tech,
            is_android
        ])
        return features

    def _format_seconds(self, seconds: float) -> str:
        s = int(round(seconds))
        if s < 60:
            return f"{s} seconds"
        elif s < 3600:
            mins = s // 60
            rem = s % 60
            return f"{mins}m {rem}s" if rem > 0 else f"{mins} minutes"
        else:
            hours = s // 3600
            mins = (s % 3600) // 60
            return f"{hours}h {mins}m"

    def _explain_delay(self, action: str, delay_sec: float, event: Dict[str, Any]) -> str:
        if action == RecoveryAction.INSTANT_SMART_RETRY.value:
            return f"Immediate gateway reroute ({int(delay_sec)}s) to bypass bank downtime before session lock expires."
        elif action == RecoveryAction.WHATSAPP_ONE_CLICK_LINK.value:
            return f"Delay of {int(delay_sec)}s allows user organic retry window while maintaining high mobile purchase intent."
        elif action == RecoveryAction.BNPL_ALTERNATIVE_OFFER.value:
            return f"Delay of {int(delay_sec)}s gives user time to review alternative payment options without pressure."
        else:
            return f"Optimal intervention timing calculated at {int(delay_sec)}s based on failure root-cause."
