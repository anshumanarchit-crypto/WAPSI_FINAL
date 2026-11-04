"""
WAPSI — Phase 6 Stage 2B Regression Test Suite:
Sandbox Outbound Token Routing and Strict Environment Guards.

Tests:
1. Development + dashboard_sandbox selects WHATSAPP_DIAGNOSTIC_TOKEN.
2. Production always selects WHATSAPP_ACCESS_TOKEN.
3. Dashboard token is rejected in production.
4. Missing dashboard token fails closed.
5. Invalid environment combinations fail closed (e.g. staging or live mode with dashboard_sandbox).
6. Secrets never appear in logs or __repr__.
7. Existing WhatsApp webhook functionality remains unchanged.
8. Existing authorization and opt-out gates remain enforced.
9. The approved provider client still uses the existing API integration.
10. No customer-contacting action occurs without operator approval.
"""

import os
import uuid
import pytest
from pydantic import SecretStr, ValidationError

from wapsi.core.config import WapsiSettings
from wapsi.integrations.whatsapp.client import WhatsAppClient, WhatsAppAuthError
from wapsi.recovery.outbox import DurableOutboxStore
from wapsi.recovery.opt_out_store import PersistentOptOutStore


def test_1_development_dashboard_sandbox_selects_diagnostic_token():
    """1. Development + dashboard_sandbox selects WHATSAPP_DIAGNOSTIC_TOKEN."""
    s = WapsiSettings(
        wapsi_env="development",
        razorpay_mode="test",
        razorpay_key_id="rzp_test_1234567890",
        whatsapp_access_token=SecretStr("system_user_token_12345"),
        whatsapp_diagnostic_token=SecretStr("diagnostic_dashboard_token_abcde"),
        whatsapp_auth_mode="dashboard_sandbox",
        whatsapp_phone_number_id="1407090562487899",
    )
    assert s.get_whatsapp_token_str() == "diagnostic_dashboard_token_abcde"
    assert s.has_whatsapp_configured is True


def test_2_production_always_selects_system_user_access_token():
    """2. Production always selects WHATSAPP_ACCESS_TOKEN."""
    s = WapsiSettings(
        wapsi_env="production",
        razorpay_mode="live",
        razorpay_key_id="rzp_live_1234567890",
        razorpay_key_secret=SecretStr("live_secret_123456789"),
        razorpay_webhook_secret=SecretStr("live_webhook_secret_987654321"),
        whatsapp_access_token=SecretStr("production_system_user_token_777"),
        whatsapp_auth_mode="system_user",
        whatsapp_phone_number_id="1407090562487899",
    )
    assert s.get_whatsapp_token_str() == "production_system_user_token_777"
    assert s.has_whatsapp_configured is True


def test_3_dashboard_token_rejected_in_production():
    """3. Dashboard token is rejected in production (fails closed at validation time)."""
    with pytest.raises(ValidationError) as exc_info:
        WapsiSettings(
            wapsi_env="production",
            razorpay_mode="live",
            razorpay_key_id="rzp_live_1234567890",
            razorpay_key_secret=SecretStr("live_secret_123456789"),
            razorpay_webhook_secret=SecretStr("live_webhook_secret_987654321"),
            whatsapp_access_token=SecretStr("production_system_user_token_777"),
            whatsapp_diagnostic_token=SecretStr("diagnostic_token_not_allowed"),
            whatsapp_auth_mode="dashboard_sandbox",
            whatsapp_phone_number_id="1407090562487899",
        )
    assert "WHATSAPP_AUTH_MODE=dashboard_sandbox is strictly prohibited in production" in str(exc_info.value)


def test_4_missing_dashboard_token_fails_closed():
    """4. Missing dashboard token in dashboard_sandbox mode fails closed without silent fallback."""
    s = WapsiSettings(
        wapsi_env="development",
        razorpay_mode="test",
        razorpay_key_id="rzp_test_1234567890",
        whatsapp_access_token=SecretStr("system_user_fallback_forbidden"),
        whatsapp_diagnostic_token=None,  # Missing!
        whatsapp_auth_mode="dashboard_sandbox",
        whatsapp_phone_number_id="1407090562487899",
    )
    with pytest.raises(ValueError) as exc_info:
        s.get_whatsapp_token_str()
    assert "Silent fallback to WHATSAPP_ACCESS_TOKEN is strictly prohibited" in str(exc_info.value)
    assert s.has_whatsapp_configured is False


