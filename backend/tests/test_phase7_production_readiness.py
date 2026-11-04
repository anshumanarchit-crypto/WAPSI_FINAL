"""
WAPSI — Phase 7 Gate 2 Security Test Suite:
Production Configuration & Credential Validation Security Matrix.

Verifies:
1. Valid Configurations:
   - Existing development configuration continues working.
   - Existing test configuration continues working.
   - Fully populated production configuration passes validation with synthetic credentials.
2. Invalid Production Configurations:
   - Missing Razorpay live mode is rejected.
   - Razorpay test mode is rejected in production.
   - Missing WhatsApp authentication mode is rejected.
   - Dashboard sandbox authentication is rejected in production.
   - Missing WhatsApp permanent system-user token is rejected.
   - Missing Meta application secret is rejected.
   - Empty or whitespace credentials are rejected.
   - Invalid environment combinations fail closed.
3. Security & Regression:
   - Credentials are never exposed through configuration representations (str, repr).
   - Credentials are never exposed through error messages or exception details.
   - Invalid production configuration does not silently downgrade to test/development.
   - Existing sandbox token routing remains unchanged outside production.
   - Existing authorization and tenant-isolation behavior remains intact.
"""

import pytest
from pydantic import SecretStr, ValidationError

from wapsi.core.config import WapsiSettings, get_settings
from wapsi.recovery.opt_out_store import PersistentOptOutStore


# Synthetic placeholder credentials for testing (NEVER real secrets)
SYNTHETIC_LIVE_KEY_ID = "rzp_live_syntheticKey0123456789"
SYNTHETIC_LIVE_SECRET = "synthetic_live_razorpay_secret_abc123"
SYNTHETIC_LIVE_WEBHOOK_SECRET = "synthetic_live_whsec_xyz987654321"
SYNTHETIC_SYSTEM_USER_TOKEN = "synthetic_meta_system_user_token_permanent_456"
SYNTHETIC_META_APP_SECRET = "synthetic_meta_app_secret_99887766"
SYNTHETIC_DIAGNOSTIC_TOKEN = "synthetic_diagnostic_token_dashboard_1122"
SYNTHETIC_PHONE_NUMBER_ID = "1407090562487899"


# ==============================================================================
# SECTION 1: VALID CONFIGURATIONS
# ==============================================================================

def test_1_existing_development_configuration_continues_working():
    """1. Existing development configuration continues working with defaults."""
    s = WapsiSettings(
        _env_file=None,
        wapsi_env="development",
        razorpay_mode="test",
        razorpay_key_id="rzp_test_devKey123456",
        razorpay_key_secret=SecretStr("dev_secret_123"),
        whatsapp_auth_mode="system_user",
    )
    assert s.wapsi_env == "development"
    assert s.razorpay_mode == "test"
    assert s.is_production is False
    assert s.masked_key_id.startswith("rzp_test_")
    # Demo keys accessible in non-production
    assert "rzp_test_wapsi_key_2026" in s.get_valid_api_keys()


def test_2_existing_test_configuration_continues_working():
    """2. Existing test configuration continues working without production constraints."""
    s = WapsiSettings(
        _env_file=None,
        wapsi_env="test",
        razorpay_mode="test",
        razorpay_key_id="rzp_test_automatedTestSuiteKey",
        razorpay_key_secret=SecretStr("test_secret_abc"),
        razorpay_webhook_secret=SecretStr("test_whsec_xyz"),
        whatsapp_auth_mode="system_user",
        whatsapp_access_token=SecretStr("test_token_123"),
    )
    assert s.wapsi_env == "test"
    assert s.razorpay_mode == "test"
    assert s.is_production is False
    assert s.get_whatsapp_token_str() == "test_token_123"


