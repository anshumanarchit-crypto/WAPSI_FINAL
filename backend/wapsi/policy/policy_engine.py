"""
Policy & Governance Engine for WAPSI Recovery Router.
Enforces TRAI DND regulations, channel-specific communication policies,
customer consent/opt-out gates, frequency caps, and merchant margin constraints.

PRINCIPLE: The Causal ML engine recommends; the Policy Engine authorizes execution.
"""

from __future__ import annotations

from typing import Dict, List, Any, Optional, Set
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except ImportError:
    from datetime import timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))

from wapsi.core.taxonomy import RecoveryAction, ACTION_METADATA


# Canonical Channel Classification
CHANNEL_MAP: Dict[str, str] = {
    # RecoveryAction enum values
    RecoveryAction.NO_ACTION.value: "none",
    RecoveryAction.INSTANT_SMART_RETRY.value: "retry",
    RecoveryAction.WHATSAPP_ONE_CLICK_LINK.value: "whatsapp",
    RecoveryAction.SMS_FALLBACK_LINK.value: "sms",
    RecoveryAction.BNPL_ALTERNATIVE_OFFER.value: "whatsapp",
    RecoveryAction.MERCHANT_DISCOUNT_NUDGE.value: "whatsapp",
    RecoveryAction.CALL_ASSIST_IVR.value: "ivr",
    # String equivalents from src/data_generator.py & frontend
    "no_action": "none",
    "NO_ACTION": "none",
    "retry_only": "retry",
    "RETRY": "retry",
    "whatsapp_nudge": "whatsapp",
    "WHATSAPP": "whatsapp",
    "sms": "sms",
    "email": "email",
    "EMAIL": "email",
    "email_followup": "email",
    "voice_call": "ivr",
    "ivr_call": "ivr",
    "VOICE": "ivr",
    "incentive_link": "whatsapp",
    "INCENTIVE": "whatsapp",
}

# Channels subject to TRAI Telecom Commercial Communications Customer Preference Regulations (TCCCPR) DND
DND_RESTRICTED_CHANNELS: Set[str] = {"whatsapp", "sms", "ivr"}


