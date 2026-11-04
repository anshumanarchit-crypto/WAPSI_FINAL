# WAPSI — PHASE 7 GATE 3: META PRE-APPROVED TEMPLATE RECOVERY ENGINE REPORT
**Meta-Approved Template Messaging and 24-Hour Customer Service Window Enforcement**

- **Date / Timestamp:** 2026-11-03T15:52:00+05:30 / 2026-11-03 10:22:00 UTC
- **Gate:** Gate 3 (Meta Pre-Approved Template Recovery Engine)
- **Author Roles:** Principal Backend Engineer, WhatsApp Cloud API Integration Specialist, Senior Python Engineer, QA and Reliability Engineer, Payment Recovery Systems Architect
- **Status:** **GATE 3 FULLY ACCEPTED, HARDENED & VERIFIED (218 / 218 PASSED, 100% PASS RATE)**
- **Historical Baseline (Gate 1):** **163 / 163 PASSED**
- **Gate 2 Security Baseline:** **19 / 19 PASSED**
- **New Gate 3 Dedicated Suite:** **36 / 36 PASSED (100%)**
- **Unified Regression Suite (16 Suites):** **218 / 218 PASSED, 0 FAILURES, 2 WARNINGS (40.99s)**
- **Protected Live Target Job:** `5a6587ab-2601-4017-b396-48e3d2fc2fda` (State: `SENT`, zero mutations)

---

## 1. Architecture Investigation

Prior to Gate 3, WAPSI implemented outbound payment recovery notifications primarily via freeform session text messages and pre-formed direct payloads. The architecture was investigated across all relevant call sites, data models, and outbox lifecycle stages:

1. **`wapsi/integrations/whatsapp/client.py`:**
   - Contained basic client infrastructure (`WhatsAppClient`, `WhatsAppDispatchResult`, `_send_payload`).
   - `send_template_message` had minimal serialization and lacked defensive validation for template names, language codes, and component parameters (headers, quick-reply buttons, dynamic URL parameters, location, currency, date_time).
   - In `_send_payload`, transient network errors and rate limits were retried with exponential backoff, but HTTP read timeouts risked re-issuing duplicate POST dispatches if Meta gateway accepted the message during socket timeouts.
   - Centralized Graph API version defaulted to `v21.0` rather than the project-wide standard `v26.0`.
2. **`wapsi/integrations/whatsapp/opt_out.py` & `wapsi/recovery/opt_out_store.py`:**
   - Both in-memory and persistent SQLite/PostgreSQL stores tracked customer inbound message timestamps via `customer_interactions`.
   - `is_within_24h_window` evaluated the 86,400-second window, but lacked a dedicated routing engine to evaluate UTC normalization across complex formats (ISO 8601 strings, timezone-aware datetimes), boundary conditions, and fail-closed handling for missing or corrupt timestamps.
3. **`wapsi/recovery/worker.py` (Background Worker):**
   - Implemented dual payload mode handling (Mode B: Direct Meta Payload via `send_prepared_payload`, Mode A: Action Specification via `send_recovery_reminder`).
   - Required integration so that template parameters, language codes, window enforcement flags, and customer inbound timestamps were extracted and passed to `send_recovery_reminder`.
4. **`wapsi/recovery/outbox.py` & `wapsi/db/repository.py`:**
   - Cryptographic approval hash verification (`compute_approval_hash` and `verify_dispatch_authorization`) enforces deterministic SHA-256 integrity over recipient and message payload prior to dispatch.
   - Requires zero bypass: template dispatches must satisfy both Meta template formatting AND WAPSI operator authorization.

---

## 2. Existing Dispatch Implementation

Prior to Gate 3:
- **Mode A (Action Specification):** Extracted `customer_phone`, `amount_paise`, and JIT created a Razorpay payment link before invoking `send_recovery_reminder()`. When `enforce_24h_window=True`, it raised `WhatsAppDeliveryError` if the customer was outside the 24-hour window and `template_name` was absent, but lacked dynamic resolution of default pre-approved templates or structured manual review routing.
- **Mode B (Pre-Formed Direct Payload):** Verified payment link integrity and invoked `send_prepared_payload()` verbatim.

