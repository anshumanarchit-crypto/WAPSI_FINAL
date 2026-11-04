"""
Domain taxonomy, enums, constants, and action metadata for WAPSI.
"""

from enum import Enum
from typing import Dict, Any


class RecoveryAction(str, Enum):
    NO_ACTION = "NO_ACTION"
    INSTANT_SMART_RETRY = "INSTANT_SMART_RETRY"
    WHATSAPP_ONE_CLICK_LINK = "WHATSAPP_ONE_CLICK_LINK"
    SMS_FALLBACK_LINK = "SMS_FALLBACK_LINK"
    BNPL_ALTERNATIVE_OFFER = "BNPL_ALTERNATIVE_OFFER"
    MERCHANT_DISCOUNT_NUDGE = "MERCHANT_DISCOUNT_NUDGE"
    CALL_ASSIST_IVR = "CALL_ASSIST_IVR"


class ErrorCategory(str, Enum):
    TECHNICAL_GATEWAY = "TECHNICAL_GATEWAY"
    FRICTION_OTP_UX = "FRICTION_OTP_UX"
    FINANCIAL_BALANCE = "FINANCIAL_BALANCE"
    ABANDONMENT_INTENT = "ABANDONMENT_INTENT"


class PaymentMethod(str, Enum):
    UPI = "upi"
    CARD_DEBIT = "card_debit"
    CARD_CREDIT = "card_credit"
    NETBANKING = "netbanking"
    BNPL = "bnpl"
    WALLET = "wallet"


class RecoveryStatus(str, Enum):
    PENDING_RECOVERY = "PENDING_RECOVERY"
    DISPATCHED = "DISPATCHED"
    DELIVERED = "DELIVERED"
    LINK_OPENED = "LINK_OPENED"
    RETRY_INITIATED = "RETRY_INITIATED"
    RECOVERED = "RECOVERED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    SUPPRESSED = "SUPPRESSED"


# Metadata for each recovery action: Direct dispatch cost (INR), customer friction cost (INR), priority rank
ACTION_METADATA: Dict[RecoveryAction, Dict[str, Any]] = {
    RecoveryAction.NO_ACTION: {
        "name": "No Action (Organic Baseline)",
        "channel": "none",
        "dispatch_cost_inr": 0.0,
        "friction_cost_inr": 0.0,
        "requires_user_contact": False,
        "description": "Do not intervene; rely on organic merchant/user retry."
    },
    RecoveryAction.INSTANT_SMART_RETRY: {
        "name": "Instant Smart Gateway Reroute",
        "channel": "gateway_reroute",
        "dispatch_cost_inr": 0.15,
        "friction_cost_inr": 0.0,
        "requires_user_contact": False,
        "description": "Instantly switch acquiring rail to a healthier bank/node without user friction."
    },
    RecoveryAction.WHATSAPP_ONE_CLICK_LINK: {
        "name": "WhatsApp 1-Click Recovery Link",
        "channel": "whatsapp",
        "dispatch_cost_inr": 0.85,
        "friction_cost_inr": 0.50,
        "requires_user_contact": True,
        "description": "Send rich interactive WhatsApp notification with deep payment intent."
    },
    RecoveryAction.SMS_FALLBACK_LINK: {
        "name": "SMS Fallback Deep Link",
        "channel": "sms",
        "dispatch_cost_inr": 0.20,
        "friction_cost_inr": 0.80,
        "requires_user_contact": True,
        "description": "Send standard SMS with direct payment recovery shortlink."
    },
    RecoveryAction.BNPL_ALTERNATIVE_OFFER: {
        "name": "BNPL / PayLater Alternative Offer",
        "channel": "whatsapp_or_sms",
        "dispatch_cost_inr": 1.20,
        "friction_cost_inr": 0.40,
        "requires_user_contact": True,
        "description": "Offer zero-interest PayLater or EMI alternative for card/balance drops."
    },
    RecoveryAction.MERCHANT_DISCOUNT_NUDGE: {
        "name": "Merchant Micro-Incentive Nudge",
        "channel": "whatsapp",
        "dispatch_cost_inr": 2.50,  # includes amortized micro-discount value
        "friction_cost_inr": 0.30,
        "requires_user_contact": True,
        "description": "Provide a time-limited 3-5% discount code to revive abandoned cart intent."
    },
    RecoveryAction.CALL_ASSIST_IVR: {
        "name": "Automated Call Assist IVR",
        "channel": "ivr",
        "dispatch_cost_inr": 3.50,
        "friction_cost_inr": 3.00,
        "requires_user_contact": True,
        "description": "Automated outbound voice call for high-ticket failures with payment guidance."
    }
}