def test_3_fully_populated_production_configuration_passes_validation():
    """3. Fully populated production configuration passes validation with synthetic credentials."""
    s = WapsiSettings(
        _env_file=None,
        wapsi_env="production",
        razorpay_mode="live",
        razorpay_key_id=SYNTHETIC_LIVE_KEY_ID,
        razorpay_key_secret=SecretStr(SYNTHETIC_LIVE_SECRET),
        razorpay_webhook_secret=SecretStr(SYNTHETIC_LIVE_WEBHOOK_SECRET),
        whatsapp_auth_mode="system_user",
        whatsapp_access_token=SecretStr(SYNTHETIC_SYSTEM_USER_TOKEN),
        meta_app_secret=SecretStr(SYNTHETIC_META_APP_SECRET),
        whatsapp_phone_number_id=SYNTHETIC_PHONE_NUMBER_ID,
    )
    assert s.wapsi_env == "production"
    assert s.razorpay_mode == "live"
    assert s.is_production is True
    assert s.get_whatsapp_token_str() == SYNTHETIC_SYSTEM_USER_TOKEN
    assert s.get_meta_app_secret_bytes() == SYNTHETIC_META_APP_SECRET.encode("utf-8")
    assert s.get_webhook_secret_bytes() == SYNTHETIC_LIVE_WEBHOOK_SECRET.encode("utf-8")
    assert s.has_whatsapp_configured is True
    assert s.masked_key_id == "rzp_live_****6789"


# ==============================================================================
# SECTION 2: INVALID PRODUCTION CONFIGURATIONS (FAIL-CLOSED)
# ==============================================================================

def test_4_missing_razorpay_live_mode_rejected_in_production():
    """4. Missing Razorpay live mode is rejected in production (defaults to test)."""
    with pytest.raises(ValidationError) as exc_info:
        WapsiSettings(
            _env_file=None,
            wapsi_env="production",
            # razorpay_mode omitted, defaults to 'test'
            razorpay_key_id=SYNTHETIC_LIVE_KEY_ID,
            razorpay_key_secret=SecretStr(SYNTHETIC_LIVE_SECRET),
            razorpay_webhook_secret=SecretStr(SYNTHETIC_LIVE_WEBHOOK_SECRET),
            whatsapp_auth_mode="system_user",
            whatsapp_access_token=SecretStr(SYNTHETIC_SYSTEM_USER_TOKEN),
            meta_app_secret=SecretStr(SYNTHETIC_META_APP_SECRET),
        )
    assert "RAZORPAY_MODE must be 'live' in production mode" in str(exc_info.value)


def test_5_razorpay_test_mode_rejected_in_production():
    """5. Explicit Razorpay test mode is rejected in production."""
    with pytest.raises(ValidationError) as exc_info:
        WapsiSettings(
            _env_file=None,
            wapsi_env="production",
            razorpay_mode="test",
            razorpay_key_id="rzp_test_syntheticKey123",
            razorpay_key_secret=SecretStr(SYNTHETIC_LIVE_SECRET),
            razorpay_webhook_secret=SecretStr(SYNTHETIC_LIVE_WEBHOOK_SECRET),
            whatsapp_auth_mode="system_user",
            whatsapp_access_token=SecretStr(SYNTHETIC_SYSTEM_USER_TOKEN),
            meta_app_secret=SecretStr(SYNTHETIC_META_APP_SECRET),
        )
    assert "RAZORPAY_MODE must be 'live' in production mode" in str(exc_info.value)
    assert "Test mode and sandbox configurations are strictly prohibited" in str(exc_info.value)


def test_6_missing_whatsapp_authentication_mode_rejected():
    """6. Missing or empty WhatsApp authentication mode is rejected."""
    with pytest.raises(ValidationError) as exc_info:
        WapsiSettings(
            _env_file=None,
            wapsi_env="production",
            razorpay_mode="live",
            razorpay_key_id=SYNTHETIC_LIVE_KEY_ID,
            razorpay_key_secret=SecretStr(SYNTHETIC_LIVE_SECRET),
            razorpay_webhook_secret=SecretStr(SYNTHETIC_LIVE_WEBHOOK_SECRET),
            whatsapp_auth_mode="",  # Empty mode
            whatsapp_access_token=SecretStr(SYNTHETIC_SYSTEM_USER_TOKEN),
            meta_app_secret=SecretStr(SYNTHETIC_META_APP_SECRET),
        )
    assert "WHATSAPP_AUTH_MODE cannot be empty" in str(exc_info.value)


