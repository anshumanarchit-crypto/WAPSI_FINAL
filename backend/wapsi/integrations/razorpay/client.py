"""
Razorpay Payment Gateway API Client.
Target: Razorpay Test Mode API (https://api.razorpay.com/v1)

Provides secure, typed API interactions for:
- Standard & 1-Click Payment Link creation
- Payment Link fetching and cancellation
- Payment entity status normalization
- Bounded retries and provider error classification
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional, Union

import httpx

from wapsi.core.config import get_settings, WapsiSettings

logger = logging.getLogger("wapsi.integrations.razorpay")

# Base API endpoint for Razorpay
RAZORPAY_API_BASE = "https://api.razorpay.com/v1"


# ==============================================================================
# Typed Provider Exceptions
# ==============================================================================
class RazorpayError(Exception):
    """Base exception for all Razorpay API client errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, error_code: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class RazorpayAuthError(RazorpayError):
    """Raised when API key credentials are invalid, missing, or unauthorized."""
    pass


class RazorpayValidationError(RazorpayError):
    """Raised when request payload fails Razorpay schema validation (e.g. invalid amount)."""
    pass


class RazorpayNotFoundError(RazorpayError):
    """Raised when requested entity (payment link, payment) does not exist."""
    pass


class RazorpayRateLimitError(RazorpayError):
    """Raised when API rate limits are exceeded (HTTP 429)."""
    pass


class RazorpayNetworkError(RazorpayError):
    """Raised when connection drops, DNS fails, or request times out."""
    pass


