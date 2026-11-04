"""
WAPSI Security Hardening & Tenant Isolation Comprehensive Test Suite.
Verifies all 16 required security scenarios across API authentication,
tenant authorization, fail-closed database context, and environment-aware fallbacks.
"""

import os
from pathlib import Path
import uuid
import hashlib
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from wapsi.api.app import app
from wapsi.core.config import WapsiSettings, get_settings, is_dev_fallback_permitted
from wapsi.db.models import (
    Base,
    MerchantModel,
    MerchantApiKeyModel,
    MerchantMembershipModel,
    RecoveryOutboxModel,
)
from wapsi.db.session import DatabaseManager
from wapsi.db.service import PersistenceService
from wapsi.db.repository import MerchantRepository
from wapsi.recovery.engine import get_recovery_engine
from wapsi.recovery.webhook_processor import DurableWebhookInbox


def make_test_settings(wapsi_env: str = "production", allow_dev_auth_fallback: bool = False, **kwargs) -> WapsiSettings:
    """Helper to instantiate valid WapsiSettings with proper credentials."""
    mode = "live" if wapsi_env.lower() == "production" else kwargs.get("razorpay_mode", "test")
    key_id = "rzp_live_prod_key_12345" if mode == "live" else "rzp_test_dev_key_12345"
    params = {
        "wapsi_env": wapsi_env,
        "razorpay_mode": mode,
        "razorpay_key_id": key_id,
        "razorpay_key_secret": "wapsi_secret_test_value_2026",
        "razorpay_webhook_secret": "wapsi_webhook_secret_test_value_2026",
        "allow_dev_auth_fallback": allow_dev_auth_fallback,
        "whatsapp_auth_mode": "system_user" if wapsi_env.lower() == "production" else "dashboard_sandbox",
        "whatsapp_access_token": "wapsi_system_user_token_prod_2026",
        "whatsapp_diagnostic_token": "wapsi_diag_token_dev_2026",
        "meta_app_secret": "wapsi_meta_app_secret_prod_2026",
        "whatsapp_webhook_verify_token": "wapsi_verify_token_2026",
        "whatsapp_phone_number_id": "100000000000001",
    }
    params.update(kwargs)
    return WapsiSettings(**params)


@pytest.fixture
def mock_db():
    """Sets up an isolated SQLite in-memory database with full schema for auth testing."""
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db_manager = DatabaseManager(database_url="sqlite:///:memory:")
    db_manager.engine = engine
    db_manager.session_factory = SessionLocal
    db_manager.SessionLocal = SessionLocal
    return db_manager


