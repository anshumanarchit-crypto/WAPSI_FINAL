"""
WhatsApp Cloud API Client (Meta Graph API).
Target: Meta Graph API (https://graph.facebook.com/v26.0/{phone_number_id}/messages)

Provides secure, typed outbound messaging for:
- Autonomous 1-Click Payment Recovery Links
- Dynamic payment-link insertion into approved templates
- Text message fallback for developer sandbox
- Message ID (wamid) capture and rate-limit backoff handling
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import httpx

from wapsi.core.config import get_settings

logger = logging.getLogger("wapsi.integrations.whatsapp")

META_GRAPH_BASE = "https://graph.facebook.com"


# ==============================================================================
# Exceptions
# ==============================================================================
class WhatsAppError(Exception):
    """Base exception for WhatsApp Cloud API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, meta_error_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code
        self.meta_error_code = meta_error_code


class WhatsAppAuthError(WhatsAppError):
    """Raised when access token is invalid, expired, or lacking permissions."""
    pass


class WhatsAppRateLimitError(WhatsAppError):
    """Raised when Meta Graph API rate limits (HTTP 429) or business tier caps are exceeded."""
    pass


class WhatsAppDeliveryError(WhatsAppError):
    """Raised when message dispatch fails at Meta API gateway (e.g. invalid phone number)."""
    pass


class WhatsAppValidationError(WhatsAppError):
    """Raised when request payload or webhook payload fails schema/data validation."""
    pass


# ==============================================================================
# Dispatch Result Data Structure
# ==============================================================================
@dataclass(frozen=True)
class WhatsAppDispatchResult:
    """Captures response from WhatsApp Cloud API dispatch."""
    success: bool
    message_id: str  # wamid.HBg...
    recipient_phone: str
    status: str      # 'accepted', 'failed'
    timestamp: float
    raw_response: Dict[str, Any]


