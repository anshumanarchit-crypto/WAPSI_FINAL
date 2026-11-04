"""
Phase 1B Persistence & Multi-Tenant Database Test Suite.
Project: ffgsrwjhguvubmhuefyj (Razorpay AI Buildathon 2026 - Track 3)

Tests:
1. ORM table creation & metadata reflection across all 15 models.
2. Integer paise monetary precision and positive amount constraints.
3. Durable multi-provider webhook inbox deduplication.
4. Idempotency lock acquisition, completion caching, and TTL expiration.
5. Transactional recovery outbox state transitions and exponential backoff.
6. Customer HMAC-SHA256 pseudonymization and opt-out consent toggling.
7. Atomic multi-entity transactional commit and rollback safety.
8. Cryptographic audit ledger SHA-256 chain continuity and tamper detection.
9. Contextual bandit weight matrix persistence and retrieval.
10. Multi-tenant data isolation across distinct merchant tenants.
11. FastAPI gateway database integration and health reporting.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from wapsi.core.config import get_settings
from wapsi.db.models import (
    AuditLedgerBlockModel,
    BanditWeightModel,
    Base,
    CausalDecisionModel,
    CustomerModel,
    IdempotencyKeyModel,
    MerchantApiKeyModel,
    MerchantConfigurationModel,
    MerchantMembershipModel,
    MerchantModel,
    ModelVersionModel,
    PaymentOutcomeModel,
    RecoveryDispatchModel,
    RecoveryOutboxModel,
    TransactionModel,
    WebhookInboxModel,
)
from wapsi.db.repository import (
    AuditLedgerRepository,
    BanditRepository,
    CausalDecisionRepository,
    CustomerRepository,
    IdempotencyRepository,
    MerchantRepository,
    RecoveryOutboxRepository,
    TransactionRepository,
    WebhookInboxRepository,
)
from wapsi.db.service import PersistenceService
from wapsi.db.session import DatabaseManager


@pytest.fixture
def test_db():
    """Provides a fresh isolated in-memory SQLite database for testing."""
    manager = DatabaseManager(database_url="sqlite:///:memory:")
    manager.create_all_tables()
    yield manager
    manager.engine.dispose()


@pytest.fixture
def test_service(test_db):
    """Provides a PersistenceService wired to the test in-memory database."""
    return PersistenceService(db_manager=test_db)


# ==============================================================================
# 1. ORM MODEL REGISTRATION AND METADATA REFLECTION
# ==============================================================================
def test_all_15_models_registered_and_table_creation(test_db):
    """Verifies that all 15 required entities are registered in SQLAlchemy metadata."""
    expected_tables = {
        "merchants",
        "merchant_memberships",
        "merchant_configurations",
        "merchant_api_keys",
        "customers",
        "transactions",
        "model_versions",
        "causal_decisions",
        "webhook_inbox",
        "idempotency_keys",
        "recovery_outbox",
        "recovery_dispatches",
        "payment_outcomes",
        "audit_ledger_blocks",
        "bandit_weights",
    }
    actual_tables = set(Base.metadata.tables.keys())
    assert expected_tables.issubset(actual_tables), f"Missing tables: {expected_tables - actual_tables}"
    assert len(expected_tables) == 15

    # Verify tables actually exist in the database engine
    with test_db.session_scope() as session:
        result = session.execute(text("SELECT name FROM sqlite_master WHERE type='table';")).scalars().all()
        for t in expected_tables:
            assert t in result, f"Table {t} was not created in database engine."


# ==============================================================================
# 2. INTEGER PAISE MONETARY PRECISION & CONSTRAINTS
# ==============================================================================
def test_integer_paise_monetary_precision_and_constraints(test_db):
    """
    Verifies that monetary amounts are strictly persisted as integer paise,
    eliminating floating-point rounding drift, and rejecting non-positive amounts.
    """
    with test_db.session_scope() as session:
        merchant = MerchantRepository.get_or_create_default(session)
        customer = CustomerRepository.get_or_create_customer(
            session=session,
            merchant_id=merchant.id,
            merchant_customer_id="cust_precision_test",
        )

        # 1. Reject <= 0 paise
        with pytest.raises(ValueError, match="strictly positive"):
            TransactionRepository.create_transaction(
                session=session,
                merchant_id=merchant.id,
                customer_id=customer.id,
                payment_id="pay_zero_amount",
                amount_paise=0,
            )

        with pytest.raises(ValueError, match="strictly positive"):
            TransactionRepository.create_transaction(
                session=session,
                merchant_id=merchant.id,
                customer_id=customer.id,
                payment_id="pay_negative_amount",
                amount_paise=-1000,
            )

        # 2. Precise paise conversion: ₹2499.50 = 249950 paise
        amount_inr = 2499.50
        amount_paise = int(round(amount_inr * 100))
        assert amount_paise == 249950

        tx = TransactionRepository.create_transaction(
            session=session,
            merchant_id=merchant.id,
            customer_id=customer.id,
            payment_id="pay_precision_ok",
            amount_paise=amount_paise,
        )
        assert tx.amount_paise == 249950

    # 3. Read back and verify exact integer precision
    with test_db.session_scope() as session:
        saved_tx = TransactionRepository.get_by_payment_id(session, merchant.id, "pay_precision_ok")
        assert saved_tx is not None
        assert isinstance(saved_tx.amount_paise, int)
        assert saved_tx.amount_paise == 249950
        # Reconstruct INR without float inaccuracy
        assert saved_tx.amount_paise / 100.0 == 2499.50


# ==============================================================================
# 3. DURABLE WEBHOOK INBOX DEDUPLICATION
# ==============================================================================
def test_webhook_inbox_durable_deduplication(test_db):
    """
    Verifies that webhook events are uniquely deduplicated by provider, environment,
    payment_id, event_type, and nonce to prevent duplicate recovery actions.
    """
    with test_db.session_scope() as session:
        merchant = MerchantRepository.get_or_create_default(session)

        # 1. First delivery of webhook
        record1, is_new1 = WebhookInboxRepository.record_and_deduplicate(
            session=session,
            provider="razorpay",
            environment="production",
            payment_id="pay_dedup_001",
            event_type="payment.failed",
            nonce="nonce_unique_12345",
            signature="sig_valid_hash_abc",
            payload_sanitized={"amount": 1500.0, "reason": "BANK_OFFLINE"},
            merchant_id=merchant.id,
        )
        assert is_new1 is True
        assert record1.status == "RECEIVED"

    # 2. Duplicate delivery with identical provider, environment, payment_id, event_type, nonce
    with test_db.session_scope() as session:
        record2, is_new2 = WebhookInboxRepository.record_and_deduplicate(
            session=session,
            provider="razorpay",
            environment="production",
            payment_id="pay_dedup_001",
            event_type="payment.failed",
            nonce="nonce_unique_12345",
            signature="sig_valid_hash_abc",
            payload_sanitized={"amount": 1500.0, "reason": "BANK_OFFLINE"},
            merchant_id=merchant.id,
        )
        assert is_new2 is False
        assert record2.id == record1.id

        # 3. New event with different nonce is accepted as new
        record3, is_new3 = WebhookInboxRepository.record_and_deduplicate(
            session=session,
            provider="razorpay",
            environment="production",
            payment_id="pay_dedup_001",
            event_type="payment.failed",
            nonce="nonce_unique_67890",
            signature="sig_valid_hash_def",
            payload_sanitized={"amount": 1500.0, "reason": "BANK_OFFLINE"},
            merchant_id=merchant.id,
        )
        assert is_new3 is True
        assert record3.id != record1.id


# ==============================================================================
# 4. IDEMPOTENCY KEY LIFECYCLE & CACHING
# ==============================================================================
def test_idempotency_lifecycle_and_caching(test_db):
    """
    Verifies API idempotency key acquisition, duplicate prevention during processing,
    response caching upon completion, and expired lock eviction.
    """
    with test_db.session_scope() as session:
        merchant = MerchantRepository.get_or_create_default(session)
        idemp_key = f"idemp_{uuid.uuid4().hex[:10]}"

        # 1. Initial acquisition
        entry, is_new = IdempotencyRepository.check_or_create(
            session=session,
            merchant_id=merchant.id,
            idempotency_key=idemp_key,
            request_path="/v1/recovery/decide",
            request_payload={"payment_id": "pay_test_idemp"},
            ttl_seconds=3600,
        )
        assert is_new is True
        assert entry.status == "PROCESSING"

        # 2. Concurrent/duplicate call before completion -> is_new is False
        entry_dup, is_new_dup = IdempotencyRepository.check_or_create(
            session=session,
            merchant_id=merchant.id,
            idempotency_key=idemp_key,
            request_path="/v1/recovery/decide",
            request_payload={"payment_id": "pay_test_idemp"},
        )
        assert is_new_dup is False
        assert entry_dup.status == "PROCESSING"

        # 3. Complete and cache response
        IdempotencyRepository.complete(
            session=session,
            idempotency_id=entry.id,
            status_code=200,
            response_body={"decision": "whatsapp_nudge", "status": "authorized"},
        )

    # 4. Subsequent read returns cached response
    with test_db.session_scope() as session:
        entry_cached, is_new_cached = IdempotencyRepository.check_or_create(
            session=session,
            merchant_id=merchant.id,
            idempotency_key=idemp_key,
            request_path="/v1/recovery/decide",
            request_payload={"payment_id": "pay_test_idemp"},
        )
        assert is_new_cached is False
        assert entry_cached.status == "COMPLETED"
        assert entry_cached.response_status_code == 200
        assert entry_cached.response_body["decision"] == "whatsapp_nudge"

        # 5. Simulate expired idempotency key
        entry_cached.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        session.flush()

        # Re-check expired key -> should be re-acquired as is_new=True
        entry_reused, is_new_reused = IdempotencyRepository.check_or_create(
            session=session,
            merchant_id=merchant.id,
            idempotency_key=idemp_key,
            request_path="/v1/recovery/decide",
            request_payload={"payment_id": "pay_test_idemp"},
        )
        assert is_new_reused is True
        assert entry_reused.status == "PROCESSING"


# ==============================================================================
# 5. TRANSACTIONAL RECOVERY OUTBOX STATE MACHINE
# ==============================================================================
def test_recovery_outbox_state_transitions(test_db):
    """
    Verifies that the transactional recovery outbox manages reliable state
    transitions: QUEUED -> SENDING -> RETRY (with backoff) -> DEAD_LETTER or SENT.
    """
    with test_db.session_scope() as session:
        merchant = MerchantRepository.get_or_create_default(session)
        customer = CustomerRepository.get_or_create_customer(session, merchant.id, "cust_outbox_test")
        tx = TransactionRepository.create_transaction(
            session=session,
            merchant_id=merchant.id,
            customer_id=customer.id,
            payment_id="pay_outbox_001",
            amount_paise=100000,
        )

        decision = CausalDecisionRepository.create_decision(session, {
            "decision_id": f"dec_{uuid.uuid4().hex[:10]}",
            "merchant_id": merchant.id,
            "transaction_id": tx.id,
            "recommended_action": "whatsapp_nudge",
            "authorized_action": "whatsapp_nudge",
            "channel": "whatsapp",
            "net_expected_utility_paise": 5000,
            "dispatch_cost_paise": 85,
            "friction_cost_paise": 50,
        })

        # 1. Enqueue outbox item
        outbox = RecoveryOutboxRepository.enqueue(
            session=session,
            merchant_id=merchant.id,
            decision_id=decision.id,
            idempotency_key=f"outbox_{uuid.uuid4().hex[:8]}",
            action="whatsapp_nudge",
            channel="whatsapp",
            recipient_masked="+9198****1234",
            message_payload={"link": "https://rzp.io/r/pay_outbox_001"},
        )
        assert outbox.status == "PENDING_APPROVAL"
        outbox = RecoveryOutboxRepository.approve_job(session, outbox.id, "operator_test")
        assert outbox.status == "QUEUED"
        assert outbox.retry_count == 0
        outbox_id = outbox.id

    # 2. Fetch queued items
    with test_db.session_scope() as session:
        queued = RecoveryOutboxRepository.fetch_queued(session, limit=10)
        assert any(item.id == outbox_id for item in queued)

        # 3. Transition to SENDING
        RecoveryOutboxRepository.transition_status(session, outbox_id, "SENDING")

    with test_db.session_scope() as session:
        item = session.get(RecoveryOutboxModel, outbox_id)
        assert item.status == "SENDING"

        # 4. Failure attempt 1 -> Transition to RETRY
        RecoveryOutboxRepository.transition_status(
            session=session,
            outbox_id=outbox_id,
            new_status="RETRY",
            last_error="WhatsApp API 429 Rate Limit",
            retry_delay_seconds=60,
        )
        assert item.status == "RETRY"
        assert item.retry_count == 1
        assert "429 Rate Limit" in item.last_error

        # 5. Failure attempt 2
        RecoveryOutboxRepository.transition_status(
            session=session,
            outbox_id=outbox_id,
            new_status="RETRY",
            last_error="WhatsApp Gateway Timeout",
        )
        assert item.status == "RETRY"
        assert item.retry_count == 2

        # 6. Failure attempt 3 -> Reaches max_retries (3) -> Moves to DEAD_LETTER
        RecoveryOutboxRepository.transition_status(
            session=session,
            outbox_id=outbox_id,
            new_status="RETRY",
            last_error="Permanent Provider Decline",
        )
        assert item.status == "DEAD_LETTER"
        assert item.retry_count == 3


# ==============================================================================
# 6. CUSTOMER HMAC-SHA256 PSEUDONYMIZATION AND CONSENT
# ==============================================================================
def test_customer_hmac_sha256_pseudonymization_and_opt_out(test_db):
    """
    Verifies that raw customer identifiers are converted to deterministic HMAC-SHA256
    pseudonyms using merchant isolation salts, and opt-out consent is durable.
    """
    with test_db.session_scope() as session:
        merchant_a_id = uuid.uuid4()
        merchant_b_id = uuid.uuid4()
        phone_number = "+919876543210"

        # 1. Deterministic hashing for same merchant
        hash_a1 = CustomerRepository.compute_pseudonym(merchant_a_id, phone_number)
        hash_a2 = CustomerRepository.compute_pseudonym(merchant_a_id, phone_number)
        assert hash_a1 == hash_a2
        assert len(hash_a1) == 64 # SHA-256 hex digest length
        assert phone_number not in hash_a1

        # 2. Cross-merchant isolation: same phone yields different pseudonym
        hash_b = CustomerRepository.compute_pseudonym(merchant_b_id, phone_number)
        assert hash_a1 != hash_b

        # 3. Create customer and test opt-out lifecycle
        merchant = MerchantRepository.get_or_create_default(session)
        customer = CustomerRepository.get_or_create_customer(
            session=session,
            merchant_id=merchant.id,
            merchant_customer_id=phone_number,
            masked_identifier="+9198****3210",
        )
        assert customer.opted_out is False
        assert customer.consent_status == "ACTIVE_CONSENT"

        # Customer opts out
        CustomerRepository.update_opt_out(session, merchant.id, customer.id, opted_out=True)
        assert customer.opted_out is True
        assert customer.consent_status == "OPTED_OUT"
        assert customer.opted_out_at is not None

        # Customer opts back in
        CustomerRepository.update_opt_out(session, merchant.id, customer.id, opted_out=False)
        assert customer.opted_out is False
        assert customer.consent_status == "ACTIVE_CONSENT"


# ==============================================================================
# 7. ATOMIC TRANSACTIONAL COMMIT AND ROLLBACK SAFETY
# ==============================================================================
def test_atomic_transactional_commit_and_rollback(test_service, test_db):
    """
    Verifies that PersistenceService commits (Transaction + Decision + Outbox + Audit Block)
    atomically in a single database transaction, with zero orphaned records on error.
    """
    decision_obj = {
        "decision_id": f"dec_atomic_{uuid.uuid4().hex[:8]}",
        "recommended_action": "whatsapp_nudge",
        "authorized_action": "whatsapp_nudge",
        "channel": "whatsapp",
        "uplift": 0.28,
        "net_expected_utility_inr": 145.50,
        "confidence_tier": "HIGH",
        "policy_status": "allowed",
    }
    raw_event = {
        "payment_id": f"pay_atomic_{uuid.uuid4().hex[:8]}",
        "amount": 1999.0,
        "payment_method": "upi",
        "error_code": "UPI_APP_TIMEOUT",
        "user_id": "usr_atomic_test",
    }

    # 1. Successful atomic persistence
    res = test_service.persist_causal_decision(decision_obj, raw_event)
    assert res["status"] == "COMMITTED"
    assert res["amount_paise"] == 199900
    assert res["audit_hash"] is not None

    # Verify all 4 records exist in the database
    with test_db.session_scope() as session:
        # Transaction
        tx = session.execute(
            select(TransactionModel).where(TransactionModel.payment_id == raw_event["payment_id"])
        ).scalar_one_or_none()
        assert tx is not None
        assert tx.amount_paise == 199900

        # Causal Decision
        decision = session.execute(
            select(CausalDecisionModel).where(CausalDecisionModel.decision_id == decision_obj["decision_id"])
        ).scalar_one_or_none()
        assert decision is not None
        assert decision.transaction_id == tx.id

        # Outbox Item
        outbox = session.execute(
            select(RecoveryOutboxModel).where(RecoveryOutboxModel.decision_id == decision.id)
        ).scalar_one_or_none()
        assert outbox is not None
        assert outbox.status == "PENDING_APPROVAL"
        outbox = RecoveryOutboxRepository.approve_job(session, outbox.id, "operator_test")
        assert outbox.status == "QUEUED"

        # Audit Block
        audit = session.execute(
            select(AuditLedgerBlockModel).where(AuditLedgerBlockModel.block_hash == res["audit_hash"])
        ).scalar_one_or_none()
        assert audit is not None
        assert audit.event_type == "CAUSAL_DECISION_COMMITTED"

    # 2. Rollback verification: simulate an unhandled failure during atomic commit
    count_before = {}
    with test_db.session_scope() as session:
        for model in (TransactionModel, CausalDecisionModel, RecoveryOutboxModel, AuditLedgerBlockModel):
            count_before[model] = session.execute(select(model)).scalars().all()

    try:
        with test_db.session_scope() as session:
            # Partially add a transaction using repository
            TransactionRepository.create_transaction(
                session=session,
                merchant_id=tx.merchant_id,
                customer_id=tx.customer_id,
                payment_id="pay_rollback_fail",
                amount_paise=50000,
            )
            # Force an unexpected exception before commit
            raise RuntimeError("Simulated infrastructure failure mid-transaction!")
    except RuntimeError:
        pass

    # Verify no partial rows were committed to any table
    with test_db.session_scope() as session:
        for model in (TransactionModel, CausalDecisionModel, RecoveryOutboxModel, AuditLedgerBlockModel):
            current_count = len(session.execute(select(model)).scalars().all())
            assert current_count == len(count_before[model]), f"Table {model.__tablename__} leaked uncommitted rows!"


# ==============================================================================
# 8. CRYPTOGRAPHIC AUDIT LEDGER CONTINUITY & TAMPER DETECTION
# ==============================================================================
def test_cryptographic_audit_ledger_continuity_and_tamper_detection(test_db):
    """
    Verifies that the audit ledger forms a continuous cryptographic SHA-256 chain,
    and any modification or broken link is immediately detected.
    """
    with test_db.session_scope() as session:
        merchant = MerchantRepository.get_or_create_default(session)
        merchant_id = merchant.id

        # Append 4 sequential blocks
        b0 = AuditLedgerRepository.append_block(session, "GENESIS_BLOCK", {"info": "genesis"}, merchant_id)
        b1 = AuditLedgerRepository.append_block(session, "POLICY_UPDATED", {"threshold": 80}, merchant_id)
        b2 = AuditLedgerRepository.append_block(session, "DECISION_COMMITTED", {"action": "whatsapp"}, merchant_id)
        b3 = AuditLedgerRepository.append_block(session, "OUTCOME_RECORDED", {"recovered": True}, merchant_id)

        assert b0.block_index == 0
        assert b0.previous_hash == "0" * 64
        assert b1.block_index == 1
        assert b1.previous_hash == b0.block_hash
        assert b2.block_index == 2
        assert b2.previous_hash == b1.block_hash
        assert b3.block_index == 3
        assert b3.previous_hash == b2.block_hash

        # Verify integrity succeeds
        check = AuditLedgerRepository.verify_integrity(session, merchant_id)
        assert check["is_valid"] is True
        assert check["blocks_count"] == 4
        assert check["latest_hash"] == b3.block_hash

        # Tamper test: Corrupt block 1 previous hash
        b1.previous_hash = "f" * 64
        session.flush()

        tampered_check = AuditLedgerRepository.verify_integrity(session, merchant_id)
        assert tampered_check["is_valid"] is False
        assert tampered_check["corrupt_index"] == 1
        assert "Hash chain broken" in tampered_check["error"]


# ==============================================================================
# 9. CONTEXTUAL BANDIT WEIGHT MATRIX PERSISTENCE
# ==============================================================================
def test_contextual_bandit_weight_persistence(test_db):
    """
    Verifies that multi-dimensional contextual bandit matrices and vectors
    are accurately persisted and restored without precision loss.
    """
    with test_db.session_scope() as session:
        merchant = MerchantRepository.get_or_create_default(session)

        # 3x3 covariance matrix and 3x1 b vector for LinUCB
        matrix_a = [
            [1.05, 0.02, 0.00],
            [0.02, 1.10, 0.04],
            [0.00, 0.04, 0.98],
        ]
        vector_b = [0.45, 0.85, 0.12]

        saved = BanditRepository.save_action_weights(
            session=session,
            merchant_id=merchant.id,
            model_version="v1.0.0",
            action="whatsapp_one_click",
            matrix_a=matrix_a,
            vector_b=vector_b,
            alpha=0.75,
            updates_count=10,
        )
        assert saved.action == "whatsapp_one_click"
        assert saved.total_updates == 10

    # Read back in new session
    with test_db.session_scope() as session:
        loaded = BanditRepository.load_action_weights(
            session=session,
            merchant_id=merchant.id,
            model_version="v1.0.0",
            action="whatsapp_one_click",
        )
        assert loaded is not None
        assert loaded.matrix_a == matrix_a
        assert loaded.vector_b == vector_b
        assert float(loaded.alpha) == 0.75
        assert loaded.total_updates == 10

        # Update weights with observation
        BanditRepository.save_action_weights(
            session=session,
            merchant_id=merchant.id,
            model_version="v1.0.0",
            action="whatsapp_one_click",
            matrix_a=[[1.10, 0.02, 0.00], [0.02, 1.15, 0.04], [0.00, 0.04, 1.02]],
            vector_b=[0.50, 0.90, 0.15],
            alpha=0.70,
            updates_count=1,
        )

    with test_db.session_scope() as session:
        updated = BanditRepository.load_action_weights(
            session=session,
            merchant_id=merchant.id,
            model_version="v1.0.0",
            action="whatsapp_one_click",
        )
        assert updated.total_updates == 11
        assert float(updated.alpha) == 0.70
        assert updated.vector_b[0] == 0.50


# ==============================================================================
# 10. MULTI-TENANT DATA ISOLATION
# ==============================================================================
def test_multi_tenant_data_isolation(test_db):
    """
    Verifies that data queries strictly isolate records between distinct merchants
    and prevent cross-tenant data leakage.
    """
    with test_db.session_scope() as session:
        # Create Tenant Alpha
        merchant_alpha = MerchantModel(
            merchant_code="MRC_ALPHA",
            name="Alpha Retail Ltd",
            business_type="Retail",
            registered_email="billing@alpharetail.in",
            country="India",
            currency="INR",
        )
        # Create Tenant Beta
        merchant_beta = MerchantModel(
            merchant_code="MRC_BETA",
            name="Beta SaaS Inc",
            business_type="B2B Software",
            registered_email="ops@betasaas.com",
            country="India",
            currency="INR",
        )
        session.add_all([merchant_alpha, merchant_beta])
        session.flush()

        # Customers under respective merchants
        cust_alpha = CustomerRepository.get_or_create_customer(session, merchant_alpha.id, "user_alpha_01")
        cust_beta = CustomerRepository.get_or_create_customer(session, merchant_beta.id, "user_beta_01")

        # Transactions under respective merchants
        tx_alpha = TransactionRepository.create_transaction(
            session, merchant_alpha.id, cust_alpha.id, "pay_alpha_101", 100000
        )
        tx_beta = TransactionRepository.create_transaction(
            session, merchant_beta.id, cust_beta.id, "pay_beta_202", 200000
        )

        # Audit blocks
        AuditLedgerRepository.append_block(session, "ALPHA_EVENT", {"k": 1}, merchant_alpha.id)
        AuditLedgerRepository.append_block(session, "BETA_EVENT", {"k": 2}, merchant_beta.id)

    # Verify isolation
    with test_db.session_scope() as session:
        # Query Alpha transactions
        alpha_txs = session.execute(
            select(TransactionModel).where(TransactionModel.merchant_id == merchant_alpha.id)
        ).scalars().all()
        assert len(alpha_txs) == 1
        assert alpha_txs[0].payment_id == "pay_alpha_101"

        # Query Beta transactions
        beta_txs = session.execute(
            select(TransactionModel).where(TransactionModel.merchant_id == merchant_beta.id)
        ).scalars().all()
        assert len(beta_txs) == 1
        assert beta_txs[0].payment_id == "pay_beta_202"

        # Verify Alpha cannot see Beta payment_id
        alpha_lookup = TransactionRepository.get_by_payment_id(session, merchant_alpha.id, "pay_beta_202")
        assert alpha_lookup is None


# ==============================================================================
# 11. FASTAPI GATEWAY PERSISTENCE HEALTH INTEGRATION
# ==============================================================================
def test_fastapi_gateway_persistence_health():
    """
    Verifies that the canonical FastAPI application initializes the PersistenceService
    and exposes database health through its /health and /healthz endpoints.
    """
    from starlette.testclient import TestClient
    from wapsi.api.app import app

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("healthy", "degraded")
    assert "database" in data
    assert data["database"]["status"] == "healthy"
    assert "latency_ms" in data["database"]