@pytest.fixture
def seeded_merchants(mock_db):
    """Seeds active and inactive test merchants with API keys in the isolated database."""
    m_active_id = uuid.uuid4()
    m_inactive_id = uuid.uuid4()
    m_user_id = uuid.uuid4()

    key_active_raw = "wapsi_live_active_key_test_12345"
    key_active_hash = hashlib.sha256(key_active_raw.encode("utf-8")).hexdigest()

    key_inactive_raw = "wapsi_live_inactive_key_test_67890"
    key_inactive_hash = hashlib.sha256(key_inactive_raw.encode("utf-8")).hexdigest()

    key_scoped_read_raw = "wapsi_read_only_key_test_99999"
    key_scoped_read_hash = hashlib.sha256(key_scoped_read_raw.encode("utf-8")).hexdigest()

    with mock_db.session_scope() as session:
        # 1. Active Merchant
        merchant_active = MerchantModel(
            id=m_active_id,
            merchant_code="merch_active_alpha",
            name="Alpha Corp",
            business_type="FinTech",
            industry="SaaS",
            registered_email="sec@alpha.corp",
            country="IN",
            currency="INR",
            timezone="Asia/Kolkata",
            status="ACTIVE",
        )
        session.add(merchant_active)

        api_key_active = MerchantApiKeyModel(
            merchant_id=m_active_id,
            key_name="Alpha Active Key",
            key_prefix="wapsi_",
            key_suffix="12345",
            hashed_key=key_active_hash,
            scopes=["recovery:predict", "recovery:read", "recovery:write"],
            is_revoked=False,
        )
        session.add(api_key_active)

        api_key_readonly = MerchantApiKeyModel(
            merchant_id=m_active_id,
            key_name="Alpha Read Key",
            key_prefix="wapsi_",
            key_suffix="99999",
            hashed_key=key_scoped_read_hash,
            scopes=["recovery:read"],
            is_revoked=False,
        )
        session.add(api_key_readonly)

        # Active Membership
        membership = MerchantMembershipModel(
            merchant_id=m_active_id,
            user_id=m_user_id,
            role="recovery_operator",
            is_active=True,
        )
        session.add(membership)

        # 2. Inactive Merchant
        merchant_inactive = MerchantModel(
            id=m_inactive_id,
            merchant_code="merch_inactive_beta",
            name="Beta Inactive Corp",
            business_type="Retail",
            industry="Ecommerce",
            registered_email="sec@beta.corp",
            country="IN",
            currency="INR",
            timezone="Asia/Kolkata",
            status="SUSPENDED",
        )
        session.add(merchant_inactive)

        api_key_inactive = MerchantApiKeyModel(
            merchant_id=m_inactive_id,
            key_name="Beta Suspended Key",
            key_prefix="wapsi_",
            key_suffix="67890",
            hashed_key=key_inactive_hash,
            scopes=["recovery:predict", "recovery:read", "recovery:write"],
            is_revoked=False,
        )
        session.add(api_key_inactive)

    return {
        "active_id": str(m_active_id),
        "active_code": "merch_active_alpha",
        "active_key": key_active_raw,
        "readonly_key": key_scoped_read_raw,
        "inactive_id": str(m_inactive_id),
        "inactive_code": "merch_inactive_beta",
        "inactive_key": key_inactive_raw,
        "user_id": m_user_id,
        "db": mock_db,
    }


@pytest.fixture
def client(monkeypatch, seeded_merchants):
    """Configures FastAPI TestClient with isolated database manager in production mode."""
    prod_settings = make_test_settings(wapsi_env="production", allow_dev_auth_fallback=False)
    monkeypatch.setattr("wapsi.db.session.get_db_manager", lambda: seeded_merchants["db"])
    monkeypatch.setattr("wapsi.api.app.get_settings", lambda: prod_settings)
    monkeypatch.setattr("wapsi.core.config.get_settings", lambda: prod_settings)
    monkeypatch.setattr("wapsi.db.service.get_settings", lambda: prod_settings)
    test_svc = PersistenceService(db_manager=seeded_merchants["db"])
    monkeypatch.setattr("wapsi.api.app.get_persistence_service", lambda: test_svc)
    monkeypatch.setattr("wapsi.db.service.get_persistence_service", lambda: test_svc)
    monkeypatch.setattr("wapsi.db.service._persistence_service", test_svc)
    from wapsi.recovery.engine import get_recovery_engine
    engine = get_recovery_engine()
    orig_db = engine.outbox.db_manager
    orig_pg = engine.outbox.is_postgres
    orig_path = getattr(engine.outbox, "db_path", None)
    engine.outbox.db_manager = seeded_merchants["db"]
    engine.outbox.is_postgres = False
    engine.outbox.db_path = str(Path(".wapsi_data") / "test_hardening_outbox.db")
    engine.outbox._init_sqlite_db()
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        engine.outbox.db_manager = orig_db
        engine.outbox.is_postgres = orig_pg
        if orig_path is not None:
            engine.outbox.db_path = orig_path
        elif hasattr(engine.outbox, "db_path"):
            delattr(engine.outbox, "db_path")