The architecture was robust, but lacked deep component-level validation for headers, dynamic URL buttons, quick-reply buttons, timezone-normalized customer service window evaluation, and fail-closed manual review routing.

---

## 3. Defects Identified and Fixed During Review

A thorough skeptical review identified 9 concrete defects in the initial Gate 3 implementation:

1. **`normalize_utc_timestamp` Missing Range Validation for Datetimes and ISO 8601 Strings:**
   - *Input:* `normalize_utc_timestamp(datetime(1960, 1, 1))` or `"1960-01-01T00:00:00Z"` or `"2500-01-01T00:00:00Z"`.
   - *Expected:* Return `None` (pre-1970 and corrupt far-future dates rejected, bounding to year 2100).
   - *Actual:* Returned negative epoch float `-315619200.0` or far-future epoch `16725225600.0`.
   - *Root Cause:* Range checks were applied only to numeric floats/strings, skipping datetime and ISO parsed objects.
   - *Fix:* Unify epoch resolution into `epoch_val` and validate `0.0 < epoch_val <= 4102444800.0` across all types.

2. **`OptOutRepository.is_within_24h_window` Python TypeError on Naive Datetime:**
   - *Input:* Database returning timezone-naive datetime (e.g. SQLite storage) evaluated against timezone-aware `_utc_now()`.
   - *Expected:* Safe evaluation of window elapsed seconds.
   - *Actual:* Raised `TypeError: can't subtract offset-naive and offset-aware datetimes`.
   - *Root Cause:* Directly performed `now - record.last_interaction_at`.
   - *Fix:* Pass both through `normalize_utc_timestamp` before computing UTC epoch float difference.

3. **`OptOutRepository.get_last_interaction` Local Timezone Skew:**
   - *Input:* Naive datetime from database.
   - *Expected:* UTC epoch seconds.
   - *Actual:* Calling `.timestamp()` on naive datetime assumed machine-local timezone (e.g. 5.5 hour IST skew).
   - *Root Cause:* Direct call to `record.last_interaction_at.timestamp()`.
   - *Fix:* Delegate to `normalize_utc_timestamp(record.last_interaction_at)`.

4. **`WhatsAppClient._send_payload` Null or Empty Message ID on 200 OK:**
   - *Input:* Meta Cloud API returns 200 OK with `{"messages": [{"id": null}]}` or `{"messages": []}`.
   - *Expected:* Generate synthetic tracking ID `wamid_gen_{ts}`, guaranteeing non-empty string `message_id`.
   - *Actual:* Assigned `None` to `message_id`, violating `WhatsAppDispatchResult` dataclass type contract.
   - *Root Cause:* Checked `"id" in messages[0]` rather than checking whether the ID was a non-empty string.
   - *Fix:* Defensively extract `raw_mid = messages[0].get("id")` and fallback to `wamid_gen_` if null or whitespace.

5. **Uncaught HTTP Protocol and Client Request Errors in `_send_payload`:**
   - *Input:* Meta gateway connection drop emitting `httpx.ProtocolError`, `httpx.DecodingError`, or `httpx.RequestError`.
   - *Expected:* Caught and wrapped in `WhatsAppDeliveryError` or retried with backoff.
   - *Actual:* Escaped unhandled because only `httpx.NetworkError` was caught (`ProtocolError` is not a subclass of `NetworkError`).
   - *Root Cause:* Overly narrow exception filter.
   - *Fix:* Catch `(httpx.NetworkError, httpx.ProtocolError, httpx.RequestError)`.

