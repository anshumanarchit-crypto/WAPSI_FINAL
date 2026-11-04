"""
Durable Transactional Outbox Pattern for WAPSI Recovery Engine.

Guarantees:
- Atomically claims pending jobs using dialect-appropriate locking:
  * PostgreSQL: Genuine SELECT ... FOR UPDATE SKIP LOCKED
  * SQLite: BEGIN IMMEDIATE exclusive transaction
- Enforces worker leasing (worker_id and lease_expires_at) to prevent concurrent dispatches.
- Recovers abandoned jobs after worker crashes.
- Bounded exponential backoff with jitter and provider Retry-After honor.
- Distinguishes retryable errors from permanent errors (DEAD_LETTER).
- Supports ambiguous network outcome handling (RECONCILIATION_REQUIRED).
- Supports both shared PostgreSQL runtime persistence and isolated SQLite persistence.
- Zero synthetic records written to hosted Supabase.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

logger = logging.getLogger("wapsi.recovery.outbox")


def compute_approval_hash(
    recipient_masked: str,
    channel: str,
    message_payload: Dict[str, Any],
    decision_id: Optional[str] = None,
    **kwargs: Any,
) -> str:
    """Computes deterministic SHA-256 hash of dispatch payload to detect any material tampering."""
    # Allow flexible parameter aliasing
    recipient_final = recipient_masked or kwargs.get("recipient", "")
    payload_final = message_payload if message_payload is not None else kwargs.get("payload", {})
    canonical_payload = json.dumps(payload_final, sort_keys=True, separators=(',', ':'))
    content = f"{recipient_final}:{channel.lower()}:{canonical_payload}:{decision_id or ''}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass
class OutboxJob:
    """Represents a durable outbox unit of recovery work."""
    id: str
    case_id: str
    payment_id: str
    merchant_id: str
    idempotency_key: str
    action: str
    channel: str
    recipient_masked: str
    message_payload: Dict[str, Any]
    status: str  # PENDING_APPROVAL, QUEUED, SENDING, SENT, FAILED, RETRY, DEAD_LETTER, RECONCILIATION_REQUIRED, CANCELLED, REJECTED
    retry_count: int
    max_retries: int
    next_attempt_at: float
    lease_expires_at: Optional[float]
    worker_id: Optional[str]
    last_error: Optional[str]
    created_at: float
    updated_at: float
    requires_operator_approval: bool = True
    approved_by_operator_id: Optional[str] = None
    approved_at: Optional[float] = None
    approval_snapshot_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _model_to_job(m: Any) -> OutboxJob:
    """Helper converting RecoveryOutboxModel ORM instance to OutboxJob dataclass."""
    next_ts = m.next_attempt_at.timestamp() if m.next_attempt_at else time.time()
    lease_ts = m.lease_expires_at.timestamp() if m.lease_expires_at else None
    created_ts = m.created_at.timestamp() if m.created_at else time.time()
    updated_ts = m.updated_at.timestamp() if m.updated_at else time.time()
    approved_ts = m.approved_at.timestamp() if getattr(m, "approved_at", None) else None
    return OutboxJob(
        id=str(m.id),
        case_id=m.case_id or "",
        payment_id=m.payment_id or "",
        merchant_id=str(m.merchant_id),
        idempotency_key=m.idempotency_key,
        action=m.action,
        channel=m.channel,
        recipient_masked=m.recipient_masked,
        message_payload=m.message_payload if isinstance(m.message_payload, dict) else {},
        status=m.status,
        retry_count=m.retry_count,
        max_retries=m.max_retries,
        next_attempt_at=next_ts,
        lease_expires_at=lease_ts,
        worker_id=m.worker_id,
        last_error=m.last_error,
        created_at=created_ts,
        updated_at=updated_ts,
        requires_operator_approval=getattr(m, "requires_operator_approval", True),
        approved_by_operator_id=getattr(m, "approved_by_operator_id", None),
        approved_at=approved_ts,
        approval_snapshot_hash=getattr(m, "approval_snapshot_hash", None),
    )


class DurableOutboxStore:
    """
    Persistent outbox storage engine supporting both:
    1. Genuine PostgreSQL runtime persistence (SELECT ... FOR UPDATE SKIP LOCKED)
    2. Isolated local SQLite persistence (BEGIN IMMEDIATE)
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        database_manager: Optional[Any] = None,
    ):
        self.db_manager = database_manager
        self.is_postgres = False

        if self.db_manager is not None:
            if hasattr(self.db_manager, "engine") and self.db_manager.engine.dialect.name == "postgresql":
                self.is_postgres = True
                logger.info("Initialized DurableOutboxStore with PostgreSQL FOR UPDATE SKIP LOCKED engine.")

        if not self.is_postgres:
            if db_path is None:
                data_dir = Path(os.environ.get("WAPSI_LOCAL_DATA_DIR", ".wapsi_data"))
                data_dir.mkdir(parents=True, exist_ok=True)
                self.db_path = str(data_dir / "recovery_outbox.db")
            else:
                self.db_path = db_path
            self._init_sqlite_db()

    def _get_sqlite_connection(self) -> sqlite3.Connection:
        if not getattr(self, "db_path", None):
            data_dir = Path(os.environ.get("WAPSI_LOCAL_DATA_DIR", ".wapsi_data"))
            data_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(data_dir / "recovery_outbox.db")
            self._init_sqlite_db()
        conn = sqlite3.connect(self.db_path, timeout=15.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_sqlite_db(self) -> None:
        with self._get_sqlite_connection() as conn:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS recovery_outbox (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    payment_id TEXT NOT NULL,
                    merchant_id TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    action TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    recipient_masked TEXT NOT NULL,
                    message_payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    max_retries INTEGER NOT NULL DEFAULT 3,
                    next_attempt_at REAL NOT NULL,
                    lease_expires_at REAL,
                    worker_id TEXT,
                    last_error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    requires_operator_approval INTEGER NOT NULL DEFAULT 1,
                    approved_by_operator_id TEXT,
                    approved_at REAL,
                    approval_snapshot_hash TEXT
                )
            """)
            # Apply additive columns to existing SQLite tables if missing
            for col, col_type in [
                ("requires_operator_approval", "INTEGER NOT NULL DEFAULT 1"),
                ("approved_by_operator_id", "TEXT"),
                ("approved_at", "REAL"),
                ("approval_snapshot_hash", "TEXT"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE recovery_outbox ADD COLUMN {col} {col_type};")
                except Exception:
                    pass

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_outbox_claiming
                ON recovery_outbox (status, next_attempt_at, lease_expires_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_outbox_case
                ON recovery_outbox (case_id)
            """)

    def _resolve_merchant_uuid(self, session: Session, merchant_id_raw: str) -> uuid.UUID:
        """Resolves merchant string identifier or code to persistent merchant UUID."""
        from wapsi.core.config import get_settings, is_dev_fallback_permitted
        settings = get_settings()

        # 1. Resolve standard default merchant aliases to configured default merchant UUID (dev only)
        if merchant_id_raw in ("default_merchant", "default", None, ""):
            if is_dev_fallback_permitted(settings):
                try:
                    return uuid.UUID(settings.default_merchant_id)
                except Exception:
                    pass
            else:
                raise PermissionError("Cannot resolve default merchant UUID without explicit merchant context in production.")

        from wapsi.db.repository import MerchantRepository
        try:
            return uuid.UUID(str(merchant_id_raw))
        except (ValueError, TypeError):
            pass

        # Try looking up by merchant_code
        m = MerchantRepository.get_by_code(session, merchant_id_raw)
        if m:
            return m.id

        # Fallback to default merchant only in dev fallback mode
        if is_dev_fallback_permitted(settings):
            default_m = MerchantRepository.get_or_create_default(session)
            return default_m.id
        raise PermissionError(f"Merchant '{merchant_id_raw}' not found in registry. Fail closed in production.")

    def enqueue(
        self,
        case_id: str,
        payment_id: str,
        idempotency_key: str,
        action: str,
        channel: str,
        recipient_masked: str,
        message_payload: Dict[str, Any],
        merchant_id: str = "default_merchant",
        max_retries: int = 3,
        delay_seconds: int = 0,
        decision_id: Optional[Any] = None,
        status: Optional[str] = None,
        requires_operator_approval: Optional[bool] = None,
        approved_by_operator_id: Optional[str] = None,
    ) -> OutboxJob:
        """Enqueues a new recovery action into the outbox with operator authorization safeguards."""
        now = time.time()
        job_id = str(uuid.uuid4())
        next_attempt = now + max(0, delay_seconds)

        is_contact = channel.lower() in ("whatsapp", "sms", "voice", "email")
        req_approval = is_contact if requires_operator_approval is None else requires_operator_approval

        if status is not None:
            final_status = status
            approved_at_ts = now if approved_by_operator_id else None
            appr_hash = compute_approval_hash(recipient_masked, channel, message_payload, str(decision_id) if decision_id else None) if approved_by_operator_id else None
        else:
            if approved_by_operator_id:
                final_status = "QUEUED"
                approved_at_ts = now
                appr_hash = compute_approval_hash(recipient_masked, channel, message_payload, str(decision_id) if decision_id else None)
            else:
                final_status = "PENDING_APPROVAL" if req_approval else "QUEUED"
                approved_at_ts = None
                appr_hash = None

        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import RecoveryOutboxRepository
            try:
                m_uuid = uuid.UUID(str(merchant_id))
            except (ValueError, AttributeError):
                with self.db_manager.session_scope() as session:
                    m_uuid = self._resolve_merchant_uuid(session, merchant_id)

            scope_ctx = getattr(self.db_manager, "tenant_session_scope", None)
            session_cm = scope_ctx(m_uuid) if scope_ctx else self.db_manager.session_scope()
            with session_cm as session:
                d_uuid = uuid.UUID(str(decision_id)) if decision_id else None
                approved_at_dt = datetime.fromtimestamp(approved_at_ts, tz=timezone.utc) if approved_at_ts else None
                model = RecoveryOutboxRepository.enqueue(
                    session=session,
                    merchant_id=m_uuid,
                    idempotency_key=idempotency_key,
                    action=action,
                    channel=channel,
                    recipient_masked=recipient_masked,
                    message_payload=message_payload,
                    decision_id=d_uuid,
                    case_id=case_id,
                    payment_id=payment_id,
                    max_retries=max_retries,
                    delay_seconds=delay_seconds,
                    status=final_status,
                    requires_operator_approval=req_approval,
                    approved_by_operator_id=approved_by_operator_id,
                    approved_at=approved_at_dt,
                    approval_snapshot_hash=appr_hash,
                )
                logger.info(f"Enqueued outbox job {model.id} into PostgreSQL for case {case_id} (status={model.status})")
                return _model_to_job(model)

        # SQLite Mode
        job = OutboxJob(
            id=job_id,
            case_id=case_id,
            payment_id=payment_id,
            merchant_id=merchant_id,
            idempotency_key=idempotency_key,
            action=action,
            channel=channel,
            recipient_masked=recipient_masked,
            message_payload=message_payload,
            status=final_status,
            retry_count=0,
            max_retries=max_retries,
            next_attempt_at=next_attempt,
            lease_expires_at=None,
            worker_id=None,
            last_error=None,
            created_at=now,
            updated_at=now,
            requires_operator_approval=req_approval,
            approved_by_operator_id=approved_by_operator_id,
            approved_at=approved_at_ts,
            approval_snapshot_hash=appr_hash,
        )

        with self._get_sqlite_connection() as conn:
            conn.execute(
                """
                INSERT INTO recovery_outbox (
                    id, case_id, payment_id, merchant_id, idempotency_key,
                    action, channel, recipient_masked, message_payload,
                    status, retry_count, max_retries, next_attempt_at,
                    lease_expires_at, worker_id, last_error, created_at, updated_at,
                    requires_operator_approval, approved_by_operator_id, approved_at, approval_snapshot_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id, job.case_id, job.payment_id, job.merchant_id, job.idempotency_key,
                    job.action, job.channel, job.recipient_masked, json.dumps(job.message_payload),
                    job.status, job.retry_count, job.max_retries, job.next_attempt_at,
                    job.lease_expires_at, job.worker_id, job.last_error, job.created_at, job.updated_at,
                    1 if job.requires_operator_approval else 0, job.approved_by_operator_id,
                    job.approved_at, job.approval_snapshot_hash,
                ),
            )

        logger.info(f"Enqueued outbox job {job.id} into SQLite for case {case_id} (status={job.status})")
        return job

    def claim_jobs(
        self,
        worker_id: str,
        limit: int = 10,
        lease_duration_seconds: int = 60,
        current_time: Optional[float] = None,
    ) -> List[OutboxJob]:
        """
        Atomically claims available pending or abandoned jobs for worker_id.
        In PostgreSQL: executes genuine SELECT ... FOR UPDATE SKIP LOCKED.
        In SQLite: executes BEGIN IMMEDIATE exclusive transaction.
        """
        now = current_time if current_time is not None else time.time()

        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import RecoveryOutboxRepository
            now_dt = datetime.fromtimestamp(now, tz=timezone.utc)
            with self.db_manager.session_scope() as session:
                models = RecoveryOutboxRepository.claim_jobs(
                    session=session,
                    worker_id=worker_id,
                    limit=limit,
                    lease_duration_seconds=lease_duration_seconds,
                    current_time=now_dt,
                )
                claimed = [_model_to_job(m) for m in models]
                if claimed:
                    logger.info(f"Worker {worker_id} claimed {len(claimed)} jobs from PostgreSQL.")
                return claimed

        # SQLite Mode
        lease_expires = now + lease_duration_seconds
        claimed_jobs: List[OutboxJob] = []
        conn = self._get_sqlite_connection()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            cursor = conn.execute(
                """
                SELECT id FROM recovery_outbox
                WHERE (
                    status NOT IN ('PENDING_APPROVAL', 'REJECTED', 'CANCELLED', 'DEAD_LETTER')
                    AND (
                        (status IN ('QUEUED', 'RETRY') AND next_attempt_at <= ?)
                        OR
                        (status = 'SENDING' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?)
                    )
                    AND (
                        requires_operator_approval = 0
                        OR (
                            approved_by_operator_id IS NOT NULL
                            AND approved_at IS NOT NULL
                            AND approval_snapshot_hash IS NOT NULL
                        )
                    )
                )
                ORDER BY next_attempt_at ASC
                LIMIT ?
                """,
                (now, now, limit),
            )
            job_ids = [row["id"] for row in cursor.fetchall()]

            if job_ids:
                placeholders = ",".join("?" for _ in job_ids)
                conn.execute(
                    f"""
                    UPDATE recovery_outbox
                    SET status = 'SENDING',
                        worker_id = ?,
                        lease_expires_at = ?,
                        updated_at = ?
                    WHERE id IN ({placeholders})
                    """,
                    [worker_id, lease_expires, now] + job_ids,
                )

                rows = conn.execute(
                    f"SELECT * FROM recovery_outbox WHERE id IN ({placeholders})", job_ids
                ).fetchall()

                for r in rows:
                    keys = r.keys()
                    claimed_jobs.append(
                        OutboxJob(
                            id=r["id"],
                            case_id=r["case_id"],
                            payment_id=r["payment_id"],
                            merchant_id=r["merchant_id"],
                            idempotency_key=r["idempotency_key"],
                            action=r["action"],
                            channel=r["channel"],
                            recipient_masked=r["recipient_masked"],
                            message_payload=json.loads(r["message_payload"]),
                            status=r["status"],
                            retry_count=r["retry_count"],
                            max_retries=r["max_retries"],
                            next_attempt_at=r["next_attempt_at"],
                            lease_expires_at=r["lease_expires_at"],
                            worker_id=r["worker_id"],
                            last_error=r["last_error"],
                            created_at=r["created_at"],
                            updated_at=r["updated_at"],
                            requires_operator_approval=bool(r["requires_operator_approval"]) if "requires_operator_approval" in keys else True,
                            approved_by_operator_id=r["approved_by_operator_id"] if "approved_by_operator_id" in keys else None,
                            approved_at=r["approved_at"] if "approved_at" in keys else None,
                            approval_snapshot_hash=r["approval_snapshot_hash"] if "approval_snapshot_hash" in keys else None,
                        )
                    )

            conn.execute("COMMIT;")
        except Exception as err:
            try:
                conn.execute("ROLLBACK;")
            except Exception:
                pass
            logger.error(f"Error during atomic job claim in SQLite: {err}")
            raise
        finally:
            conn.close()

        if claimed_jobs:
            logger.info(f"Worker {worker_id} successfully claimed {len(claimed_jobs)} outbox jobs from SQLite.")
        return claimed_jobs

    def claim_job_by_id(
        self,
        job_id: str,
        worker_id: str,
        lease_duration_seconds: int = 60,
        merchant_id: Optional[str] = None,
        current_time: Optional[float] = None,
    ) -> Optional[OutboxJob]:
        """
        Atomically claims ONLY the specified job_id.
        Guarantees exact-job dispatch isolation: no other queued job can be claimed.
        """
        now = current_time if current_time is not None else time.time()
        try:
            j_uuid = uuid.UUID(str(job_id))
        except (ValueError, TypeError):
            return None

        m_uuid: Optional[uuid.UUID] = None
        if merchant_id:
            try:
                m_uuid = uuid.UUID(str(merchant_id))
            except (ValueError, TypeError):
                return None

        if self.is_postgres and self.db_manager:
            # SAFETY GUARD: Prevent tests from claiming the live hosted target job
            if os.environ.get("PYTEST_CURRENT_TEST"):
                if str(job_id).lower() == "5a6587ab-2601-4017-b396-48e3d2fc2fda":
                    raise RuntimeError(
                        f"TEST SAFETY GUARD: Test '{os.environ.get('PYTEST_CURRENT_TEST')}' "
                        "attempted to claim the live hosted target job 5a6587ab-2601-4017-b396-48e3d2fc2fda! "
                        "Tests are strictly forbidden from claiming the live target outbox job. "
                        "Use an isolated synthetic test job or SQLite test database."
                    )

            if not merchant_id or not m_uuid:
                logger.warning(f"Refusing to claim exact job {job_id} without authenticated merchant_id.")
                return None
            from wapsi.db.repository import RecoveryOutboxRepository
            now_dt = datetime.fromtimestamp(now, tz=timezone.utc)
            with self.db_manager.tenant_session_scope(m_uuid) as session:
                model = RecoveryOutboxRepository.claim_job_by_id(
                    session=session,
                    job_id=j_uuid,
                    worker_id=worker_id,
                    merchant_id=m_uuid,
                    lease_duration_seconds=lease_duration_seconds,
                    current_time=now_dt,
                )
                if model:
                    job = _model_to_job(model)
                    logger.info(f"Worker {worker_id} claimed exact job {job_id} from PostgreSQL.")
                    return job
                return None

        # SQLite Mode
        lease_expires = now + lease_duration_seconds
        conn = self._get_sqlite_connection()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            sql = """
                SELECT id FROM recovery_outbox
                WHERE id = ?
                  AND status NOT IN ('PENDING_APPROVAL', 'REJECTED', 'CANCELLED', 'DEAD_LETTER')
                  AND (
                      (status IN ('QUEUED', 'RETRY') AND next_attempt_at <= ?)
                      OR
                      (status = 'SENDING' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?)
                  )
                  AND (
                      requires_operator_approval = 0
                      OR (
                          approved_by_operator_id IS NOT NULL
                          AND approved_at IS NOT NULL
                          AND approval_snapshot_hash IS NOT NULL
                      )
                  )
            """
            params: list = [str(job_id), now, now]
            if merchant_id:
                sql += " AND merchant_id = ?"
                params.append(str(merchant_id))

            cursor = conn.execute(sql, tuple(params))
            row = cursor.fetchone()
            if not row:
                conn.execute("ROLLBACK;")
                return None

            conn.execute(
                """
                UPDATE recovery_outbox
                SET status = 'SENDING',
                    worker_id = ?,
                    lease_expires_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (worker_id, lease_expires, now, str(job_id)),
            )
            r = conn.execute("SELECT * FROM recovery_outbox WHERE id = ?", (str(job_id),)).fetchone()
            conn.execute("COMMIT;")
            keys = r.keys()
            raw_payload = r["message_payload"]
            parsed_payload = json.loads(raw_payload) if isinstance(raw_payload, str) else (raw_payload or {})
            return OutboxJob(
                id=r["id"],
                case_id=r["case_id"],
                payment_id=r["payment_id"],
                merchant_id=r["merchant_id"],
                idempotency_key=r["idempotency_key"],
                action=r["action"],
                channel=r["channel"],
                recipient_masked=r["recipient_masked"],
                message_payload=parsed_payload,
                status=r["status"],
                retry_count=r["retry_count"],
                max_retries=r["max_retries"],
                next_attempt_at=r["next_attempt_at"],
                lease_expires_at=r["lease_expires_at"],
                worker_id=r["worker_id"],
                last_error=r["last_error"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                requires_operator_approval=bool(r["requires_operator_approval"]) if "requires_operator_approval" in keys else True,
                approved_by_operator_id=r["approved_by_operator_id"] if "approved_by_operator_id" in keys else None,
                approved_at=r["approved_at"] if "approved_at" in keys else None,
                approval_snapshot_hash=r["approval_snapshot_hash"] if "approval_snapshot_hash" in keys else None,
            )
        except Exception as e:
            try:
                conn.execute("ROLLBACK;")
            except Exception:
                pass
            logger.error(f"Error claiming specific job {job_id} in SQLite: {e}")
            raise
        finally:
            conn.close()

    def complete_job(
        self,
        job_id: str,
        worker_id: str,
        result_metadata: Optional[Dict[str, Any]] = None,
        merchant_id: Optional[str] = None,
    ) -> bool:
        """Marks a claimed job as SENT (completed)."""
        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import RecoveryOutboxRepository
            j_uuid = uuid.UUID(str(job_id))
            m_uuid = None
            if merchant_id:
                try:
                    m_uuid = uuid.UUID(str(merchant_id))
                except (ValueError, TypeError):
                    pass
            with self.db_manager.session_scope() as session:
                return RecoveryOutboxRepository.complete_job(session, j_uuid, worker_id, merchant_id=m_uuid)

        # SQLite Mode
        now = time.time()
        with self._get_sqlite_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE recovery_outbox
                SET status = 'SENT',
                    lease_expires_at = NULL,
                    updated_at = ?,
                    last_error = NULL
                WHERE id = ? AND worker_id = ?
                """,
                (now, job_id, worker_id),
            )
            return cursor.rowcount > 0

    def fail_job(
        self,
        job_id: str,
        worker_id: str,
        error_message: str,
        is_retryable: bool = True,
        backoff_seconds: int = 60,
        retry_after_seconds: Optional[int] = None,
        merchant_id: Optional[str] = None,
    ) -> bool:
        """Transitions a job to RETRY (with backoff) or DEAD_LETTER if max retries exceeded or non-retryable."""
        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import RecoveryOutboxRepository
            j_uuid = uuid.UUID(str(job_id))
            m_uuid = None
            if merchant_id:
                try:
                    m_uuid = uuid.UUID(str(merchant_id))
                except (ValueError, TypeError):
                    pass
            with self.db_manager.session_scope() as session:
                return RecoveryOutboxRepository.fail_job(
                    session=session,
                    job_id=j_uuid,
                    worker_id=worker_id,
                    error_message=error_message,
                    is_retryable=is_retryable,
                    backoff_seconds=backoff_seconds,
                    retry_after_seconds=retry_after_seconds,
                    merchant_id=m_uuid,
                )

        # SQLite Mode
        now = time.time()
        conn = self._get_sqlite_connection()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            row = conn.execute(
                "SELECT retry_count, max_retries FROM recovery_outbox WHERE id = ? AND worker_id = ?",
                (job_id, worker_id),
            ).fetchone()

            if not row:
                conn.execute("ROLLBACK;")
                return False

            new_retry_count = row["retry_count"] + 1
            max_retries = row["max_retries"]

            if not is_retryable or new_retry_count >= max_retries:
                new_status = "DEAD_LETTER"
                next_attempt = now
                logger.warning(
                    f"Job {job_id} permanently failed -> DEAD_LETTER "
                    f"(retryable={is_retryable}, attempts={new_retry_count}/{max_retries}): {error_message}"
                )
            else:
                new_status = "RETRY"
                delay = retry_after_seconds if retry_after_seconds is not None else backoff_seconds
                next_attempt = now + delay
                logger.info(
                    f"Job {job_id} scheduled for RETRY in {delay}s "
                    f"(attempt {new_retry_count}/{max_retries}): {error_message}"
                )

            conn.execute(
                """
                UPDATE recovery_outbox
                SET status = ?,
                    retry_count = ?,
                    next_attempt_at = ?,
                    lease_expires_at = NULL,
                    last_error = ?,
                    updated_at = ?
                WHERE id = ? AND worker_id = ?
                """,
                (new_status, new_retry_count, next_attempt, error_message, now, job_id, worker_id),
            )
            conn.execute("COMMIT;")
            return True
        except Exception:
            conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()

    def mark_reconciliation_required(
        self,
        job_id: str,
        worker_id: str,
        reason: str,
        merchant_id: Optional[str] = None,
    ) -> bool:
        """Transitions an ambiguous network outcome to RECONCILIATION_REQUIRED."""
        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import RecoveryOutboxRepository
            j_uuid = uuid.UUID(str(job_id))
            m_uuid = None
            if merchant_id:
                try:
                    m_uuid = uuid.UUID(str(merchant_id))
                except (ValueError, TypeError):
                    pass
            with self.db_manager.session_scope() as session:
                return RecoveryOutboxRepository.mark_reconciliation_required(
                    session, j_uuid, worker_id, reason, merchant_id=m_uuid
                )

        # SQLite Mode
        now = time.time()
        with self._get_sqlite_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE recovery_outbox
                SET status = 'RECONCILIATION_REQUIRED',
                    lease_expires_at = NULL,
                    last_error = ?,
                    updated_at = ?
                WHERE id = ? AND worker_id = ?
                """,
                (f"Ambiguous network outcome: {reason}", now, job_id, worker_id),
            )
            return cursor.rowcount > 0

    def cancel_jobs_for_case(
        self,
        case_id: str,
        reason: str = "CASE_RECOVERED",
        merchant_id: Optional[str] = None,
    ) -> int:
        """Cancels all pending or scheduled outbox jobs when a case is recovered or cancelled."""
        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import RecoveryOutboxRepository
            m_uuid = None
            if merchant_id:
                try:
                    m_uuid = uuid.UUID(str(merchant_id))
                except (ValueError, TypeError):
                    pass
            with self.db_manager.session_scope() as session:
                return RecoveryOutboxRepository.cancel_jobs_for_case(session, case_id, reason, merchant_id=m_uuid)

        # SQLite Mode
        now = time.time()
        with self._get_sqlite_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE recovery_outbox
                SET status = 'CANCELLED',
                    lease_expires_at = NULL,
                    last_error = ?,
                    updated_at = ?
                WHERE case_id = ? AND status IN ('PENDING_APPROVAL', 'QUEUED', 'RETRY', 'SENDING')
                """,
                (reason, now, case_id),
            )
            return cursor.rowcount

    def approve_job(
        self,
        job_id: str,
        operator_id: str,
        merchant_id: Optional[str] = None,
    ) -> bool:
        """
        Explicitly approves a job in PENDING_APPROVAL status.
        Transitions the status to QUEUED and registers operator ID, timestamp, and payload snapshot hash.
        """
        if not operator_id or not str(operator_id).strip():
            raise ValueError("operator_id is required to approve an outbox job")

        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import RecoveryOutboxRepository
            from wapsi.db.models import RecoveryOutboxModel
            j_uuid = uuid.UUID(str(job_id))
            scope = self.db_manager.tenant_session_scope(merchant_id) if merchant_id else self.db_manager.session_scope()
            with scope as session:
                job_model = session.get(RecoveryOutboxModel, j_uuid)
                if not job_model:
                    return False
                if job_model.status != "PENDING_APPROVAL":
                    logger.warning(f"Cannot approve job {job_id}: current status is {job_model.status}, expected PENDING_APPROVAL")
                    return False
                appr_hash = compute_approval_hash(
                    recipient_masked=job_model.recipient_masked,
                    channel=job_model.channel,
                    message_payload=job_model.message_payload,
                    decision_id=str(job_model.decision_id) if job_model.decision_id else None,
                )
                RecoveryOutboxRepository.approve_job(
                    session=session,
                    job_id=j_uuid,
                    operator_id=str(operator_id).strip(),
                    snapshot_hash=appr_hash,
                )
                logger.info(f"Operator {operator_id} approved job {job_id} (PostgreSQL).")
                return True

        # SQLite Mode
        now = time.time()
        conn = self._get_sqlite_connection()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            if merchant_id:
                row = conn.execute(
                    "SELECT recipient_masked, channel, message_payload, status FROM recovery_outbox WHERE id = ? AND merchant_id = ?",
                    (job_id, str(merchant_id)),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT recipient_masked, channel, message_payload, status FROM recovery_outbox WHERE id = ?",
                    (job_id,),
                ).fetchone()
            if not row:
                conn.execute("ROLLBACK;")
                return False
            if row["status"] != "PENDING_APPROVAL":
                logger.warning(f"Cannot approve job {job_id}: current status is {row['status']}, expected PENDING_APPROVAL")
                conn.execute("ROLLBACK;")
                return False

            payload = json.loads(row["message_payload"])
            appr_hash = compute_approval_hash(
                recipient_masked=row["recipient_masked"],
                channel=row["channel"],
                message_payload=payload,
            )
            cursor = conn.execute(
                """
                UPDATE recovery_outbox
                SET status = 'QUEUED',
                    approved_by_operator_id = ?,
                    approved_at = ?,
                    approval_snapshot_hash = ?,
                    updated_at = ?
                WHERE id = ? AND status = 'PENDING_APPROVAL'
                """,
                (str(operator_id).strip(), now, appr_hash, now, job_id),
            )
            success = cursor.rowcount > 0
            conn.execute("COMMIT;")
            if success:
                logger.info(f"Operator {operator_id} approved job {job_id} (SQLite).")
            return success
        except Exception as e:
            try:
                conn.execute("ROLLBACK;")
            except Exception:
                pass
            logger.error(f"Error approving job {job_id} in SQLite: {e}")
            raise
        finally:
            conn.close()

    def reject_job(
        self,
        job_id: str,
        operator_id: str,
        reason: str = "Rejected by operator",
        merchant_id: Optional[str] = None,
    ) -> bool:
        """
        Explicitly rejects a job in PENDING_APPROVAL status.
        Transitions the status to REJECTED so workers never claim it.
        """
        if not operator_id or not str(operator_id).strip():
            raise ValueError("operator_id is required to reject an outbox job")

        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import RecoveryOutboxRepository
            from wapsi.db.models import RecoveryOutboxModel
            j_uuid = uuid.UUID(str(job_id))
            scope = self.db_manager.tenant_session_scope(merchant_id) if merchant_id else self.db_manager.session_scope()
            with scope as session:
                job_model = session.get(RecoveryOutboxModel, j_uuid)
                if not job_model:
                    return False
                RecoveryOutboxRepository.reject_job(
                    session=session,
                    job_id=j_uuid,
                    operator_id=str(operator_id).strip(),
                    reason=reason,
                )
                logger.info(f"Operator {operator_id} rejected job {job_id} (PostgreSQL): {reason}")
                return True

        # SQLite Mode
        now = time.time()
        conn = self._get_sqlite_connection()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            if merchant_id:
                cursor = conn.execute(
                    """
                    UPDATE recovery_outbox
                    SET status = 'REJECTED',
                        last_error = ?,
                        updated_at = ?
                    WHERE id = ? AND merchant_id = ? AND status = 'PENDING_APPROVAL'
                    """,
                    (f"Rejected by operator {operator_id}: {reason}", now, job_id, str(merchant_id)),
                )
            else:
                cursor = conn.execute(
                    """
                    UPDATE recovery_outbox
                    SET status = 'REJECTED',
                        last_error = ?,
                        updated_at = ?
                    WHERE id = ? AND status = 'PENDING_APPROVAL'
                    """,
                    (f"Rejected by operator {operator_id}: {reason}", now, job_id),
                )
            success = cursor.rowcount > 0
            conn.execute("COMMIT;")
            if success:
                logger.info(f"Operator {operator_id} rejected job {job_id} (SQLite): {reason}")
            return success
        except Exception as e:
            try:
                conn.execute("ROLLBACK;")
            except Exception:
                pass
            logger.error(f"Error rejecting job {job_id} in SQLite: {e}")
            raise
        finally:
            conn.close()

    def verify_dispatch_authorization(
        self,
        job: OutboxJob,
        opt_out_store: Optional[Any] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Defensively validates authorization and payload integrity prior to external provider dispatch.
        Guarantees:
        1. If channel is customer-contacting and requires operator approval, job must have operator ID, approval timestamp, and snapshot hash.
        2. Computed SHA-256 hash over current job properties must strictly match approval_snapshot_hash (prevents payload tampering).
        3. Job status must NOT be PENDING_APPROVAL, REJECTED, CANCELLED, or DEAD_LETTER.
        4. Customer recipient must not be opted out.
        """
        is_contact = job.channel.lower() in ("whatsapp", "sms", "voice", "email")
        if job.requires_operator_approval or is_contact:
            if not job.approved_by_operator_id:
                return False, f"Job {job.id} requires operator approval but approved_by_operator_id is missing."
            if not job.approved_at:
                return False, f"Job {job.id} requires operator approval but approved_at is missing."
            if not job.approval_snapshot_hash:
                return False, f"Job {job.id} requires operator approval but approval_snapshot_hash is missing."

            expected_hash = compute_approval_hash(
                recipient_masked=job.recipient_masked,
                channel=job.channel,
                message_payload=job.message_payload,
            )
            if job.approval_snapshot_hash != expected_hash:
                return False, (
                    f"Job {job.id} payload integrity violation: expected hash {expected_hash}, "
                    f"found snapshot {job.approval_snapshot_hash}. Message payload or recipient modified after approval."
                )

        if job.status in ("PENDING_APPROVAL", "REJECTED", "CANCELLED", "DEAD_LETTER"):
            return False, f"Job {job.id} is in non-dispatchable status {job.status}."

        if opt_out_store is not None:
            payload = job.message_payload or {}
            phone_to_check = payload.get("customer_phone") or payload.get("phone") or job.recipient_masked
            if phone_to_check and opt_out_store.is_opted_out(phone_to_check):
                return False, f"Customer {phone_to_check} is registered as opted out."

        return True, None

    def get_job(self, job_id: str, merchant_id: Optional[str] = None) -> Optional[OutboxJob]:
        """Retrieves a single job by ID."""
        if self.is_postgres and self.db_manager:
            from wapsi.db.models import RecoveryOutboxModel
            try:
                j_uuid = uuid.UUID(str(job_id))
            except (ValueError, TypeError):
                return None
            scope = self.db_manager.tenant_session_scope(merchant_id) if merchant_id else self.db_manager.session_scope()
            with scope as session:
                model = session.execute(
                    select(RecoveryOutboxModel).where(RecoveryOutboxModel.id == j_uuid)
                ).scalar_one_or_none()
                return _model_to_job(model) if model else None

        # SQLite Mode
        with self._get_sqlite_connection() as conn:
            if merchant_id:
                r = conn.execute(
                    "SELECT * FROM recovery_outbox WHERE id = ? AND merchant_id = ?",
                    (job_id, str(merchant_id)),
                ).fetchone()
            else:
                r = conn.execute("SELECT * FROM recovery_outbox WHERE id = ?", (job_id,)).fetchone()
            if not r:
                return None
            keys = r.keys()
            return OutboxJob(
                id=r["id"],
                case_id=r["case_id"],
                payment_id=r["payment_id"],
                merchant_id=r["merchant_id"],
                idempotency_key=r["idempotency_key"],
                action=r["action"],
                channel=r["channel"],
                recipient_masked=r["recipient_masked"],
                message_payload=json.loads(r["message_payload"]),
                status=r["status"],
                retry_count=r["retry_count"],
                max_retries=r["max_retries"],
                next_attempt_at=r["next_attempt_at"],
                lease_expires_at=r["lease_expires_at"],
                worker_id=r["worker_id"],
                last_error=r["last_error"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                requires_operator_approval=bool(r["requires_operator_approval"]) if "requires_operator_approval" in keys else True,
                approved_by_operator_id=r["approved_by_operator_id"] if "approved_by_operator_id" in keys else None,
                approved_at=r["approved_at"] if "approved_at" in keys else None,
                approval_snapshot_hash=r["approval_snapshot_hash"] if "approval_snapshot_hash" in keys else None,
            )

    def get_metrics(self) -> Dict[str, int]:
        """Returns counts of outbox jobs partitioned by status."""
        metrics: Dict[str, int] = {
            "PENDING_APPROVAL": 0,
            "QUEUED": 0,
            "SENDING": 0,
            "SENT": 0,
            "RETRY": 0,
            "DEAD_LETTER": 0,
            "RECONCILIATION_REQUIRED": 0,
            "CANCELLED": 0,
            "REJECTED": 0,
            "TOTAL": 0,
        }
        if self.is_postgres and self.db_manager:
            from wapsi.db.models import RecoveryOutboxModel
            with self.db_manager.session_scope() as session:
                rows = session.execute(
                    select(RecoveryOutboxModel.status, func.count(RecoveryOutboxModel.id)).group_by(RecoveryOutboxModel.status)
                ).all()
                total = 0
                for st, cnt in rows:
                    cnt_int = int(cnt)
                    metrics[st] = cnt_int
                    total += cnt_int
                metrics["TOTAL"] = total
            return metrics

        # SQLite Mode
        with self._get_sqlite_connection() as conn:
            rows = conn.execute("SELECT status, COUNT(*) as cnt FROM recovery_outbox GROUP BY status").fetchall()
            total = 0
            for r in rows:
                st = r["status"]
                cnt = int(r["cnt"])
                metrics[st] = cnt
                total += cnt
            metrics["TOTAL"] = total
        return metrics

    def count_active_leases(
        self,
        worker_id: Optional[str] = None,
        current_time: Optional[float] = None,
        merchant_id: Optional[str] = None,
    ) -> int:
        """Counts currently active leases (status='SENDING' and lease_expires_at >= now)."""
        now = current_time if current_time is not None else time.time()
        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import RecoveryOutboxRepository
            now_dt = datetime.fromtimestamp(now, tz=timezone.utc)
            m_uuid = None
            if merchant_id:
                try:
                    m_uuid = uuid.UUID(str(merchant_id))
                except (ValueError, TypeError):
                    pass
            with self.db_manager.session_scope() as session:
                return RecoveryOutboxRepository.count_active_leases(
                    session=session,
                    worker_id=worker_id,
                    current_time=now_dt,
                    merchant_id=m_uuid,
                )

        # SQLite Mode
        with self._get_sqlite_connection() as conn:
            sql = "SELECT COUNT(*) as cnt FROM recovery_outbox WHERE status = 'SENDING' AND lease_expires_at IS NOT NULL AND lease_expires_at >= ?"
            params: list = [now]
            if worker_id:
                sql += " AND worker_id = ?"
                params.append(worker_id)
            if merchant_id:
                sql += " AND merchant_id = ?"
                params.append(str(merchant_id))
            row = conn.execute(sql, tuple(params)).fetchone()
            return int(row["cnt"]) if row else 0

    def release_lease(
        self,
        job_id: str,
        worker_id: str,
        merchant_id: Optional[str] = None,
    ) -> bool:
        """
        Releases an active lease for an undispatched job held by worker_id,
        returning it to QUEUED status so it can be claimed by other workers.
        Only jobs currently in status 'SENDING' held by worker_id can be released.
        """
        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import RecoveryOutboxRepository
            try:
                j_uuid = uuid.UUID(str(job_id))
            except (ValueError, TypeError):
                return False
            m_uuid = None
            if merchant_id:
                try:
                    m_uuid = uuid.UUID(str(merchant_id))
                except (ValueError, TypeError):
                    pass
            with self.db_manager.session_scope() as session:
                return RecoveryOutboxRepository.release_lease(session, j_uuid, worker_id, merchant_id=m_uuid)

        # SQLite Mode
        now = time.time()
        with self._get_sqlite_connection() as conn:
            sql = """
                UPDATE recovery_outbox
                SET status = 'QUEUED',
                    worker_id = NULL,
                    lease_expires_at = NULL,
                    updated_at = ?
                WHERE id = ? AND worker_id = ? AND status = 'SENDING'
            """
            params: list = [now, str(job_id), worker_id]
            if merchant_id:
                sql += " AND merchant_id = ?"
                params.append(str(merchant_id))
            cursor = conn.execute(sql, tuple(params))
            return cursor.rowcount > 0

    def release_leases_for_worker(
        self,
        worker_id: str,
        merchant_id: Optional[str] = None,
        exclude_job_ids: Optional[List[str]] = None,
    ) -> int:
        """
        Releases all undispatched leases held by worker_id (e.g. during graceful shutdown).
        Only jobs currently in status 'SENDING' held by worker_id are reset to 'QUEUED'.
        Optional exclude_job_ids preserves in-flight operations that timed out.
        """
        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import RecoveryOutboxRepository
            m_uuid = None
            if merchant_id:
                try:
                    m_uuid = uuid.UUID(str(merchant_id))
                except (ValueError, TypeError):
                    pass
            ex_uuids = None
            if exclude_job_ids:
                ex_uuids = []
                for jid in exclude_job_ids:
                    try:
                        ex_uuids.append(uuid.UUID(str(jid)))
                    except (ValueError, TypeError):
                        pass
            with self.db_manager.session_scope() as session:
                return RecoveryOutboxRepository.release_leases_for_worker(
                    session,
                    worker_id,
                    merchant_id=m_uuid,
                    exclude_job_ids=ex_uuids,
                )

        # SQLite Mode
        now = time.time()
        with self._get_sqlite_connection() as conn:
            sql = """
                UPDATE recovery_outbox
                SET status = 'QUEUED',
                    worker_id = NULL,
                    lease_expires_at = NULL,
                    updated_at = ?
                WHERE worker_id = ? AND status = 'SENDING'
            """
            params: list = [now, worker_id]
            if merchant_id:
                sql += " AND merchant_id = ?"
                params.append(str(merchant_id))
            if exclude_job_ids:
                placeholders = ",".join("?" for _ in exclude_job_ids)
                sql += f" AND id NOT IN ({placeholders})"
                params.extend([str(jid) for jid in exclude_job_ids])

            cursor = conn.execute(sql, tuple(params))
            return cursor.rowcount

    def reclaim_expired_leases(
        self,
        current_time: Optional[float] = None,
        max_reclaim: int = 50,
        merchant_id: Optional[str] = None,
    ) -> int:
        """
        Reclaims abandoned/expired leases where lease_expires_at < current_time.
        Transitions expired SENDING jobs back to QUEUED with lease_expires_at = NULL and worker_id = NULL.
        """
        now = current_time if current_time is not None else time.time()
        if self.is_postgres and self.db_manager:
            from wapsi.db.repository import RecoveryOutboxRepository
            now_dt = datetime.fromtimestamp(now, tz=timezone.utc)
            m_uuid = None
            if merchant_id:
                try:
                    m_uuid = uuid.UUID(str(merchant_id))
                except (ValueError, TypeError):
                    pass
            with self.db_manager.session_scope() as session:
                return RecoveryOutboxRepository.reclaim_expired_leases(
                    session=session,
                    current_time=now_dt,
                    max_reclaim=max_reclaim,
                    merchant_id=m_uuid,
                )

        # SQLite Mode
        conn = self._get_sqlite_connection()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            sql = """
                SELECT id FROM recovery_outbox
                WHERE status = 'SENDING'
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at < ?
            """
            params: list = [now]
            if merchant_id:
                sql += " AND merchant_id = ?"
                params.append(str(merchant_id))
            sql += f" LIMIT {int(max_reclaim)}"

            rows = conn.execute(sql, tuple(params)).fetchall()
            ids = [r["id"] for r in rows]
            if not ids:
                conn.execute("COMMIT;")
                return 0

            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                f"""
                UPDATE recovery_outbox
                SET status = 'QUEUED',
                    worker_id = NULL,
                    lease_expires_at = NULL,
                    updated_at = ?
                WHERE id IN ({placeholders})
                """,
                [now] + ids,
            )
            conn.execute("COMMIT;")
            return len(ids)
        except Exception as e:
            try:
                conn.execute("ROLLBACK;")
            except Exception:
                pass
            logger.error(f"Error reclaiming expired leases in SQLite: {e}")
            raise
        finally:
            conn.close()


_outbox_store: Optional[DurableOutboxStore] = None


def get_outbox_store(
    db_path: Optional[str] = None,
    database_manager: Optional[Any] = None,
) -> DurableOutboxStore:
    global _outbox_store
    if _outbox_store is None or db_path is not None or database_manager is not None:
        mgr = database_manager
        if mgr is None and db_path is None:
            from wapsi.db.session import get_db_manager
            try:
                mgr = get_db_manager()
            except Exception:
                mgr = None
        _outbox_store = DurableOutboxStore(db_path=db_path, database_manager=mgr)
    return _outbox_store
