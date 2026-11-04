"""
WhatsApp 24-Hour Customer Service Window Router & Policy Engine for WAPSI.

Governs Meta Platform compliance for outbound WhatsApp messaging:
- Meta Cloud API Rule: Freeform session text messages are permitted ONLY
  within 24 hours of the customer's last qualifying inbound message.
- Outside the 24-hour customer service window, only Meta pre-approved templates
  (e.g. 'payment_recovery_v1') are permitted.
- If the customer's inbound timestamp is absent, invalid, or ambiguous, the engine
  fails closed: it does NOT assume the customer service window is open. It routes
  the notification to an eligible pre-approved template, or flags the operation
  for manual operator review if no approved template is configured.
- Boundary condition: Exactly 24.0 hours (86,400.0 seconds).
  <= 86,400.0 seconds: OPEN (freeform permitted)
  > 86,400.0 seconds: EXPIRED (template required)
- Timezone handling: All timestamps are normalized to UTC epoch seconds, eliminating
  any dependence on machine-local timezone assumptions.
"""

from __future__ import annotations

import enum
import logging
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Tuple, Union

from wapsi.core.config import get_settings

logger = logging.getLogger("wapsi.integrations.whatsapp.service_window")

SECONDS_IN_24_HOURS: float = 86400.0
MAX_FUTURE_DRIFT_SECONDS: float = 60.0  # Tolerable clock drift for future-dated timestamps


class WindowStatus(str, enum.Enum):
    """Classification of customer service window based on last qualifying inbound message."""
    OPEN = "OPEN"          # Within permitted 24-hour window
    EXPIRED = "EXPIRED"    # Past 24-hour window
    UNKNOWN = "UNKNOWN"    # No inbound message record found (fail-closed)
    INVALID = "INVALID"    # Timestamp corrupt, unparseable, or nonsensical (fail-closed)


@dataclass(frozen=True)
class WindowRoutingDecision:
    """Outbound recovery routing decision determined by customer service window policy."""
    status: WindowStatus
    is_window_open: bool
    dispatch_channel: str
    message_type: str              # 'text', 'template', 'manual_review'
    template_name: Optional[str]
    language_code: str
    requires_manual_review: bool
    reason: str
    inbound_timestamp_utc: Optional[float]
    evaluated_at_utc: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "is_window_open": self.is_window_open,
            "dispatch_channel": self.dispatch_channel,
            "message_type": self.message_type,
            "template_name": self.template_name,
            "language_code": self.language_code,
            "requires_manual_review": self.requires_manual_review,
            "reason": self.reason,
            "inbound_timestamp_utc": self.inbound_timestamp_utc,
            "evaluated_at_utc": self.evaluated_at_utc,
        }


def normalize_utc_timestamp(ts: Union[float, int, str, datetime, None]) -> Optional[float]:
    """
    Normalizes diverse timestamp representations strictly into a UTC Unix epoch float.

    Supported inputs:
    - float / int Unix epoch seconds (e.g. 1762164000.0)
    - datetime objects (timezone-aware or naive assumed UTC)
    - ISO 8601 strings (e.g. '2026-11-03T10:00:00+05:30', '2026-11-03T04:30:00Z')
    - Numeric strings (e.g. '1762164000')

    Rejects:
    - None
    - Booleans (bool is a subclass of int in Python)
    - NaN, positive/negative infinity
    - Negative or zero epoch values
    - Far-future corruptions (> year 2100 / 4,102,444,800)
    - Malformed / unparseable strings
    """
    if ts is None:
        return None

    if isinstance(ts, bool):
        return None

    epoch_val: Optional[float] = None

    if isinstance(ts, (int, float)):
        if not (math.isnan(ts) or math.isinf(ts)):
            epoch_val = float(ts)

    elif isinstance(ts, datetime):
        try:
            if ts.tzinfo is not None:
                epoch_val = ts.astimezone(timezone.utc).timestamp()
            else:
                epoch_val = ts.replace(tzinfo=timezone.utc).timestamp()
        except (OSError, OverflowError, ValueError):
            return None

    elif isinstance(ts, str):
        cleaned = ts.strip()
        if not cleaned:
            return None

        # 1. Try parsing as numeric epoch
        try:
            num = float(cleaned)
            if not (math.isnan(num) or math.isinf(num)):
                epoch_val = num
        except ValueError:
            pass

        # 2. Try parsing as ISO 8601 string if numeric parsing did not resolve
        if epoch_val is None:
            try:
                iso_str = cleaned.replace("Z", "+00:00")
                dt = datetime.fromisoformat(iso_str)
                if dt.tzinfo is not None:
                    epoch_val = dt.astimezone(timezone.utc).timestamp()
                else:
                    epoch_val = dt.replace(tzinfo=timezone.utc).timestamp()
            except (OSError, OverflowError, ValueError, Exception):
                return None

    if epoch_val is not None:
        # Strictly enforce non-negative, non-zero, non-infinite, bounded to year 2100 (4,102,444,800)
        if 0.0 < epoch_val <= 4102444800.0 and not (math.isnan(epoch_val) or math.isinf(epoch_val)):
            return epoch_val

    return None


