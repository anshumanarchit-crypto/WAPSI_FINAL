# WAPSI — PHASE 7 GATE 2: PRODUCTION CONFIGURATION & CREDENTIAL SECURITY REPORT
**Enforcement of Fail-Closed Production Environment Validation and Secret Protection**

- **Date / Timestamp:** 2026-11-03T14:30:00+05:30 / 2026-11-03 09:00:00 UTC
- **Gate:** Gate 2 (Production Configuration & Credential Security)
- **Author Roles:** Principal Security Engineer, Senior Python Backend Engineer, Application Security Architect
- **Status:** **GATE 2 ACCEPTED & VERIFIED (182 / 182 PASSED, 100% PASS RATE)**
- **Historical Regression Suite:** **163 / 163 PASSED, 0 FAILURES, 2 WARNINGS**
- **New Gate 2 Security Test Suite:** **19 / 19 PASSED, 0 FAILURES, 0 WARNINGS**
- **Protected Live Target Job:** `5a6587ab-2601-4017-b396-48e3d2fc2fda` (State: `SENT`, zero mutations)

---

## 1. Existing Security Architecture

Prior to Gate 2, WAPSI utilized a centralized configuration abstraction implemented in `wapsi/core/config.py` via Pydantic v2's `BaseSettings` (`WapsiSettings`). Key properties of this architecture included:
- **Environment and Mode Routing:** Configured through `WAPSI_ENV` (defaults to `"development"`) and `RAZORPAY_MODE` (defaults to `"test"`).
- **Secret Redaction:** Key credentials such as `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_DIAGNOSTIC_TOKEN`, and `META_APP_SECRET` were typed as `pydantic.SecretStr`, ensuring redaction in standard string formatting (`"**********"`).
- **Windows User Registry Fallbacks:** `_get_windows_user_env()` provided fallbacks for Razorpay credentials from `HKEY_CURRENT_USER\Environment`.
- **Sandbox Token Routing:** `WHATSAPP_AUTH_MODE` routed between permanent system user tokens (`"system_user"`) and short-lived dashboard tokens (`"dashboard_sandbox"`).

### Identified Architectural Vulnerabilities Prior to Gate 2:
1. **Silent Fallback from Windows Registry in Production:** If `WAPSI_ENV=production` was instantiated without explicit credentials, `populate_windows_env_fallbacks` would query Windows user registry and inject development/test credentials (`rzp_test_...`).
2. **Permissive Production Mode:** `WapsiSettings` allowed `WAPSI_ENV=production` with `RAZORPAY_MODE=test` to be initialized without raising an immediate initialization error if `razorpay_key_id` had a test prefix.
3. **Incomplete Production Meta Secret Enforcement:** Missing or empty `META_APP_SECRET` did not halt `WapsiSettings` initialization, deferring failure until runtime webhook signature verification.
4. **Permissive Empty String Handling:** Values consisting solely of whitespace or empty strings `""` were not uniformly validated for non-emptiness across all production credential fields.

---

## 2. Configuration Validation Changes

In `wapsi/core/config.py`, the validation pipeline was significantly enhanced with fail-closed security guards:

### 2.1 Prevention of Silent Windows Registry Fallback in Production
In `populate_windows_env_fallbacks`, an explicit environment check was introduced before querying Windows registry:
```python
env = values.get("wapsi_env") or values.get("WAPSI_ENV") or os.environ.get("WAPSI_ENV", "development")
if str(env).strip().lower() == "production":
    return values
```
This guarantees that production settings never pull test or development secrets from local workstation registry keys.

### 2.2 Field-Level Validation on `wapsi_env`, `razorpay_mode`, and `whatsapp_auth_mode`
- `validate_wapsi_env`: Rejects empty or whitespace-only environment strings.
- `validate_mode`: Validates mode is strictly `"test"` or `"live"`. When `wapsi_env == "production"`, immediately rejects any mode other than `"live"` (`RAZORPAY_MODE must be 'live' in production mode`).
- `validate_key_prefix`: Enforces that in live mode or production, `RAZORPAY_KEY_ID` must start with `"rzp_live_"`. Rejects live keys in test mode and test keys in live mode.
- `validate_wa_mode`: Enforces that `WHATSAPP_AUTH_MODE` must be non-empty and one of `{"system_user", "dashboard_sandbox"}`.

### 2.3 Strict Fail-Closed Model Validator (`validate_production_safety`)
When `WAPSI_ENV=production`:
1. `RAZORPAY_MODE` must be `"live"`.
2. `RAZORPAY_KEY_ID` must be configured, non-empty, and prefixed with `rzp_live_`.
3. `RAZORPAY_KEY_SECRET` must be configured and contain non-empty secret value.
4. `RAZORPAY_WEBHOOK_SECRET` must be configured and contain non-empty secret value.
5. `WHATSAPP_AUTH_MODE` must be `"system_user"` (rejection of `"dashboard_sandbox"`).
6. `WHATSAPP_ACCESS_TOKEN` must be configured and contain non-empty permanent system-user token.
7. `META_APP_SECRET` must be configured and contain non-empty application secret.