def test_7_dashboard_sandbox_authentication_rejected_in_production():
    """7. Dashboard sandbox authentication mode is rejected in production."""
    with pytest.raises(ValidationError) as exc_info:
        WapsiSettings(
            _env_file=None,
            wapsi_env="production",
            razorpay_mode="live",
            razorpay_key_id=SYNTHETIC_LIVE_KEY_ID,
            razorpay_key_secret=SecretStr(SYNTHETIC_LIVE_SECRET),
            razorpay_webhook_secret=SecretStr(SYNTHETIC_LIVE_WEBHOOK_SECRET),
            whatsapp_auth_mode="dashboard_sandbox",
            whatsapp_access_token=SecretStr(SYNTHETIC_SYSTEM_USER_TOKEN),
            whatsapp_diagnostic_token=SecretStr(SYNTHETIC_DIAGNOSTIC_TOKEN),
            meta_app_secret=SecretStr(SYNTHETIC_META_APP_SECRET),
        )
    assert "WHATSAPP_AUTH_MODE=dashboard_sandbox is strictly prohibited in production/live mode" in str(exc_info.value)


def test_8_missing_whatsapp_system_user_token_rejected_in_production():
    """8. Missing WhatsApp permanent system-user access token is rejected in production."""
    with pytest.raises(ValidationError) as exc_info:
        WapsiSettings(
            _env_file=None,
            wapsi_env="production",
            razorpay_mode="live",
            razorpay_key_id=SYNTHETIC_LIVE_KEY_ID,
            razorpay_key_secret=SecretStr(SYNTHETIC_LIVE_SECRET),
            razorpay_webhook_secret=SecretStr(SYNTHETIC_LIVE_WEBHOOK_SECRET),
            whatsapp_auth_mode="system_user",
            whatsapp_access_token=None,  # Missing!
            meta_app_secret=SecretStr(SYNTHETIC_META_APP_SECRET),
        )
    assert "WHATSAPP_ACCESS_TOKEN (permanent system-user token) is required in production mode" in str(exc_info.value)


def test_9_missing_meta_app_secret_rejected_in_production():
    """9. Missing Meta application secret is rejected in production."""
    with pytest.raises(ValidationError) as exc_info:
        WapsiSettings(
            _env_file=None,
            wapsi_env="production",
            razorpay_mode="live",
            razorpay_key_id=SYNTHETIC_LIVE_KEY_ID,
            razorpay_key_secret=SecretStr(SYNTHETIC_LIVE_SECRET),
            razorpay_webhook_secret=SecretStr(SYNTHETIC_LIVE_WEBHOOK_SECRET),
            whatsapp_auth_mode="system_user",
            whatsapp_access_token=SecretStr(SYNTHETIC_SYSTEM_USER_TOKEN),
            meta_app_secret=None,  # Missing!
        )
    assert "META_APP_SECRET is required in production mode" in str(exc_info.value)


def test_10_empty_credentials_rejected():
    """10. Empty or whitespace credentials are fail-closed rejected across all required fields."""
    base_kwargs = {
        "_env_file": None,
        "wapsi_env": "production",
        "razorpay_mode": "live",
        "razorpay_key_id": SYNTHETIC_LIVE_KEY_ID,
        "razorpay_key_secret": SecretStr(SYNTHETIC_LIVE_SECRET),
        "razorpay_webhook_secret": SecretStr(SYNTHETIC_LIVE_WEBHOOK_SECRET),
        "whatsapp_auth_mode": "system_user",
        "whatsapp_access_token": SecretStr(SYNTHETIC_SYSTEM_USER_TOKEN),
        "meta_app_secret": SecretStr(SYNTHETIC_META_APP_SECRET),
    }

    # Empty razorpay_key_id
    kw = dict(base_kwargs, razorpay_key_id="   ")
    with pytest.raises(ValidationError) as exc:
        WapsiSettings(**kw)
    assert "RAZORPAY_KEY_ID is required" in str(exc.value)

    # Empty razorpay_key_secret
    kw = dict(base_kwargs, razorpay_key_secret=SecretStr("   "))
    with pytest.raises(ValidationError) as exc:
        WapsiSettings(**kw)
    assert "RAZORPAY_KEY_SECRET is required" in str(exc.value)

    # Empty razorpay_webhook_secret
    kw = dict(base_kwargs, razorpay_webhook_secret=SecretStr(""))
    with pytest.raises(ValidationError) as exc:
        WapsiSettings(**kw)
    assert "RAZORPAY_WEBHOOK_SECRET is required" in str(exc.value)

    # Empty whatsapp_access_token
    kw = dict(base_kwargs, whatsapp_access_token=SecretStr("   "))
    with pytest.raises(ValidationError) as exc:
        WapsiSettings(**kw)
    assert "WHATSAPP_ACCESS_TOKEN" in str(exc.value)

    # Empty meta_app_secret
    kw = dict(base_kwargs, meta_app_secret=SecretStr(""))
    with pytest.raises(ValidationError) as exc:
        WapsiSettings(**kw)
    assert "META_APP_SECRET is required in production mode" in str(exc.value)