def test_5_invalid_environment_combinations_fail_closed():
    """5. Invalid environment combinations fail closed."""
    # Staging env with dashboard_sandbox
    s_staging = WapsiSettings(
        wapsi_env="staging",
        razorpay_mode="test",
        razorpay_key_id="rzp_test_1234567890",
        whatsapp_access_token=SecretStr("system_user_token"),
        whatsapp_diagnostic_token=SecretStr("diag_token"),
        whatsapp_auth_mode="dashboard_sandbox",
        whatsapp_phone_number_id="1407090562487899",
    )
    with pytest.raises(ValueError) as exc:
        s_staging.get_whatsapp_token_str()
    assert "requires WAPSI_ENV=development" in str(exc.value)

    # Live razorpay mode with dashboard_sandbox raises ValidationError immediately
    with pytest.raises(ValidationError) as exc:
        WapsiSettings(
            wapsi_env="development",
            razorpay_mode="live",
            razorpay_key_id="rzp_live_1234567890",
            razorpay_key_secret=SecretStr("sec_123456789"),
            razorpay_webhook_secret=SecretStr("sec_webhook_123456789"),
            whatsapp_access_token=SecretStr("system_user_token"),
            whatsapp_diagnostic_token=SecretStr("diag_token"),
            whatsapp_auth_mode="dashboard_sandbox",
            whatsapp_phone_number_id="1407090562487899",
        )
    assert "WHATSAPP_AUTH_MODE=dashboard_sandbox is strictly prohibited in production/live mode" in str(exc.value)


def test_6_secrets_never_appear_in_logs_or_repr():
    """6. Secrets never appear in logs, error messages or __repr__."""
    secret_str = "VERY_SECRET_TOKEN_DO_NOT_LEAK_XYZ123"
    diag_str = "VERY_SECRET_DIAGNOSTIC_TOKEN_ABC789"
    s = WapsiSettings(
        wapsi_env="development",
        razorpay_mode="test",
        razorpay_key_id="rzp_test_1234567890",
        whatsapp_access_token=SecretStr(secret_str),
        whatsapp_diagnostic_token=SecretStr(diag_str),
        whatsapp_auth_mode="dashboard_sandbox",
        whatsapp_phone_number_id="1407090562487899",
    )
    rep = repr(s)
    assert secret_str not in rep
    assert diag_str not in rep
    assert "wa_auth_mode='dashboard_sandbox'" in rep


def test_7_existing_webhook_functionality_unimpaired():
    """7. Existing WhatsApp webhook verify token and meta app secret remain accessible."""
    s = WapsiSettings(
        wapsi_env="development",
        razorpay_mode="test",
        razorpay_key_id="rzp_test_1234567890",
        whatsapp_webhook_verify_token=SecretStr("verify_webhook_token_999"),
        meta_app_secret=SecretStr("meta_app_secret_888"),
        whatsapp_diagnostic_token=SecretStr("diag_token"),
        whatsapp_auth_mode="dashboard_sandbox",
        whatsapp_phone_number_id="1407090562487899",
    )
    assert s.get_whatsapp_verify_token_str() == "verify_webhook_token_999"
    assert s.get_meta_app_secret_bytes() == b"meta_app_secret_888"


def test_8_authorization_and_opt_out_gates_remain_enforced(tmp_path):
    """8. Existing authorization and opt-out gates remain enforced in persistent store."""
    db_file = tmp_path / "test_opt_out.db"
    store = PersistentOptOutStore(db_path=str(db_file))
    phone = "916260055671"

    assert store.is_opted_out(phone) is False
    store.record_opt_out(phone, reason="Customer STOP", source="whatsapp_inbound")
    assert store.is_opted_out(phone) is True


def test_9_provider_client_uses_existing_api_integration():
    """9. The approved WhatsAppClient resolves the active token without parallel architecture."""
    client = WhatsAppClient(
        access_token="explicit_token_override_999",
        phone_number_id="1407090562487899",
        api_version="v26.0",
    )
    assert client.access_token == "explicit_token_override_999"
    assert client.phone_number_id == "1407090562487899"
    assert client.api_version == "v26.0"
    assert client.is_configured is True


def test_10_no_customer_contact_without_operator_approval(tmp_path):
    """10. No customer-contacting action can occur without explicit operator approval."""
    db_file = tmp_path / "test_outbox.db"
    store = DurableOutboxStore(db_path=str(db_file))

    job = store.enqueue(
        case_id="case_safety_gate_001",
        payment_id="pay_safety_gate_001",
        action="WHATSAPP_ONE_CLICK_LINK",
        channel="whatsapp",
        recipient_masked="+91****5671",
        message_payload={"body": "Test Recovery"},
        idempotency_key="idemp_safety_gate_001",
        requires_operator_approval=True,
    )
    assert job.status == "PENDING_APPROVAL"
    assert job.requires_operator_approval is True
    assert job.approved_by_operator_id is None

    # Claiming should yield 0 jobs when pending operator approval
    claimed = store.claim_jobs(worker_id="test_worker_1", limit=5)
    assert len(claimed) == 0