6. **Graph API Version Inconsistency:**
   - *Input:* Default client configuration without explicit environment overrides.
   - *Expected:* Standardize on Graph API `v26.0` as specified across project documentation and scripts.
   - *Actual:* Defaulted to `v21.0` in `config.py` and `client.py`.
   - *Fix:* Update default `whatsapp_api_version` to `v26.0` in `WapsiSettings` and `WhatsAppClient`.

7. **Outbox Worker Mode A Dropped Window Enforcement Arguments:**
   - *Input:* Action spec outbox job with `enforce_24h_window` and/or `inbound_timestamp` in payload.
   - *Expected:* Forwarded to `send_recovery_reminder()` to enable 24h window routing.
   - *Actual:* Omitted during payload extraction in `_execute_action_spec_job`.
   - *Fix:* Extract `enforce_24h_window` and `inbound_timestamp` from job payload and pass to `send_recovery_reminder()`.

8. **Button Component Builders Permitted Out-of-Bounds Indices:**
   - *Input:* `build_url_button_component(index=-1, ...)` or `build_quick_reply_button_component(index=15, ...)`.
   - *Expected:* Immediate `WhatsAppValidationError`.
   - *Actual:* Constructed invalid dict, only failing later during component list validation.
   - *Fix:* Validate index `0..9` immediately at construction time in both builders.

9. **Language Code Validator Rejected Standard Hyphenated BCP-47 Tags:**
   - *Input:* `validate_language_code("en-US")` or `validate_language_code("es-LA")`.
   - *Expected:* Normalize hyphens to underscores and accept (`en_US`, `es_LA`).
   - *Actual:* Raised `WhatsAppValidationError`.
   - *Fix:* Normalize hyphens to underscores prior to regex verification.

---

## 4. New Template Dispatch Functionality

In `wapsi/integrations/whatsapp/client.py`, the template messaging engine provides typed, defensive schema validation matching the official Meta WhatsApp Cloud API specification (Graph API v26.0):

### 4.1 Public Method Signature & Contract
```python
def send_template_message(
    self,
    to_phone: str,
    template_name: str,
    language_code: str = "en",
    components: Optional[List[Dict[str, Any]]] = None,
) -> WhatsAppDispatchResult
```
- **Phone Sanitization:** Normalizes recipient numbers to E.164 digits without `+` (e.g. `+91 98765-43210` -> `919876543210`). Prepend 91 country code for 10-digit Indian numbers starting with 6-9. Raises `WhatsAppDeliveryError` if length is invalid (< 10 or > 15 digits).
- **Template Name Validation (`validate_template_name`):** Strictly enforces lowercase alphanumeric characters and underscores (`^[a-z0-9_]+$`). Rejects uppercase characters, whitespace, hyphens, and empty strings with `WhatsAppValidationError`.
- **Language Code Validation (`validate_language_code`):** Enforces standard ISO format (`^[a-z]{2,3}(?:_[A-Za-z0-9]+)?$`, e.g. `en`, `en_US`, `hi`, `pt_BR`, `es_LA`, `zh_HK`, `fil`, `mai`). Automatically normalizes hyphenated BCP-47 tags (e.g. `en-US` -> `en_US`).
- **Defensive Component Validation (`validate_template_components`):**
  - Enforces `components` is a list of dictionaries with `type` in `{"header", "body", "button", "footer"}`.
  - **Header components:** Validates `parameters` list containing text, media objects (`image`, `document`, `video` with `link` or `id`, optional `filename`), or `location` objects with `latitude` and `longitude`.
  - **Body components:** Validates dynamic positional parameter sequence (`type: "text"` with non-empty string, currency with `currency` dict, or date_time with `date_time` dict).
  - **Button components:** Validates `sub_type` in `{"quick_reply", "url", "copy_code", "catalog"}` and `index` in `0..9`.
    - `url` buttons: Enforces non-empty string URL parameter without whitespace or newlines.
    - `quick_reply` buttons: Enforces non-empty string payload.