Failure of any condition immediately raises a `ValidationError` / `ValueError`, preventing platform instantiation.

### 2.4 Token Getter Hardening
- `get_whatsapp_token_str()`: Rejects `dashboard_sandbox` in production; requires non-empty `WHATSAPP_ACCESS_TOKEN` in production.
- `get_meta_app_secret_bytes()`: Enforces non-empty secret with `.strip()`.
- `get_webhook_secret_bytes()`: Enforces non-empty secret with `.strip()`, rejects fallback demo secrets in production.
- `get_valid_api_keys()`: Prohibits demo test keys (`rzp_live_wapsi_key_demo`, `rzp_test_wapsi_key_2026`) when `WAPSI_ENV=production`.
- `is_production`: Added boolean property `s.wapsi_env.strip().lower() == "production"`.
- `__str__` and `__repr__`: Guaranteed to expose zero credentials.

---

## 3. Credential Requirements

When `WAPSI_ENV=production`, the following configuration specification is strictly required:

| Field Name | Environment Variable | Required Value / Format | Allowed in Production |
|:---|:---|:---|:---:|
| `wapsi_env` | `WAPSI_ENV` | `production` | **Yes** |
| `razorpay_mode` | `RAZORPAY_MODE` | `live` | **Yes** (`test` strictly rejected) |
| `razorpay_key_id` | `RAZORPAY_KEY_ID` | `rzp_live_<alphanumeric>` | **Yes** |
| `razorpay_key_secret` | `RAZORPAY_KEY_SECRET` | Non-empty live API key secret | **Yes** |
| `razorpay_webhook_secret` | `RAZORPAY_WEBHOOK_SECRET` | Non-empty live webhook HMAC secret | **Yes** |
| `whatsapp_auth_mode` | `WHATSAPP_AUTH_MODE` | `system_user` | **Yes** (`dashboard_sandbox` rejected) |
| `whatsapp_access_token` | `WHATSAPP_ACCESS_TOKEN` | Non-empty permanent Meta System User token | **Yes** |
| `whatsapp_diagnostic_token` | `WHATSAPP_DIAGNOSTIC_TOKEN` | Sandbox diagnostic token | **Rejected** (routing prohibited) |
| `meta_app_secret` | `META_APP_SECRET` | Non-empty Meta App Secret | **Yes** |
| `wapsi_api_key` | `WAPSI_API_KEY` | Optional production API key (demo keys disabled) | **Yes** |

---

## 4. Fail-Closed Behavior

1. **Missing Razorpay Live Mode:**
   If `WAPSI_ENV=production` and `RAZORPAY_MODE` is omitted or set to `test`:
   `ValueError: RAZORPAY_MODE must be 'live' in production mode, got: 'test'. Test mode and sandbox configurations are strictly prohibited in production.`
2. **Missing or Sandbox WhatsApp Mode:**
   If `WAPSI_ENV=production` and `WHATSAPP_AUTH_MODE=dashboard_sandbox`:
   `ValueError: WHATSAPP_AUTH_MODE=dashboard_sandbox is strictly prohibited in production/live mode. Only system_user mode is permitted.`
3. **Missing System User Token:**
   If `WAPSI_ENV=production` and `WHATSAPP_ACCESS_TOKEN` is `None` or `SecretStr("")`:
   `ValueError: WHATSAPP_ACCESS_TOKEN (permanent system-user token) is required in production mode.`
4. **Missing Meta App Secret:**
   If `WAPSI_ENV=production` and `META_APP_SECRET` is `None` or `SecretStr("")`:
   `ValueError: META_APP_SECRET is required in production mode.`
5. **No Downgrade or Silent Fallback:**
   Invalid production configurations raise `ValidationError` at startup. The system never reverts to development environment, test modes, or hardcoded demo credentials.

---

## 5. Security Test Matrix and Results

All 19 test cases covering Gate 2 requirements and hardened edge cases were implemented in `tests/test_phase7_production_readiness.py`:

```powershell
.venv\Scripts\python -m pytest tests/test_phase7_production_readiness.py -v
```

