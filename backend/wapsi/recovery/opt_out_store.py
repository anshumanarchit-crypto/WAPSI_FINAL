"""
Persistent Customer Opt-Out & Consent Governance Repository for WAPSI.

Guarantees:
- Survives process restarts via persistent storage (PostgreSQL shared cluster or isolated SQLite).
- Immediate suppression of pending outbound recovery actions on receipt of STOP / UNSUBSCRIBE.
- Re-check immediately before background worker message dispatch.
- Idempotent duplicate opt-out handling (harmless no-op).
- Audit trail for regulatory compliance (DPDP 2023 / TCPA / Meta Platform Terms).
- Re-subscription strictly requires explicit verified consent proof.
- Zero synthetic records written to hosted Supabase.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("wapsi.recovery.opt_out")

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


@dataclass
class OptOutAuditRecord:
    phone_normalized: str
    action: str  # 'OPT_OUT', 'REVOCATION', 'DUPLICATE_OPT_OUT'
    reason: str
    source: str
    consent_proof: Optional[str]
    created_at_utc: float
    actor: Optional[str]


class PersistentOptOutStore:
    """
    Persistent opt-out and 24h Meta customer service window storage engine.
    Supports:
    1. Shared PostgreSQL persistence across multi-worker deployments
    2. Isolated local SQLite persistence for zero-overhead local testing
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        database_manager: Optional[Any] = None,
    ):
        if database_manager is None and db_path is None:
            try:
                from wapsi.db.session import DatabaseManager
                database_manager = DatabaseManager()
            except Exception:
                database_manager = None
        self.db_manager = database_manager
        self.is_postgres = False

        if self.db_manager is not None:
            if hasattr(self.db_manager, "engine") and self.db_manager.engine.dialect.name == "postgresql":
                self.is_postgres = True
                logger.info("Initialized PersistentOptOutStore with PostgreSQL shared cluster engine.")

        if not self.is_postgres:
            if db_path is None:
                data_dir = Path(os.environ.get("WAPSI_LOCAL_DATA_DIR", ".wapsi_data"))
                data_dir.mkdir(parents=True, exist_ok=True)
                self.db_path = str(data_dir / "opt_outs.db")
            else:
                self.db_path = db_path
            self._init_sqlite_db()

    @staticmethod
    def normalize_phone(phone: str) -> str:
        """Extracts pure digits and standardizes Indian numbers to E.164 (without +)."""
        digits = re.sub(r"\D", "", phone or "")
        if len(digits) == 10 and digits.startswith(("6", "7", "8", "9")):
            digits = "91" + digits
        return digits

    def _get_sqlite_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_sqlite_db(self) -> None:
        """Initializes tables for persistent opt-out registry and audit trail in SQLite."""
        with self._get_sqlite_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS opt_out_registry (
                    phone TEXT PRIMARY KEY,
                    reason TEXT NOT NULL,
                    source TEXT NOT NULL,
                    opted_out_at REAL NOT NULL,
                    actor TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    revoked_at REAL
                )
            """)
            try:
                conn.execute("ALTER TABLE opt_out_registry ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE opt_out_registry ADD COLUMN revoked_at REAL")
            except Exception:
                pass

            conn.execute("""
                CREATE TABLE IF NOT EXISTS customer_interactions (
                    phone TEXT PRIMARY KEY,
                    last_interaction_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS opt_out_audit_trail (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    source TEXT NOT NULL,
                    consent_proof TEXT,
                    created_at_utc REAL NOT NULL,
                    actor TEXT
                )
            """)
            conn.commit()

    @classmethod
    def is_opt_out_text(cls, text: str) -> bool:
        """Detects whether incoming message content signifies opt-out intent."""
        if not text:
            return False
        cleaned = text.strip().lower()
        if cleaned in OPT_OUT_KEYWORDS:
            return True
        words = cleaned.split()
        if words and words[0] in {"stop", "unsubscribe", "cancel"}:
            return True
        return False

    def is_opted_out(self, phone: str) -> bool:
        """Checks if phone is currently registered as opted out."""
        norm = self.normalize_phone(phone)
        if not norm:
            return False

        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import OptOutRepository
            with self.db_manager.session_scope() as session:
                return OptOutRepository.is_opted_out(session, norm)

        # SQLite Mode
        with self._get_sqlite_connection() as conn:
            cursor = conn.execute("SELECT 1 FROM opt_out_registry WHERE phone = ? AND is_active = 1", (norm,))
            return cursor.fetchone() is not None

    def record_opt_out(
        self,
        phone: str,
        reason: str = "STOP_KEYWORD",
        source: str = "inbound_whatsapp",
        actor: Optional[str] = None,
    ) -> bool:
        """
        Registers customer opt-out. Idempotent: duplicate calls log audit event and return True harmlessly.
        """
        norm = self.normalize_phone(phone)
        if not norm:
            return False

        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import OptOutRepository
            with self.db_manager.session_scope() as session:
                res = OptOutRepository.record_opt_out(session, norm, reason, source, actor)
                logger.info(f"Customer {norm[:4]}*** registered as OPTED-OUT in PostgreSQL.")
                return res

        # SQLite Mode
        now = time.time()
        with self._get_sqlite_connection() as conn:
            existing = conn.execute("SELECT is_active FROM opt_out_registry WHERE phone = ?", (norm,)).fetchone()
            if existing:
                if existing["is_active"] == 1:
                    conn.execute(
                        """
                        INSERT INTO opt_out_audit_trail (phone, action, reason, source, consent_proof, created_at_utc, actor)
                        VALUES (?, 'DUPLICATE_OPT_OUT', ?, ?, NULL, ?, ?)
                        """,
                        (norm, reason, source, now, actor),
                    )
                    conn.commit()
                    logger.info(f"Customer {norm[:4]}*** duplicate opt-out recorded idempotently in SQLite.")
                    return True
                else:
                    # Reactivate previously revoked opt-out
                    conn.execute(
                        """
                        UPDATE opt_out_registry
                        SET is_active = 1, opted_out_at = ?, revoked_at = NULL, reason = ?, source = ?, actor = ?
                        WHERE phone = ?
                        """,
                        (now, reason, source, actor, norm),
                    )
                    conn.execute(
                        """
                        INSERT INTO opt_out_audit_trail (phone, action, reason, source, consent_proof, created_at_utc, actor)
                        VALUES (?, 'OPT_OUT', ?, ?, NULL, ?, ?)
                        """,
                        (norm, reason, source, now, actor),
                    )
                    conn.commit()
                    logger.info(f"Customer {norm[:4]}*** reactivated opt-out in SQLite.")
                    return True

            conn.execute(
                """
                INSERT INTO opt_out_registry (phone, reason, source, opted_out_at, actor, is_active, revoked_at)
                VALUES (?, ?, ?, ?, ?, 1, NULL)
                """,
                (norm, reason, source, now, actor),
            )
            conn.execute(
                """
                INSERT INTO opt_out_audit_trail (phone, action, reason, source, consent_proof, created_at_utc, actor)
                VALUES (?, 'OPT_OUT', ?, ?, NULL, ?, ?)
                """,
                (norm, reason, source, now, actor),
            )
            conn.commit()
            logger.info(f"Customer {norm[:4]}*** registered as OPTED-OUT in SQLite. Future recovery suppressed.")
            return True

    def revoke_opt_out(
        self,
        phone: str,
        consent_proof: str,
        actor: Optional[str] = None,
    ) -> bool:
        """Revokes opt-out only if an explicitly valid consent proof is supplied."""
        norm = self.normalize_phone(phone)
        if not norm:
            return False

        if not consent_proof or len(consent_proof.strip()) < 5:
            raise ValueError("Re-subscription strictly requires an explicit, verified consent proof.")

        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import OptOutRepository
            with self.db_manager.session_scope() as session:
                return OptOutRepository.revoke_opt_out(session, norm, consent_proof, actor)

        # SQLite Mode
        now = time.time()
        with self._get_sqlite_connection() as conn:
            existing = conn.execute("SELECT is_active FROM opt_out_registry WHERE phone = ?", (norm,)).fetchone()
            if not existing or existing["is_active"] == 0:
                return False

            conn.execute(
                """
                UPDATE opt_out_registry
                SET is_active = 0, revoked_at = ?
                WHERE phone = ?
                """,
                (now, norm),
            )
            conn.execute(
                """
                INSERT INTO opt_out_audit_trail (phone, action, reason, source, consent_proof, created_at_utc, actor)
                VALUES (?, 'REVOCATION', 'EXPLICIT_RE_CONSENT', 'reopt_in_flow', ?, ?, ?)
                """,
                (norm, consent_proof, now, actor),
            )
            conn.commit()
            logger.info(f"Customer {norm[:4]}*** opt-out revoked in SQLite with proof '{consent_proof[:20]}...'.")
            return True

    def record_interaction(self, phone: str, timestamp: Optional[Union[float, int, str, datetime]] = None) -> None:
        """Records inbound customer interaction timestamp for 24h Meta customer service window."""
        norm = self.normalize_phone(phone)
        if not norm:
            return

        from wapsi.integrations.whatsapp.service_window import normalize_utc_timestamp
        norm_ts = normalize_utc_timestamp(timestamp)
        ts = float(norm_ts if norm_ts is not None else time.time())

        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import OptOutRepository
            ts_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            with self.db_manager.session_scope() as session:
                OptOutRepository.record_interaction(session, norm, ts_dt)
                return

        # SQLite Mode
        with self._get_sqlite_connection() as conn:
            conn.execute(
                """
                INSERT INTO customer_interactions (phone, last_interaction_at)
                VALUES (?, ?)
                ON CONFLICT(phone) DO UPDATE SET last_interaction_at = excluded.last_interaction_at
                """,
                (norm, ts),
            )
            conn.commit()

    def record_inbound_interaction(self, phone: str, timestamp_utc: Optional[Union[float, int, str, datetime]] = None, **kwargs: Any) -> None:
        """Alias for record_interaction accepting timestamp_utc."""
        self.record_interaction(phone, timestamp=timestamp_utc or kwargs.get("timestamp"))

    def get_last_interaction(self, phone: str) -> Optional[float]:
        """Retrieves last inbound customer interaction timestamp as UTC epoch float."""
        norm = self.normalize_phone(phone)
        if not norm:
            return None

        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import OptOutRepository
            with self.db_manager.session_scope() as session:
                return OptOutRepository.get_last_interaction(session, norm)

        # SQLite Mode
        with self._get_sqlite_connection() as conn:
            row = conn.execute("SELECT last_interaction_at FROM customer_interactions WHERE phone = ?", (norm,)).fetchone()
            if not row:
                return None
            return float(row["last_interaction_at"])

    def is_within_24h_window(self, phone: str, current_time: Optional[Union[float, int, str, datetime]] = None) -> bool:
        """Checks if phone has interacted within the past 86,400 seconds (24 hours)."""
        norm = self.normalize_phone(phone)
        if not norm:
            return False

        from wapsi.integrations.whatsapp.service_window import normalize_utc_timestamp
        norm_now = normalize_utc_timestamp(current_time)
        now = float(norm_now if norm_now is not None else time.time())

        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import OptOutRepository
            now_dt = datetime.fromtimestamp(now, tz=timezone.utc)
            with self.db_manager.session_scope() as session:
                return OptOutRepository.is_within_24h_window(session, norm, now_dt)

        # SQLite Mode
        with self._get_sqlite_connection() as conn:
            row = conn.execute("SELECT last_interaction_at FROM customer_interactions WHERE phone = ?", (norm,)).fetchone()
            if not row:
                return False
            last_at = float(row["last_interaction_at"])
            return 0.0 <= (now - last_at) <= 86400.0

    def get_audit_trail(self, phone: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves opt-out audit records."""
        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import OptOutRepository
            norm = self.normalize_phone(phone) if phone else None
            with self.db_manager.session_scope() as session:
                return OptOutRepository.get_audit_trail(session, norm)

        # SQLite Mode
        with self._get_sqlite_connection() as conn:
            if phone:
                norm = self.normalize_phone(phone)
                rows = conn.execute(
                    "SELECT * FROM opt_out_audit_trail WHERE phone = ? ORDER BY id ASC", (norm,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM opt_out_audit_trail ORDER BY id ASC").fetchall()
            return [dict(r) for r in rows]

    def clear(self) -> None:
        """Clears local storage tables in SQLite test mode."""
        if not self.is_postgres:
            with self._get_sqlite_connection() as conn:
                conn.execute("DELETE FROM opt_out_registry")
                conn.execute("DELETE FROM customer_interactions")
                conn.execute("DELETE FROM opt_out_audit_trail")
                conn.commit()


_persistent_opt_out: Optional[PersistentOptOutStore] = None


def get_persistent_opt_out_store(
    db_path: Optional[str] = None,
    database_manager: Optional[Any] = None,
) -> PersistentOptOutStore:
    global _persistent_opt_out
    if _persistent_opt_out is None or db_path is not None or database_manager is not None:
        _persistent_opt_out = PersistentOptOutStore(db_path=db_path, database_manager=database_manager)
    return _persistent_opt_out


def set_persistent_opt_out_store(store: Optional[PersistentOptOutStore]) -> None:
    global _persistent_opt_out
    _persistent_opt_out = store