def test_11_invalid_environment_combinations_fail_closed():
    """11. Invalid environment combinations fail closed at initialization or retrieval."""
    # Staging env with dashboard_sandbox mode
    s_staging = WapsiSettings(
        _env_file=None,
        wapsi_env="staging",
        razorpay_mode="test",
        razorpay_key_id="rzp_test_syntheticKey123",
        whatsapp_diagnostic_token=SecretStr(SYNTHETIC_DIAGNOSTIC_TOKEN),
        whatsapp_auth_mode="dashboard_sandbox",
    )
    with pytest.raises(ValueError) as exc:
        s_staging.get_whatsapp_token_str()
    assert "requires WAPSI_ENV=development" in str(exc.value)

    # Development env with live razorpay mode and dashboard_sandbox mode
    with pytest.raises(ValidationError) as exc:
        WapsiSettings(
            _env_file=None,
            wapsi_env="development",
            razorpay_mode="live",
            razorpay_key_id=SYNTHETIC_LIVE_KEY_ID,
            razorpay_key_secret=SecretStr(SYNTHETIC_LIVE_SECRET),
            razorpay_webhook_secret=SecretStr(SYNTHETIC_LIVE_WEBHOOK_SECRET),
            whatsapp_auth_mode="dashboard_sandbox",
            whatsapp_diagnostic_token=SecretStr(SYNTHETIC_DIAGNOSTIC_TOKEN),
        )
    assert "WHATSAPP_AUTH_MODE=dashboard_sandbox is strictly prohibited in production/live mode" in str(exc.value)

    # Production mode with test-prefix key id
    with pytest.raises(ValidationError) as exc:
        WapsiSettings(
            _env_file=None,
            wapsi_env="production",
            razorpay_mode="live",
            razorpay_key_id="rzp_test_cannotUseTestKeyInLiveMode",
            razorpay_key_secret=SecretStr(SYNTHETIC_LIVE_SECRET),
            razorpay_webhook_secret=SecretStr(SYNTHETIC_LIVE_WEBHOOK_SECRET),
            whatsapp_auth_mode="system_user",
            whatsapp_access_token=SecretStr(SYNTHETIC_SYSTEM_USER_TOKEN),
            meta_app_secret=SecretStr(SYNTHETIC_META_APP_SECRET),
        )
    assert "must start with 'rzp_live_'" in str(exc.value)


# ==============================================================================
# SECTION 3: SECURITY & REGRESSION
# ==============================================================================

def test_12_credentials_not_exposed_through_configuration_representations():
    """12. Credentials are never exposed through configuration representations (str, repr)."""
    s = WapsiSettings(
        _env_file=None,
        wapsi_env="production",
        razorpay_mode="live",
        razorpay_key_id=SYNTHETIC_LIVE_KEY_ID,
        razorpay_key_secret=SecretStr(SYNTHETIC_LIVE_SECRET),
        razorpay_webhook_secret=SecretStr(SYNTHETIC_LIVE_WEBHOOK_SECRET),
        whatsapp_auth_mode="system_user",
        whatsapp_access_token=SecretStr(SYNTHETIC_SYSTEM_USER_TOKEN),
        meta_app_secret=SecretStr(SYNTHETIC_META_APP_SECRET),
        wapsi_api_key=SecretStr("super_secret_api_key_value_99999"),
    )

    rep = repr(s)
    text = str(s)

    for secret in [
        SYNTHETIC_LIVE_SECRET,
        SYNTHETIC_LIVE_WEBHOOK_SECRET,
        SYNTHETIC_SYSTEM_USER_TOKEN,
        SYNTHETIC_META_APP_SECRET,
        "super_secret_api_key_value_99999",
    ]:
        assert secret not in rep
        assert secret not in text

    # Key ID must be masked
    assert SYNTHETIC_LIVE_KEY_ID not in rep
    assert SYNTHETIC_LIVE_KEY_ID not in text
    assert "rzp_live_****6789" in rep
    assert "rzp_live_****6789" in text