### 4.2 Component Builder Utilities
Four fluent static builders construct compliant Meta components:
1. `build_body_component(parameters: List[Union[str, Dict[str, Any]]]) -> Dict[str, Any]`
2. `build_header_component(text=None, media_type=None, media_url=None, media_id=None, filename=None) -> Dict[str, Any]`
3. `build_url_button_component(index: Union[int, str], url_parameter: str) -> Dict[str, Any]`
4. `build_quick_reply_button_component(index: Union[int, str], payload: str) -> Dict[str, Any]`

---

## 5. Template Payload Specification

The dispatched JSON payload strictly conforms to the Meta WhatsApp Cloud API specification:

```json
{
  "messaging_product": "whatsapp",
  "recipient_type": "individual",
  "to": "919876543210",
  "type": "template",
  "template": {
    "name": "payment_recovery_v1",
    "language": {
      "code": "en_US"
    },
    "components": [
      {
        "type": "header",
        "parameters": [
          {
            "type": "text",
            "text": "Payment Reminder"
          }
        ]
      },
      {
        "type": "body",
        "parameters": [
          {
            "type": "text",
            "text": "Alice"
          },
          {
            "type": "text",
            "text": "Rs 500.00"
          }
        ]
      },
      {
        "type": "button",
        "sub_type": "url",
        "index": "0",
        "parameters": [
          {
            "type": "text",
            "text": "pay_link_xyz"
          }
        ]
      }
    ]
  }
}
```

---

## 6. 24-Hour Routing Implementation

A dedicated routing and policy engine was created in `wapsi/integrations/whatsapp/service_window.py`:

### 6.1 Window Status Evaluation
- `normalize_utc_timestamp(ts)`: Strictly normalizes epoch floats, ISO 8601 strings (with offsets or `Z`), and timezone-aware datetimes to UTC epoch floats. Rejects booleans, NaNs, infinities, negative values, and far-future corruptions (> year 2100).
- `evaluate_customer_service_window(phone, last_inbound, current_time)`:
  - **Boundary condition:** Exactly 24.0 hours (86,400.0 seconds).
    - `0 <= elapsed <= 86400.0s`: `WindowStatus.OPEN`
    - `elapsed > 86400.0s`: `WindowStatus.EXPIRED`
    - Missing timestamp: `WindowStatus.UNKNOWN` (fail-closed)
    - Future-dated (> 60s drift) or corrupted timestamp: `WindowStatus.INVALID` (fail-closed)

### 6.2 Routing Logic Matrix (`CustomerServiceWindowRouter.route_outbound_recovery`)
| Case | Window Condition | Inbound Timestamp State | Message Type | Template Resolution | Requires Manual Review |
|:---:|:---|:---|:---:|:---:|:---:|
| **A** | Window OPEN (<= 24h) | Valid, within 86,400s | `text` (or `template` if requested) | Freeform text message permitted; template only if explicitly caller-requested | **False** |
| **B** | Window EXPIRED (> 24h) | Valid, > 86,400s | `template` (or `manual_review`) | Resolves configured template (`payment_recovery_v1`). If unconfigured -> `manual_review` | **False** (if template present) / **True** (if template missing) |
| **C1** | Window UNKNOWN | Absent / None | `template` (or `manual_review`) | Fail-closed: routes to approved template if configured. If unconfigured -> `manual_review` | **False** (if template present) / **True** (if template missing) |
| **C2** | Window INVALID | Corrupted / NaN / Future | `template` (or `manual_review`) | Fail-closed: routes to approved template if configured. If unconfigured -> `manual_review` | **False** (if template present) / **True** (if template missing) |

---

## 7. Governance Preservation