# ==============================================================================
# WhatsApp Cloud API Client
# ==============================================================================
class WhatsAppClient:
    """
    HTTP client for Meta's WhatsApp Cloud API.
    Manages bearer tokens, template parameter serialization, and E.164 phone sanitization.
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        api_version: Optional[str] = None,
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        settings = get_settings()
        self.access_token = access_token if access_token is not None else settings.get_whatsapp_token_str()
        self.phone_number_id = phone_number_id if phone_number_id is not None else settings.whatsapp_phone_number_id
        self.api_version = api_version or settings.whatsapp_api_version or "v26.0"
        self.timeout = timeout_seconds
        self.max_retries = max_retries
        self._transport = transport

    @property
    def is_configured(self) -> bool:
        """Returns True if minimum credentials are set."""
        return bool(self.access_token and self.phone_number_id)

    @staticmethod
    def sanitize_phone_number(phone: str) -> str:
        """
        Normalizes phone numbers to standard Meta format: E.164 digits without '+' or leading zeros.
        Example: '+91 98765-43210' -> '919876543210'
        """
        if not phone:
            raise WhatsAppDeliveryError("Recipient phone number must not be empty.")
        digits = re.sub(r"\D", "", phone)
        # If 10 digits provided for Indian number, prepend 91 country code
        if len(digits) == 10 and digits.startswith(("6", "7", "8", "9")):
            digits = "91" + digits
        if len(digits) < 10 or len(digits) > 15:
            raise WhatsAppDeliveryError(f"Invalid phone number length ({len(digits)} digits): {phone}")
        return digits

    def _get_headers(self) -> Dict[str, str]:
        if not self.access_token:
            raise WhatsAppAuthError(
                "WhatsApp Access Token is not configured. Set WHATSAPP_ACCESS_TOKEN in environment or .env."
            )
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "WAPSI-Autonomous-Recovery/2.0",
        }

    def _get_endpoint(self) -> str:
        if not self.phone_number_id:
            raise WhatsAppAuthError(
                "WhatsApp Phone Number ID is not configured. Set WHATSAPP_PHONE_NUMBER_ID in environment or .env."
            )
        return f"{META_GRAPH_BASE}/{self.api_version}/{self.phone_number_id}/messages"

    def _classify_error(self, response: httpx.Response) -> WhatsAppError:
        status = response.status_code
        try:
            body = response.json()
            err_obj = body.get("error", {})
            msg = err_obj.get("message", response.text)
            code = err_obj.get("code")
            subcode = err_obj.get("error_subcode")
        except Exception:
            msg = response.text[:200]
            code = None
            subcode = None

        safe_msg = f"WhatsApp Cloud API Error ({status} - code: {code}, subcode: {subcode}): {msg}"

        if status in (401, 403) or code in (190, 10, 200):
            return WhatsAppAuthError(safe_msg, status_code=status, meta_error_code=code)
        elif status == 429 or code in (4, 17, 32, 613):
            return WhatsAppRateLimitError(safe_msg, status_code=status, meta_error_code=code)
        elif status == 400 or code in (100, 131030, 131026, 132000, 132001, 132005, 132015, 132016):
            return WhatsAppDeliveryError(safe_msg, status_code=status, meta_error_code=code)
        else:
            return WhatsAppError(safe_msg, status_code=status, meta_error_code=code)

    def _send_payload(self, payload: Dict[str, Any]) -> WhatsAppDispatchResult:
        """Issues POST request to Meta Graph API with bounded retries on 429 / 5xx."""
        url = self._get_endpoint()
        headers = self._get_headers()
        to_phone = payload.get("to", "")

        last_exception = None
        for attempt in range(1, self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                    resp = client.post(url, json=payload, headers=headers)

                    if resp.is_success:
                        try:
                            data = resp.json()
                            if not isinstance(data, dict):
                                data = {"raw": resp.text}
                        except Exception:
                            data = {"raw": resp.text}

                        if isinstance(data, dict) and "error" in data:
                            err = self._classify_error(resp)
                            raise err

                        messages = data.get("messages") if isinstance(data, dict) else []
                        if not isinstance(messages, list):
                            messages = []

                        raw_mid = None
                        if messages and isinstance(messages[0], dict):
                            raw_mid = messages[0].get("id")

                        message_id = (
                            str(raw_mid).strip()
                            if (raw_mid is not None and str(raw_mid).strip())
                            else f"wamid_gen_{int(time.time()*1000)}"
                        )
                        logger.info(f"WhatsApp message dispatched successfully to {to_phone[:4]}***{to_phone[-2:]} (ID: {message_id})")
                        return WhatsAppDispatchResult(
                            success=True,
                            message_id=message_id,
                            recipient_phone=to_phone,
                            status="accepted",
                            timestamp=time.time(),
                            raw_response=data,
                        )

                    err = self._classify_error(resp)
                    if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                        backoff = 0.5 * (2 ** (attempt - 1))
                        logger.warning(f"Transient Meta API error ({resp.status_code}); retrying in {backoff}s (attempt {attempt}/{self.max_retries})...")
                        time.sleep(backoff)
                        continue
                    raise err

            except httpx.TimeoutException as timeout_err:
                # Ambiguous network timeout: request was dispatched and provider may have received it.
                # Avoid blind retries to prevent duplicate outbound messages to customers.
                logger.error(
                    f"Ambiguous network timeout communicating with WhatsApp Cloud API for {to_phone[:4]}***: {timeout_err}"
                )
                raise timeout_err

            except (httpx.NetworkError, httpx.ProtocolError, httpx.RequestError) as net_err:
                last_exception = WhatsAppDeliveryError(f"Network error communicating with WhatsApp Cloud API: {net_err}")
                if attempt < self.max_retries:
                    backoff = 0.5 * (2 ** (attempt - 1))
                    logger.warning(f"Network drop connecting to Meta API; retrying in {backoff}s (attempt {attempt}/{self.max_retries})...")
                    time.sleep(backoff)
                    continue
                raise last_exception

        if last_exception:
            raise last_exception
        raise WhatsAppError("Maximum retry budget exhausted without successful dispatch.")

    def send_text_message(self, to_phone: str, body_text: str, preview_url: bool = True) -> WhatsAppDispatchResult:
        """
        Sends standard text message with optional link preview.
        Suitable for developer sandbox testing and active customer service windows.
        """
        clean_phone = self.sanitize_phone_number(to_phone)
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_phone,
            "type": "text",
            "text": {
                "preview_url": preview_url,
                "body": body_text,
            },
        }
        return self._send_payload(payload)

    @staticmethod
    def validate_template_name(name: str) -> str:
        """
        Validates template name according to Meta WhatsApp Cloud API specifications.
        Meta template names must be non-empty, lowercase alphanumeric with underscores only.
        """
        if not name or not isinstance(name, str):
            raise WhatsAppValidationError("Template name must be a non-empty string.")
        cleaned = name.strip()
        if not cleaned:
            raise WhatsAppValidationError("Template name must not be empty or whitespace.")
        if not re.match(r"^[a-z0-9_]+$", cleaned):
            raise WhatsAppValidationError(
                f"Invalid template name: {name!r}. Template names must contain only lowercase "
                "alphanumeric characters and underscores (e.g. 'payment_recovery_v1')."
            )
        return cleaned

    @staticmethod
    def validate_language_code(code: str) -> str:
        """
        Validates language code according to Meta WhatsApp Cloud API specifications.
        Accepts standard codes like 'en', 'en_US', 'hi', 'pt_BR', 'es_LA', 'zh_HK', 'fil'.
        Normalizes hyphens to underscores (e.g. 'en-US' -> 'en_US').
        """
        if not code or not isinstance(code, str):
            raise WhatsAppValidationError("Language code must be a non-empty string.")
        cleaned = code.strip()
        if not cleaned:
            raise WhatsAppValidationError("Language code must not be empty or whitespace.")
        normalized = cleaned.replace("-", "_")
        if not re.match(r"^[a-z]{2,3}(?:_[A-Za-z0-9]+)?$", normalized):
            raise WhatsAppValidationError(
                f"Invalid language code: {code!r}. Must follow standard ISO language format (e.g. 'en', 'en_US')."
            )
        return normalized

    @classmethod
    def validate_template_components(cls, components: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """
        Defensively validates template components against Meta WhatsApp Cloud API contract.
        Validates structure for headers, body parameters, and interactive buttons (URL and quick-reply).
        """
        if components is None:
            return []
        if not isinstance(components, list):
            raise WhatsAppValidationError(f"Template components must be a list, got {type(components).__name__}.")

        validated: List[Dict[str, Any]] = []
        for i, comp in enumerate(components):
            if not isinstance(comp, dict):
                raise WhatsAppValidationError(f"Component at index {i} must be a dict, got {type(comp).__name__}.")
            ctype = comp.get("type")
            if not ctype or ctype not in {"header", "body", "button", "footer"}:
                raise WhatsAppValidationError(
                    f"Component at index {i} has invalid or missing 'type': {ctype!r}. "
                    "Expected 'header', 'body', 'button', or 'footer'."
                )

            # Validate header
            if ctype == "header":
                params = comp.get("parameters")
                if not isinstance(params, list):
                    raise WhatsAppValidationError(f"Header component at index {i} must contain a 'parameters' list.")
                for p_idx, p in enumerate(params):
                    if not isinstance(p, dict) or "type" not in p:
                        raise WhatsAppValidationError(
                            f"Header parameter {p_idx} must be a dict with a 'type' field."
                        )
                    ptype = p["type"]
                    if ptype not in {"text", "image", "document", "video", "location"}:
                        raise WhatsAppValidationError(
                            f"Unsupported header parameter type: {ptype!r}. Must be text, image, document, video, or location."
                        )
                    if ptype == "text" and ("text" not in p or not isinstance(p["text"], str)):
                        raise WhatsAppValidationError(f"Header text parameter {p_idx} must contain string 'text'.")
                    if ptype in {"image", "document", "video"}:
                        media_obj = p.get(ptype)
                        if not isinstance(media_obj, dict) or (not media_obj.get("link") and not media_obj.get("id")):
                            raise WhatsAppValidationError(
                                f"Header {ptype} parameter {p_idx} must contain object with 'link' or 'id'."
                            )
                    if ptype == "location":
                        loc_obj = p.get("location")
                        if not isinstance(loc_obj, dict) or "latitude" not in loc_obj or "longitude" not in loc_obj:
                            raise WhatsAppValidationError(
                                f"Header location parameter {p_idx} must contain object with 'latitude' and 'longitude'."
                            )

            # Validate body
            elif ctype == "body":
                params = comp.get("parameters")
                if not isinstance(params, list):
                    raise WhatsAppValidationError(f"Body component at index {i} must contain a 'parameters' list.")
                for p_idx, p in enumerate(params):
                    if not isinstance(p, dict) or "type" not in p:
                        raise WhatsAppValidationError(
                            f"Body parameter {p_idx} must be a dict with a 'type' field."
                        )
                    ptype = p["type"]
                    if ptype not in {"text", "currency", "date_time"}:
                        raise WhatsAppValidationError(f"Unsupported body parameter type: {ptype!r}.")
                    if ptype == "text" and ("text" not in p or not isinstance(p["text"], str)):
                        raise WhatsAppValidationError(f"Body text parameter {p_idx} must contain string 'text'.")
                    if ptype == "currency" and ("currency" not in p or not isinstance(p["currency"], dict)):
                        raise WhatsAppValidationError(f"Body currency parameter {p_idx} must contain 'currency' dict.")
                    if ptype == "date_time" and ("date_time" not in p or not isinstance(p["date_time"], dict)):
                        raise WhatsAppValidationError(f"Body date_time parameter {p_idx} must contain 'date_time' dict.")

            # Validate button
            elif ctype == "button":
                sub_type = comp.get("sub_type")
                if not sub_type or sub_type not in {"quick_reply", "url", "copy_code", "catalog"}:
                    raise WhatsAppValidationError(
                        f"Button component at index {i} requires valid 'sub_type' ('quick_reply', 'url'), got {sub_type!r}."
                    )
                raw_idx = comp.get("index")
                if raw_idx is None:
                    raise WhatsAppValidationError(f"Button component at index {i} requires an 'index' field.")
                try:
                    idx_int = int(str(raw_idx).strip())
                    if idx_int < 0 or idx_int > 9:
                        raise ValueError()
                except (ValueError, TypeError):
                    raise WhatsAppValidationError(
                        f"Button component at index {i} has invalid index: {raw_idx!r}. Must be an integer 0..9."
                    )

                params = comp.get("parameters")
                if not isinstance(params, list) or len(params) == 0:
                    raise WhatsAppValidationError(
                        f"Button component at index {i} must contain a non-empty 'parameters' list."
                    )

                if sub_type == "quick_reply":
                    for p_idx, p in enumerate(params):
                        if not isinstance(p, dict) or p.get("type") != "payload" or not str(p.get("payload", "")).strip():
                            raise WhatsAppValidationError(
                                f"Quick reply button parameter {p_idx} must have type='payload' with non-empty 'payload'."
                            )
                elif sub_type == "url":
                    for p_idx, p in enumerate(params):
                        if not isinstance(p, dict) or p.get("type") != "text" or not str(p.get("text", "")).strip():
                            raise WhatsAppValidationError(
                                f"URL button parameter {p_idx} must have type='text' with non-empty 'text' parameter."
                            )
                        url_param = str(p.get("text", ""))
                        if re.search(r"[\s\r\n]", url_param):
                            raise WhatsAppValidationError(
                                f"Dynamic URL button parameter must not contain whitespace or newlines: {url_param!r}."
                            )

            validated.append(comp)

        return validated

    @staticmethod
    def build_body_component(parameters: List[Union[str, Dict[str, Any]]]) -> Dict[str, Any]:
        """Constructs a validated body component from a list of text strings or parameter dicts."""
        formatted_params = []
        for p in parameters:
            if isinstance(p, str):
                formatted_params.append({"type": "text", "text": p})
            elif isinstance(p, dict):
                formatted_params.append(p)
            else:
                formatted_params.append({"type": "text", "text": str(p)})
        return {"type": "body", "parameters": formatted_params}

    @staticmethod
    def build_header_component(
        text: Optional[str] = None,
        media_type: Optional[str] = None,
        media_url: Optional[str] = None,
        media_id: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Constructs a validated header component (text or media)."""
        if text:
            return {"type": "header", "parameters": [{"type": "text", "text": text}]}
        elif media_type and (media_url or media_id):
            media_obj: Dict[str, Any] = {}
            if media_url:
                media_obj["link"] = media_url
            if media_id:
                media_obj["id"] = media_id
            if filename and media_type == "document":
                media_obj["filename"] = filename
            return {"type": "header", "parameters": [{"type": media_type, media_type: media_obj}]}
        raise WhatsAppValidationError("Header component requires text or media parameters.")

    @staticmethod
    def build_url_button_component(index: Union[int, str], url_parameter: str) -> Dict[str, Any]:
        """Constructs a validated dynamic URL button component."""
        idx_str = str(index).strip()
        try:
            idx_int = int(idx_str)
            if idx_int < 0 or idx_int > 9:
                raise ValueError()
        except (ValueError, TypeError):
            raise WhatsAppValidationError(f"Button index must be an integer 0..9, got {index!r}.")

        clean_param = str(url_parameter).strip()
        if not clean_param:
            raise WhatsAppValidationError("Dynamic URL parameter cannot be empty.")
        if re.search(r"[\s\r\n]", clean_param):
            raise WhatsAppValidationError(f"Dynamic URL parameter cannot contain whitespace or newlines: {clean_param!r}")
        return {
            "type": "button",
            "sub_type": "url",
            "index": str(idx_int),
            "parameters": [{"type": "text", "text": clean_param}],
        }

    @staticmethod
    def build_quick_reply_button_component(index: Union[int, str], payload: str) -> Dict[str, Any]:
        """Constructs a validated quick reply button component."""
        idx_str = str(index).strip()
        try:
            idx_int = int(idx_str)
            if idx_int < 0 or idx_int > 9:
                raise ValueError()
        except (ValueError, TypeError):
            raise WhatsAppValidationError(f"Button index must be an integer 0..9, got {index!r}.")

        clean_payload = str(payload).strip()
        if not clean_payload:
            raise WhatsAppValidationError("Quick reply payload cannot be empty.")
        return {
            "type": "button",
            "sub_type": "quick_reply",
            "index": str(idx_int),
            "parameters": [{"type": "payload", "payload": clean_payload}],
        }

    def send_template_message(
        self,
        to_phone: str,
        template_name: str,
        language_code: str = "en",
        components: Optional[List[Dict[str, Any]]] = None,
    ) -> WhatsAppDispatchResult:
        """
        Sends pre-approved WhatsApp Business message template.
        Required by Meta for initiating conversations outside the 24-hour service window.
        """
        clean_phone = self.sanitize_phone_number(to_phone)
        valid_name = self.validate_template_name(template_name)
        valid_lang = self.validate_language_code(language_code)
        valid_components = self.validate_template_components(components)

        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_phone,
            "type": "template",
            "template": {
                "name": valid_name,
                "language": {"code": valid_lang},
            },
        }
        if valid_components:
            payload["template"]["components"] = valid_components

        logger.info(
            f"send_template_message: dispatching template '{valid_name}' ({valid_lang}) "
            f"to {clean_phone[:4]}***{clean_phone[-2:]}"
        )
        return self._send_payload(payload)

    def send_prepared_payload(self, payload: Dict[str, Any]) -> WhatsAppDispatchResult:
        """
        Dispatches a pre-formed, operator-approved Meta WhatsApp Cloud API payload verbatim.

        Used exclusively for Mode B (pre-formed direct payloads) where the complete message
        structure was approved and cryptographically locked by an operator prior to dispatch.

        Validates minimum required structure, normalizes the 'to' phone number (digits only,
        no content change), and delegates to _send_payload() using the centrally configured
        token and phone_number_id.  Does NOT modify message content, template fields, or any
        other approved field beyond normalizing the recipient phone to E.164 digit format.

        Args:
            payload: A dict representing a complete Meta WhatsApp Cloud API message object.
                     Required keys: 'messaging_product' == 'whatsapp', 'to', 'type'.
                     At least one of 'text' or 'template' must be present.

        Returns:
            WhatsAppDispatchResult with wamid, recipient, and status.

        Raises:
            WhatsAppValidationError: If minimum structural requirements are not met.
            WhatsAppDeliveryError: If the recipient phone is invalid or Meta rejects delivery.
            WhatsAppRateLimitError: If Meta rate-limits the request.
            WhatsAppAuthError: If the access token is absent or rejected.
        """
        if not isinstance(payload, dict):
            raise WhatsAppValidationError("send_prepared_payload requires a dict payload.")
        if payload.get("messaging_product") != "whatsapp":
            raise WhatsAppValidationError(
                "Payload 'messaging_product' must be 'whatsapp'; "
                f"got: {payload.get('messaging_product')!r}"
            )
        if not payload.get("to"):
            raise WhatsAppValidationError("Payload must contain a non-empty 'to' phone number.")
        if "type" not in payload:
            raise WhatsAppValidationError("Payload must contain a 'type' field.")
        if payload.get("type") not in ("text", "template", "image", "document", "audio", "video", "interactive", "reaction", "sticker"):
            raise WhatsAppValidationError(
                f"Unsupported payload type: {payload.get('type')!r}. "
                "Expected one of: text, template, image, document, audio, video, interactive."
            )

        if payload.get("type") == "template":
            tpl_obj = payload.get("template")
            if not isinstance(tpl_obj, dict):
                raise WhatsAppValidationError("Template payload must contain a 'template' object.")
            self.validate_template_name(tpl_obj.get("name", ""))
            lang_obj = tpl_obj.get("language")
            if not isinstance(lang_obj, dict) or not lang_obj.get("code"):
                raise WhatsAppValidationError("Template object must contain a 'language' dict with 'code'.")
            self.validate_language_code(lang_obj.get("code", ""))
            if "components" in tpl_obj:
                self.validate_template_components(tpl_obj.get("components"))

        # Normalize recipient phone number to E.164 digits (raises WhatsAppDeliveryError if invalid)
        raw_to = str(payload["to"])
        normalized_to = self.sanitize_phone_number(raw_to)

        # Build final payload with normalized phone; preserve all other approved fields verbatim
        final_payload = dict(payload)
        final_payload["to"] = normalized_to

        logger.info(
            f"send_prepared_payload: dispatching pre-approved {payload.get('type')!r} payload "
            f"verbatim to {normalized_to[:4]}***{normalized_to[-2:]} "
            f"(type={payload.get('type')}, product={payload.get('messaging_product')})"
        )
        return self._send_payload(final_payload)

    def send_recovery_reminder(
        self,
        to_phone: str,
        customer_name: str,
        amount_str: str,
        payment_link: str,
        merchant_name: str = "Merchant",
        template_name: Optional[str] = None,
        language_code: str = "en",
        enforce_24h_window: Optional[bool] = None,
        components: Optional[List[Dict[str, Any]]] = None,
        current_time: Optional[Union[float, datetime]] = None,
        inbound_timestamp: Optional[Union[float, datetime, str]] = None,
    ) -> WhatsAppDispatchResult:
        """
        Constructs and dispatches autonomous payment recovery reminder.
        Supports approved templates and rich text message formats with 1-click link.
        
        Meta Platform Policy:
        - Freeform text messages are only permitted within 24 hours of customer's last interaction.
        - Outside the 24-hour window, an approved template (e.g. 'payment_recovery_v1') must be used.
        """
        clean_phone = self.sanitize_phone_number(to_phone)
        settings = get_settings()
        should_enforce = (
            enforce_24h_window
            if enforce_24h_window is not None
            else getattr(settings, "whatsapp_enforce_24h_window", False)
        )

        if should_enforce:
            from wapsi.integrations.whatsapp.service_window import CustomerServiceWindowRouter
            router = CustomerServiceWindowRouter(
                default_template_name=template_name,
                default_language_code=language_code,
            )
            decision = router.route_outbound_recovery(
                phone=clean_phone,
                requested_template=template_name,
                language_code=language_code,
                last_inbound=inbound_timestamp,
                current_time=current_time,
            )

            if not decision.is_window_open and template_name is None:
                raise WhatsAppDeliveryError(
                    "Meta Policy Violation: Customer is outside the 24-hour service window and freeform text messages are prohibited. Fallback requires manual review."
                )

            if decision.requires_manual_review:
                raise WhatsAppDeliveryError(
                    f"Meta Policy Violation: Customer is outside the 24-hour service window. {decision.reason}"
                )

            if decision.message_type == "template":
                tpl_name = decision.template_name or "payment_recovery_v1"
                tpl_components = components or [
                    self.build_body_component([
                        customer_name,
                        merchant_name,
                        amount_str,
                        payment_link,
                    ])
                ]
                return self.send_template_message(
                    to_phone=clean_phone,
                    template_name=tpl_name,
                    language_code=decision.language_code,
                    components=tpl_components,
                )

        if template_name:
            # Structure components for standard utility template
            tpl_components = components or [
                self.build_body_component([
                    customer_name,
                    merchant_name,
                    amount_str,
                    payment_link,
                ])
            ]
            return self.send_template_message(
                to_phone=clean_phone,
                template_name=template_name,
                language_code=language_code,
                components=tpl_components,
            )

        # High-impact rich text fallback format
        body_text = (
            f"Hi {customer_name},\n\n"
            f"We noticed your payment of {amount_str} to {merchant_name} could not be completed.\n\n"
            f"You can quickly finish your payment using this secure 1-click Razorpay link:\n"
            f"{payment_link}\n\n"
            f"This link expires in 15 minutes.\n"
            f"(Reply STOP to unsubscribe from payment updates)"
        )
        return self.send_text_message(to_phone=clean_phone, body_text=body_text, preview_url=True)
