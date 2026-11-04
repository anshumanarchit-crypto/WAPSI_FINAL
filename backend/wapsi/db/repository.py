"""
Database Repositories for WAPSI Multi-Tenant Persistence Layer.
Project: ffgsrwjhguvubmhuefyj (Razorpay AI Buildathon 2026 - Track 3)

Implements clean data access patterns for:
  - Tenant Merchants & Configurations
  - Pseudonymized Customers
  - Integer-Paise Transactions
  - Causal Decisions Snapshot
  - Durable Multi-Provider Webhook Inbox Deduplication
  - API Idempotency Locks
  - Transactional Recovery Outbox
  - Tamper-Evident Audit Ledger Blocks
  - Contextual Bandit Weights
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, desc, func, or_, select, text, update
from sqlalchemy.orm import Session

from wapsi.core.config import get_settings
from wapsi.db.models import (
    AuditLedgerBlockModel,
    BanditWeightModel,
    CausalDecisionModel,
    CustomerInteractionModel,
    CustomerModel,
    IdempotencyKeyModel,
    MerchantApiKeyModel,
    MerchantConfigurationModel,
    MerchantMembershipModel,
    MerchantModel,
    OptOutAuditTrailModel,
    OptOutRegistryModel,
    PaymentOutcomeModel,
    RecoveryDispatchModel,
    RecoveryOutboxModel,
    TransactionModel,
    WebhookInboxModel,
    ObservationalLearningRecordModel,
)

logger = logging.getLogger("wapsi.repository")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ==============================================================================
# 1. MERCHANT REPOSITORY
# ==============================================================================
class MerchantRepository:

    @staticmethod
    def get_by_code(session: Session, merchant_code: str) -> Optional[MerchantModel]:
        stmt = select(MerchantModel).where(MerchantModel.merchant_code == merchant_code)
        return session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def get_by_id(session: Session, merchant_id: uuid.UUID) -> Optional[MerchantModel]:
        stmt = select(MerchantModel).where(MerchantModel.id == merchant_id)
        return session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def get_or_create_default(session: Session) -> MerchantModel:
        """Ensures the default development merchant exists."""
        default_code = "MRC_928374"
        merchant = MerchantRepository.get_by_code(session, default_code)
        if not merchant:
            merchant = MerchantModel(
                merchant_code=default_code,
                name="Acme Global Technologies",
                business_type="Enterprise SaaS & Subscriptions",
                industry="FinTech / Ecommerce",
                website="https://acmeglobal.io",
                registered_email="compliance@acmeglobal.io",
                country="India",
                currency="INR",
                timezone="Asia/Kolkata",
                status="ACTIVE",
            )
            session.add(merchant)
            session.flush()

            # Create default configuration
            cfg = MerchantConfigurationModel(
                merchant_id=merchant.id,
                recovery_enabled_percent=84,
                confidence_threshold_percent=80,
                min_uplift_threshold_percent=12,
                retry_attempt_limit=3,
                contact_budget_per_customer=2,
                min_ivr_amount_paise=150000,
                default_merchant_margin_basis_points=2000,
            )
            session.add(cfg)
            session.flush()

        return merchant

    @staticmethod
    def get_configuration(session: Session, merchant_id: uuid.UUID) -> Optional[MerchantConfigurationModel]:
        stmt = select(MerchantConfigurationModel).where(MerchantConfigurationModel.merchant_id == merchant_id)
        return session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def authenticate_api_key(session: Session, raw_api_key: str) -> Optional[Dict[str, Any]]:
        """
        Authenticates an incoming raw API key strictly via public.lookup_merchant_by_api_key_hash(text).
        Never performs direct SELECT on restricted public.merchant_api_keys.
        Under PostgreSQL, calls the hardened SECURITY DEFINER procedure.
        Under local SQLite (testing/mock), evaluates the key record directly.
        """
        if not raw_api_key or not isinstance(raw_api_key, str):
            return None

        clean_key = raw_api_key.strip()
        if not clean_key:
            return None

        hashed_key = hashlib.sha256(clean_key.encode("utf-8")).hexdigest()

        bind = session.get_bind()
        if bind and bind.dialect.name == "postgresql":
            stmt = text(
                "SELECT merchant_id, merchant_code, merchant_status, key_scopes "
                "FROM public.lookup_merchant_by_api_key_hash(:h)"
            )
            row = session.execute(stmt, {"h": hashed_key}).fetchone()
            if row:
                return {
                    "merchant_id": str(row[0]),
                    "merchant_code": row[1],
                    "merchant_status": row[2],
                    "key_scopes": row[3] if isinstance(row[3], list) else list(row[3] or []),
                }
            return None
        else:
            # SQLite / Mock offline unit-testing fallback
            stmt = select(MerchantApiKeyModel).where(
                MerchantApiKeyModel.hashed_key == hashed_key,
                MerchantApiKeyModel.is_revoked == False,
            )
            key_rec = session.execute(stmt).scalar_one_or_none()
            if key_rec and (key_rec.expires_at is None or key_rec.expires_at > _utc_now()):
                merch = session.get(MerchantModel, key_rec.merchant_id)
                if merch and merch.status == "ACTIVE":
                    return {
                        "merchant_id": str(merch.id),
                        "merchant_code": merch.merchant_code,
                        "merchant_status": merch.status,
                        "key_scopes": key_rec.scopes,
                    }
            return None


# ==============================================================================
# 2. CUSTOMER REPOSITORY (Pseudonymized Identity)
# ==============================================================================
class CustomerRepository:

    @staticmethod
    def compute_pseudonym(merchant_id: uuid.UUID, customer_identifier: str) -> str:
        """Computes deterministic merchant-scoped customer pseudonym using HMAC-SHA256."""
        settings = get_settings()
        salt = settings.customer_hash_salt.get_secret_value().encode("utf-8")
        raw_msg = f"{merchant_id}:{customer_identifier}".encode("utf-8")
        return hmac.new(salt, raw_msg, hashlib.sha256).hexdigest()

    @staticmethod
    def get_or_create_customer(
        session: Session,
        merchant_id: uuid.UUID,
        merchant_customer_id: str,
        masked_identifier: Optional[str] = None,
        account_age_days: int = 0,
    ) -> CustomerModel:
        stmt = select(CustomerModel).where(
            CustomerModel.merchant_id == merchant_id,
            CustomerModel.merchant_customer_id == merchant_customer_id,
        )
        customer = session.execute(stmt).scalar_one_or_none()
        if not customer:
            pseudonym = CustomerRepository.compute_pseudonym(merchant_id, merchant_customer_id)
            masked = masked_identifier or f"Cust_{merchant_customer_id[:4]}****"
            customer = CustomerModel(
                merchant_id=merchant_id,
                merchant_customer_id=merchant_customer_id,
                customer_pseudonym=pseudonym,
                masked_identifier=masked,
                account_age_days=account_age_days,
            )
            session.add(customer)
            session.flush()
        return customer

    @staticmethod
    def update_opt_out(session: Session, merchant_id: uuid.UUID, customer_id: uuid.UUID, opted_out: bool) -> None:
        stmt = select(CustomerModel).where(
            CustomerModel.merchant_id == merchant_id,
            CustomerModel.id == customer_id,
        )
        cust = session.execute(stmt).scalar_one_or_none()
        if cust:
            cust.opted_out = opted_out
            cust.consent_status = "OPTED_OUT" if opted_out else "ACTIVE_CONSENT"
            cust.opted_out_at = _utc_now() if opted_out else None
            session.flush()


# ==============================================================================
# 3. TRANSACTION REPOSITORY (Monetary Integer Paise)
# ==============================================================================
class TransactionRepository:

    @staticmethod
    def create_transaction(
        session: Session,
        merchant_id: uuid.UUID,
        customer_id: uuid.UUID,
        payment_id: str,
        amount_paise: int,
        payment_method: str = "upi",
        error_code: str = "UPI_APP_TIMEOUT",
        error_category: str = "FRICTION_OTP_UX",
        error_description: Optional[str] = None,
        hour_of_day: int = 14,
        is_dnd_window: bool = False,
        status: str = "FAILED",
    ) -> TransactionModel:
        if amount_paise <= 0:
            raise ValueError(f"Transaction amount in paise must be strictly positive, got: {amount_paise}")

        tx = TransactionModel(
            merchant_id=merchant_id,
            customer_id=customer_id,
            payment_id=payment_id,
            amount_paise=amount_paise,
            payment_method=payment_method,
            error_code=error_code,
            error_category=error_category,
            error_description=error_description,
            hour_of_day=hour_of_day,
            is_dnd_window=is_dnd_window,
            status=status,
        )
        session.add(tx)
        session.flush()
        return tx

    @staticmethod
    def get_by_payment_id(session: Session, merchant_id: uuid.UUID, payment_id: str) -> Optional[TransactionModel]:
        stmt = select(TransactionModel).where(
            TransactionModel.merchant_id == merchant_id,
            TransactionModel.payment_id == payment_id,
        )
        return session.execute(stmt).scalar_one_or_none()


# ==============================================================================
# 4. CAUSAL DECISION REPOSITORY
# ==============================================================================
class CausalDecisionRepository:

    @staticmethod
    def create_decision(session: Session, decision_attrs: Dict[str, Any]) -> CausalDecisionModel:
        defaults = {
            "causal_uplift_tau_basis_points": 2800,
            "baseline_prob_basis_points": 1500,
            "expected_prob_basis_points": 4300,
            "conformal_interval": [0.20, 0.36],
            "confidence_tier": "HIGH",
            "conformal_calibration_status": "CALIBRATED_NOMINAL_90",
            "net_expected_utility_paise": 10000,
            "plain_english_rationale": "Recommended based on optimal causal uplift estimation.",
            "localized_customer_copy": {},
        }
        full_attrs = {**defaults, **decision_attrs}
        decision = CausalDecisionModel(**full_attrs)
        session.add(decision)
        session.flush()
        return decision

    @staticmethod
    def get_by_decision_id(session: Session, decision_id: str) -> Optional[CausalDecisionModel]:
        stmt = select(CausalDecisionModel).where(CausalDecisionModel.decision_id == decision_id)
        return session.execute(stmt).scalar_one_or_none()


# ==============================================================================
# 5. WEBHOOK INBOX REPOSITORY (Durable Event Deduplication)
# ==============================================================================
class WebhookInboxRepository:

    @staticmethod
    def record_and_deduplicate(
        session: Session,
        provider: str,
        environment: str,
        payment_id: str,
        event_type: str,
        nonce: str,
        signature: str,
        payload_sanitized: Dict[str, Any],
        merchant_id: Optional[uuid.UUID] = None,
        signature_verified: bool = True,
    ) -> Tuple[WebhookInboxModel, bool]:
        """
        Durable webhook deduplication:
        Returns:
            (record, is_new: bool)
            If is_new is False, event is an idempotent duplicate and must NOT trigger side-effects.
        """
        stmt = select(WebhookInboxModel).where(
            WebhookInboxModel.provider == provider,
            WebhookInboxModel.environment == environment,
            WebhookInboxModel.payment_id == payment_id,
            WebhookInboxModel.event_type == event_type,
            WebhookInboxModel.nonce == nonce,
        )
        existing = session.execute(stmt).scalar_one_or_none()
        if existing:
            return existing, False

        ev_id = f"{provider}_{payment_id}_{nonce}"
        if len(ev_id) > 128:
            ev_id = f"{provider}_{hashlib.sha256(ev_id.encode('utf-8')).hexdigest()[:32]}_{payment_id[:64]}"[:128]

        record = WebhookInboxModel(
            merchant_id=merchant_id,
            provider=provider[:32],
            environment=environment[:16],
            event_id=ev_id,
            event_type=event_type[:64],
            payment_id=payment_id[:128],
            nonce=nonce[:128],
            signature=signature[:128],
            signature_verified=signature_verified,
            status="RECEIVED",
            payload_sanitized=payload_sanitized,
        )
        session.add(record)
        session.flush()
        return record, True

    @staticmethod
    def mark_processed(session: Session, inbox_id: uuid.UUID, status: str = "PROCESSED") -> None:
        stmt = select(WebhookInboxModel).where(WebhookInboxModel.id == inbox_id)
        record = session.execute(stmt).scalar_one_or_none()
        if record:
            record.status = status
            record.processed_at = _utc_now()
            session.flush()


# ==============================================================================
# 6. IDEMPOTENCY REPOSITORY
# ==============================================================================
class IdempotencyRepository:

    @staticmethod
    def check_or_create(
        session: Session,
        merchant_id: uuid.UUID,
        idempotency_key: str,
        request_path: str,
        request_payload: Any,
        ttl_seconds: int = 86400,
    ) -> Tuple[IdempotencyKeyModel, bool]:
        """
        Returns (record, is_new).
        If not new and status == 'COMPLETED', cached response is safe to return.
        """
        now = _utc_now()
        stmt = select(IdempotencyKeyModel).where(
            IdempotencyKeyModel.merchant_id == merchant_id,
            IdempotencyKeyModel.idempotency_key == idempotency_key,
        )
        existing = session.execute(stmt).scalar_one_or_none()

        if existing:
            # Check if expired (normalizing tz for SQLite and Postgres compatibility)
            exp = existing.expires_at
            if exp and exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp and exp < now:
                # Expired idempotency key: reset and reuse
                existing.status = "PROCESSING"
                existing.created_at = now
                existing.expires_at = now + timedelta(seconds=ttl_seconds)
                existing.response_status_code = None
                existing.response_body = None
                session.flush()
                return existing, True
            return existing, False

        # Compute SHA-256 hash of payload
        payload_bytes = json.dumps(request_payload, sort_keys=True).encode("utf-8") if request_payload else b""
        req_hash = hashlib.sha256(payload_bytes).hexdigest()

        new_entry = IdempotencyKeyModel(
            merchant_id=merchant_id,
            idempotency_key=idempotency_key,
            request_path=request_path,
            request_hash=req_hash,
            status="PROCESSING",
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        session.add(new_entry)
        session.flush()
        return new_entry, True

    @staticmethod
    def complete(
        session: Session,
        idempotency_id: uuid.UUID,
        status_code: int,
        response_body: Dict[str, Any],
    ) -> None:
        stmt = select(IdempotencyKeyModel).where(IdempotencyKeyModel.id == idempotency_id)
        record = session.execute(stmt).scalar_one_or_none()
        if record:
            record.status = "COMPLETED"
            record.response_status_code = status_code
            record.response_body = response_body
            session.flush()


# ==============================================================================
# 7. RECOVERY OUTBOX REPOSITORY (Transactional Outbox Pattern)
# ==============================================================================
class RecoveryOutboxRepository:

    @staticmethod
    def enqueue(
        session: Session,
        merchant_id: uuid.UUID,
        idempotency_key: str,
        action: str,
        channel: str,
        recipient_masked: str,
        message_payload: Dict[str, Any],
        decision_id: Optional[uuid.UUID] = None,
        case_id: Optional[str] = None,
        payment_id: Optional[str] = None,
        max_retries: int = 3,
        delay_seconds: int = 0,
        status: Optional[str] = None,
        requires_operator_approval: Optional[bool] = None,
        approved_by_operator_id: Optional[str] = None,
        approved_at: Optional[datetime] = None,
        approval_snapshot_hash: Optional[str] = None,
    ) -> RecoveryOutboxModel:
        now = _utc_now()
        next_attempt = now + timedelta(seconds=max(0, delay_seconds))

        # Determine operator authorization gate
        is_contact = channel.lower() in ("whatsapp", "sms", "voice", "email")
        req_approval = is_contact if requires_operator_approval is None else requires_operator_approval

        if status is not None:
            final_status = status
        else:
            if approved_by_operator_id:
                final_status = "QUEUED"
            else:
                final_status = "PENDING_APPROVAL" if req_approval else "QUEUED"

        outbox = RecoveryOutboxModel(
            merchant_id=merchant_id,
            decision_id=decision_id,
            case_id=case_id,
            payment_id=payment_id,
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
            requires_operator_approval=req_approval,
            approved_by_operator_id=approved_by_operator_id,
            approved_at=approved_at,
            approval_snapshot_hash=approval_snapshot_hash,
            created_at=now,
            updated_at=now,
        )
        session.add(outbox)
        session.flush()
        return outbox

    @staticmethod
    def approve_job(
        session: Session,
        job_id: uuid.UUID,
        operator_id: str,
        snapshot_hash: Optional[str] = None,
    ) -> RecoveryOutboxModel:
        """
        Explicitly approves a pending recovery action in the outbox.
        Transitions status from PENDING_APPROVAL to QUEUED.
        Stores operator identity, timestamp, and payload cryptographic hash.
        """
        job = session.get(RecoveryOutboxModel, job_id)
        if not job:
            raise ValueError(f"Outbox job {job_id} not found.")

        now = _utc_now()
        from wapsi.recovery.outbox import compute_approval_hash
        computed_hash = snapshot_hash or compute_approval_hash(
            recipient_masked=job.recipient_masked,
            channel=job.channel,
            message_payload=job.message_payload,
            decision_id=str(job.decision_id) if job.decision_id else None,
        )

        job.approved_by_operator_id = operator_id
        job.approved_at = now
        job.approval_snapshot_hash = computed_hash
        job.status = "QUEUED"
        job.updated_at = now
        session.flush()
        return job

    @staticmethod
    def reject_job(
        session: Session,
        job_id: uuid.UUID,
        operator_id: str,
        reason: str = "Rejected by operator",
    ) -> RecoveryOutboxModel:
        """Explicitly marks an outbox job as REJECTED so workers never claim it."""
        job = session.get(RecoveryOutboxModel, job_id)
        if not job:
            raise ValueError(f"Outbox job {job_id} not found.")
        now = _utc_now()
        job.status = "REJECTED"
        job.last_error = f"Rejected by {operator_id}: {reason}"
        job.updated_at = now
        session.flush()
        return job

    @staticmethod
    def fetch_queued(session: Session, limit: int = 50) -> List[RecoveryOutboxModel]:
        now = _utc_now()
        stmt = (
            select(RecoveryOutboxModel)
            .where(
                RecoveryOutboxModel.status.in_(["QUEUED", "RETRY"]),
                RecoveryOutboxModel.next_attempt_at <= now,
            )
            .order_by(RecoveryOutboxModel.next_attempt_at.asc())
            .limit(limit)
        )
        return list(session.execute(stmt).scalars().all())
    @staticmethod
    def claim_jobs(
        session: Session,
        worker_id: str,
        limit: int = 10,
        lease_duration_seconds: int = 60,
        current_time: Optional[datetime] = None,
    ) -> List[RecoveryOutboxModel]:
        """
        Atomically claims pending or expired jobs.
        Under PostgreSQL: First tries public.claim_recovery_outbox_jobs(text, int, int)
        (the hardened SECURITY DEFINER procedure that avoids requiring BYPASSRLS or cross-tenant SELECT grants).
        Falls back to SELECT ... FOR UPDATE SKIP LOCKED candidate selection if running under admin role.
        Under SQLite: performs an atomic candidate select within active transaction.
        """
        now = current_time or _utc_now()
        lease_expires = now + timedelta(seconds=lease_duration_seconds)
        bind = session.get_bind()
        dialect = bind.dialect.name if bind else "sqlite"

        if dialect == "postgresql":
            # Attempt 1: Hardened SECURITY DEFINER procedure (used in real-time execution when current_time is not simulated)
            if current_time is None:
                try:
                    with session.begin_nested():
                        stmt = text(
                            "SELECT id, case_id, payment_id, merchant_id, idempotency_key, "
                            "action, channel, recipient_masked, message_payload, status, "
                            "retry_count, max_retries, next_attempt_at, lease_expires_at, "
                            "worker_id, last_error, created_at, updated_at, "
                            "requires_operator_approval, approved_by_operator_id, approved_at, approval_snapshot_hash "
                            "FROM public.claim_recovery_outbox_jobs(:worker_id, :limit, :lease_sec)"
                        )
                        rows = session.execute(
                            stmt,
                            {
                                "worker_id": worker_id,
                                "limit": limit,
                                "lease_sec": lease_duration_seconds,
                            },
                        ).fetchall()
                    if rows:
                        claimed_models: List[RecoveryOutboxModel] = []
                        for r in rows:
                            m = RecoveryOutboxModel(
                                id=r[0] if isinstance(r[0], uuid.UUID) else uuid.UUID(str(r[0])),
                                case_id=r[1],
                                payment_id=r[2],
                                merchant_id=r[3] if isinstance(r[3], uuid.UUID) else uuid.UUID(str(r[3])),
                                idempotency_key=r[4],
                                action=r[5],
                                channel=r[6],
                                recipient_masked=r[7],
                                message_payload=r[8] if isinstance(r[8], dict) else {},
                                status=r[9],
                                retry_count=r[10],
                                max_retries=r[11],
                                next_attempt_at=r[12],
                                lease_expires_at=r[13],
                                worker_id=r[14],
                                last_error=r[15],
                                created_at=r[16],
                                updated_at=r[17],
                                requires_operator_approval=r[18] if len(r) > 18 else True,
                                approved_by_operator_id=r[19] if len(r) > 19 else None,
                                approved_at=r[20] if len(r) > 20 else None,
                                approval_snapshot_hash=r[21] if len(r) > 21 else None,
                            )
                            claimed_models.append(m)
                        return claimed_models
                    return []
                except Exception as fn_err:
                    logger.debug(f"claim_recovery_outbox_jobs function not available: {fn_err}")

            # Attempt 2: Direct SELECT ... FOR UPDATE SKIP LOCKED
            candidate_stmt = (
                select(RecoveryOutboxModel.id)
                .where(
                    or_(
                        and_(
                            RecoveryOutboxModel.status.in_(["QUEUED", "RETRY"]),
                            RecoveryOutboxModel.next_attempt_at <= now,
                        ),
                        and_(
                            RecoveryOutboxModel.status == "SENDING",
                            RecoveryOutboxModel.lease_expires_at.is_not(None),
                            RecoveryOutboxModel.lease_expires_at < now,
                        ),
                    ),
                    RecoveryOutboxModel.status.notin_(["PENDING_APPROVAL", "REJECTED", "CANCELLED", "DEAD_LETTER"]),
                    or_(
                        RecoveryOutboxModel.requires_operator_approval.is_(False),
                        and_(
                            RecoveryOutboxModel.requires_operator_approval.is_(True),
                            RecoveryOutboxModel.approved_by_operator_id.isnot(None),
                            RecoveryOutboxModel.approved_at.isnot(None),
                            RecoveryOutboxModel.approval_snapshot_hash.isnot(None),
                        ),
                    ),
                )
                .order_by(RecoveryOutboxModel.next_attempt_at.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            candidate_ids = list(session.execute(candidate_stmt).scalars().all())
            if not candidate_ids:
                return []

            update_stmt = (
                update(RecoveryOutboxModel)
                .where(RecoveryOutboxModel.id.in_(candidate_ids))
                .values(
                    status="SENDING",
                    worker_id=worker_id,
                    lease_expires_at=lease_expires,
                    updated_at=now,
                )
            )
            session.execute(update_stmt)
            session.flush()

            claimed = list(
                session.execute(
                    select(RecoveryOutboxModel)
                    .where(RecoveryOutboxModel.id.in_(candidate_ids))
                    .order_by(RecoveryOutboxModel.next_attempt_at.asc())
                ).scalars().all()
            )
            return claimed
        else:
            candidate_stmt = (
                select(RecoveryOutboxModel)
                .where(
                    or_(
                        and_(
                            RecoveryOutboxModel.status.in_(["QUEUED", "RETRY"]),
                            RecoveryOutboxModel.next_attempt_at <= now,
                        ),
                        and_(
                            RecoveryOutboxModel.status == "SENDING",
                            RecoveryOutboxModel.lease_expires_at.is_not(None),
                            RecoveryOutboxModel.lease_expires_at < now,
                        ),
                    ),
                    RecoveryOutboxModel.status.notin_(["PENDING_APPROVAL", "REJECTED", "CANCELLED", "DEAD_LETTER"]),
                    or_(
                        RecoveryOutboxModel.requires_operator_approval.is_(False),
                        and_(
                            RecoveryOutboxModel.requires_operator_approval.is_(True),
                            RecoveryOutboxModel.approved_by_operator_id.isnot(None),
                            RecoveryOutboxModel.approved_at.isnot(None),
                            RecoveryOutboxModel.approval_snapshot_hash.isnot(None),
                        ),
                    ),
                )
                .order_by(RecoveryOutboxModel.next_attempt_at.asc())
                .limit(limit)
            )
            candidates = list(session.execute(candidate_stmt).scalars().all())
            for c in candidates:
                c.status = "SENDING"
                c.worker_id = worker_id
                c.lease_expires_at = lease_expires
                c.updated_at = now
            session.flush()
            return candidates

    @staticmethod
    def claim_job_by_id(
        session: Session,
        job_id: uuid.UUID,
        worker_id: str,
        merchant_id: Optional[uuid.UUID] = None,
        lease_duration_seconds: int = 60,
        current_time: Optional[datetime] = None,
    ) -> Optional[RecoveryOutboxModel]:
        """
        Atomically claims a specific outbox job by its unique UUID and merchant boundary.
        Strictly enforces that ONLY this exact job for the authorized tenant can be claimed.
        Under PostgreSQL: executes public.claim_specific_recovery_outbox_job(:jid, :mid, :worker_id, :lease_sec).
        Falls back to direct SELECT ... FOR UPDATE SKIP LOCKED on the exact job ID and merchant ID.
        Under SQLite: selects only this exact job ID in BEGIN IMMEDIATE transaction.
        Returns the claimed model, or None if unapproved, not found, wrong tenant, or active lease held.
        """
        now = current_time or _utc_now()
        lease_expires = now + timedelta(seconds=lease_duration_seconds)
        bind = session.get_bind()
        dialect = bind.dialect.name if bind else "sqlite"

        if dialect == "postgresql":
            if current_time is None:
                try:
                    with session.begin_nested():
                        stmt = text(
                            "SELECT id, case_id, payment_id, merchant_id, idempotency_key, "
                            "action, channel, recipient_masked, message_payload, status, "
                            "retry_count, max_retries, next_attempt_at, lease_expires_at, "
                            "worker_id, last_error, created_at, updated_at, "
                            "requires_operator_approval, approved_by_operator_id, approved_at, approval_snapshot_hash "
                            "FROM public.claim_specific_recovery_outbox_job(:jid, :mid, :worker_id, :lease_sec)"
                        )
                        rows = session.execute(
                            stmt,
                            {
                                "jid": job_id,
                                "mid": merchant_id,
                                "worker_id": worker_id,
                                "lease_sec": lease_duration_seconds,
                            },
                        ).fetchall()
                    if rows:
                        r = rows[0]
                        return RecoveryOutboxModel(
                            id=r[0] if isinstance(r[0], uuid.UUID) else uuid.UUID(str(r[0])),
                            case_id=r[1],
                            payment_id=r[2],
                            merchant_id=r[3] if isinstance(r[3], uuid.UUID) else uuid.UUID(str(r[3])),
                            idempotency_key=r[4],
                            action=r[5],
                            channel=r[6],
                            recipient_masked=r[7],
                            message_payload=r[8] if isinstance(r[8], dict) else {},
                            status=r[9],
                            retry_count=r[10],
                            max_retries=r[11],
                            next_attempt_at=r[12],
                            lease_expires_at=r[13],
                            worker_id=r[14],
                            last_error=r[15],
                            created_at=r[16],
                            updated_at=r[17],
                            requires_operator_approval=r[18] if len(r) > 18 else True,
                            approved_by_operator_id=r[19] if len(r) > 19 else None,
                            approved_at=r[20] if len(r) > 20 else None,
                            approval_snapshot_hash=r[21] if len(r) > 21 else None,
                        )
                    return None
                except Exception as fn_err:
                    logger.debug(f"claim_specific_recovery_outbox_job error: {fn_err}")

            # Fallback to direct candidate selection on this exact job_id and merchant_id
            filters = [
                RecoveryOutboxModel.id == job_id,
                or_(
                    and_(
                        RecoveryOutboxModel.status.in_(["QUEUED", "RETRY"]),
                        RecoveryOutboxModel.next_attempt_at <= now,
                    ),
                    and_(
                        RecoveryOutboxModel.status == "SENDING",
                        RecoveryOutboxModel.lease_expires_at.is_not(None),
                        RecoveryOutboxModel.lease_expires_at < now,
                    ),
                ),
                RecoveryOutboxModel.status.notin_(["PENDING_APPROVAL", "REJECTED", "CANCELLED", "DEAD_LETTER"]),
                or_(
                    RecoveryOutboxModel.requires_operator_approval.is_(False),
                    and_(
                        RecoveryOutboxModel.requires_operator_approval.is_(True),
                        RecoveryOutboxModel.approved_by_operator_id.isnot(None),
                        RecoveryOutboxModel.approved_at.isnot(None),
                        RecoveryOutboxModel.approval_snapshot_hash.isnot(None),
                    ),
                ),
            ]
            if merchant_id is not None:
                filters.append(RecoveryOutboxModel.merchant_id == merchant_id)

            candidate_stmt = select(RecoveryOutboxModel.id).where(*filters).with_for_update(skip_locked=True)
            cid = session.execute(candidate_stmt).scalar_one_or_none()
            if not cid:
                return None

            update_stmt = (
                update(RecoveryOutboxModel)
                .where(RecoveryOutboxModel.id == cid)
                .values(
                    status="SENDING",
                    worker_id=worker_id,
                    lease_expires_at=lease_expires,
                    updated_at=now,
                )
            )
            session.execute(update_stmt)
            session.flush()
            return session.get(RecoveryOutboxModel, cid)
        else:
            sqlite_filters = [
                RecoveryOutboxModel.id == job_id,
                or_(
                    and_(
                        RecoveryOutboxModel.status.in_(["QUEUED", "RETRY"]),
                        RecoveryOutboxModel.next_attempt_at <= now,
                    ),
                    and_(
                        RecoveryOutboxModel.status == "SENDING",
                        RecoveryOutboxModel.lease_expires_at.is_not(None),
                        RecoveryOutboxModel.lease_expires_at < now,
                    ),
                ),
                RecoveryOutboxModel.status.notin_(["PENDING_APPROVAL", "REJECTED", "CANCELLED", "DEAD_LETTER"]),
                or_(
                    RecoveryOutboxModel.requires_operator_approval.is_(False),
                    and_(
                        RecoveryOutboxModel.requires_operator_approval.is_(True),
                        RecoveryOutboxModel.approved_by_operator_id.isnot(None),
                        RecoveryOutboxModel.approved_at.isnot(None),
                        RecoveryOutboxModel.approval_snapshot_hash.isnot(None),
                    ),
                ),
            ]
            if merchant_id is not None:
                sqlite_filters.append(RecoveryOutboxModel.merchant_id == merchant_id)

            candidate_stmt = select(RecoveryOutboxModel).where(*sqlite_filters)
            candidate = session.execute(candidate_stmt).scalar_one_or_none()
            if not candidate:
                return None
            candidate.status = "SENDING"
            candidate.worker_id = worker_id
            candidate.lease_expires_at = lease_expires
            candidate.updated_at = now
            session.flush()
            return candidate

    @staticmethod
    def complete_job(
        session: Session,
        job_id: uuid.UUID,
        worker_id: str,
        merchant_id: Optional[Any] = None,
    ) -> bool:
        bind = session.get_bind()
        if merchant_id and bind and bind.dialect.name == "postgresql":
            session.execute(
                text("SELECT set_config('app.current_merchant_id', :m_id, true)"),
                {"m_id": str(merchant_id)},
            )
        stmt = (
            update(RecoveryOutboxModel)
            .where(RecoveryOutboxModel.id == job_id, RecoveryOutboxModel.worker_id == worker_id)
            .values(
                status="SENT",
                lease_expires_at=None,
                updated_at=_utc_now(),
                last_error=None,
            )
        )
        res = session.execute(stmt)
        session.flush()
        return res.rowcount > 0

    @staticmethod
    def fail_job(
        session: Session,
        job_id: uuid.UUID,
        worker_id: str,
        error_message: str,
        is_retryable: bool = True,
        backoff_seconds: int = 60,
        retry_after_seconds: Optional[int] = None,
        merchant_id: Optional[Any] = None,
    ) -> bool:
        bind = session.get_bind()
        if merchant_id and bind and bind.dialect.name == "postgresql":
            session.execute(
                text("SELECT set_config('app.current_merchant_id', :m_id, true)"),
                {"m_id": str(merchant_id)},
            )
        now = _utc_now()
        stmt = select(RecoveryOutboxModel).where(
            RecoveryOutboxModel.id == job_id, RecoveryOutboxModel.worker_id == worker_id
        )
        item = session.execute(stmt).scalar_one_or_none()
        if not item:
            return False

        item.retry_count += 1
        if not is_retryable or item.retry_count >= item.max_retries:
            item.status = "DEAD_LETTER"
            item.next_attempt_at = now
        else:
            item.status = "RETRY"
            delay = retry_after_seconds if retry_after_seconds is not None else backoff_seconds
            item.next_attempt_at = now + timedelta(seconds=delay)

        item.lease_expires_at = None
        item.last_error = error_message
        item.updated_at = now
        session.flush()
        return True

    @staticmethod
    def mark_reconciliation_required(
        session: Session,
        job_id: uuid.UUID,
        worker_id: str,
        reason: Optional[str] = None,
        error_message: Optional[str] = None,
        merchant_id: Optional[Any] = None,
    ) -> bool:
        bind = session.get_bind()
        if merchant_id and bind and bind.dialect.name == "postgresql":
            session.execute(
                text("SELECT set_config('app.current_merchant_id', :m_id, true)"),
                {"m_id": str(merchant_id)},
            )
        now = _utc_now()
        effective_reason = error_message or reason or "Ambiguous network outcome"
        stmt = (
            update(RecoveryOutboxModel)
            .where(
                RecoveryOutboxModel.id == job_id,
                or_(RecoveryOutboxModel.worker_id == worker_id, RecoveryOutboxModel.worker_id.is_(None)),
            )
            .values(
                status="RECONCILIATION_REQUIRED",
                lease_expires_at=None,
                last_error=f"Ambiguous network outcome: {effective_reason}",
                updated_at=now,
            )
        )
        res = session.execute(stmt)
        session.flush()
        return res.rowcount > 0

    @staticmethod
    def cancel_jobs_for_case(
        session: Session,
        case_id: str,
        reason: str = "CASE_RECOVERED",
        merchant_id: Optional[Any] = None,
    ) -> int:
        bind = session.get_bind()
        if merchant_id and bind and bind.dialect.name == "postgresql":
            session.execute(
                text("SELECT set_config('app.current_merchant_id', :m_id, true)"),
                {"m_id": str(merchant_id)},
            )
        now = _utc_now()
        stmt = (
            update(RecoveryOutboxModel)
            .where(
                RecoveryOutboxModel.case_id == case_id,
                RecoveryOutboxModel.status.in_(["PENDING_APPROVAL", "QUEUED", "RETRY", "SENDING"]),
            )
            .values(
                status="CANCELLED",
                lease_expires_at=None,
                last_error=reason,
                updated_at=now,
            )
        )
        res = session.execute(stmt)
        session.flush()
        return res.rowcount

    @staticmethod
    def transition_status(
        session: Session,
        outbox_id: uuid.UUID,
        new_status: str,
        last_error: Optional[str] = None,
        retry_delay_seconds: int = 60,
    ) -> None:
        stmt = select(RecoveryOutboxModel).where(RecoveryOutboxModel.id == outbox_id)
        item = session.execute(stmt).scalar_one_or_none()
        if not item:
            return

        item.status = new_status
        if last_error:
            item.last_error = last_error

        if new_status == "RETRY":
            item.retry_count += 1
            if item.retry_count >= item.max_retries:
                item.status = "DEAD_LETTER"
            else:
                # Exponential backoff
                backoff = retry_delay_seconds * (2 ** (item.retry_count - 1))
                item.next_attempt_at = _utc_now() + timedelta(seconds=backoff)
        elif new_status == "SENT":
            item.last_error = None

        session.flush()

    @staticmethod
    def count_active_leases(
        session: Session,
        worker_id: Optional[str] = None,
        current_time: Optional[datetime] = None,
        merchant_id: Optional[Any] = None,
    ) -> int:
        """Counts currently active leases (status='SENDING' and lease_expires_at >= now)."""
        now = current_time or _utc_now()
        bind = session.get_bind()
        if merchant_id and bind and bind.dialect.name == "postgresql":
            session.execute(
                text("SELECT set_config('app.current_merchant_id', :m_id, true)"),
                {"m_id": str(merchant_id)},
            )
        stmt = select(func.count(RecoveryOutboxModel.id)).where(
            RecoveryOutboxModel.status == "SENDING",
            RecoveryOutboxModel.lease_expires_at.is_not(None),
            RecoveryOutboxModel.lease_expires_at >= now,
        )
        if worker_id:
            stmt = stmt.where(RecoveryOutboxModel.worker_id == worker_id)
        if merchant_id is not None:
            m_uuid = uuid.UUID(str(merchant_id)) if not isinstance(merchant_id, uuid.UUID) else merchant_id
            stmt = stmt.where(RecoveryOutboxModel.merchant_id == m_uuid)
        return int(session.execute(stmt).scalar() or 0)

    @staticmethod
    def release_lease(
        session: Session,
        job_id: uuid.UUID,
        worker_id: str,
        merchant_id: Optional[Any] = None,
    ) -> bool:
        """
        Releases an active lease for an undispatched job held by worker_id,
        returning it to QUEUED status so it can be claimed by other workers.
        Only jobs currently in status 'SENDING' held by worker_id can be released.
        """
        bind = session.get_bind()
        if merchant_id and bind and bind.dialect.name == "postgresql":
            session.execute(
                text("SELECT set_config('app.current_merchant_id', :m_id, true)"),
                {"m_id": str(merchant_id)},
            )
        now = _utc_now()
        stmt = (
            update(RecoveryOutboxModel)
            .where(
                RecoveryOutboxModel.id == job_id,
                RecoveryOutboxModel.worker_id == worker_id,
                RecoveryOutboxModel.status == "SENDING",
            )
            .values(
                status="QUEUED",
                worker_id=None,
                lease_expires_at=None,
                updated_at=now,
            )
        )
        if merchant_id is not None:
            m_uuid = uuid.UUID(str(merchant_id)) if not isinstance(merchant_id, uuid.UUID) else merchant_id
            stmt = stmt.where(RecoveryOutboxModel.merchant_id == m_uuid)
        res = session.execute(stmt)
        session.flush()
        return res.rowcount > 0

    @staticmethod
    def release_leases_for_worker(
        session: Session,
        worker_id: str,
        merchant_id: Optional[Any] = None,
        exclude_job_ids: Optional[List[Any]] = None,
    ) -> int:
        """
        Releases all undispatched leases held by worker_id (e.g. during graceful shutdown).
        Only jobs currently in status 'SENDING' held by worker_id are reset to 'QUEUED'.
        Optional exclude_job_ids preserves in-flight operations that timed out.
        """
        bind = session.get_bind()
        if merchant_id and bind and bind.dialect.name == "postgresql":
            session.execute(
                text("SELECT set_config('app.current_merchant_id', :m_id, true)"),
                {"m_id": str(merchant_id)},
            )
        now = _utc_now()
        stmt = (
            update(RecoveryOutboxModel)
            .where(
                RecoveryOutboxModel.worker_id == worker_id,
                RecoveryOutboxModel.status == "SENDING",
            )
            .values(
                status="QUEUED",
                worker_id=None,
                lease_expires_at=None,
                updated_at=now,
            )
        )
        if merchant_id is not None:
            m_uuid = uuid.UUID(str(merchant_id)) if not isinstance(merchant_id, uuid.UUID) else merchant_id
            stmt = stmt.where(RecoveryOutboxModel.merchant_id == m_uuid)
        if exclude_job_ids:
            clean_ex_ids = [
                uuid.UUID(str(jid)) if not isinstance(jid, uuid.UUID) else jid
                for jid in exclude_job_ids
            ]
            stmt = stmt.where(~RecoveryOutboxModel.id.in_(clean_ex_ids))
        res = session.execute(stmt)
        session.flush()
        return res.rowcount

    @staticmethod
    def reclaim_expired_leases(
        session: Session,
        current_time: Optional[datetime] = None,
        max_reclaim: int = 50,
        merchant_id: Optional[Any] = None,
    ) -> int:
        """
        Reclaims abandoned/expired leases where lease_expires_at < current_time.
        Transitions expired SENDING jobs back to QUEUED with lease_expires_at = None and worker_id = None.
        Uses FOR UPDATE SKIP LOCKED under PostgreSQL to coordinate safely across concurrent workers.
        """
        now = current_time or _utc_now()
        bind = session.get_bind()
        m_uuid = None
        if merchant_id is not None:
            m_uuid = uuid.UUID(str(merchant_id)) if not isinstance(merchant_id, uuid.UUID) else merchant_id
            if bind and bind.dialect.name == "postgresql":
                session.execute(
                    text("SELECT set_config('app.current_merchant_id', :m_id, true)"),
                    {"m_id": str(m_uuid)},
                )

        dialect = bind.dialect.name if bind else "sqlite"
        if dialect == "postgresql":
            candidate_stmt = (
                select(RecoveryOutboxModel.id)
                .where(
                    RecoveryOutboxModel.status == "SENDING",
                    RecoveryOutboxModel.lease_expires_at.is_not(None),
                    RecoveryOutboxModel.lease_expires_at < now,
                )
            )
            if m_uuid is not None:
                candidate_stmt = candidate_stmt.where(RecoveryOutboxModel.merchant_id == m_uuid)
            candidate_stmt = candidate_stmt.limit(max_reclaim).with_for_update(skip_locked=True)

            cids = list(session.execute(candidate_stmt).scalars().all())
            if not cids:
                return 0

            update_stmt = (
                update(RecoveryOutboxModel)
                .where(RecoveryOutboxModel.id.in_(cids))
                .values(
                    status="QUEUED",
                    worker_id=None,
                    lease_expires_at=None,
                    updated_at=now,
                )
            )
            res = session.execute(update_stmt)
            session.flush()
            return res.rowcount
        else:
            # SQLite / Fallback dialect via SQLAlchemy
            candidate_stmt = (
                select(RecoveryOutboxModel.id)
                .where(
                    RecoveryOutboxModel.status == "SENDING",
                    RecoveryOutboxModel.lease_expires_at.is_not(None),
                    RecoveryOutboxModel.lease_expires_at < now,
                )
            )
            if m_uuid is not None:
                candidate_stmt = candidate_stmt.where(RecoveryOutboxModel.merchant_id == m_uuid)
            candidate_stmt = candidate_stmt.limit(max_reclaim)

            cids = list(session.execute(candidate_stmt).scalars().all())
            if not cids:
                return 0

            stmt = (
                update(RecoveryOutboxModel)
                .where(RecoveryOutboxModel.id.in_(cids))
                .values(
                    status="QUEUED",
                    worker_id=None,
                    lease_expires_at=None,
                    updated_at=now,
                )
            )
            res = session.execute(stmt)
            session.flush()
            return res.rowcount


# ==============================================================================
# 8. AUDIT LEDGER REPOSITORY (Append-Only Cryptographic Chain)
# ==============================================================================
class AuditLedgerRepository:

    @staticmethod
    def append_block(
        session: Session,
        event_type: str,
        data_payload: Dict[str, Any],
        merchant_id: Optional[uuid.UUID] = None,
    ) -> AuditLedgerBlockModel:
        """Appends a new cryptographically chained block to the audit ledger."""
        # Under PostgreSQL, acquire transaction-scoped advisory lock to prevent concurrent index collision
        try:
            bind = session.get_bind()
            if bind and "postgresql" in str(bind.url):
                lock_id = (hash(f"audit_ledger_{merchant_id}") & 0x7FFFFFFF)
                session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})
        except Exception:
            pass  # Fallback gracefully if dialect doesn't support advisory locks

        # Find latest block index and hash
        stmt = (
            select(AuditLedgerBlockModel)
            .where(AuditLedgerBlockModel.merchant_id == merchant_id)
            .order_by(desc(AuditLedgerBlockModel.block_index))
            .limit(1)
        )
        last_block = session.execute(stmt).scalar_one_or_none()

        if last_block:
            next_index = last_block.block_index + 1
            prev_hash = last_block.block_hash
        else:
            next_index = 0
            prev_hash = "0" * 64

        now = _utc_now()
        timestamp_str = now.isoformat()

        # Compute SHA-256 block hash
        canonical_data = json.dumps(data_payload, sort_keys=True)
        raw_to_hash = f"{next_index}:{prev_hash}:{timestamp_str}:{event_type}:{canonical_data}"
        block_hash = hashlib.sha256(raw_to_hash.encode("utf-8")).hexdigest()

        block = AuditLedgerBlockModel(
            merchant_id=merchant_id,
            block_index=next_index,
            previous_hash=prev_hash,
            block_hash=block_hash,
            event_type=event_type,
            data_payload=data_payload,
            timestamp=now,
        )
        session.add(block)
        session.flush()
        return block

    @staticmethod
    def verify_integrity(session: Session, merchant_id: Optional[uuid.UUID] = None) -> Dict[str, Any]:
        """Validates the continuous SHA-256 hash chaining of all blocks in database."""
        stmt = (
            select(AuditLedgerBlockModel)
            .where(AuditLedgerBlockModel.merchant_id == merchant_id)
            .order_by(AuditLedgerBlockModel.block_index.asc())
        )
        blocks = list(session.execute(stmt).scalars().all())

        if not blocks:
            return {"is_valid": True, "blocks_count": 0, "message": "No blocks in ledger."}

        prev_hash = "0" * 64
        for idx, block in enumerate(blocks):
            if block.block_index != idx:
                return {
                    "is_valid": False,
                    "error": f"Sequence break at block index {block.block_index}, expected {idx}",
                    "corrupt_index": block.block_index,
                }
            if block.previous_hash != prev_hash:
                return {
                    "is_valid": False,
                    "error": f"Hash chain broken at index {idx}! Expected previous {prev_hash}, got {block.previous_hash}",
                    "corrupt_index": idx,
                }
            prev_hash = block.block_hash

        return {"is_valid": True, "blocks_count": len(blocks), "latest_hash": prev_hash}

    @staticmethod
    def get_recent_blocks(session: Session, merchant_id: Optional[uuid.UUID] = None, limit: int = 50) -> List[AuditLedgerBlockModel]:
        stmt = (
            select(AuditLedgerBlockModel)
            .where(AuditLedgerBlockModel.merchant_id == merchant_id)
            .order_by(desc(AuditLedgerBlockModel.block_index))
            .limit(limit)
        )
        return list(session.execute(stmt).scalars().all())

# ==============================================================================
# 9. BANDIT WEIGHTS REPOSITORY (Online Learning State Persistence)
# ==============================================================================
class BanditRepository:

    @staticmethod
    def save_action_weights(
        session: Session,
        merchant_id: uuid.UUID,
        model_version: str,
        action: str,
        matrix_a: List[List[float]],
        vector_b: List[float],
        alpha: float = 0.8,
        updates_count: int = 1,
    ) -> BanditWeightModel:
        stmt = select(BanditWeightModel).where(
            BanditWeightModel.merchant_id == merchant_id,
            BanditWeightModel.model_version == model_version,
            BanditWeightModel.action == action,
        )
        record = session.execute(stmt).scalar_one_or_none()
        if record:
            record.matrix_a = matrix_a
            record.vector_b = vector_b
            record.alpha = alpha
            record.total_updates += updates_count
            record.last_updated_at = _utc_now()
        else:
            record = BanditWeightModel(
                merchant_id=merchant_id,
                model_version=model_version,
                action=action,
                matrix_a=matrix_a,
                vector_b=vector_b,
                alpha=alpha,
                total_updates=updates_count,
            )
            session.add(record)
        session.flush()
        return record

    @staticmethod
    def load_action_weights(
        session: Session,
        merchant_id: uuid.UUID,
        model_version: str,
        action: str,
    ) -> Optional[BanditWeightModel]:
        stmt = select(BanditWeightModel).where(
            BanditWeightModel.merchant_id == merchant_id,
            BanditWeightModel.model_version == model_version,
            BanditWeightModel.action == action,
        )
        return session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def load_all_weights(
        session: Session,
        merchant_id: uuid.UUID,
        model_version: str = "v1.0.0",
    ) -> Dict[str, Dict[str, Any]]:
        stmt = select(BanditWeightModel).where(
            BanditWeightModel.merchant_id == merchant_id,
            BanditWeightModel.model_version == model_version,
        )
        records = session.execute(stmt).scalars().all()
        return {
            r.action: {
                "matrix_a": r.matrix_a,
                "vector_b": r.vector_b,
                "alpha": float(r.alpha),
                "total_updates": r.total_updates,
            }
            for r in records
        }


# ==============================================================================
# 11. PERSISTENT OPT-OUT & CONSENT REPOSITORY
# ==============================================================================
class OptOutRepository:

    @staticmethod
    def is_opted_out(session: Session, phone_normalized: str) -> bool:
        stmt = select(OptOutRegistryModel).where(
            OptOutRegistryModel.phone == phone_normalized,
            OptOutRegistryModel.is_active.is_(True),
        )
        return session.execute(stmt).scalar_one_or_none() is not None

    @staticmethod
    def record_opt_out(
        session: Session,
        phone_normalized: str,
        reason: str = "STOP_KEYWORD",
        source: str = "inbound_whatsapp",
        actor: Optional[str] = None,
    ) -> bool:
        now = _utc_now()
        existing = session.execute(
            select(OptOutRegistryModel).where(OptOutRegistryModel.phone == phone_normalized)
        ).scalar_one_or_none()

        if existing:
            if existing.is_active:
                audit = OptOutAuditTrailModel(
                    phone=phone_normalized,
                    action="DUPLICATE_OPT_OUT",
                    reason=reason,
                    source=source,
                    consent_proof=None,
                    created_at_utc=now,
                    actor=actor,
                )
                session.add(audit)
                session.flush()
                return True
            else:
                # Subsequent opt-out: Reactivate existing record
                existing.is_active = True
                existing.opted_out_at = now
                existing.revoked_at = None
                existing.reason = reason
                existing.source = source
                existing.actor = actor

                audit = OptOutAuditTrailModel(
                    phone=phone_normalized,
                    action="OPT_OUT",
                    reason=reason,
                    source=source,
                    consent_proof=None,
                    created_at_utc=now,
                    actor=actor,
                )
                session.add(audit)
                session.flush()
                return True

        reg = OptOutRegistryModel(
            phone=phone_normalized,
            reason=reason,
            source=source,
            opted_out_at=now,
            actor=actor,
            is_active=True,
            revoked_at=None,
        )
        audit = OptOutAuditTrailModel(
            phone=phone_normalized,
            action="OPT_OUT",
            reason=reason,
            source=source,
            consent_proof=None,
            created_at_utc=now,
            actor=actor,
        )
        session.add(reg)
        session.add(audit)
        session.flush()
        return True

    @staticmethod
    def revoke_opt_out(
        session: Session,
        phone_normalized: str,
        consent_proof: str,
        actor: Optional[str] = None,
    ) -> bool:
        if not consent_proof or len(consent_proof.strip()) < 5:
            raise ValueError("Re-subscription strictly requires an explicit, verified consent proof.")

        stmt = select(OptOutRegistryModel).where(OptOutRegistryModel.phone == phone_normalized)
        existing = session.execute(stmt).scalar_one_or_none()
        if not existing or not existing.is_active:
            return False

        now = _utc_now()
        existing.is_active = False
        existing.revoked_at = now
        audit = OptOutAuditTrailModel(
            phone=phone_normalized,
            action="REVOCATION",
            reason="EXPLICIT_RE_CONSENT",
            source="reopt_in_flow",
            consent_proof=consent_proof,
            created_at_utc=now,
            actor=actor,
        )
        session.add(audit)
        session.flush()
        return True

    @staticmethod
    def record_interaction(session: Session, phone_normalized: str, timestamp_dt: Optional[datetime] = None) -> None:
        now = timestamp_dt or _utc_now()
        stmt = select(CustomerInteractionModel).where(CustomerInteractionModel.phone == phone_normalized)
        existing = session.execute(stmt).scalar_one_or_none()
        if existing:
            existing.last_interaction_at = now
        else:
            rec = CustomerInteractionModel(phone=phone_normalized, last_interaction_at=now)
            session.add(rec)
        session.flush()

    @staticmethod
    def get_last_interaction(session: Session, phone_normalized: str) -> Optional[float]:
        from wapsi.integrations.whatsapp.service_window import normalize_utc_timestamp
        stmt = select(CustomerInteractionModel).where(CustomerInteractionModel.phone == phone_normalized)
        record = session.execute(stmt).scalar_one_or_none()
        if not record or not record.last_interaction_at:
            return None
        return normalize_utc_timestamp(record.last_interaction_at)

    @staticmethod
    def is_within_24h_window(session: Session, phone_normalized: str, current_time: Optional[Union[datetime, float, int, str]] = None) -> bool:
        from wapsi.integrations.whatsapp.service_window import normalize_utc_timestamp
        stmt = select(CustomerInteractionModel).where(CustomerInteractionModel.phone == phone_normalized)
        record = session.execute(stmt).scalar_one_or_none()
        if not record or not record.last_interaction_at:
            return False
        last_utc = normalize_utc_timestamp(record.last_interaction_at)
        if last_utc is None:
            return False
        now_utc = normalize_utc_timestamp(current_time) if current_time is not None else time.time()
        if now_utc is None:
            now_utc = time.time()
        diff = now_utc - last_utc
        return 0.0 <= diff <= 86400.0

    @staticmethod
    def get_audit_trail(session: Session, phone_normalized: Optional[str] = None) -> List[Dict[str, Any]]:
        stmt = select(OptOutAuditTrailModel)
        if phone_normalized:
            stmt = stmt.where(OptOutAuditTrailModel.phone == phone_normalized)
        stmt = stmt.order_by(OptOutAuditTrailModel.created_at_utc.asc())
        records = session.execute(stmt).scalars().all()
        return [r.to_dict() for r in records]


# ==============================================================================
# 12. OBSERVATIONAL LEARNING RECORD REPOSITORY (Gate 5 PostgreSQL Persistence)
# ==============================================================================
class ObservationalRecordRepository:
    """Repository for ObservationalLearningRecordModel persistence, queries, and offline DML export."""

    @staticmethod
    def save_record(session: Session, record_dict: Dict[str, Any]) -> ObservationalLearningRecordModel:
        """Persists a new decision observation record."""
        model = ObservationalLearningRecordModel(
            decision_id=record_dict["decision_id"],
            payment_id=record_dict["payment_id"],
            merchant_id=str(record_dict["merchant_id"]),
            case_id=record_dict.get("case_id"),
            decision_timestamp_utc=record_dict.get("decision_timestamp_utc", _utc_now().isoformat()),
            context_features=record_dict.get("context_features", {}),
            feature_vector=record_dict.get("feature_vector"),
            action_selected=record_dict["action_selected"],
            action_id=record_dict.get("action_id"),
            assignment_propensity=float(record_dict.get("assignment_propensity", 1.0)),
            is_propensity_valid=bool(record_dict.get("is_propensity_valid", True)),
            policy_version=record_dict.get("policy_version", "v1.0.0"),
            model_version=record_dict.get("model_version", "v1.2.0-dml"),
            feature_schema_version=record_dict.get("feature_schema_version", "v1"),
            reward_definition_version=record_dict.get("reward_definition_version", "v1"),
            observation_status=record_dict.get("observation_status", "PENDING_OUTCOME"),
            outcome_status=record_dict.get("outcome_status"),
            recovered_amount_paise=int(record_dict.get("recovered_amount_paise", 0)),
            outcome_timestamp_utc=record_dict.get("outcome_timestamp_utc"),
            event_id=record_dict.get("event_id"),
            event_source=record_dict.get("event_source"),
            deterministic_reward=record_dict.get("deterministic_reward"),
            is_eligible_for_dml=bool(record_dict.get("is_eligible_for_dml", False)),
            is_eligible_for_bandit=bool(record_dict.get("is_eligible_for_bandit", False)),
            exclusion_reasons=record_dict.get("exclusion_reasons", []),
            correction_history=record_dict.get("correction_history", []),
            created_at_utc=record_dict.get("created_at_utc", _utc_now().isoformat()),
            updated_at_utc=record_dict.get("updated_at_utc", _utc_now().isoformat()),
        )
        session.add(model)
        session.flush()
        return model

    @staticmethod
    def get_by_decision_id(session: Session, decision_id: str) -> Optional[ObservationalLearningRecordModel]:
        stmt = select(ObservationalLearningRecordModel).where(
            ObservationalLearningRecordModel.decision_id == decision_id
        )
        return session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def get_by_payment_id(
        session: Session, payment_id: str, merchant_id: Optional[str] = None
    ) -> Optional[ObservationalLearningRecordModel]:
        stmt = select(ObservationalLearningRecordModel).where(
            ObservationalLearningRecordModel.payment_id == payment_id
        )
        if merchant_id:
            stmt = stmt.where(ObservationalLearningRecordModel.merchant_id == str(merchant_id))
        stmt = stmt.order_by(desc(ObservationalLearningRecordModel.created_at_utc)).limit(1)
        return session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def get_by_case_id(
        session: Session, case_id: str, merchant_id: Optional[str] = None
    ) -> Optional[ObservationalLearningRecordModel]:
        stmt = select(ObservationalLearningRecordModel).where(
            ObservationalLearningRecordModel.case_id == case_id
        )
        if merchant_id:
            stmt = stmt.where(ObservationalLearningRecordModel.merchant_id == str(merchant_id))
        stmt = stmt.order_by(desc(ObservationalLearningRecordModel.created_at_utc)).limit(1)
        return session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def update_record(session: Session, record_dict: Dict[str, Any]) -> Optional[ObservationalLearningRecordModel]:
        dec_id = record_dict["decision_id"]
        model = ObservationalRecordRepository.get_by_decision_id(session, dec_id)
        if not model:
            return None
        model.observation_status = record_dict.get("observation_status", model.observation_status)
        model.outcome_status = record_dict.get("outcome_status", model.outcome_status)
        model.recovered_amount_paise = int(record_dict.get("recovered_amount_paise", model.recovered_amount_paise))
        model.outcome_timestamp_utc = record_dict.get("outcome_timestamp_utc", model.outcome_timestamp_utc)
        model.event_id = record_dict.get("event_id", model.event_id)
        model.event_source = record_dict.get("event_source", model.event_source)
        model.deterministic_reward = record_dict.get("deterministic_reward", model.deterministic_reward)
        model.is_eligible_for_dml = bool(record_dict.get("is_eligible_for_dml", model.is_eligible_for_dml))
        model.is_eligible_for_bandit = bool(record_dict.get("is_eligible_for_bandit", model.is_eligible_for_bandit))
        model.exclusion_reasons = record_dict.get("exclusion_reasons", model.exclusion_reasons)
        model.correction_history = record_dict.get("correction_history", model.correction_history)
        model.updated_at_utc = record_dict.get("updated_at_utc", _utc_now().isoformat())
        session.flush()
        return model

    @staticmethod
    def query_records(
        session: Session,
        merchant_id: Optional[str] = None,
        eligible_only: bool = True,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[ObservationalLearningRecordModel]:
        stmt = select(ObservationalLearningRecordModel)
        if merchant_id:
            stmt = stmt.where(ObservationalLearningRecordModel.merchant_id == str(merchant_id))
        if eligible_only:
            stmt = stmt.where(ObservationalLearningRecordModel.is_eligible_for_dml.is_(True))
        if start_date:
            stmt = stmt.where(ObservationalLearningRecordModel.decision_timestamp_utc >= str(start_date))
        if end_date:
            stmt = stmt.where(ObservationalLearningRecordModel.decision_timestamp_utc <= str(end_date))
        stmt = stmt.order_by(
            ObservationalLearningRecordModel.decision_timestamp_utc.asc(),
            ObservationalLearningRecordModel.decision_id.asc(),
        )
        return list(session.execute(stmt).scalars().all())