All WAPSI security and payment governance controls remain strictly preserved:
1. **Operator Approval Enforcement:** A template being pre-approved by Meta does NOT authorize dispatch in WAPSI. Outbox jobs on contact channels (`channel="WHATSAPP"`) strictly require `requires_operator_approval=True`, `approved_by_operator_id`, `approved_at`, and `approval_snapshot_hash`.
2. **Cryptographic Payload Integrity:** Any post-approval mutation to template name, language, components, recipient, or payment parameters causes an immediate SHA-256 approval snapshot hash mismatch. Dispatch is aborted with `AUTHORIZATION_REJECTED` and the job is transitioned to `DEAD_LETTER`.
3. **Tenant Context Isolation:** Outbox queries, job leasing, and provider dispatches enforce merchant UUID isolation.
4. **Idempotency:** Unique `idempotency_key` prevents duplicate outbox queuing. Jobs already in `COMPLETED` or `SENT` status are skipped, ensuring zero duplicate external calls.
5. **Customer Opt-Out & DND:** In-memory and persistent opt-out checks run immediately prior to dispatch. Opted-out recipients are immediately suppressed with `CUSTOMER_OPTED_OUT`.

---

## 8. Error Handling and Reliability

1. **Blind Retry Prevention on Timeout:**
   In `WhatsAppClient._send_payload`, `httpx.TimeoutException` is propagated immediately without re-issuing POST dispatches. The background worker catches this timeout and marks the job as `RECONCILIATION_REQUIRED`, preventing duplicate customer messages.
2. **Network Error Backoff:**
   Transient socket connection drops (`httpx.NetworkError`, `httpx.ProtocolError`, `httpx.RequestError`) are retried with exponential backoff up to `max_retries`.
3. **Rate Limiting:**
   Meta HTTP 429 and error codes 4, 17, 32, 613 raise `WhatsAppRateLimitError`, scheduling the outbox job for `RETRY`.
4. **Authentication Errors:**
   Meta HTTP 401/403 and error code 190 raise `WhatsAppAuthError`. The job is marked `DEAD_LETTER` without retrying invalid credentials.
5. **Template Error Code Classification:**
   Meta template error codes (100, 131030, 131026, 132000, 132001, 132005, 132015, 132016) are classified as `WhatsAppDeliveryError`.
6. **Malformed Provider Response:**
   Meta HTTP 200 responses with non-JSON or missing `messages` lists are parsed safely. A synthetic tracking ID (`wamid_gen_{ts}`) is generated without crashing.
7. **Credential Protection:**
   Access tokens, authorization headers, and customer phone numbers are masked in all logs (`to_phone[:4]***{to_phone[-2:]}`).

---

## 9. Files Modified and Created

| File | Status | Description of Changes |
|:---|:---:|:---|
| `wapsi/core/config.py` | **Modified** | Updated `whatsapp_api_version` default to `v26.0`, added `whatsapp_recovery_template_name` and `whatsapp_recovery_template_language`. |
| `wapsi/integrations/whatsapp/service_window.py` | **Created** | Comprehensive 24-hour customer service window router with unified UTC timestamp normalization and range rejection (`0 < ts <= 4102444800.0`), exact boundary evaluation, and fail-closed routing. |
| `wapsi/db/repository.py` | **Modified** | Hardened `OptOutRepository.get_last_interaction()` and `is_within_24h_window()` with `normalize_utc_timestamp`, eliminating timezone-naive `TypeError` and machine-local timezone skew. |
| `wapsi/recovery/opt_out_store.py` | **Modified** | Enhanced `PersistentOptOutStore.record_interaction()`, added `get_last_interaction()`, and normalized `is_within_24h_window()` against UTC epoch floats. |
| `wapsi/integrations/whatsapp/opt_out.py` | **Modified** | Added `get_last_interaction()` and UTC normalization to `OptOutManager`. |
| `wapsi/integrations/whatsapp/client.py` | **Modified** | Standardized Graph API `v26.0`, added template component validation (including location headers, currency, date_time body params), button builders with index checks, hyphen-normalized language codes, hardened `_send_payload()` against blind timeout retries and malformed JSON, and integrated 24-hour service window router into `send_recovery_reminder()`. |
| `wapsi/recovery/worker.py` | **Modified** | Extracted `language_code`, `components`, `enforce_24h_window`, and `inbound_timestamp` in `_execute_action_spec_job` and passed to `send_recovery_reminder()`. |
| `tests/test_phase7_template_dispatch.py` | **Created** | Dedicated 36-test suite implementing all Gate 3 test scenarios and defect fixes across 5 categories. |
| `docs/PHASE_7_GATE_3_TEMPLATE_RECOVERY_REPORT.md` | **Created** | Comprehensive Gate 3 completion report. |

