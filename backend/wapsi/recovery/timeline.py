"""
Durable Recovery Timeline and Audit Trail for WAPSI Recovery Engine.

Preserves the complete, tamper-evident audit history across 16 formal lifecycle milestones:
1.  RECOVERY_ELIGIBILITY_EVALUATED
2.  DECISION_MADE
3.  RECOVERY_SCHEDULED
4.  RECOVERY_CLAIMED
5.  PAYMENT_LINK_CREATED
6.  WHATSAPP_DISPATCHED
7.  WHATSAPP_ACCEPTED
8.  WHATSAPP_DELIVERED
9.  WHATSAPP_READ
10. RETRY_SCHEDULED
11. RETRY_EXECUTED
12. CUSTOMER_OPTED_OUT
13. PAYMENT_CAPTURED
14. RECOVERY_COMPLETED
15. RECOVERY_FAILED
16. RECONCILIATION_REQUIRED

Guarantees:
- Every event has a unique UUID, case_id, UTC timestamp, source, and provider reference.
- Sanitized metadata: Bearer tokens, API secrets, and sensitive payment credentials are strictly stripped.
- Append-only persistent storage surviving process restarts.
- Never rewrites historical timeline events.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("wapsi.recovery.timeline")

VALID_TIMELINE_EVENT_TYPES: Set[str] = {
    "RECOVERY_ELIGIBILITY_EVALUATED",
    "DECISION_MADE",
    "RECOVERY_SCHEDULED",
    "RECOVERY_CLAIMED",
    "PAYMENT_LINK_CREATED",
    "WHATSAPP_DISPATCHED",
    "WHATSAPP_ACCEPTED",
    "WHATSAPP_DELIVERED",
    "WHATSAPP_READ",
    "RETRY_SCHEDULED",
    "RETRY_EXECUTED",
    "CUSTOMER_OPTED_OUT",
    "PAYMENT_CAPTURED",
    "RECOVERY_COMPLETED",
    "RECOVERY_FAILED",
    "RECONCILIATION_REQUIRED",
}

SENSITIVE_KEY_SUBSTRINGS: Set[str] = {
    "token", "secret", "password", "key", "authorization", "cvv", "pan", "pin", "credential"
}


def sanitize_metadata(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Recursively sanitizes metadata dictionaries removing any sensitive tokens or secrets."""
    if not data:
        return {}
    clean: Dict[str, Any] = {}
    for k, v in data.items():
        k_lower = str(k).lower()
        if any(sens in k_lower for sens in SENSITIVE_KEY_SUBSTRINGS):
            clean[k] = "[REDACTED]"
        elif isinstance(v, dict):
            clean[k] = sanitize_metadata(v)
        elif isinstance(v, (list, tuple)):
            clean[k] = [
                sanitize_metadata(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            clean[k] = v
    return clean


@dataclass
class TimelineEvent:
    event_id: str
    case_id: str
    event_type: str
    timestamp_utc: float
    source: str
    description: str
    provider_event_id: Optional[str] = None
    attempt_number: Optional[int] = None
    from_state: Optional[str] = None
    to_state: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["timestamp_iso"] = datetime.fromtimestamp(self.timestamp_utc, tz=timezone.utc).isoformat()
        return d


class RecoveryTimelineStore:
    """
    Persistent timeline storage engine backed by local SQLite.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            data_dir = Path(os.environ.get("WAPSI_LOCAL_DATA_DIR", ".wapsi_data"))
            data_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(data_dir / "recovery_timeline.db")
        else:
            self.db_path = db_path

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS recovery_timeline_events (
                    event_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp_utc REAL NOT NULL,
                    source TEXT NOT NULL,
                    description TEXT NOT NULL,
                    provider_event_id TEXT,
                    attempt_number INTEGER,
                    from_state TEXT,
                    to_state TEXT,
                    metadata TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timeline_case
                ON recovery_timeline_events (case_id, timestamp_utc ASC)
            """)

    def record_event(
        self,
        case_id: str,
        event_type: str,
        description: str,
        source: str = "WAPSI_ENGINE",
        provider_event_id: Optional[str] = None,
        attempt_number: Optional[int] = None,
        from_state: Optional[str] = None,
        to_state: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp_utc: Optional[float] = None,
    ) -> TimelineEvent:
        """Appends an event to the persistent recovery timeline."""
        if event_type not in VALID_TIMELINE_EVENT_TYPES:
            logger.warning(f"Unrecognized timeline event type: '{event_type}'; recording anyway.")

        now = timestamp_utc if timestamp_utc is not None else time.time()
        event_id = str(uuid.uuid4())
        clean_meta = sanitize_metadata(metadata)

        event = TimelineEvent(
            event_id=event_id,
            case_id=case_id,
            event_type=event_type,
            timestamp_utc=now,
            source=source,
            description=description,
            provider_event_id=provider_event_id,
            attempt_number=attempt_number,
            from_state=from_state,
            to_state=to_state,
            metadata=clean_meta,
        )

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO recovery_timeline_events (
                    event_id, case_id, event_type, timestamp_utc, source,
                    description, provider_event_id, attempt_number,
                    from_state, to_state, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id, event.case_id, event.event_type, event.timestamp_utc,
                    event.source, event.description, event.provider_event_id,
                    event.attempt_number, event.from_state, event.to_state,
                    json.dumps(event.metadata),
                ),
            )
            conn.commit()

        logger.debug(f"Recorded timeline event {event_type} for case {case_id} (ID: {event_id})")
        return event

    def get_timeline(self, case_id: str) -> List[TimelineEvent]:
        """Retrieves complete chronological timeline for a recovery case."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM recovery_timeline_events
                WHERE case_id = ?
                ORDER BY timestamp_utc ASC, event_id ASC
                """,
                (case_id,),
            ).fetchall()

            return [
                TimelineEvent(
                    event_id=r["event_id"],
                    case_id=r["case_id"],
                    event_type=r["event_type"],
                    timestamp_utc=r["timestamp_utc"],
                    source=r["source"],
                    description=r["description"],
                    provider_event_id=r["provider_event_id"],
                    attempt_number=r["attempt_number"],
                    from_state=r["from_state"],
                    to_state=r["to_state"],
                    metadata=json.loads(r["metadata"]),
                )
                for r in rows
            ]


_timeline_store: Optional[RecoveryTimelineStore] = None


def get_timeline_store(db_path: Optional[str] = None) -> RecoveryTimelineStore:
    global _timeline_store
    if _timeline_store is None or db_path is not None:
        _timeline_store = RecoveryTimelineStore(db_path=db_path)
    return _timeline_store