# ==============================================================================
# 1. Missing API Key on Protected Endpoint
# ==============================================================================
def test_01_missing_api_key_on_protected_endpoint(client):
    """Protected endpoints reject requests without an API key with HTTP 401."""
    payload = {
        "case_id": "CASE_TEST_01",
        "merchant_id": "merch_active_alpha",
        "domain": "ecommerce",
        "amount": 1500.0,
        "decline_reason": "card_declined",
    }
    # Calling predict without X-API-Key or Authorization header in production mode
    res = client.post("/api/v1/recovery/predict", json=payload)
    assert res.status_code == 401
    assert "Missing API Key" in res.json().get("detail", "")


# ==============================================================================
# 2. Invalid API Key
# ==============================================================================
def test_02_invalid_api_key(client):
    """Requests with unknown or forged API key receive HTTP 401 Unauthorized."""
    payload = {
        "case_id": "CASE_TEST_02",
        "merchant_id": "merch_active_alpha",
        "domain": "ecommerce",
        "amount": 1500.0,
        "decline_reason": "card_declined",
    }
    headers = {"X-API-Key": "wapsi_forged_unauthorized_key_99999"}
    res = client.post("/api/v1/recovery/predict", json=payload, headers=headers)
    assert res.status_code == 401
    assert "Invalid WAPSI API Key" in res.json().get("detail", "")