def test_13_credentials_not_exposed_through_error_messages():
    """13. Credentials are never exposed through error messages or exception details."""
    sensitive_token = "VERY_CONFIDENTIAL_TOKEN_DO_NOT_EXPOSE_9999"

    with pytest.raises(ValidationError) as exc:
        WapsiSettings(
            _env_file=None,
            wapsi_env="production",
            razorpay_mode="live",
            razorpay_key_id=SYNTHETIC_LIVE_KEY_ID,
            razorpay_key_secret=SecretStr(sensitive_token),
            razorpay_webhook_secret=SecretStr("   "),  # Triggers error
            whatsapp_auth_mode="system_user",
            whatsapp_access_token=SecretStr(sensitive_token),
            meta_app_secret=SecretStr(sensitive_token),
        )

    err_str = str(exc.value)
    assert sensitive_token not in err_str
    assert "RAZORPAY_WEBHOOK_SECRET is required" in err_str


def test_14_invalid_production_configuration_does_not_silently_downgrade():
    """14. Invalid production configuration does not silently downgrade to test or development."""
    with pytest.raises(ValidationError):
        WapsiSettings(
            _env_file=None,
            wapsi_env="production",
            razorpay_mode="test",
            razorpay_key_id="rzp_test_someKey",
        )

    # In production, fallback demo API keys and webhook secrets are strictly prohibited
    s_prod = WapsiSettings(
        _env_file=None,
        wapsi_env="production",
        razorpay_mode="live",
        razorpay_key_id=SYNTHETIC_LIVE_KEY_ID,
        razorpay_key_secret=SecretStr(SYNTHETIC_LIVE_SECRET),
        razorpay_webhook_secret=SecretStr(SYNTHETIC_LIVE_WEBHOOK_SECRET),
        whatsapp_auth_mode="system_user",
        whatsapp_access_token=SecretStr(SYNTHETIC_SYSTEM_USER_TOKEN),
        meta_app_secret=SecretStr(SYNTHETIC_META_APP_SECRET),
        wapsi_api_key=SecretStr("prod_custom_key_only"),
    )
    api_keys = s_prod.get_valid_api_keys()
    assert "rzp_test_wapsi_key_2026" not in api_keys
    assert "rzp_live_wapsi_key_demo" not in api_keys
    assert "prod_custom_key_only" in api_keys


def test_15_existing_sandbox_token_routing_unchanged_outside_production():
    """15. Existing sandbox token routing remains unchanged outside production."""
    # Development + dashboard_sandbox
    s_sandbox = WapsiSettings(
        _env_file=None,
        wapsi_env="development",
        razorpay_mode="test",
        razorpay_key_id="rzp_test_1234567890",
        whatsapp_diagnostic_token=SecretStr(SYNTHETIC_DIAGNOSTIC_TOKEN),
        whatsapp_access_token=SecretStr(SYNTHETIC_SYSTEM_USER_TOKEN),
        whatsapp_auth_mode="dashboard_sandbox",
        whatsapp_phone_number_id=SYNTHETIC_PHONE_NUMBER_ID,
    )
    assert s_sandbox.get_whatsapp_token_str() == SYNTHETIC_DIAGNOSTIC_TOKEN
    assert s_sandbox.has_whatsapp_configured is True

    # Development + system_user
    s_system = WapsiSettings(
        _env_file=None,
        wapsi_env="development",
        razorpay_mode="test",
        razorpay_key_id="rzp_test_1234567890",
        whatsapp_access_token=SecretStr(SYNTHETIC_SYSTEM_USER_TOKEN),
        whatsapp_auth_mode="system_user",
        whatsapp_phone_number_id=SYNTHETIC_PHONE_NUMBER_ID,
    )
    assert s_system.get_whatsapp_token_str() == SYNTHETIC_SYSTEM_USER_TOKEN
    assert s_system.has_whatsapp_configured is True


def test_16_existing_authorization_and_tenant_isolation_remains_intact(tmp_path):
    """16. Existing authorization and tenant-isolation behavior remains intact."""
    # Opt-out persistent store isolation
    db_file = tmp_path / "test_opt_out_phase7.db"
    store = PersistentOptOutStore(db_path=str(db_file))
    customer_phone = "919988776655"

    assert store.is_opted_out(customer_phone) is False
    store.record_opt_out(customer_phone, reason="USER_STOP", source="whatsapp_inbound")
    assert store.is_opted_out(customer_phone) is True

    # Non-production settings include backward-compatible demo API keys
    s_dev = WapsiSettings(
        _env_file=None,
        wapsi_env="development",
        razorpay_mode="test",
        razorpay_key_id="rzp_test_1234567890",
    )
    assert "rzp_test_wapsi_key_2026" in s_dev.get_valid_api_keys()
    assert "rzp_live_wapsi_key_demo" in s_dev.get_valid_api_keys()