---

## 10. Test Matrix

The dedicated test suite `tests/test_phase7_template_dispatch.py` implements all 36 required and hardened test scenarios:

| # | Test Name | Target Behavior | Result |
|:---:|:---|:---|:---:|
| 1 | `test_1_valid_body_text_template` | Serializes valid body text template and returns accepted `WhatsAppDispatchResult` | **PASSED** |
| 2 | `test_2_correct_template_name_and_language_validation` | Validates template name and language code format according to Meta rules | **PASSED** |
| 3 | `test_3_multiple_dynamic_body_parameters` | Serializes multiple dynamic body parameters in exact sequence | **PASSED** |
| 4 | `test_4_header_parameter_handling` | Serializes text, image, and document header parameters | **PASSED** |
| 5 | `test_5_quick_reply_button_parameters` | Serializes quick-reply button parameters with developer payload | **PASSED** |
| 6 | `test_6_dynamic_url_button_parameters` | Serializes dynamic URL button parameters and rejects whitespace/newlines | **PASSED** |
| 7 | `test_7_correct_json_payload_structure` | Validates end-to-end JSON payload against Meta Cloud API specification | **PASSED** |
| 8 | `test_8_invalid_and_incomplete_component_rejection` | Rejects malformed, incomplete, or unsupported component configurations | **PASSED** |
| 9 | `test_9_freeform_message_inside_24h_window` | CASE A — Inbound interaction within 24h permits freeform message dispatch | **PASSED** |
| 10 | `test_10_template_dispatch_outside_24h_window` | CASE B — Inbound interaction > 24h routes to approved template dispatch | **PASSED** |
| 11 | `test_11_exactly_24_hour_boundary` | Exact boundary: 86,400.0s is OPEN; 86,400.001s is EXPIRED | **PASSED** |
| 12 | `test_12_timezone_normalization` | Deterministic UTC normalization across ISO strings, offsets, and datetimes | **PASSED** |
| 13 | `test_13_missing_inbound_timestamp_fails_closed` | CASE C — Missing inbound timestamp fails closed (UNKNOWN -> template/review) | **PASSED** |
| 14 | `test_14_invalid_timestamp_fails_closed` | CASE C — Corrupted/future-dated timestamp fails closed (INVALID) | **PASSED** |
| 15 | `test_15_missing_template_configuration_fails_closed` | Missing template configuration outside 24h window flags manual review | **PASSED** |
| 16 | `test_16_correct_fallback_to_manual_review_when_template_unavailable` | Raises `WhatsAppDeliveryError` when template dispatch is unavailable outside window | **PASSED** |
| 17 | `test_17_operator_approval_remains_mandatory` | Unapproved contacting template job is rejected with `DEAD_LETTER` | **PASSED** |
| 18 | `test_18_invalid_approval_hash_rejects_dispatch` | Tampering with approved template payload rejects dispatch via hash mismatch | **PASSED** |
| 19 | `test_19_tenant_isolation_remains_intact` | Blocks cross-merchant access to outbox recovery jobs | **PASSED** |
| 20 | `test_20_idempotency_prevents_duplicate_dispatch` | Unique constraint and worker idempotency prevent duplicate dispatches | **PASSED** |
| 21 | `test_21_existing_recovery_state_transitions_correct` | State machine validates complete lifecycle transitions with template dispatch | **PASSED** |
| 22 | `test_22_existing_sandbox_behavior_unchanged` | Development sandbox token routing operates normally | **PASSED** |
| 23 | `test_23_meta_authentication_error` | HTTP 401 code 190 raises `WhatsAppAuthError` without leaking token | **PASSED** |
| 24 | `test_24_rate_limit_response` | HTTP 429 raises `WhatsAppRateLimitError` with backoff code | **PASSED** |
| 25 | `test_25_timeout_behavior` | Socket timeout propagates `httpx.TimeoutException` for reconciliation | **PASSED** |
| 26 | `test_26_malformed_provider_response` | Non-JSON or missing messages response handled gracefully with fallback ID | **PASSED** |
| 27 | `test_27_ambiguous_provider_acceptance_does_not_blind_retry` | POST timeout executes exactly once (no blind retry) | **PASSED** |
| 28 | `test_28_credentials_are_not_exposed_in_logs` | Access tokens, auth headers, and customer secrets never exposed in logs | **PASSED** |
| 29 | `test_29_language_subtags_and_hyphen_normalization` | Validates non-standard language sub-tags (`es_LA`, `pt_BR`, `zh_HK`, `fil`) and hyphenated BCP-47 (`en-US`) | **PASSED** |
| 30 | `test_30_normalize_utc_timestamp_strict_range_rejection` | Rejects pre-1970 and far-future corruptions across datetimes and ISO strings | **PASSED** |
| 31 | `test_31_opt_out_repository_timezone_naive_compatibility` | OptOutRepository handles timezone-naive datetimes without TypeError or local skew | **PASSED** |
| 32 | `test_32_meta_response_null_or_empty_id_fallback` | Fallback synthetic wamid is assigned when Meta returns null or empty message ID | **PASSED** |
| 33 | `test_33_button_builder_index_validation` | Button component builders enforce index bounds (0..9) at creation time | **PASSED** |
| 34 | `test_34_body_currency_and_date_time_validation` | Validates currency and date_time body parameter structures | **PASSED** |
| 35 | `test_35_location_header_parameter_handling` | Validates location header component parameters | **PASSED** |
| 36 | `test_36_worker_mode_a_extracts_and_routes_24h_service_window` | Worker Mode A extracts `enforce_24h_window` and `inbound_timestamp` and routes to template | **PASSED** |

