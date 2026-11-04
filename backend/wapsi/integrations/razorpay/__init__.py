"""
Razorpay Payment Gateway Integration Package.
Provides typed HTTP client, Payment Links API, status normalization, and raw-body webhook verification.
"""

from wapsi.integrations.razorpay.client import (
    RazorpayAuthError,
    RazorpayClient,
    RazorpayError,
    RazorpayNetworkError,
    RazorpayNotFoundError,
    RazorpayRateLimitError,
    RazorpayValidationError,
)
from wapsi.integrations.razorpay.webhook import (
    RazorpayWebhookEvent,
    RazorpayWebhookHandler,
)

__all__ = [
    "RazorpayClient",
    "RazorpayError",
    "RazorpayAuthError",
    "RazorpayValidationError",
    "RazorpayNotFoundError",
    "RazorpayRateLimitError",
    "RazorpayNetworkError",
    "RazorpayWebhookHandler",
    "RazorpayWebhookEvent",
]

