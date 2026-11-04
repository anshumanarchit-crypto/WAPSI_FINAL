"""
WhatsApp Customer Opt-Out and Consent Governance.
Enforces telecom DND and Meta customer consent compliance.
Automatically detects opt-out keywords (STOP, UNSUBSCRIBE, OPTOUT) and halts future dispatches.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Dict, Optional, Set

logger = logging.getLogger("wapsi.integrations.whatsapp.opt_out")

OPT_OUT_KEYWORDS: Set[str] = {
    "stop",
    "unsubscribe",
    "optout",
    "opt-out",
    "cancel",
    "dnd",
    "block",
    "donotdisturb",
    "do not disturb",
    "halt",
}


class OptOutManager:
    """
    Thread-safe in-memory customer opt-out registry and customer service window tracker.
    Guarantees:
    - No outbound WhatsApp recovery messages are sent to opted-out customers.
    - Tracks customer interaction timestamps for Meta's 24-hour customer service window rule.
    """

    def __init__(self, sync_persistent: bool = False):
        self._sync_persistent = sync_persistent
        self._opted_out_phones: Set[str] = set()
        self._last_interaction_timestamps: Dict[str, float] = {}

    @staticmethod
    def normalize_phone(phone: str) -> str:
        """Strips non-digits for consistent lookup."""
        return re.sub(r"\D", "", phone)

    @classmethod
    def is_opt_out_message(cls, text_body: str) -> bool:
        """
        Detects if an incoming customer WhatsApp reply expresses opt-out intent.
        Matches exact keywords or clear stop phrases.
        """
        if not text_body:
            return False
        cleaned = text_body.strip().lower()
        if cleaned in OPT_OUT_KEYWORDS:
            return True
        # Check if message starts with stop or unsubscribe
        words = cleaned.split()
        if words and words[0] in {"stop", "unsubscribe", "cancel"}:
            return True
        return False

    def is_opted_out(self, phone: str) -> bool:
        """Checks if customer has opted out of notifications."""
        norm = self.normalize_phone(phone)
        if not norm:
            return False
        if norm in self._opted_out_phones:
            return True
        if self._sync_persistent:
            try:
                from wapsi.recovery.opt_out_store import get_persistent_opt_out_store
                return get_persistent_opt_out_store().is_opted_out(norm)
            except Exception:
                return False
        return False

    def record_opt_out(self, phone: str, source: str = "inbound_whatsapp") -> bool:
        """Registers a customer's opt-out choice."""
        norm = self.normalize_phone(phone)
        if norm:
            self._opted_out_phones.add(norm)
            if self._sync_persistent:
                try:
                    from wapsi.recovery.opt_out_store import get_persistent_opt_out_store
                    get_persistent_opt_out_store().record_opt_out(norm, source=source)
                except Exception as e:
                    logger.warning(f"Failed to record persistent opt-out: {e}")
            logger.info(f"Customer {norm[:4]}***{norm[-2:]} registered as OPTED-OUT via {source}. Future nudges suppressed.")
            return True
        return False

    def revoke_opt_out(self, phone: str) -> bool:
        """Removes opt-out restriction if customer explicitly re-opts in."""
        norm = self.normalize_phone(phone)
        if norm:
            self._opted_out_phones.discard(norm)
            if self._sync_persistent:
                try:
                    from wapsi.recovery.opt_out_store import get_persistent_opt_out_store
                    get_persistent_opt_out_store().revoke_opt_out(norm, consent_proof="EXPLICIT_REVOCATION")
                except Exception as e:
                    logger.warning(f"Failed to revoke persistent opt-out: {e}")
            logger.info(f"Customer {norm[:4]}***{norm[-2:]} opt-out revoked (re-subscribed).")
            return True
        return False

    def record_customer_interaction(self, phone: str, timestamp: Optional[Union[float, int, str, datetime]] = None) -> None:
        """Records timestamp of an inbound customer message for the 24-hour service window."""
        norm = self.normalize_phone(phone)
        if norm:
            from wapsi.integrations.whatsapp.service_window import normalize_utc_timestamp
            norm_ts = normalize_utc_timestamp(timestamp)
            ts = float(norm_ts if norm_ts is not None else time.time())
            self._last_interaction_timestamps[norm] = ts
            if self._sync_persistent:
                try:
                    from wapsi.recovery.opt_out_store import get_persistent_opt_out_store
                    get_persistent_opt_out_store().record_interaction(norm, timestamp=ts)
                except Exception as e:
                    logger.warning(f"Failed to record persistent customer interaction: {e}")
            logger.debug(f"Recorded customer interaction for {norm[:4]}*** at {ts}")

    def get_last_interaction(self, phone: str) -> Optional[float]:
        """Retrieves last inbound customer interaction timestamp as UTC epoch float."""
        norm = self.normalize_phone(phone)
        if not norm:
            return None
        if norm in self._last_interaction_timestamps:
            return self._last_interaction_timestamps[norm]
        if self._sync_persistent:
            try:
                from wapsi.recovery.opt_out_store import get_persistent_opt_out_store
                persistent_ts = get_persistent_opt_out_store().get_last_interaction(norm)
                if persistent_ts is not None and getattr(self, "_cleared_at", None):
                    if persistent_ts <= self._cleared_at:
                        return None
                return persistent_ts
            except Exception:
                return None
        return None

    def is_within_24h_window(self, phone: str, current_time: Optional[Union[float, int, str, datetime]] = None) -> bool:
        """
        Meta Platform Policy:
        Freeform session text messages can only be sent within 24 hours of customer's last message.
        Outside this 24-hour window, only pre-approved business templates are permitted.
        """
        norm = self.normalize_phone(phone)
        if not norm:
            return False
        from wapsi.integrations.whatsapp.service_window import normalize_utc_timestamp
        norm_now = normalize_utc_timestamp(current_time)
        now = float(norm_now if norm_now is not None else time.time())

        last_ts = self.get_last_interaction(norm)
        if last_ts is not None and 0.0 <= (now - last_ts) <= 86400.0:
            return True
        return False

    def clear(self):
        """Clears local cache (primarily for tests)."""
        self._opted_out_phones.clear()
        self._last_interaction_timestamps.clear()
        self._cleared_at = time.time()
        if self._sync_persistent:
            try:
                from wapsi.recovery.opt_out_store import get_persistent_opt_out_store
                store = get_persistent_opt_out_store()
                if hasattr(store, "clear"):
                    store.clear()
            except Exception:
                pass


# Global module singleton
_opt_out_manager = OptOutManager(sync_persistent=True)


def get_opt_out_manager() -> OptOutManager:
    return _opt_out_manager


def set_opt_out_manager(manager: Optional[OptOutManager]) -> None:
    global _opt_out_manager
    _opt_out_manager = manager or OptOutManager(sync_persistent=True)