def test_17_duplicate_diagnostic_token_as_access_token_rejected_in_production():
    """17. Accidental configuration of sandbox diagnostic token as system user access token fails closed."""
    with pytest.raises(ValidationError) as exc:
        WapsiSettings(
            _env_file=None,
            wapsi_env="production",
            razorpay_mode="live",
            razorpay_key_id=SYNTHETIC_LIVE_KEY_ID,
            razorpay_key_secret=SecretStr(SYNTHETIC_LIVE_SECRET),
            razorpay_webhook_secret=SecretStr(SYNTHETIC_LIVE_WEBHOOK_SECRET),
            whatsapp_auth_mode="system_user",
            whatsapp_access_token=SecretStr(SYNTHETIC_DIAGNOSTIC_TOKEN),
            whatsapp_diagnostic_token=SecretStr(SYNTHETIC_DIAGNOSTIC_TOKEN),
            meta_app_secret=SecretStr(SYNTHETIC_META_APP_SECRET),
        )
    assert "WHATSAPP_ACCESS_TOKEN cannot be identical to WHATSAPP_DIAGNOSTIC_TOKEN" in str(exc.value)
    assert "Dashboard sandbox tokens are strictly prohibited in production mode" in str(exc.value)


def test_18_credential_getters_strip_whitespace_and_newlines():
    """18. Credential getters strictly strip whitespace, newlines, and trailing spaces."""
    s = WapsiSettings(
        _env_file=None,
        wapsi_env="production",
        razorpay_mode="live",
        razorpay_key_id=f"  {SYNTHETIC_LIVE_KEY_ID}  ",
        razorpay_key_secret=SecretStr(f" \n {SYNTHETIC_LIVE_SECRET} \r\t "),
        razorpay_webhook_secret=SecretStr(f"  {SYNTHETIC_LIVE_WEBHOOK_SECRET}\n"),
        whatsapp_auth_mode="system_user",
        whatsapp_access_token=SecretStr(f"\t{SYNTHETIC_SYSTEM_USER_TOKEN} \n"),
        whatsapp_webhook_verify_token=SecretStr("  verify_token_with_spaces  "),
        meta_app_secret=SecretStr(f" \n {SYNTHETIC_META_APP_SECRET} "),
        wapsi_api_key=SecretStr("  custom_prod_api_key  "),
    )

    assert s.get_whatsapp_token_str() == SYNTHETIC_SYSTEM_USER_TOKEN
    assert s.get_whatsapp_verify_token_str() == "verify_token_with_spaces"
    assert s.get_meta_app_secret_bytes() == SYNTHETIC_META_APP_SECRET.encode("utf-8")
    assert s.get_webhook_secret_bytes() == SYNTHETIC_LIVE_WEBHOOK_SECRET.encode("utf-8")
    assert "custom_prod_api_key" in s.get_valid_api_keys()


def test_19_case_insensitive_production_env_blocks_windows_fallback(monkeypatch):
    """19. Windows registry fallback is bypassed under case-insensitive production env designations."""
    import wapsi.core.config as config_mod

    # Mock _get_windows_user_env to return a test secret if called
    reg_called = False
    def mock_reg(var_name):
        nonlocal reg_called
        reg_called = True
        return "injected_test_val"

    monkeypatch.setattr(config_mod, "_get_windows_user_env", mock_reg)

    # Upper case WAPSI_ENV in dict
    vals = {"WAPSI_ENV": "PRODUCTION"}
    result = config_mod.WapsiSettings.populate_windows_env_fallbacks(vals)
    assert reg_called is False
    assert "RAZORPAY_KEY_ID" not in result

    # Mixed case with extra whitespace
    vals2 = {"wapsi_env": "  PrOdUcTiOn  "}
    result2 = config_mod.WapsiSettings.populate_windows_env_fallbacks(vals2)
    assert reg_called is False
    assert "RAZORPAY_KEY_ID" not in result2