class PolicyEngine:
    """
    Deterministic rule-based policy validation and governance guardrail.
    Differentiates compliance rules across WhatsApp, SMS, Email, IVR, and Server-to-Server Retries.
    """

    def __init__(
        self,
        max_daily_user_nudges: int = 2,
        dnd_start_hour: int = 21,  # 9 PM IST
        dnd_end_hour: int = 9,     # 9 AM IST
        min_order_amount_for_ivr: float = 1500.0,
        min_net_utility_threshold: float = 0.0,
        dnd_restricted_channels: Optional[Set[str]] = None
    ):
        self.max_daily_user_nudges = max_daily_user_nudges
        self.dnd_start_hour = dnd_start_hour
        self.dnd_end_hour = dnd_end_hour
        self.min_order_amount_for_ivr = min_order_amount_for_ivr
        self.min_net_utility_threshold = min_net_utility_threshold
        self.dnd_restricted_channels = dnd_restricted_channels or DND_RESTRICTED_CHANNELS
        
        # User frequency tracker: user_id -> list of execution datetimes
        self.user_nudge_history: Dict[str, List[datetime]] = {}

    def get_channel(self, action: str) -> str:
        """Resolves channel type from action name or enum."""
        return CHANNEL_MAP.get(action, "whatsapp")

    def get_current_ist_hour(self, event_dict: Optional[Dict[str, Any]] = None) -> int:
        """Resolves hour in IST timezone strictly according to Asia/Kolkata."""
        if event_dict:
            if "hour_of_day" in event_dict and event_dict["hour_of_day"] is not None:
                return int(event_dict["hour_of_day"])
            if "hour" in event_dict and event_dict["hour"] is not None:
                return int(event_dict["hour"])
        return datetime.now(IST).hour

    def _get_current_ist_hour(self, event_dict: Dict[str, Any]) -> int:
        """Resolves hour in IST timezone, preferring explicit event fields."""
        return self.get_current_ist_hour(event_dict)

    def is_dnd_active_for_hour(self, hour: int) -> bool:
        """Returns True if the specified IST hour falls within the 21:00 to 09:00 DND restriction window."""
        return (hour >= self.dnd_start_hour) or (hour < self.dnd_end_hour)

    def evaluate(
        self,
        event_dict: Dict[str, Any],
        proposed_action: str,
        causal_net_utility: float,
        merchant_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Evaluates proposed action against regulatory compliance, customer consent, and merchant rules.
        """
        merchant_config = merchant_config or {}
        user_id = str(event_dict.get("user_id") or event_dict.get("customer_id") or "anonymous")
        amount = float(event_dict.get("amount_in_inr") or event_dict.get("amount") or 1000.0)
        hour = self._get_current_ist_hour(event_dict)
        
        channel = self.get_channel(proposed_action)
        requires_contact = channel not in {"none", "retry"}
        
        violations: List[str] = []
        is_dnd_window = self.is_dnd_active_for_hour(hour)
        authorized_action = proposed_action
        override_applied = False

        # Rule 1: Customer Consent & Opt-Out Enforcement
        is_opted_out = bool(
            event_dict.get("opt_out") or 
            event_dict.get("customer_opted_out") or 
            event_dict.get("opted_out") or 
            event_dict.get("consent_revoked") or 
            event_dict.get("opt_out_all")
        )
        if requires_contact and is_opted_out:
            violations.append("Customer Consent: User has opted out of outbound recovery communications.")
            authorized_action = RecoveryAction.NO_ACTION.value
            override_applied = True

        # Rule 2: Channel-Specific TRAI DND Window Check (21:00 - 09:00 IST)
        # Applies strictly to channels subject to telecom DND (WhatsApp, SMS, Voice).
        # Does NOT apply to server-to-server retries or email notifications.
        dnd_active_for_channel = is_dnd_window and (channel in self.dnd_restricted_channels)
        if dnd_active_for_channel:
            violations.append(
                f"TRAI DND Compliance: Outbound communication on channel '{channel}' restricted "
                f"between {self.dnd_start_hour}:00 and {self.dnd_end_hour:02d}:00 IST (Current hour: {hour}:00 IST)."
            )
            # Safe Fallback: switch to non-intrusive instant gateway retry if user contact was proposed
            if authorized_action != RecoveryAction.INSTANT_SMART_RETRY.value and proposed_action not in ("retry_only", "RETRY"):
                authorized_action = RecoveryAction.INSTANT_SMART_RETRY.value
                override_applied = True

        # Rule 3: Customer Communication Frequency Capping (Max N touches per 24 hours)
        user_nudges = self.user_nudge_history.get(user_id, [])
        if requires_contact and len(user_nudges) >= self.max_daily_user_nudges:
            violations.append(
                f"Frequency Cap Exceeded: User '{user_id}' has received {len(user_nudges)} touches in 24h "
                f"(Configured Limit: {self.max_daily_user_nudges})."
            )
            authorized_action = RecoveryAction.NO_ACTION.value
            override_applied = True

        # Rule 4: Voice / IVR Ticket Size Gate
        if channel == "ivr" and amount < self.min_order_amount_for_ivr:
            violations.append(
                f"IVR Threshold Gate: Order amount ₹{amount:.2f} is below minimum IVR ticket size threshold "
                f"₹{self.min_order_amount_for_ivr:.2f}."
            )
            authorized_action = RecoveryAction.WHATSAPP_ONE_CLICK_LINK.value
            override_applied = True

        # Rule 5: Merchant-Specific Channel Exclusions
        disallowed = set(merchant_config.get("disallowed_actions", []))
        if proposed_action in disallowed or channel in disallowed:
            violations.append(f"Merchant Policy: Action '{proposed_action}' is disabled by merchant configuration.")
            authorized_action = RecoveryAction.NO_ACTION.value
            override_applied = True

        # Rule 6: Net Utility Non-Negativity Gate
        if causal_net_utility < self.min_net_utility_threshold and proposed_action not in (
            RecoveryAction.NO_ACTION.value, "no_action", "NO_ACTION"
        ):
            violations.append(
                f"Negative Utility Gate: Expected net return ₹{causal_net_utility:.2f} does not cover direct execution costs."
            )
            authorized_action = RecoveryAction.NO_ACTION.value
            override_applied = True

        is_allowed = (len(violations) == 0)
        remaining_nudges = max(0, self.max_daily_user_nudges - len(user_nudges))

        return {
            "is_allowed": is_allowed,
            "allowed": is_allowed,  # Backward compatibility with src/inference.py
            "proposed_action": proposed_action,
            "authorized_action": authorized_action,
            "override_applied": override_applied,
            "violations": violations,
            "dnd_active": is_dnd_window,
            "dnd_restricted": dnd_active_for_channel,
            "channel": channel,
            "timezone": "Asia/Kolkata",
            "hour_ist": hour,
            "frequency_cap_remaining": remaining_nudges,
            "rule_evaluation_summary": (
                "Authorized without violations" if not violations else "Policy override applied: " + "; ".join(violations)
            )
        }

    def record_execution(self, user_id: str, action: str):
        """Records an executed recovery action against user's contact frequency quota."""
        channel = self.get_channel(action)
        if channel not in {"none", "retry"}:
            if user_id not in self.user_nudge_history:
                self.user_nudge_history[user_id] = []
            self.user_nudge_history[user_id].append(datetime.now(IST))

    def _check_dnd(self, hour: int) -> bool:
        """Backward compatibility helper for tests."""
        return self.is_dnd_active_for_hour(hour)