| # | Test Name | Target Behavior | Result | Duration |
|:---:|:---|:---|:---:|:---:|
| 1 | `test_1_existing_development_configuration_continues_working` | Development mode continues operating normally with test keys | **PASSED** | 0.05s |
| 2 | `test_2_existing_test_configuration_continues_working` | Test mode operates without production constraints | **PASSED** | 0.02s |
| 3 | `test_3_fully_populated_production_configuration_passes_validation` | Fully populated production settings pass validation | **PASSED** | 0.03s |
| 4 | `test_4_missing_razorpay_live_mode_rejected_in_production` | Omission of live mode in production fails closed | **PASSED** | 0.02s |
| 5 | `test_5_razorpay_test_mode_rejected_in_production` | Explicit test mode in production fails closed | **PASSED** | 0.02s |
| 6 | `test_6_missing_whatsapp_authentication_mode_rejected` | Empty WhatsApp auth mode is rejected | **PASSED** | 0.02s |
| 7 | `test_7_dashboard_sandbox_authentication_rejected_in_production` | Dashboard sandbox auth mode is rejected in production | **PASSED** | 0.03s |
| 8 | `test_8_missing_whatsapp_system_user_token_rejected_in_production` | Missing permanent system user token is rejected | **PASSED** | 0.02s |
| 9 | `test_9_missing_meta_app_secret_rejected_in_production` | Missing Meta app secret is rejected in production | **PASSED** | 0.02s |
| 10 | `test_10_empty_credentials_rejected` | Empty/whitespace credentials rejected across all fields | **PASSED** | 0.04s |
| 11 | `test_11_invalid_environment_combinations_fail_closed` | Invalid cross-env combinations fail closed | **PASSED** | 0.03s |
| 12 | `test_12_credentials_not_exposed_through_configuration_representations` | Zero secret exposure in `str()`, `repr()`, masked key id | **PASSED** | 0.02s |
| 13 | `test_13_credentials_not_exposed_through_error_messages` | Zero secret values leaked in exception messages | **PASSED** | 0.02s |
| 14 | `test_14_invalid_production_configuration_does_not_silently_downgrade` | Prevents fallback to demo keys and dev settings | **PASSED** | 0.03s |
| 15 | `test_15_existing_sandbox_token_routing_unchanged_outside_production` | Sandbox token routing functions in development | **PASSED** | 0.03s |
| 16 | `test_16_existing_authorization_and_tenant_isolation_remains_intact` | Opt-out registry and auth gates remain intact | **PASSED** | 0.03s |
| 17 | `test_17_duplicate_diagnostic_token_as_access_token_rejected_in_production` | Sandbox token copy-pasted as system user token fails closed | **PASSED** | 0.02s |
| 18 | `test_18_credential_getters_strip_whitespace_and_newlines` | Credential getters strip whitespace and newlines from SecretStr | **PASSED** | 0.03s |
| 19 | `test_19_case_insensitive_production_env_blocks_windows_fallback` | Windows registry bypass enforced under case-insensitive WAPSI_ENV | **PASSED** | 0.02s |

**Gate 2 Test Suite Summary:** **19 passed in 0.58s (100% Pass Rate)**

---

## 6. Files Created and Modified

1. **`wapsi/core/config.py` (Modified):**
   - Added Windows registry fallback bypass when `WAPSI_ENV=production` with case-insensitive key resolution.
   - Added field validators for `wapsi_env`, `razorpay_mode`, and `whatsapp_auth_mode`.
   - Enhanced `validate_production_safety` model validator for fail-closed production checks, including rejection of identical dashboard sandbox tokens configured as system user tokens.
   - Enhanced `get_whatsapp_token_str()`, `get_meta_app_secret_bytes()`, and `get_webhook_secret_bytes()` with whitespace stripping and fail-closed checks.
   - Added `is_production` property and explicit `__str__()` method.
2. **`tests/test_phase7_production_readiness.py` (Created):**
   - Implemented 19 test cases covering valid configurations, invalid production configurations, credential masking, error message security, non-downgrade behavior, getter whitespace trimming, duplicate sandbox token rejection, and case-insensitive fallback protection.
3. **`docs/PHASE_7_GATE_2_PRODUCTION_SECURITY_REPORT.md` (Created):**
   - This comprehensive security report.

---

## 7. Historical Regression Results

The full 14-suite historical regression baseline was verified:

```powershell
.venv\Scripts\python -m pytest tests/test_phase6_stage2c_operator_approval_preparation.py tests/test_phase6_stage2d1_tenant_isolation_and_operator_auth.py tests/test_phase6_stage2d2_fail_closed_tenant_context.py tests/test_phase6_stage2d_exact_job_isolation.py tests/test_phase6_stage2e3_direct_payload.py tests/test_phase6_stage3_recovery_lifecycle.py tests/test_phase6_stage4_production_hardening.py tests/test_frontend_adapter.py tests/test_phase6_stage2b_sandbox_token_routing.py tests/test_phase6_stage2a_authorization.py tests/test_phase6_sandbox_execution.py tests/test_phase6_webhook_authentication_and_ingestion.py tests/test_phase3_recovery_workflow.py tests/test_phase3_1_postgres_workflow.py -q
```
- **Exit Code:** 0
- **Summary:** **163 passed, 2 warnings in 44.11s**