def evaluate_customer_service_window(
    phone: str,
    last_inbound_timestamp: Optional[Union[float, int, str, datetime]] = None,
    current_time: Optional[Union[float, int, str, datetime]] = None,
    opt_out_store: Optional[Any] = None,
) -> Tuple[WindowStatus, Optional[float], float]:
    """
    Evaluates the Meta 24-hour customer service window for a given phone number.

    Returns:
        Tuple of (WindowStatus, inbound_timestamp_utc, evaluated_at_utc)

    Boundary Rules:
    - 0 <= (now - last_inbound) <= 86,400.0 seconds: WindowStatus.OPEN
    - (now - last_inbound) > 86,400.0 seconds: WindowStatus.EXPIRED
    - Missing timestamp: WindowStatus.UNKNOWN (fail-closed)
    - Corrupt or future-dated timestamp: WindowStatus.INVALID (fail-closed)
    """
    if current_time is not None:
        now_utc = normalize_utc_timestamp(current_time)
        if now_utc is None:
            return WindowStatus.INVALID, None, time.time()
    else:
        now_utc = time.time()

    # If last_inbound_timestamp was not passed explicitly, attempt lookup in opt_out_store
    inbound_raw = last_inbound_timestamp
    if inbound_raw is None and opt_out_store is not None:
        if hasattr(opt_out_store, "get_last_interaction"):
            inbound_raw = opt_out_store.get_last_interaction(phone)
    elif inbound_raw is None:
        # Check global opt_out_manager fallback
        try:
            from wapsi.integrations.whatsapp.opt_out import get_opt_out_manager
            mgr = get_opt_out_manager()
            if hasattr(mgr, "get_last_interaction"):
                inbound_raw = mgr.get_last_interaction(phone)
        except Exception:
            pass


    if inbound_raw is None:
        return WindowStatus.UNKNOWN, None, now_utc

    inbound_utc = normalize_utc_timestamp(inbound_raw)
    if inbound_utc is None:
        return WindowStatus.INVALID, None, now_utc

    elapsed = now_utc - inbound_utc

    # Future timestamp check (greater than allowed drift)
    if elapsed < -MAX_FUTURE_DRIFT_SECONDS:
        logger.warning(
            f"Customer interaction for {phone[:4]}*** has future-dated timestamp: "
            f"{inbound_utc} vs now {now_utc} (diff: {elapsed:.2f}s). Classified as INVALID."
        )
        return WindowStatus.INVALID, inbound_utc, now_utc

    if elapsed <= SECONDS_IN_24_HOURS:
        return WindowStatus.OPEN, inbound_utc, now_utc
    else:
        return WindowStatus.EXPIRED, inbound_utc, now_utc