---

## 11. Focused Test Results

```powershell
.venv\Scripts\python -m pytest tests/test_phase7_template_dispatch.py -v
```

- **Exit Code:** `0`
- **Results:** **36 passed in 2.56s (100% Pass Rate)**

---

## 12. Full Regression Results

The complete 16-suite unified regression suite was executed:

```powershell
.venv\Scripts\python -m pytest `
  tests/test_phase7_template_dispatch.py `
  tests/test_phase7_production_readiness.py `
  tests/test_phase6_stage2c_operator_approval_preparation.py `
  tests/test_phase6_stage2d1_tenant_isolation_and_operator_auth.py `
  tests/test_phase6_stage2d2_fail_closed_tenant_context.py `
  tests/test_phase6_stage2d_exact_job_isolation.py `
  tests/test_phase6_stage2e3_direct_payload.py `
  tests/test_phase6_stage3_recovery_lifecycle.py `
  tests/test_phase6_stage4_production_hardening.py `
  tests/test_frontend_adapter.py `
  tests/test_phase6_stage2b_sandbox_token_routing.py `
  tests/test_phase6_stage2a_authorization.py `
  tests/test_phase6_sandbox_execution.py `
  tests/test_phase6_webhook_authentication_and_ingestion.py `
  tests/test_phase3_recovery_workflow.py `
  tests/test_phase3_1_postgres_workflow.py -q
```

- **Exit Code:** `0`
- **Summary:** **218 passed, 2 warnings in 40.99s**
- **Baseline Breakdown:**
  - Historical Baseline (Gate 1): 163 passed
  - Gate 2 Security Suite: 19 passed
  - Gate 3 Template Recovery Suite: 36 passed
  - **Total Unified Suite:** **218 passed (100% Pass Rate)**
