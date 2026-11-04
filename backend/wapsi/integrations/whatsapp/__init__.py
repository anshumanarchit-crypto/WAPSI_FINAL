"""
WhatsApp Cloud API Integration Package (Meta Graph API).
Provides typed messaging, recovery template nudges, delivery webhook parsing, and opt-out governance.
"""

from wapsi.integrations.whatsapp.client import (
    WhatsAppAuthError,
    WhatsAppClient,
    WhatsAppDeliveryError,
    WhatsAppDispatchResult,
    WhatsAppError,
    WhatsAppRateLimitError,
    WhatsAppValidationError,
)
from wapsi.integrations.whatsapp.opt_out import OptOutManager
from wapsi.integrations.whatsapp.webhook import (
    WhatsAppDeliveryStatus,
    WhatsAppEvent,
    WhatsAppWebhookHandler,
)

__all__ = [
    "WhatsAppClient",
    "WhatsAppDispatchResult",
    "WhatsAppError",
    "WhatsAppAuthError",
    "WhatsAppRateLimitError",
    "WhatsAppDeliveryError",
    "WhatsAppValidationError",
    "WhatsAppWebhookHandler",
    "WhatsAppDeliveryStatus",
    "WhatsAppEvent",
    "OptOutManager",
]
