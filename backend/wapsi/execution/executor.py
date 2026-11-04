"""
Recovery Action Dispatcher & Execution Simulator.
Orchestrates simulated delivery across WhatsApp, SMS, Smart Retry, BNPL, and IVR channels
with strict idempotency guarantees.
"""

from typing import Dict, Any, Optional
import uuid
import time
from datetime import datetime, timezone
from wapsi.core.taxonomy import RecoveryAction, ACTION_METADATA


class RecoveryExecutor:
    """
    Dispatches and tracks recovery actions with idempotency protection.
    """

    def __init__(self):
        # Idempotency cache: idempotency_key -> execution_receipt
        self.idempotency_store: Dict[str, Dict[str, Any]] = {}
        # Execution history
        self.dispatches: Dict[str, Dict[str, Any]] = {}

    def execute(
        self,
        event_dict: Dict[str, Any],
        authorized_action: str,
        message_copy: Dict[str, Any],
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes or simulates the dispatch of the authorized recovery intervention.
        """
        idem_key = idempotency_key or f"idem_{uuid.uuid4().hex[:12]}"
        
        # Check idempotency
        if idem_key in self.idempotency_store:
            receipt = self.idempotency_store[idem_key]
            receipt["is_idempotent_replay"] = True
            return receipt

        dispatch_id = f"disp_{uuid.uuid4().hex[:12]}"
        payment_id = event_dict.get("payment_id", f"pay_{uuid.uuid4().hex[:8]}")
        merchant_id = event_dict.get("merchant_id", "merch_default")
        amount = float(event_dict.get("amount_in_inr", 1000.0))
        
        act_enum = RecoveryAction(authorized_action)
        meta = ACTION_METADATA[act_enum]
        channel = meta["channel"]

        # Channel-specific execution simulation
        channel_payload = self._simulate_channel_dispatch(
            act_enum,
            payment_id,
            merchant_id,
            amount,
            message_copy
        )

        receipt = {
            "dispatch_id": dispatch_id,
            "idempotency_key": idem_key,
            "payment_id": payment_id,
            "merchant_id": merchant_id,
            "action_executed": authorized_action,
            "action_name": meta["name"],
            "channel": channel,
            "status": "DELIVERED" if channel != "none" else "SUPPRESSED",
            "dispatch_cost_inr": meta["dispatch_cost_inr"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "channel_details": channel_payload,
            "is_idempotent_replay": False
        }

        # Store in caches
        self.idempotency_store[idem_key] = receipt
        self.dispatches[dispatch_id] = receipt
        return receipt

    def _simulate_channel_dispatch(
        self,
        action: RecoveryAction,
        payment_id: str,
        merchant_id: str,
        amount: float,
        message_copy: Dict[str, Any]
    ) -> Dict[str, Any]:
        if action == RecoveryAction.WHATSAPP_ONE_CLICK_LINK:
            return {
                "provider": "Razorpay WhatsApp Business API (Simulated)",
                "message_id": f"wam_{uuid.uuid4().hex[:16]}",
                "template_name": message_copy.get("template_id", "rzp_1click"),
                "recipient_masked": "+91 98****3210",
                "interactive_url": message_copy.get("cta_url", f"https://rzp.io/r/{payment_id}"),
                "rendered_text": message_copy.get("body_text", "")
            }
        elif action == RecoveryAction.SMS_FALLBACK_LINK:
            return {
                "provider": "Razorpay SMS Gateway (Simulated)",
                "sms_id": f"sms_{uuid.uuid4().hex[:14]}",
                "dlt_template_id": "DLT_RZP_RECOVER_01",
                "recipient_masked": "+91 98****3210",
                "shortlink": message_copy.get("cta_url", f"https://rzp.io/r/{payment_id}"),
                "rendered_text": message_copy.get("body_text", "")
            }
        elif action == RecoveryAction.INSTANT_SMART_RETRY:
            return {
                "provider": "Razorpay Optimizer Smart Routing (Simulated)",
                "routing_id": f"route_{uuid.uuid4().hex[:12]}",
                "reroute_target": "HDFC_PRIMARY_SWITCH_NODE_B",
                "latency_ms": 48,
                "zero_friction": True
            }
        elif action == RecoveryAction.BNPL_ALTERNATIVE_OFFER:
            return {
                "provider": "Razorpay PayLater Network (Simulated)",
                "preapproved_credit_limit_inr": max(5000.0, amount * 2),
                "bnpl_session_id": f"bnpl_{uuid.uuid4().hex[:12]}",
                "tenure_options": ["3_months_no_cost", "pay_next_month"]
            }
        elif action == RecoveryAction.MERCHANT_DISCOUNT_NUDGE:
            return {
                "provider": "Dynamic Promo Engine (Simulated)",
                "coupon_code": f"REC5_{payment_id[:6].upper()}",
                "discount_pct": 5.0,
                "validity_minutes": 15
            }
        elif action == RecoveryAction.CALL_ASSIST_IVR:
            return {
                "provider": "Razorpay Cloud IVR (Simulated)",
                "call_session_id": f"ivr_{uuid.uuid4().hex[:14]}",
                "tts_voice": "en-IN-Wavenet-D",
                "outbound_status": "RINGING_ANSWERED"
            }
        else:
            return {"provider": "None", "note": "No external dispatch initiated"}