### Unified Regression Run (15 Test Suites — 182 Tests Total)
```powershell
.venv\Scripts\python -m pytest tests/test_phase7_production_readiness.py tests/test_phase6_stage2c_operator_approval_preparation.py tests/test_phase6_stage2d1_tenant_isolation_and_operator_auth.py tests/test_phase6_stage2d2_fail_closed_tenant_context.py tests/test_phase6_stage2d_exact_job_isolation.py tests/test_phase6_stage2e3_direct_payload.py tests/test_phase6_stage3_recovery_lifecycle.py tests/test_phase6_stage4_production_hardening.py tests/test_frontend_adapter.py tests/test_phase6_stage2b_sandbox_token_routing.py tests/test_phase6_stage2a_authorization.py tests/test_phase6_sandbox_execution.py tests/test_phase6_webhook_authentication_and_ingestion.py tests/test_phase3_recovery_workflow.py tests/test_phase3_1_postgres_workflow.py -q
```
- **Exit Code:** 0
- **Summary:** **182 passed, 2 warnings in 45.08s**
- **Regressions:** Exactly 0.

---

## 8. Git Integrity Results

1. **Git Diff Check Investigation:**
   - Command: `git diff --check wapsi/core/config.py tests/test_phase7_production_readiness.py`
   - Output: Exit code 0 (clean, zero whitespace errors in Gate 2 files).
   - Pre-existing whitespace warnings in working directory (`wapsi/api/schemas.py:252` new blank line at EOF, `wapsi/db/repository.py:465` trailing whitespace) were identified as pre-dating Gate 1 and preserved untouched in accordance with operational safety guidelines.
2. **Branch Status:**
   - Active branch: `phase4/whatsapp-inbound-integration`
   - All modified and untracked files preserved without deletion or destructive resetting.
   - Zero commits, staging, or push actions performed.

---

## 9. Secret Exposure Verification

- `SecretStr` prevents token disclosure across logs, console output, `str(settings)`, and `repr(settings)`.
- Synthetic placeholder credentials (`synthetic_live_...`, `synthetic_meta_...`) were used exclusively in all new tests. No real production credentials were used, requested, or stored.
- Error messages when rejecting invalid configurations never reflect raw token values.

---

## 10. Operational Safety Verification

- `WAPSI_ENV` remains `development`.
- `RAZORPAY_MODE` remains `test`.
- Real `.env` file was **NOT** modified.
- Production mode was **NOT** activated in the running application.
- No live Razorpay API calls or real WhatsApp messages were dispatched.
- Zero database migrations executed.
- Live target job `5a6587ab-2601-4017-b396-48e3d2fc2fda` verified read-only:
  - `status`: `SENT`
  - `retry_count`: `1`
  - `approved_by_operator_id`: `operator_arpit`
  - `approval_snapshot_hash`: `dd0bcf49b2fa5204052b24e401c680d2ebf6d125aedbae88434b96fc8214e8cd`
  - **Mutations during Gate 2:** Exactly 0.

---

## 11. Remaining Risks

1. **Live Meta System User Token Lifecycle:** Permanent tokens must be provisioned through Meta Business Manager with proper granular scopes (`whatsapp_business_messaging`, `whatsapp_business_management`) before actual cutover.
2. **Template Pre-Registration:** Outside the 24-hour service window, outbound messages require pre-approved Meta templates (addressed in Gate 3).

---

## 12. Gate 2 Acceptance Checklist

- [x] Strict production environment validation implemented in `wapsi/core/config.py`.
- [x] `WAPSI_ENV=production` requires `RAZORPAY_MODE=live`.
- [x] `WAPSI_ENV=production` requires `WHATSAPP_AUTH_MODE=system_user`.
- [x] `WAPSI_ENV=production` requires valid, non-empty permanent WhatsApp system user token.
- [x] `WAPSI_ENV=production` requires valid, non-empty Meta application secret.
- [x] Dashboard sandbox tokens and routing are strictly rejected in production.
- [x] Fail-closed behavior on missing or empty configuration verified.
- [x] Windows user environment registry test key bypass enforced in production.
- [x] Security test matrix (`tests/test_phase7_production_readiness.py`, 19 tests) passed (100%).
- [x] Historical regression suite (14 suites, 163 tests) passed (100%).
- [x] Live target job `5a6587ab-2601-4017-b396-48e3d2fc2fda` verified intact (0 mutations).
- [x] Comprehensive report `docs/PHASE_7_GATE_2_PRODUCTION_SECURITY_REPORT.md` generated.
- [x] Execution stopped before Gate 3 awaiting operator approval.