# ==============================================================================
# 3. Valid API Key for Active Merchant
# ==============================================================================
def test_03_valid_api_key_for_active_merchant(client, seeded_merchants):
    """Valid API key for an active merchant succeeds and derives authoritative tenant context."""
    payload = {
        "case_id": "CASE_TEST_03",
        "merchant_id": seeded_merchants["active_code"],
        "domain": "ecommerce",
        "amount": 2500.0,
        "decline_reason": "card_declined",
    }
    headers = {"X-API-Key": seeded_merchants["active_key"]}
    res = client.post("/api/v1/recovery/predict", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "decision_id" in data
    assert data["policy_status"] == "allowed"


# ==============================================================================
# 4. Inactive Merchant
# ==============================================================================
def test_04_inactive_merchant(client, seeded_merchants):
    """Valid API key for an inactive/suspended merchant must receive HTTP 403 Forbidden."""
    payload = {
        "case_id": "CASE_TEST_04",
        "merchant_id": seeded_merchants["inactive_code"],
        "domain": "ecommerce",
        "amount": 1500.0,
        "decline_reason": "card_declined",
    }
    headers = {"X-API-Key": seeded_merchants["inactive_key"]}
    res = client.post("/api/v1/recovery/predict", json=payload, headers=headers)
    assert res.status_code == 403
    assert "expected 'ACTIVE'" in res.json().get("detail", "") or "inactive or suspended" in res.json().get("detail", "")


# ==============================================================================
# 5. Invalid Merchant Membership
# ==============================================================================
def test_05_invalid_merchant_membership(seeded_merchants):
    """User membership validation rejects non-members and unauthorized roles."""
    db = seeded_merchants["db"]
    active_uuid = uuid.UUID(seeded_merchants["active_id"])
    valid_user_id = seeded_merchants["user_id"]
    random_user_id = uuid.uuid4()

    with db.session_scope() as session:
        # Valid member with operator role
        assert MerchantRepository.validate_user_membership(session, active_uuid, valid_user_id, "recovery_operator") is True
        # Wrong role requested
        assert MerchantRepository.validate_user_membership(session, active_uuid, valid_user_id, "merchant_admin") is False
        # Non-member user
        assert MerchantRepository.validate_user_membership(session, active_uuid, random_user_id) is False


# ==============================================================================
# 6. Contradictory X-Merchant-ID
# ==============================================================================
def test_06_contradictory_x_merchant_id(client, seeded_merchants):
    """Request with valid API key for Merchant A but X-Merchant-ID of Merchant B is rejected with 403."""
    payload = {
        "case_id": "CASE_TEST_06",
        "merchant_id": seeded_merchants["active_code"],
        "domain": "ecommerce",
        "amount": 1000.0,
        "decline_reason": "card_declined",
    }
    headers = {
        "X-API-Key": seeded_merchants["active_key"],
        "X-Merchant-ID": "merch_spoofed_victim_id",
    }
    res = client.post("/api/v1/recovery/predict", json=payload, headers=headers)
    assert res.status_code == 403
    assert "Tenant authorization failure" in res.json().get("detail", "")


# ==============================================================================
# 7. Contradictory Request-Body merchant_id
# ==============================================================================
def test_07_contradictory_request_body_merchant_id(client, seeded_merchants):
    """Request with valid API key for Merchant A but body merchant_id of Merchant B is rejected with 403."""
    payload = {
        "case_id": "CASE_TEST_07",
        "merchant_id": "merch_victim_unauthorized",
        "domain": "ecommerce",
        "amount": 1000.0,
        "decline_reason": "card_declined",
    }
    headers = {"X-API-Key": seeded_merchants["active_key"]}
    res = client.post("/api/v1/recovery/predict", json=payload, headers=headers)
    assert res.status_code == 403
    assert "Tenant authorization failure" in res.json().get("detail", "")


# ==============================================================================
# 8. Attempted Cross-Tenant Read
# ==============================================================================
def test_08_attempted_cross_tenant_read(client, seeded_merchants):
    """Merchant A cannot read outbox job owned by Merchant B."""
    engine = get_recovery_engine()
    # Seed an outbox job under Merchant B (inactive_id)
    job = engine.outbox.enqueue(
        case_id="case_cross_tenant_001",
        payment_id="pay_cross_tenant_001",
        idempotency_key=f"idemp_{uuid.uuid4().hex[:8]}",
        action="whatsapp_nudge",
        channel="whatsapp",
        recipient_masked="+91987****210",
        message_payload={"amount": 1000},
        merchant_id=seeded_merchants["inactive_id"],
    )

    # Merchant A attempts to fetch Merchant B's job
    headers = {"X-API-Key": seeded_merchants["active_key"]}
    res = client.get(f"/api/v1/recovery/outbox/{job.id}", headers=headers)
    assert res.status_code == 404
    assert f"Outbox job '{job.id}' not found" in res.json().get("detail", "")


# ==============================================================================
# 9. Attempted Cross-Tenant Insert
# ==============================================================================
def test_09_attempted_cross_tenant_insert(seeded_merchants):
    """PersistenceService fails closed if body merchant contradicts authenticated merchant."""
    service = PersistenceService(db_manager=seeded_merchants["db"])
    authenticated_id = seeded_merchants["active_id"]
    contradictory_code = "merch_victim_corp"

    with pytest.raises(PermissionError) as exc_info:
        service.persist_causal_decision(
            decision_object={
                "decision_id": "dec_cross_insert",
                "recommended_action": "whatsapp_nudge",
                "uplift": 0.2,
                "confidence": 0.8,
                "policy_status": "allowed",
            },
            raw_event={
                "merchant_id": contradictory_code,
                "payment_id": "pay_cross_insert",
            },
            merchant_code=contradictory_code,
            authenticated_merchant_id=authenticated_id,
        )
    assert "Tenant authorization failure" in str(exc_info.value)


# ==============================================================================
# 10. Missing PostgreSQL Tenant Context
# ==============================================================================
def test_10_missing_tenant_context_fails_closed():
    """tenant_session_scope with empty or None merchant zeroes out tenant context cleanly with is_local=true."""
    from unittest.mock import MagicMock
    dm = DatabaseManager()
    dm.engine = MagicMock()
    dm.engine.dialect.name = "postgresql"
    mock_session = MagicMock()
    dm.session_factory = MagicMock(return_value=mock_session)

    # None merchant -> sets empty string ""
    with dm.tenant_session_scope(None) as session:
        assert session is mock_session

    calls = mock_session.execute.call_args_list
    assert len(calls) == 1
    sql, params = calls[0].args[0], calls[0].args[1]
    assert "set_config('app.current_merchant_id', :merchant_id, true)" in str(sql)
    assert params["merchant_id"] == ""
    assert mock_session.commit.called
    assert mock_session.close.called

    mock_session.reset_mock()
    # Whitespace merchant -> sets empty string ""
    with dm.tenant_session_scope("   ") as session:
        assert session is mock_session

    calls = mock_session.execute.call_args_list
    assert len(calls) == 1
    sql, params = calls[0].args[0], calls[0].args[1]
    assert "set_config('app.current_merchant_id', :merchant_id, true)" in str(sql)
    assert params["merchant_id"] == ""
    assert mock_session.commit.called
    assert mock_session.close.called

    mock_session.reset_mock()
    # "null" literal string -> sets empty string ""
    with dm.tenant_session_scope("null") as session:
        assert session is mock_session

    calls = mock_session.execute.call_args_list
    assert len(calls) == 1
    sql, params = calls[0].args[0], calls[0].args[1]
    assert "set_config('app.current_merchant_id', :merchant_id, true)" in str(sql)
    assert params["merchant_id"] == ""
    assert mock_session.commit.called
    assert mock_session.close.called


# ==============================================================================
# 11. Transaction-Local Tenant Context Cleanup
# ==============================================================================
def test_11_transaction_local_tenant_context_cleanup():
    """tenant_session_scope executes set_config with is_local=true and session_scope zeroes lingering context."""
    from unittest.mock import MagicMock
    dm = DatabaseManager()
    dm.engine = MagicMock()
    dm.engine.dialect.name = "postgresql"
    mock_session = MagicMock()
    dm.session_factory = MagicMock(return_value=mock_session)

    merchant_uuid = str(uuid.uuid4())
    with dm.tenant_session_scope(merchant_uuid) as s1:
        assert s1 is mock_session

    calls = mock_session.execute.call_args_list
    assert len(calls) == 1
    sql, params = calls[0].args[0], calls[0].args[1]
    # Verified that is_local parameter (third arg) is true, meaning transaction-local
    assert "set_config('app.current_merchant_id', :merchant_id, true)" in str(sql)
    assert params["merchant_id"] == merchant_uuid
    assert mock_session.commit.called
    assert mock_session.close.called

    mock_session.reset_mock()
    # Plain session_scope unconditionally clears any lingering tenant context
    with dm.session_scope() as s2:
        assert s2 is mock_session

    calls = mock_session.execute.call_args_list
    assert len(calls) == 1
    sql = str(calls[0].args[0])
    assert "set_config('app.current_merchant_id', '', true)" in sql
    assert mock_session.commit.called
    assert mock_session.close.called


# ==============================================================================
# 12. Tenant Context After Rollback
# ==============================================================================
def test_12_tenant_context_after_rollback():
    """When an error occurs, rollback cleanly cleans up session context without leaks."""
    from unittest.mock import MagicMock
    dm = DatabaseManager()
    dm.engine = MagicMock()
    dm.engine.dialect.name = "postgresql"
    mock_session = MagicMock()
    dm.session_factory = MagicMock(return_value=mock_session)

    merchant_uuid = str(uuid.uuid4())
    with pytest.raises(RuntimeError):
        with dm.tenant_session_scope(merchant_uuid) as session:
            raise RuntimeError("Simulated transaction failure")

    assert mock_session.rollback.called
    assert not mock_session.commit.called
    assert mock_session.close.called

    mock_session.reset_mock()
    # After rollback, plain session executes reset of context
    with dm.session_scope() as clean_session:
        assert clean_session is mock_session

    calls = mock_session.execute.call_args_list
    assert len(calls) == 1
    assert "set_config('app.current_merchant_id', '', true)" in str(calls[0].args[0])
    assert mock_session.commit.called
    assert mock_session.close.called


# ==============================================================================
# 13. Development Fallback Disabled Outside Local Development
# ==============================================================================
def test_13_development_fallback_disabled_outside_local_development():
    """is_dev_fallback_permitted fails closed in production, staging, and over public tunnels."""
    # Production
    prod_s = make_test_settings(wapsi_env="production", allow_dev_auth_fallback=True)
    assert is_dev_fallback_permitted(prod_s) is False

    # Staging
    stage_s = make_test_settings(wapsi_env="staging", allow_dev_auth_fallback=True)
    assert is_dev_fallback_permitted(stage_s) is False

    # Development with tunnel (ngrok)
    tunnel_s = make_test_settings(
        wapsi_env="development",
        allow_dev_auth_fallback=True,
        public_base_url="https://crablike-outlook-pulmonary.ngrok-free.dev",
    )
    assert is_dev_fallback_permitted(tunnel_s) is False

    # Development without explicit flag
    no_flag_s = make_test_settings(
        wapsi_env="development",
        allow_dev_auth_fallback=False,
        public_base_url="http://localhost:8000",
    )
    old_test_mode = os.environ.pop("WAPSI_TEST_MODE", None)
    try:
        assert is_dev_fallback_permitted(no_flag_s) is False
    finally:
        if old_test_mode is not None:
            os.environ["WAPSI_TEST_MODE"] = old_test_mode


# ==============================================================================
# 14. Hardcoded Demo Key Rejection in Production
# ==============================================================================
def test_14_hardcoded_demo_key_rejection_in_production(client):
    """Hardcoded demo keys (rzp_live_wapsi_key_demo, rzp_test_wapsi_key_2026) must be rejected with 401 in production."""
    payload = {
        "case_id": "CASE_TEST_14",
        "merchant_id": "merch_active_alpha",
        "domain": "ecommerce",
        "amount": 1500.0,
        "decline_reason": "card_declined",
    }
    # Test rzp_live_wapsi_key_demo
    headers_live = {"X-API-Key": "rzp_live_wapsi_key_demo"}
    res_live = client.post("/api/v1/recovery/predict", json=payload, headers=headers_live)
    assert res_live.status_code == 401
    assert "Invalid WAPSI API Key" in res_live.json().get("detail", "")

    # Test rzp_test_wapsi_key_2026
    headers_test = {"X-API-Key": "rzp_test_wapsi_key_2026"}
    res_test = client.post("/api/v1/recovery/predict", json=payload, headers=headers_test)
    assert res_test.status_code == 401
    assert "Invalid WAPSI API Key" in res_test.json().get("detail", "")


# ==============================================================================
# 15. Default Merchant Fallback Unavailable in Production
# ==============================================================================
def test_15_default_merchant_fallback_unavailable_in_production(mock_db, monkeypatch):
    """PersistenceService rejects unauthenticated persistence operations in production."""
    prod_s = make_test_settings(wapsi_env="production", allow_dev_auth_fallback=False)
    monkeypatch.setattr("wapsi.core.config.get_settings", lambda: prod_s)
    monkeypatch.setattr("wapsi.db.service.get_settings", lambda: prod_s)
    service = PersistenceService(db_manager=mock_db)

    with pytest.raises(PermissionError) as exc_info:
        service.persist_causal_decision(
            decision_object={
                "decision_id": "dec_prod_no_auth",
                "recommended_action": "whatsapp_nudge",
            },
            raw_event={"payment_id": "pay_prod_no_auth"},
            merchant_code="merch_some_corp",
            authenticated_merchant_id=None,  # Missing authenticated merchant!
        )
    assert "Cannot persist causal decision without verified authenticated merchant context" in str(exc_info.value)


# ==============================================================================
# 16. Tenant-Safe Webhook Processing
# ==============================================================================
def test_16_tenant_safe_webhook_processing(mock_db, monkeypatch):
    """DurableWebhookInbox enforces tenant boundary and rejects unauthenticated fallback in production."""
    prod_s = make_test_settings(wapsi_env="production", allow_dev_auth_fallback=False)
    monkeypatch.setattr("wapsi.core.config.get_settings", lambda: prod_s)
    monkeypatch.setattr("wapsi.core.config.is_dev_fallback_permitted", lambda *args, **kwargs: False)
    inbox = DurableWebhookInbox(database_manager=mock_db)
    inbox.is_postgres = True  # test postgres fail-closed tenant logic

    with pytest.raises(PermissionError) as exc_info:
        inbox.check_or_record(
            provider="razorpay",
            event_id="evt_webhook_prod_001",
            event_type="payment.failed",
            payment_id="pay_wh_001",
            payload_sanitized={"payment": {"id": "pay_wh_001"}},
            merchant_id=None,
        )
    assert "Cannot record webhook event without resolved merchant context in production" in str(exc_info.value)


# ==============================================================================
# 17. Development Fallback Rejects Spoofed X-Merchant-ID
# ==============================================================================
def test_17_dev_fallback_rejects_spoofed_x_merchant_id(client, monkeypatch):
    """In development mode, requests with unauthenticated spoofed X-Merchant-ID are rejected with 403."""
    dev_s = make_test_settings(wapsi_env="development", allow_dev_auth_fallback=True)
    monkeypatch.setattr("wapsi.core.config.get_settings", lambda: dev_s)
    monkeypatch.setattr("wapsi.api.app.get_settings", lambda: dev_s)

    payload = {
        "case_id": "CASE_TEST_DEV_SPOOF",
        "merchant_id": "merch_spoofed_victim",
        "domain": "ecommerce",
        "amount": 1000.0,
        "decline_reason": "card_declined",
    }
    headers = {"X-Merchant-ID": "merch_spoofed_victim"}
    res = client.post("/api/v1/recovery/predict", json=payload, headers=headers)
    assert res.status_code == 403
    assert "Tenant authorization failure" in res.json().get("detail", "")


# ==============================================================================
# 18. Execute Recovery Requires Authentication
# ==============================================================================
def test_18_execute_recovery_requires_authentication(client):
    """Calling POST /api/v1/execute without API key in production mode is rejected with 401."""
    payload = {
        "payment_id": "pay_exec_unauth",
        "authorized_action": "whatsapp_nudge",
        "event_data": {"amount_in_inr": 1000.0, "merchant_id": "merch_active_alpha"},
    }
    res = client.post("/api/v1/execute", json=payload)
    assert res.status_code == 401
    assert "Missing API Key" in res.json().get("detail", "")


# ==============================================================================
# 19. Execute Recovery Rejects Contradictory Tenant
# ==============================================================================
def test_19_execute_recovery_rejects_contradictory_tenant(client, seeded_merchants):
    """Calling POST /api/v1/execute with Merchant A's key but Merchant B in payload is rejected with 403."""
    payload = {
        "payment_id": "pay_exec_mismatch",
        "authorized_action": "whatsapp_nudge",
        "event_data": {"amount_in_inr": 1000.0, "merchant_id": seeded_merchants["inactive_code"]},
    }
    headers = {"X-API-Key": seeded_merchants["active_key"]}
    res = client.post("/api/v1/execute", json=payload, headers=headers)
    assert res.status_code == 403
    assert "Tenant authorization failure" in res.json().get("detail", "")


# ==============================================================================
# 20. Outbox Enqueue Fails Closed Without Valid Merchant in Production
# ==============================================================================
def test_20_outbox_enqueue_fails_closed_without_merchant_in_production(mock_db, monkeypatch):
    """DurableOutboxStore.enqueue rejects unresolvable merchant in production."""
    prod_s = make_test_settings(wapsi_env="production", allow_dev_auth_fallback=False)
    monkeypatch.setattr("wapsi.core.config.get_settings", lambda: prod_s)
    from wapsi.recovery.outbox import DurableOutboxStore
    store = DurableOutboxStore(database_manager=mock_db)
    store.is_postgres = True

    with pytest.raises(PermissionError) as exc_info:
        store.enqueue(
            case_id="case_prod_no_m",
            payment_id="pay_prod_no_m",
            idempotency_key=f"idemp_{uuid.uuid4().hex[:8]}",
            action="whatsapp_nudge",
            channel="whatsapp",
            recipient_masked="+919876543210",
            message_payload={"amount": 1000},
            merchant_id="unregistered_phantom_merchant",
        )
    assert "not found in registry" in str(exc_info.value) or "Cannot resolve" in str(exc_info.value)