class CustomerServiceWindowRouter:
    """
    Routing engine that selects appropriate WhatsApp messaging format (freeform text
    vs pre-approved template vs manual review) based on customer service window status.
    """

    def __init__(
        self,
        opt_out_store: Optional[Any] = None,
        default_template_name: Optional[str] = None,
        default_language_code: Optional[str] = None,
    ):
        self.opt_out_store = opt_out_store
        self._default_template_name = default_template_name
        self._default_language_code = default_language_code

    def get_default_template_name(self) -> Optional[str]:
        if self._default_template_name is not None:
            return self._default_template_name
        settings = get_settings()
        return getattr(settings, "whatsapp_recovery_template_name", None)

    def get_default_language_code(self) -> str:
        if self._default_language_code is not None:
            return self._default_language_code
        settings = get_settings()
        return getattr(settings, "whatsapp_recovery_template_language", "en")

    def route_outbound_recovery(
        self,
        phone: str,
        requested_template: Optional[str] = None,
        language_code: Optional[str] = None,
        last_inbound: Optional[Union[float, int, str, datetime]] = None,
        current_time: Optional[Union[float, int, str, datetime]] = None,
    ) -> WindowRoutingDecision:
        """
        Calculates routing decision for an outbound recovery message.

        Cases:
        - CASE A (Window OPEN):
          Freeform session text permitted. Preserves existing freeform message behavior.
          If caller explicitly requested a template, honours that request.
        - CASE B (Window EXPIRED):
          Pre-approved template required. Resolves template configuration.
          If template is configured, routes to template dispatch.
          If template is unavailable, falls closed to manual review.
        - CASE C (Window UNKNOWN or INVALID):
          Fails closed. Does not assume customer service window is open.
          Prefers eligible pre-approved template, or flags for manual review if unavailable.
        """
        status, inbound_utc, now_utc = evaluate_customer_service_window(
            phone=phone,
            last_inbound_timestamp=last_inbound,
            current_time=current_time,
            opt_out_store=self.opt_out_store,
        )

        lang = language_code or self.get_default_language_code()

        # CASE A: Window is actively OPEN
        if status == WindowStatus.OPEN:
            if requested_template:
                return WindowRoutingDecision(
                    status=status,
                    is_window_open=True,
                    dispatch_channel="whatsapp",
                    message_type="template",
                    template_name=requested_template,
                    language_code=lang,
                    requires_manual_review=False,
                    reason="Customer service window is OPEN; caller explicitly requested template dispatch.",
                    inbound_timestamp_utc=inbound_utc,
                    evaluated_at_utc=now_utc,
                )
            return WindowRoutingDecision(
                status=status,
                is_window_open=True,
                dispatch_channel="whatsapp",
                message_type="text",
                template_name=None,
                language_code=lang,
                requires_manual_review=False,
                reason="Customer service window is OPEN (inbound interaction within 24h). Freeform message permitted.",
                inbound_timestamp_utc=inbound_utc,
                evaluated_at_utc=now_utc,
            )

        # Resolve template name for Case B and Case C
        resolved_template = requested_template or self.get_default_template_name()

        # CASE B: Window is EXPIRED
        if status == WindowStatus.EXPIRED:
            if resolved_template:
                return WindowRoutingDecision(
                    status=status,
                    is_window_open=False,
                    dispatch_channel="whatsapp",
                    message_type="template",
                    template_name=resolved_template,
                    language_code=lang,
                    requires_manual_review=False,
                    reason="Customer service window EXPIRED (> 24h). Routed to approved Meta template.",
                    inbound_timestamp_utc=inbound_utc,
                    evaluated_at_utc=now_utc,
                )
            else:
                return WindowRoutingDecision(
                    status=status,
                    is_window_open=False,
                    dispatch_channel="whatsapp",
                    message_type="manual_review",
                    template_name=None,
                    language_code=lang,
                    requires_manual_review=True,
                    reason="Customer service window EXPIRED and no pre-approved template configured. Operation routed for manual review.",
                    inbound_timestamp_utc=inbound_utc,
                    evaluated_at_utc=now_utc,
                )

        # CASE C: Window is UNKNOWN or INVALID (Fail-Closed)
        if resolved_template:
            reason = (
                f"Customer service window {status.value}. Fail-closed: routed to approved Meta template."
            )
            return WindowRoutingDecision(
                status=status,
                is_window_open=False,
                dispatch_channel="whatsapp",
                message_type="template",
                template_name=resolved_template,
                language_code=lang,
                requires_manual_review=False,
                reason=reason,
                inbound_timestamp_utc=inbound_utc,
                evaluated_at_utc=now_utc,
            )
        else:
            reason = (
                f"Customer service window {status.value} and no pre-approved template configured. "
                "Operation routed for manual review."
            )
            return WindowRoutingDecision(
                status=status,
                is_window_open=False,
                dispatch_channel="whatsapp",
                message_type="manual_review",
                template_name=None,
                language_code=lang,
                requires_manual_review=True,
                reason=reason,
                inbound_timestamp_utc=inbound_utc,
                evaluated_at_utc=now_utc,
            )
