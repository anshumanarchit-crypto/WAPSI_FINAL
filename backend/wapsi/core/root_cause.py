"""
Root-cause classification engine for payment failures.
Maps low-level gateway/bank errors into actionable recovery taxonomies.
"""

from typing import Dict, Any, Tuple
from wapsi.core.taxonomy import ErrorCategory


# Deterministic mapping for standard Razorpay and UPI/Bank failure codes
ERROR_CODE_TAXONOMY_MAP: Dict[str, Tuple[ErrorCategory, str, float]] = {
    # Technical / Gateway
    "GATEWAY_ERROR": (ErrorCategory.TECHNICAL_GATEWAY, "Acquiring bank gateway error or intermittent downtime", 0.95),
    "BANK_DOWNTIME": (ErrorCategory.TECHNICAL_GATEWAY, "Issuing/acquiring bank experiencing system outage", 0.98),
    "SERVER_ERROR": (ErrorCategory.TECHNICAL_GATEWAY, "Payment switch internal server error", 0.90),
    "NETWORK_ERROR": (ErrorCategory.TECHNICAL_GATEWAY, "Network socket disconnect during handshake", 0.85),
    "ACQUIRER_TIMEOUT": (ErrorCategory.TECHNICAL_GATEWAY, "Acquirer node timed out waiting for core banking response", 0.92),
    "BAD_REQUEST_PAYMENT_TIMED_OUT": (ErrorCategory.TECHNICAL_GATEWAY, "Gateway response timeout during session lock", 0.90),
    
    # Friction / OTP / UX
    "OTP_NOT_ENTERED": (ErrorCategory.FRICTION_OTP_UX, "User did not submit OTP before expiration", 0.95),
    "OTP_EXPIRED": (ErrorCategory.FRICTION_OTP_UX, "OTP expired due to delivery or entry delay", 0.92),
    "AUTHENTICATION_FAILED": (ErrorCategory.FRICTION_OTP_UX, "3D Secure authentication failure or incorrect PIN", 0.88),
    "UPI_APP_TIMEOUT": (ErrorCategory.FRICTION_OTP_UX, "UPI collect request timed out in external UPI app (GPay/PhonePe)", 0.94),
    "APP_SWITCH_FAILED": (ErrorCategory.FRICTION_OTP_UX, "OS intent failed to switch to third-party UPI client", 0.96),
    "USER_DROPPED_OUT_AT_PIN": (ErrorCategory.FRICTION_OTP_UX, "Customer navigated back during MPIN entry screen", 0.91),
    
    # Financial / Balance
    "INSUFFICIENT_FUNDS": (ErrorCategory.FINANCIAL_BALANCE, "Payer account has insufficient funds for order amount", 0.97),
    "CARD_LIMIT_EXCEEDED": (ErrorCategory.FINANCIAL_BALANCE, "Card monthly or per-transaction spending limit exceeded", 0.95),
    "ACCOUNT_INACTIVE": (ErrorCategory.FINANCIAL_BALANCE, "Bank account dormant or inactive", 0.90),
    "PAYMENT_DECLINED_BY_BANK": (ErrorCategory.FINANCIAL_BALANCE, "Issuer declined transaction under risk/balance policy", 0.85),
    "INVALID_CVV": (ErrorCategory.FINANCIAL_BALANCE, "Card details entered incorrectly", 0.88),
    
    # Abandonment / Intent
    "USER_CANCELLED": (ErrorCategory.ABANDONMENT_INTENT, "User explicitly tapped cancel or closed the modal", 0.95),
    "CART_ABANDONED_ON_CHECKOUT": (ErrorCategory.ABANDONMENT_INTENT, "User left checkout open without initiating payment", 0.90),
    "PAYMENT_TIMED_OUT_NO_ATTEMPT": (ErrorCategory.ABANDONMENT_INTENT, "Checkout session expired with no payment interaction", 0.89),
    "TAB_CLOSED": (ErrorCategory.ABANDONMENT_INTENT, "Browser tab or app dismissed during checkout", 0.88),
}


class RootCauseClassifier:
    """
    Classifies payment failures into high-level actionable root cause categories.
    Combines rule-based taxonomy mapping with heuristic signal enrichment.
    """

    @classmethod
    def classify(cls, error_code: str, error_description: str = "", metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Classifies an incoming payment failure event.
        
        Returns:
            Dict with category, category_label, confidence, summary, and suggested_focus
        """
        code_upper = (error_code or "").strip().upper()
        metadata = metadata or {}
        
        if code_upper in ERROR_CODE_TAXONOMY_MAP:
            category, summary, confidence = ERROR_CODE_TAXONOMY_MAP[code_upper]
        else:
            # Fallback heuristic based on description or substring
            desc_lower = (error_description or "").lower()
            if any(k in desc_lower for k in ["timeout", "downtime", "server", "gateway", "network", "socket"]):
                category = ErrorCategory.TECHNICAL_GATEWAY
                summary = "Likely technical or upstream bank switch issue"
                confidence = 0.70
            elif any(k in desc_lower for k in ["otp", "pin", "auth", "3ds", "app switch"]):
                category = ErrorCategory.FRICTION_OTP_UX
                summary = "Likely authentication or app navigation friction"
                confidence = 0.70
            elif any(k in desc_lower for k in ["balance", "limit", "decline", "fund", "insufficient"]):
                category = ErrorCategory.FINANCIAL_BALANCE
                summary = "Likely insufficient balance or card limit constraint"
                confidence = 0.70
            elif any(k in desc_lower for k in ["cancel", "close", "abandon", "dismiss"]):
                category = ErrorCategory.ABANDONMENT_INTENT
                summary = "Likely price hesitation or checkout drop-off"
                confidence = 0.70
            else:
                category = ErrorCategory.TECHNICAL_GATEWAY
                summary = "Unclassified failure code; treated as gateway fallback"
                confidence = 0.50

        suggested_focus_map = {
            ErrorCategory.TECHNICAL_GATEWAY: "Smart retry across alternate gateway rails without disturbing customer",
            ErrorCategory.FRICTION_OTP_UX: "Direct seamless 1-click retry links via WhatsApp or SMS to bypass checkout friction",
            ErrorCategory.FINANCIAL_BALANCE: "Presenting alternative credit, BNPL, or split payment methods",
            ErrorCategory.ABANDONMENT_INTENT: "Soft micro-incentive nudge or high-touch recovery communication"
        }

        return {
            "error_category": category.value,
            "category_label": category.name,
            "confidence": confidence,
            "root_cause_summary": summary,
            "suggested_recovery_focus": suggested_focus_map.get(category, "Causal evaluation needed")
        }
