"""
Centralized Configuration and Credential Management for WAPSI.
Reads configuration from process environment variables, optional .env files,
and Windows user environment registry when applicable.
Enforces strict secret masking, credential validation, and fail-closed production safety.
"""

from __future__ import annotations

import os
import sys
from typing import Optional, Set
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _get_windows_user_env(var_name: str) -> Optional[str]:
    """Fallback reader for Windows User Environment variables stored in registry."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
            val, _ = winreg.QueryValueEx(key, var_name)
            return str(val) if val else None
    except Exception:
        return None


class WapsiSettings(BaseSettings):
    """
    Centralized WAPSI configuration with Pydantic v2 validation and SecretStr redaction.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True
    )

    # Environment
    wapsi_env: str = Field(default="development", alias="WAPSI_ENV")
    wapsi_log_level: str = Field(default="INFO", alias="WAPSI_LOG_LEVEL")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    models_dir: str = Field(default="models", alias="MODELS_DIR")
    public_base_url: str = Field(default="http://127.0.0.1:8000", alias="WAPSI_PUBLIC_BASE_URL")

    # Razorpay Credentials (Test Mode)
    razorpay_mode: str = Field(default="test", alias="RAZORPAY_MODE")
    razorpay_key_id: Optional[str] = Field(default=None, alias="RAZORPAY_KEY_ID")
    razorpay_key_secret: Optional[SecretStr] = Field(default=None, alias="RAZORPAY_KEY_SECRET")
    razorpay_webhook_secret: Optional[SecretStr] = Field(default=None, alias="RAZORPAY_WEBHOOK_SECRET")

    # WhatsApp Cloud API (Meta Graph API)
    whatsapp_access_token: Optional[SecretStr] = Field(default=None, alias="WHATSAPP_ACCESS_TOKEN")
    whatsapp_diagnostic_token: Optional[SecretStr] = Field(default=None, alias="WHATSAPP_DIAGNOSTIC_TOKEN")
    whatsapp_auth_mode: str = Field(default="system_user", alias="WHATSAPP_AUTH_MODE")
    whatsapp_phone_number_id: Optional[str] = Field(default=None, alias="WHATSAPP_PHONE_NUMBER_ID")
    whatsapp_business_account_id: Optional[str] = Field(default=None, alias="WHATSAPP_BUSINESS_ACCOUNT_ID")
    whatsapp_webhook_verify_token: Optional[SecretStr] = Field(default=None, alias="WHATSAPP_WEBHOOK_VERIFY_TOKEN")
    meta_app_secret: Optional[SecretStr] = Field(default=None, alias="META_APP_SECRET")
    whatsapp_api_version: str = Field(default="v26.0", alias="WHATSAPP_API_VERSION")
    whatsapp_enforce_24h_window: bool = Field(default=False, alias="WHATSAPP_ENFORCE_24H_WINDOW")
    whatsapp_recovery_template_name: Optional[str] = Field(default=None, alias="WHATSAPP_RECOVERY_TEMPLATE_NAME")
    whatsapp_recovery_template_language: str = Field(default="en", alias="WHATSAPP_RECOVERY_TEMPLATE_LANGUAGE")
    test_recipient_phone: Optional[str] = Field(default=None, alias="TEST_RECIPIENT_PHONE")

    # WAPSI Security
    wapsi_api_key: Optional[SecretStr] = Field(default=None, alias="WAPSI_API_KEY")
    wapsi_api_rate_limit: int = Field(default=120, alias="WAPSI_API_RATE_LIMIT")

    # Policy Defaults
    policy_dnd_start_hour: int = Field(default=21, alias="POLICY_DND_START_HOUR")
    policy_dnd_end_hour: int = Field(default=9, alias="POLICY_DND_END_HOUR")
    policy_max_daily_touches: int = Field(default=2, alias="POLICY_MAX_DAILY_TOUCHES")
    policy_min_ivr_amount: float = Field(default=1500.0, alias="POLICY_MIN_IVR_AMOUNT")

    # Database & Supabase Configuration (Target: WAPSI-DEV-MUMBAI, Region: ap-south-1)
    database_url: Optional[str] = Field(default=None, alias="DATABASE_URL")
    default_merchant_id: str = Field(default="04a2aaf8-8c8a-4d99-852c-cefc80e82019", alias="DEFAULT_MERCHANT_ID")
    supabase_url: str = Field(default="https://filofxijqmgluuulivxb.supabase.co", alias="SUPABASE_URL")
    supabase_anon_key: Optional[SecretStr] = Field(default=None, alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: Optional[SecretStr] = Field(default=None, alias="SUPABASE_SERVICE_ROLE_KEY")
    customer_hash_salt: SecretStr = Field(default=SecretStr("wapsi_customer_hash_salt_demo_2026"), alias="CUSTOMER_HASH_SALT")

    # LLM Providers for Synthetic Narrative Generation
    groq_api_key: Optional[SecretStr] = Field(default=None, alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")
    gemini_api_key: Optional[SecretStr] = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    ollama_base_url: str = Field(default="http://localhost:11434/v1", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="llama3", alias="OLLAMA_MODEL")

    @model_validator(mode="before")
    @classmethod
    def populate_windows_env_fallbacks(cls, values: dict) -> dict:
        """If key variables are absent in process env or .env, check Windows user environment."""
        if not isinstance(values, dict):
            values = {}

        # In production mode, never silently fall back to Windows registry defaults
        env = None
        for k, v in values.items():
            if str(k).lower() == "wapsi_env":
                env = v
                break
        if env is None:
            env = os.environ.get("WAPSI_ENV") or os.environ.get("wapsi_env") or "development"

        if str(env).strip().lower() == "production":
            return values

        for var_name in ["RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_MODE", "RAZORPAY_WEBHOOK_SECRET"]:
            field_key = var_name.lower()
            if not values.get(field_key) and not values.get(var_name) and not os.environ.get(var_name):
                reg_val = _get_windows_user_env(var_name)
                if reg_val:
                    values[var_name] = reg_val
        return values

    @field_validator("wapsi_env")
    @classmethod
    def validate_wapsi_env(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("WAPSI_ENV cannot be empty.")
        return str(v).strip().lower()

    @field_validator("razorpay_mode")
    @classmethod
    def validate_mode(cls, v: str, info) -> str:
        if not v or not str(v).strip():
            raise ValueError("RAZORPAY_MODE cannot be empty. Must be 'test' or 'live'.")
        mode = str(v).strip().lower()
        if mode not in {"test", "live"}:
            raise ValueError(f"RAZORPAY_MODE must be 'test' or 'live', got: '{v}'")
        env = str(info.data.get("wapsi_env") or "development").strip().lower()
        if env == "production" and mode != "live":
            raise ValueError(
                f"RAZORPAY_MODE must be 'live' in production mode, got: '{v}'. "
                "Test mode and sandbox configurations are strictly prohibited in production."
            )
        return mode

    @field_validator("razorpay_key_id")
    @classmethod
    def validate_key_prefix(cls, v: Optional[str], info) -> Optional[str]:
        if not v:
            return v
        key = v.strip()
        if not key:
            return ""
        env = str(info.data.get("wapsi_env") or "development").strip().lower()
        mode = info.data.get("razorpay_mode", "test")
        if env == "production" and mode != "live":
            raise ValueError(
                f"RAZORPAY_MODE must be 'live' in production mode, got: '{mode}'. "
                "Test mode and sandbox configurations are strictly prohibited in production."
            )
        if mode == "test" and not key.startswith("rzp_test_"):
            raise ValueError(f"RAZORPAY_KEY_ID in test mode must start with 'rzp_test_', got: '{key[:12]}...'")
        elif mode == "live" and not key.startswith("rzp_live_"):
            raise ValueError(f"RAZORPAY_KEY_ID in live mode must start with 'rzp_live_', got: '{key[:12]}...'")
        return key

    @field_validator("whatsapp_auth_mode")
    @classmethod
    def validate_wa_mode(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("WHATSAPP_AUTH_MODE cannot be empty. Must be 'system_user' or 'dashboard_sandbox'.")
        mode = str(v).strip().lower()
        if mode not in {"system_user", "dashboard_sandbox"}:
            raise ValueError(
                f"Invalid WHATSAPP_AUTH_MODE: '{v}'. Must be 'system_user' or 'dashboard_sandbox'."
            )
        return mode

    @model_validator(mode="after")
    def validate_production_safety(self) -> "WapsiSettings":
        """Fail closed in production if required secrets or configurations are absent or invalid."""
        env = (self.wapsi_env or "").strip().lower()
        mode = (self.razorpay_mode or "").strip().lower()
        wa_mode = (self.whatsapp_auth_mode or "").strip().lower()

        # Shared checks whenever live mode or production is active
        if env == "production" or mode == "live":
            if not self.razorpay_key_id or not self.razorpay_key_id.strip():
                raise ValueError("RAZORPAY_KEY_ID is required in production/live mode.")
            if not self.razorpay_key_secret or not self.razorpay_key_secret.get_secret_value().strip():
                raise ValueError("RAZORPAY_KEY_SECRET is required in production/live mode.")
            if not self.razorpay_webhook_secret or not self.razorpay_webhook_secret.get_secret_value().strip():
                raise ValueError("RAZORPAY_WEBHOOK_SECRET is required in production/live mode.")
            if wa_mode == "dashboard_sandbox":
                raise ValueError(
                    "WHATSAPP_AUTH_MODE=dashboard_sandbox is strictly prohibited in production/live mode. "
                    "Only system_user mode is permitted."
                )

        # Strict Production environment enforcements
        if env == "production":
            if mode != "live":
                raise ValueError(
                    f"RAZORPAY_MODE must be 'live' in production mode, got: '{self.razorpay_mode}'. "
                    "Test mode and sandbox configurations are strictly prohibited in production."
                )
            if wa_mode != "system_user":
                raise ValueError(
                    f"WHATSAPP_AUTH_MODE must be 'system_user' in production mode, got: '{self.whatsapp_auth_mode}'."
                )
            if not self.whatsapp_access_token or not self.whatsapp_access_token.get_secret_value().strip():
                raise ValueError(
                    "WHATSAPP_ACCESS_TOKEN (permanent system-user token) is required in production mode."
                )
            if (
                self.whatsapp_diagnostic_token
                and self.whatsapp_diagnostic_token.get_secret_value().strip()
                and self.whatsapp_access_token.get_secret_value().strip() == self.whatsapp_diagnostic_token.get_secret_value().strip()
            ):
                raise ValueError(
                    "WHATSAPP_ACCESS_TOKEN cannot be identical to WHATSAPP_DIAGNOSTIC_TOKEN. "
                    "Dashboard sandbox tokens are strictly prohibited in production mode."
                )
            if not self.meta_app_secret or not self.meta_app_secret.get_secret_value().strip():
                raise ValueError(
                    "META_APP_SECRET is required in production mode."
                )

        return self

    @property
    def masked_key_id(self) -> str:
        """Returns safe masked key id (e.g. rzp_test_****1234)."""
        if not self.razorpay_key_id:
            return "NOT_CONFIGURED"
        prefix = "rzp_test_" if self.razorpay_key_id.startswith("rzp_test_") else (
            "rzp_live_" if self.razorpay_key_id.startswith("rzp_live_") else self.razorpay_key_id[:8]
        )
        if len(self.razorpay_key_id) <= 12:
            return f"{prefix}****"
        return f"{prefix}****{self.razorpay_key_id[-4:]}"

    @property
    def has_key_secret(self) -> bool:
        return bool(self.razorpay_key_secret and self.razorpay_key_secret.get_secret_value())

    @property
    def has_webhook_secret(self) -> bool:
        return bool(self.razorpay_webhook_secret and self.razorpay_webhook_secret.get_secret_value())

    @property
    def is_public_base_url_configured(self) -> bool:
        if not self.public_base_url:
            return False
        clean = self.public_base_url.strip().lower()
        return (
            clean.startswith("https://")
            and not clean.startswith("https://127.0.0.1")
            and not clean.startswith("https://localhost")
        )

    @property
    def razorpay_webhook_url(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/api/v1/webhooks/razorpay"

    @property
    def whatsapp_webhook_url(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/api/v1/webhooks/whatsapp"

    def get_valid_api_keys(self) -> Set[str]:
        """Returns set of authorized API keys for request authentication."""
        keys = set()
        if self.wapsi_api_key and self.wapsi_api_key.get_secret_value().strip():
            keys.add(self.wapsi_api_key.get_secret_value().strip())
        # In non-production, include standard demo key for backward-compatible test suites
        if self.wapsi_env.lower() != "production":
            keys.add("rzp_live_wapsi_key_demo")
            keys.add("rzp_test_wapsi_key_2026")
        return keys

    def get_webhook_secret_bytes(self) -> bytes:
        """Returns webhook secret as bytes for constant-time HMAC calculation."""
        if self.razorpay_webhook_secret and self.razorpay_webhook_secret.get_secret_value().strip():
            return self.razorpay_webhook_secret.get_secret_value().strip().encode("utf-8")
        if self.wapsi_env.lower() != "production":
            return b"rzp_webhook_secret_dev_demo"
        raise ValueError("RAZORPAY_WEBHOOK_SECRET must be configured in production.")

    @property
    def has_whatsapp_configured(self) -> bool:
        """Checks if minimum WhatsApp Cloud API credentials are provided based on the active auth mode."""
        try:
            token = self.get_whatsapp_token_str()
            return bool(token and self.whatsapp_phone_number_id)
        except Exception:
            return False

    def get_whatsapp_token_str(self) -> Optional[str]:
        """
        Retrieves the active WhatsApp token based on WHATSAPP_AUTH_MODE.
        Enforces strict fail-closed safety for sandbox-only tokens.
        """
        mode = self.whatsapp_auth_mode.strip().lower()
        if mode == "dashboard_sandbox":
            # Strict safety checks: only allowed in development with razorpay test mode
            if self.wapsi_env.lower() == "production":
                raise ValueError("WHATSAPP_AUTH_MODE=dashboard_sandbox is forbidden in production environment.")
            if self.wapsi_env.lower() != "development":
                raise ValueError(
                    f"WHATSAPP_AUTH_MODE=dashboard_sandbox requires WAPSI_ENV=development, got: '{self.wapsi_env}'."
                )
            if self.razorpay_mode.lower() != "test":
                raise ValueError(
                    f"WHATSAPP_AUTH_MODE=dashboard_sandbox requires RAZORPAY_MODE=test, got: '{self.razorpay_mode}'."
                )

            # Fail closed: must not silently fall back to WHATSAPP_ACCESS_TOKEN
            if not self.whatsapp_diagnostic_token or not self.whatsapp_diagnostic_token.get_secret_value().strip():
                raise ValueError(
                    "WHATSAPP_AUTH_MODE=dashboard_sandbox requires WHATSAPP_DIAGNOSTIC_TOKEN to be configured. "
                    "Silent fallback to WHATSAPP_ACCESS_TOKEN is strictly prohibited."
                )
            return self.whatsapp_diagnostic_token.get_secret_value().strip()
        elif mode == "system_user":
            if self.whatsapp_access_token and self.whatsapp_access_token.get_secret_value().strip():
                return self.whatsapp_access_token.get_secret_value().strip()
            if self.wapsi_env.lower() == "production":
                raise ValueError("WHATSAPP_ACCESS_TOKEN (permanent system-user token) is required in production mode.")
            return None
        else:
            raise ValueError(
                f"Invalid WHATSAPP_AUTH_MODE: '{self.whatsapp_auth_mode}'. Must be 'system_user' or 'dashboard_sandbox'."
            )

    def get_whatsapp_verify_token_str(self) -> Optional[str]:
        if self.whatsapp_webhook_verify_token and self.whatsapp_webhook_verify_token.get_secret_value().strip():
            return self.whatsapp_webhook_verify_token.get_secret_value().strip()
        return None

    def get_meta_app_secret_bytes(self) -> bytes:
        if self.meta_app_secret and self.meta_app_secret.get_secret_value().strip():
            return self.meta_app_secret.get_secret_value().strip().encode("utf-8")
        raise ValueError("META_APP_SECRET is not configured.")

    @property
    def has_groq_configured(self) -> bool:
        return bool(self.groq_api_key and self.groq_api_key.get_secret_value().strip())

    @property
    def has_gemini_configured(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_api_key.get_secret_value().strip())

    @property
    def has_ollama_configured(self) -> bool:
        return bool(self.ollama_base_url and self.ollama_base_url.strip())

    @property
    def is_production(self) -> bool:
        """Returns True if WAPSI is configured in production environment."""
        return (self.wapsi_env or "").strip().lower() == "production"

    def __repr__(self) -> str:
        return (
            f"WapsiSettings(env='{self.wapsi_env}', mode='{self.razorpay_mode}', "
            f"key_id='{self.masked_key_id}', has_secret={self.has_key_secret}, "
            f"wa_auth_mode='{self.whatsapp_auth_mode}', "
            f"models_dir='{self.models_dir}')"
        )

    def __str__(self) -> str:
        return self.__repr__()


# Global singleton instance
_settings_instance: Optional[WapsiSettings] = None


def get_settings() -> WapsiSettings:
    """Returns the cached singleton WapsiSettings instance."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = WapsiSettings()
    return _settings_instance

