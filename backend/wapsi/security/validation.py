"""
Security Validation & Governance Utilities.
Provides constant-time HMAC SHA-256 raw-body webhook validation, replay protection,
rate limiting, and fail-closed safety handlers.
"""

from __future__ import annotations

from typing import Dict, Any, Optional, Union, Set
import hmac
import hashlib
import time
from collections import defaultdict
from wapsi.core.config import get_settings


class WebhookValidator:
    """
    Validates cryptographic authenticity of incoming payment gateway webhooks
    using raw request bytes and constant-time HMAC-SHA256 comparison.
    """

    @classmethod
    def compute_signature(cls, raw_bytes: bytes, secret: Union[str, bytes]) -> str:
        """Computes HMAC-SHA256 signature over raw request bytes."""
        secret_bytes = secret if isinstance(secret, bytes) else secret.encode("utf-8")
        return hmac.new(secret_bytes, raw_bytes, hashlib.sha256).hexdigest()

    @classmethod
    def verify_signature(
        cls,
        payload_bytes: bytes,
        signature: Optional[str],
        secret: Optional[Union[str, bytes]] = None
    ) -> bool:
        """
        Verifies HMAC-SHA256 signature against expected secret.
        Uses constant-time comparison (hmac.compare_digest) to prevent timing attacks.
        """
        if not signature or not payload_bytes:
            return False

        if secret is None:
            secret = get_settings().get_webhook_secret_bytes()
        elif isinstance(secret, str):
            secret = secret.encode("utf-8")

        if not secret:
            return False

        expected_sig = cls.compute_signature(payload_bytes, secret)
        return hmac.compare_digest(expected_sig, signature.strip())

    @classmethod
    def validate_timestamp_freshness(cls, event_timestamp: int, max_age_seconds: int = 300) -> bool:
        """Enforces timestamp freshness window (default: within 300 seconds of current time)."""
        now = int(time.time())
        return abs(now - event_timestamp) <= max_age_seconds


class AntiReplayCache:
    """
    In-memory bounded anti-replay deduplication cache for webhook nonces and event IDs.
    """

    def __init__(self, max_entries: int = 20000, ttl_seconds: int = 86400):
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self.seen_events: Dict[str, float] = {}

    def is_duplicate(self, event_key: str) -> bool:
        """Checks if event key has already been seen within TTL window."""
        now = time.time()
        self._prune(now)
        if event_key in self.seen_events:
            if now - self.seen_events[event_key] <= self.ttl_seconds:
                return True
        self.seen_events[event_key] = now
        return False

    def check_and_record(self, event_key: str) -> bool:
        """Returns True if allowed (not duplicate), False if duplicate."""
        return not self.is_duplicate(event_key)

    def _prune(self, now: float):
        """Prunes expired keys if cache exceeds threshold or expired entries exist."""
        cutoff = now - self.ttl_seconds
        if len(self.seen_events) > self.max_entries or any(v <= cutoff for v in self.seen_events.values()):
            self.seen_events = {k: v for k, v in self.seen_events.items() if v > cutoff}


class InMemoryRateLimiter:
    """
    Sliding-window rate limiter per tenant / client ID.
    """

    def __init__(self, max_requests_per_minute: int = 120):
        self.max_rpm = max_requests_per_minute
        self.request_timestamps: Dict[str, list] = defaultdict(list)

    def is_allowed(self, client_id: str) -> bool:
        now = time.time()
        cutoff = now - 60.0
        
        # Clean older entries
        self.request_timestamps[client_id] = [
            t for t in self.request_timestamps[client_id] if t > cutoff
        ]
        
        if len(self.request_timestamps[client_id]) >= self.max_rpm:
            return False

        self.request_timestamps[client_id].append(now)
        return True