# ==============================================================================
# Razorpay HTTP Client
# ==============================================================================
class RazorpayClient:
    """
    Asynchronous and synchronous HTTP client for Razorpay Payment Links and Payments.
    Enforces Test Mode safety, credential protection, and retry backoff.
    """

    def __init__(
        self,
        key_id: Optional[str] = None,
        key_secret: Optional[str] = None,
        settings: Optional[WapsiSettings] = None,
        base_url: str = RAZORPAY_API_BASE,
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        transport: Optional[httpx.BaseTransport] = None,
        async_transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        active_settings = settings or get_settings()
        self.key_id = key_id if key_id is not None else active_settings.razorpay_key_id
        if key_secret is not None:
            self.key_secret = key_secret
        else:
            self.key_secret = (
                active_settings.razorpay_key_secret.get_secret_value() if active_settings.razorpay_key_secret else None
            )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds
        self.max_retries = max_retries
        self._sync_transport = transport
        self._async_transport = async_transport

        # Validation: Never allow live key IDs in test configurations
        if self.key_id and self.key_id.startswith("rzp_live_"):
            if active_settings.razorpay_mode == "test":
                raise RazorpayAuthError(
                    "Safety violation: Live Razorpay Key ID (rzp_live_) detected in test mode configuration. "
                    "Phase 2 requires test mode credentials exclusively."
                )

    def _get_auth(self) -> httpx.BasicAuth:
        """Constructs BasicAuth, validating that credentials exist."""
        if not self.key_id or not self.key_secret:
            raise RazorpayAuthError(
                "Razorpay API credentials are not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET."
            )
        return httpx.BasicAuth(self.key_id, self.key_secret)

    def _classify_error(self, response: httpx.Response) -> RazorpayError:
        """Classifies HTTP error responses into typed exceptions without leaking secrets."""
        status = response.status_code
        try:
            body = response.json()
            err_data = body.get("error", {})
            desc = err_data.get("description", response.text)
            code = err_data.get("code", "UNKNOWN_ERROR")
        except Exception:
            desc = response.text[:200]
            code = "PARSE_ERROR"

        safe_msg = f"Razorpay API error ({status} - {code}): {desc}"

        if status == 401 or status == 403:
            return RazorpayAuthError(safe_msg, status_code=status, error_code=code)
        elif status == 400 or status == 422:
            return RazorpayValidationError(safe_msg, status_code=status, error_code=code)
        elif status == 404:
            return RazorpayNotFoundError(safe_msg, status_code=status, error_code=code)
        elif status == 429:
            return RazorpayRateLimitError(safe_msg, status_code=status, error_code=code)
        else:
            return RazorpayError(safe_msg, status_code=status, error_code=code)

    # --------------------------------------------------------------------------
    # Synchronous API Methods
    # --------------------------------------------------------------------------
    def _request_sync(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Executes HTTP request with bounded exponential backoff retries on transient errors."""
        auth = self._get_auth()
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {"User-Agent": "WAPSI-Autonomous-Recovery/2.0"}

        last_exception = None
        for attempt in range(1, self.max_retries + 1):
            try:
                with httpx.Client(
                    auth=auth,
                    timeout=self.timeout,
                    transport=self._sync_transport,
                ) as client:
                    resp = client.request(
                        method=method,
                        url=url,
                        json=json_data,
                        params=params,
                        headers=headers,
                    )

                    if resp.is_success:
                        return resp.json()

                    # Classify error
                    err = self._classify_error(resp)
                    # Only retry on 5xx server errors or 429 rate limit
                    if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                        backoff = 0.5 * (2 ** (attempt - 1))
                        logger.warning(f"Transient Razorpay error {resp.status_code}; retrying in {backoff}s (attempt {attempt}/{self.max_retries})")
                        time.sleep(backoff)
                        continue
                    raise err

            except (httpx.TimeoutException, httpx.NetworkError) as net_err:
                last_exception = RazorpayNetworkError(
                    f"Network error communicating with Razorpay: {type(net_err).__name__}"
                )
                if attempt < self.max_retries:
                    backoff = 0.5 * (2 ** (attempt - 1))
                    logger.warning(f"Network timeout/drop connecting to Razorpay; retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                raise last_exception

        if last_exception:
            raise last_exception
        raise RazorpayError("Maximum retry budget exhausted without successful response.")

    def create_payment_link(
        self,
        amount_in_paise: int,
        currency: str = "INR",
        description: str = "Payment Recovery Link",
        customer: Optional[Dict[str, str]] = None,
        notes: Optional[Dict[str, str]] = None,
        expire_by: Optional[int] = None,
        callback_url: Optional[str] = None,
        notify_whatsapp: bool = False,
        notify_sms: bool = False,
        reference_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates a standard or 1-click Razorpay Payment Link.
        
        Args:
            amount_in_paise: Payment amount in integer paise (e.g. 150000 = Rs 1,500.00).
            currency: Currency code (default: 'INR').
            description: Customer-facing payment purpose.
            customer: Dict with 'name', 'contact', 'email'.
            notes: Metadata dictionary for merchant tracking (case_id, merchant_id, etc.).
            expire_by: Unix timestamp when link expires.
            callback_url: URL to redirect customer upon payment completion.
            notify_whatsapp: Whether Razorpay should trigger its own automated WhatsApp notification.
            notify_sms: Whether Razorpay should trigger SMS.
            reference_id: Optional unique merchant reference ID for idempotency.
        """
        if not isinstance(amount_in_paise, int) or amount_in_paise <= 0:
            raise RazorpayValidationError(f"Amount must be a positive integer in paise, got: {amount_in_paise}")

        payload: Dict[str, Any] = {
            "amount": amount_in_paise,
            "currency": currency.upper(),
            "accept_partial": False,
            "description": description,
            "notify": {
                "sms": notify_sms,
                "email": False,
                "whatsapp": notify_whatsapp,
            },
            "reminder_enable": False,  # Reminders are autonomously governed by WAPSI
        }

        if reference_id:
            payload["reference_id"] = reference_id

        if customer:
            clean_cust = {}
            if "name" in customer:
                clean_cust["name"] = customer["name"]
            if "contact" in customer:
                clean_cust["contact"] = customer["contact"]
            if "email" in customer:
                clean_cust["email"] = customer["email"]
            if clean_cust:
                payload["customer"] = clean_cust

        if notes:
            payload["notes"] = {str(k): str(v) for k, v in notes.items()}

        if expire_by:
            payload["expire_by"] = expire_by

        if callback_url:
            payload["callback_url"] = callback_url
            payload["callback_method"] = "get"

        logger.info(f"Issuing Razorpay Payment Link creation request for amount {amount_in_paise} paise...")
        return self._request_sync("POST", "payment_links", json_data=payload)

    def get_payment_link(self, payment_link_id: str) -> Dict[str, Any]:
        """Fetches Payment Link details by link ID (plink_...)."""
        if not payment_link_id:
            raise RazorpayValidationError("payment_link_id must not be empty.")
        return self._request_sync("GET", f"payment_links/{payment_link_id}")

    def cancel_payment_link(self, payment_link_id: str) -> Dict[str, Any]:
        """Cancels an active unpaid payment link."""
        if not payment_link_id:
            raise RazorpayValidationError("payment_link_id must not be empty.")
        return self._request_sync("POST", f"payment_links/{payment_link_id}/cancel")

    def get_payment(self, payment_id: str) -> Dict[str, Any]:
        """Fetches payment entity details by payment ID (pay_...)."""
        if not payment_id:
            raise RazorpayValidationError("payment_id must not be empty.")
        return self._request_sync("GET", f"payments/{payment_id}")

    @staticmethod
    def normalize_payment_status(status_str: Optional[str]) -> str:
        """
        Normalizes Razorpay payment / link status strings into unified WAPSI recovery states.
        
        Razorpay statuses:
        - 'paid', 'captured' -> 'RECOVERED'
        - 'created', 'issued' -> 'PENDING'
        - 'attempted', 'processing' -> 'PROCESSING'
        - 'failed' -> 'FAILED'
        - 'cancelled' -> 'CANCELLED'
        - 'expired' -> 'EXPIRED'
        """
        if not status_str:
            return "UNKNOWN"
        s = status_str.strip().lower()
        mapping = {
            "paid": "RECOVERED",
            "captured": "RECOVERED",
            "authorized": "PROCESSING",
            "processing": "PROCESSING",
            "created": "PENDING",
            "issued": "PENDING",
            "partially_paid": "PARTIAL",
            "failed": "FAILED",
            "cancelled": "CANCELLED",
            "canceled": "CANCELLED",
            "expired": "EXPIRED",
            "refunded": "REFUNDED",
        }
        return mapping.get(s, "UNKNOWN")