- **Regressions:** Exactly 0.

---

## 13. Git Integrity Verification

1. **Whitespace and Formatting Check:**
   - Command:
     ```powershell
     git diff --check
     ```
   - Exit code: `0` (Zero whitespace, trailing space, or syntax errors).
2. **Branch Status:**
   - Active branch: `phase4/whatsapp-inbound-integration`
   - All modified and untracked files preserved without deletion.
   - Zero commits, staging, or push actions performed.

---

## 14. Operational Safety Verification

- `WAPSI_ENV` remains `development`.
- `RAZORPAY_MODE` remains `test`.
- Real `.env` file was **NOT** modified.
- All Meta HTTP dispatches in tests used `httpx.MockTransport` or synthetic mocks. Zero external network dispatches to Meta or Razorpay.
- No real WhatsApp messages were sent to live customers.
- Zero database migrations executed.
- Live target job `5a6587ab-2601-4017-b396-48e3d2fc2fda` verified read-only in PostgreSQL:
  - `status`: `SENT`
  - `retry_count`: `1`
  - `approved_by_operator_id`: `operator_arpit`
  - `approval_snapshot_hash`: `dd0bcf49b2fa5204052b24e401c680d2ebf6d125aedbae88434b96fc8214e8cd`
  - **Mutations during Gate 3:** Exactly 0.

---

## 15. Remaining Limitations and Risks

1. **Meta Template Provisioning in Business Manager:** Prior to live production dispatches outside the 24-hour window, the specific template (e.g. `payment_recovery_v1`) and its language variants must be created and approved within the Meta WhatsApp Business Account manager.
2. **Permanent System User Token Permissions:** Production token must carry active `whatsapp_business_messaging` and `whatsapp_business_management` permissions.
3. **Background Worker Daemon Execution:** Gate 4 addresses the continuous daemon loop, lease renewal, concurrency, and multi-worker scale.

---

## 16. Gate 3 Acceptance Checklist

- [x] Implemented `send_template_message(to_phone, template_name, language_code, components)` returning `WhatsAppDispatchResult`.
- [x] Supported dynamic body parameters, header parameters (text, image, document, location), quick-reply button parameters, and dynamic URL button parameters.
- [x] Implemented strict validation for template name (`validate_template_name`), language code (`validate_language_code`), and components (`validate_template_components`).
- [x] Verified payload structure against Meta WhatsApp Cloud API specifications.
- [x] Standardized on Graph API `v26.0` centralized in `WapsiSettings`.
- [x] Implemented 24-hour customer service window routing in `service_window.py` with UTC timestamp normalization and exact 86,400.0s boundary.
- [x] Preserved freeform text message behavior inside the 24-hour window (Case A).
- [x] Routed outbound recovery to approved templates outside the 24-hour window (Case B).
- [x] Implemented fail-closed handling for missing or invalid inbound timestamps (Case C).
- [x] Implemented structured manual review fallback when template configuration is unavailable outside the 24h window.
- [x] Preserved operator approval (`requires_operator_approval=True`), cryptographic approval hash validation, tenant isolation, and idempotency.
- [x] Hardened `_send_payload` to avoid blind retries on ambiguous POST timeouts, catch protocol/request errors, and handle null message IDs gracefully.
- [x] Verified zero credential disclosure in logs and exceptions.
- [x] Dedicated Gate 3 test suite (`tests/test_phase7_template_dispatch.py`, 36 tests) passed (100%).
- [x] Full unified regression suite (16 suites, 218 tests) passed (100%).
- [x] Protected live target job `5a6587ab-2601-4017-b396-48e3d2fc2fda` verified intact (0 mutations).
- [x] Generated comprehensive completion report `docs/PHASE_7_GATE_3_TEMPLATE_RECOVERY_REPORT.md`.
- [x] Stopped execution cleanly before Gate 4.
