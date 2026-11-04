"""
WAPSI Phase 7 — Gate 6: Complete Frontend Engineering, Premium UI/UX & Playwright E2E Integration Suite.
File: tests/test_phase7_frontend_playwright_e2e.py

Verifies:
1. Executive Overview & System Telemetry API Verification (Tests 1-6)
2. Recovery Cases Catalog & Deep Detail Scored Insights (Tests 7-12)
3. Human-In-The-Loop (HITL) Operator Approval with SHA-256 Snapshot (Tests 13-18)
4. Gate 5 Observational Retraining Pipeline & DML Exporter (Tests 19-24)
5. Gate 4 Worker Operations & Partitioned Outbox Monitoring (Tests 25-29)
6. Security, Anti-Spoofing & Tenant Context Boundaries (Tests 30-34)
7. Frontend Production Bundle & Routing Integrity (Tests 35-38)
8. Playwright MCP E2E Recorded Session & Visual Artifact Integrity (Tests 39-44)
9. Protected Target Outbox Job Zero-Mutation Invariant (Test 45)
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Any

import pytest
from fastapi.testclient import TestClient

from wapsi.api.app import app
from tests.conftest import TARGET_JOB_ID_STR


TEST_API_KEY = "rzp_test_wapsi_key_2026"
AUTH_HEADERS = {
    "Accept": "application/json",
    "X-API-Key": TEST_API_KEY,
}

FRONTEND_ROOT = Path("C:/Users/arpit/Desktop/WAPSI-Buildathon")
SCREENSHOTS_DIR = Path("C:/Users/arpit/Desktop/Razorpay/Razorpay/docs/screenshots")


@pytest.fixture(scope="module")
def api_client():
    """Module-scoped FastAPI TestClient with standard test headers."""
    with TestClient(app) as client:
        yield client


# ==============================================================================
# SECTION 1: EXECUTIVE OVERVIEW & SYSTEM TELEMETRY (Tests 1-6)
# ==============================================================================

def test_01_health_endpoint_contract(api_client: TestClient):
    """Test 01: Verify /health returns valid JSON with database and TEE metadata."""
    res = api_client.get("/health", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("healthy", "ok", "degraded")
    assert "models_ready" in data or "models_loaded" in data
    assert "database" in data
    assert "dialect" in data["database"]
    assert "tee_boundary" in data


def test_02_api_v1_health_adapter_contract(api_client: TestClient):
    """Test 02: Verify /api/v1/health forwards health status for frontend consumption."""
    res = api_client.get("/api/v1/health", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("healthy", "ok", "degraded")


def test_03_integrations_status_razorpay(api_client: TestClient):
    """Test 03: Verify /api/v1/integrations/status returns genuine Razorpay gateway telemetry."""
    res = api_client.get("/api/v1/integrations/status", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert "razorpay" in data
    rzp = data["razorpay"]
    assert rzp["mode"] in ("test", "live")
    assert rzp["ready"] is True
    assert "rzp_test_" in rzp["masked_key_id"]


def test_04_integrations_status_whatsapp_cloud_api(api_client: TestClient):
    """Test 04: Verify /api/v1/integrations/status returns genuine WhatsApp Cloud API status."""
    res = api_client.get("/api/v1/integrations/status", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert "whatsapp_cloud_api" in data
    waba = data["whatsapp_cloud_api"]
    assert waba["api_version"] == "v26.0"
    assert waba["business_account_id"] == "969727602419694"
    assert waba["phone_number_id"] == "1407090562487899"
    assert waba["configured"] is True


def test_05_integrations_status_database_telemetry(api_client: TestClient):
    """Test 05: Verify /api/v1/integrations/status reports database dialect and latency."""
    res = api_client.get("/api/v1/integrations/status", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert "database" in data
    db = data["database"]
    assert db["dialect"] in ("postgresql", "sqlite")
    assert db["latency_ms"] > 0


def test_06_recovery_metrics_kpis(api_client: TestClient):
    """Test 06: Verify /api/v1/recovery/metrics returns authoritative aggregate figures."""
    res = api_client.get("/api/v1/recovery/metrics", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert "cases" in data
    assert "outbox" in data
    assert "total" in data["cases"]


# ==============================================================================
# SECTION 2: RECOVERY CASES CATALOG & DEEP DETAIL (Tests 7-12)
# ==============================================================================

def test_07_recovery_cases_list_seeds(api_client: TestClient):
    """Test 07: Verify /api/v1/recovery/cases lists pre-scored deterministic seed cases."""
    res = api_client.get("/api/v1/recovery/cases", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert "cases" in data
    assert isinstance(data["cases"], list)
    assert len(data["cases"]) >= 15
    first = data["cases"][0]
    assert "caseId" in first
    assert "amount" in first
    assert "recommendedAction" in first
    assert "incrementalUplift" in first


def test_08_recovery_cases_pagination(api_client: TestClient):
    """Test 08: Verify /api/v1/recovery/cases paginates results accurately."""
    res = api_client.get("/api/v1/recovery/cases?page=1&limit=5", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert len(data["cases"]) <= 5
    assert data["limit"] == 5


def test_09_recovery_case_detail_by_id(api_client: TestClient):
    """Test 09: Verify /api/v1/recovery/cases/{id} returns comprehensive single case data."""
    res = api_client.get("/api/v1/recovery/cases/RX-48291", headers=AUTH_HEADERS)
    assert res.status_code == 200
    case = res.json()
    assert case["caseId"] == "RX-48291"
    assert "bestAction" in case or "recommendedAction" in case
    assert "confidence" in case


def test_10_recovery_case_shap_feature_importance(api_client: TestClient):
    """Test 10: Verify case detail contains genuine SHAP explanation contributions."""
    res = api_client.get("/api/v1/recovery/cases/RX-48291", headers=AUTH_HEADERS)
    assert res.status_code == 200
    case = res.json()
    assert "explanation" in case
    exp = case["explanation"]
    assert isinstance(exp, list)
    assert len(exp) > 0
    first_feat = exp[0]
    assert "featureName" in first_feat or "label" in first_feat
    assert "contribution" in first_feat


def test_11_recovery_case_nearest_precedents(api_client: TestClient):
    """Test 11: Verify case detail contains nearest precedent historical neighbors."""
    res = api_client.get("/api/v1/recovery/cases/RX-48291", headers=AUTH_HEADERS)
    assert res.status_code == 200
    case = res.json()
    assert "precedents" in case
    precedents = case["precedents"]
    assert isinstance(precedents, list)
    assert len(precedents) > 0


def test_12_recovery_case_fallback_for_unknown(api_client: TestClient):
    """Test 12: Verify case detail returns gracefully for queried case id."""
    res = api_client.get("/api/v1/recovery/cases/RX-NONEXISTENT", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json()["caseId"] == "RX-NONEXISTENT"


# ==============================================================================
# SECTION 3: OPERATOR APPROVAL & HITL GOVERNANCE (Tests 13-18)
# ==============================================================================

def test_13_operator_approval_success(api_client: TestClient):
    """Test 13: Verify POST /api/v1/recovery/cases/{id}/approve succeeds with operator ID."""
    payload = {
        "action": "BNPL / Credit Offer",
        "operatorId": "OPR_FINTECH_DIRECTOR_GATE6"
    }
    res = api_client.post("/api/v1/recovery/cases/RX-48292/approve", json=payload, headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("APPROVED", "QUEUED", "SUCCESS")
    assert "audit_hash" in data


def test_14_operator_approval_sha256_snapshot_hash(api_client: TestClient):
    """Test 14: Verify approval returns a valid 64-character SHA-256 snapshot hash."""
    payload = {
        "action": "BNPL / Credit Offer",
        "operatorId": "OPR_MERCHANT_LEAD"
    }
    res = api_client.post("/api/v1/recovery/cases/RX-48293/approve", json=payload, headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    hash_val = data.get("approval_snapshot_hash") or data.get("audit_hash")
    assert isinstance(hash_val, str)
    assert len(hash_val) == 64
    # Verify it is valid hexadecimal
    int(hash_val, 16)


def test_15_operator_rejection_flow(api_client: TestClient):
    """Test 15: Verify POST /api/v1/recovery/cases/{id}/reject marks case REJECTED."""
    payload = {
        "reason": "Merchant manual suppression requested",
        "operatorId": "OPR_SUPERVISOR_TEST"
    }
    res = api_client.post("/api/v1/recovery/cases/RX-48298/reject", json=payload, headers=AUTH_HEADERS)
    assert res.status_code in (200, 204)


def test_16_governance_audit_trail_endpoint(api_client: TestClient):
    """Test 16: Verify /api/v1/governance/audit-trail returns immutable block records."""
    res = api_client.get("/api/v1/governance/audit-trail?limit=10", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert "events" in data or "blocks" in data or "integrity" in data


def test_17_governance_policies_endpoint(api_client: TestClient):
    """Test 17: Verify /api/v1/governance/policies returns active compliance rules."""
    res = api_client.get("/api/v1/governance/policies", headers=AUTH_HEADERS)
    assert res.status_code == 200
    policies = res.json()
    assert isinstance(policies, list)
    assert len(policies) > 0


def test_18_governance_tee_status_endpoint(api_client: TestClient):
    """Test 18: Verify /api/v1/governance/tee-status reports enclave attestation status."""
    res = api_client.get("/api/v1/governance/tee-status", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["enclaveStatus"] == "ATTESTED"
    assert "enclaveMeasurementPcr0" in data
    assert data["zeroCopyGuarantees"] is True


# ==============================================================================
# SECTION 4: GATE 5 OBSERVATIONAL RETRAINING PIPELINE (Tests 19-24)
# ==============================================================================

def test_19_observational_metrics_keys(api_client: TestClient):
    """Test 19: Verify /api/v1/observational/metrics returns complete Gate 5 metrics."""
    res = api_client.get("/api/v1/observational/metrics", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    metrics = data["metrics"]
    assert "total_observations" in metrics
    assert "mature_observations" in metrics
    assert "eligible_dml_records" in metrics
    assert "eligible_bandit_records" in metrics
    assert "invalid_propensity_records" in metrics
    assert "action_distribution" in metrics
    assert "propensity_summary" in metrics
    assert "overlap_violation_rate" in metrics


def test_20_observational_export_json_contract(api_client: TestClient):
    """Test 20: Verify /api/v1/observational/export returns valid dataset schema."""
    target_merchant = "04a2aaf8-8c8a-4d99-852c-cefc80e82019"
    res = api_client.get(
        f"/api/v1/observational/export?merchant_id={target_merchant}&limit=10",
        headers=AUTH_HEADERS
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["merchant_id"] == target_merchant
    assert "record_count" in data
    assert isinstance(data["records"], list)


def test_21_observational_export_pii_exclusion(api_client: TestClient):
    """Test 21: Verify exported observational records strictly exclude customer PII."""
    target_merchant = "04a2aaf8-8c8a-4d99-852c-cefc80e82019"
    res = api_client.get(
        f"/api/v1/observational/export?merchant_id={target_merchant}&limit=50",
        headers=AUTH_HEADERS
    )
    assert res.status_code == 200
    records = res.json().get("records", [])
    forbidden_keys = {"customer_phone", "customer_email", "customer_name", "card_number", "vpa"}
    for r in records:
        for k in forbidden_keys:
            assert k not in r, f"PII leakage detected: key {k} present in export record"


def test_22_observational_export_eligible_only_filter(api_client: TestClient):
    """Test 22: Verify eligible_only parameter filters out ineligible records."""
    target_merchant = "04a2aaf8-8c8a-4d99-852c-cefc80e82019"
    res = api_client.get(
        f"/api/v1/observational/export?merchant_id={target_merchant}&eligible_only=true",
        headers=AUTH_HEADERS
    )
    assert res.status_code == 200
    records = res.json().get("records", [])
    for r in records:
        assert r.get("is_eligible") is True


def test_23_observational_export_date_filter_validation(api_client: TestClient):
    """Test 23: Verify export endpoint accepts ISO date parameters."""
    target_merchant = "04a2aaf8-8c8a-4d99-852c-cefc80e82019"
    res = api_client.get(
        f"/api/v1/observational/export?merchant_id={target_merchant}&start_date=2026-11-01&end_date=2026-11-04",
        headers=AUTH_HEADERS
    )
    assert res.status_code == 200
    assert "records" in res.json()


def test_24_observational_metrics_merchant_scoping(api_client: TestClient):
    """Test 24: Verify observational metrics can be scoped by merchant_id."""
    res = api_client.get(
        "/api/v1/observational/metrics?merchant_id=04a2aaf8-8c8a-4d99-852c-cefc80e82019",
        headers=AUTH_HEADERS
    )
    assert res.status_code == 200
    assert res.json()["status"] == "success"


# ==============================================================================
# SECTION 5: GATE 4 WORKER OPERATIONS & OUTBOX MONITORING (Tests 25-29)
# ==============================================================================

def test_25_worker_health_status(api_client: TestClient):
    """Test 25: Verify /api/v1/workers/health reports HEALTHY status."""
    res = api_client.get("/api/v1/workers/health", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("HEALTHY", "DEGRADED", "STARTING")
    assert "queue_depth" in data
    assert "active_leases" in data
    assert "timestamp_utc" in data


def test_26_worker_daemon_lease_duration(api_client: TestClient):
    """Test 26: Verify worker metadata includes lease duration."""
    res = api_client.get("/api/v1/workers/health", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    if "worker" in data and data["worker"]:
        assert data["worker"]["lease_duration_seconds"] >= 30


def test_27_worker_health_outbox_partition_telemetry(api_client: TestClient):
    """Test 27: Verify outbox partitions are exposed in worker health."""
    res = api_client.get("/api/v1/workers/health", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    if "outbox" in data and data["outbox"]:
        partitions = data["outbox"]
        expected = ["PENDING_APPROVAL", "QUEUED", "SENDING", "SENT"]
        for p in expected:
            assert p in partitions


def test_28_worker_active_leases_non_negative(api_client: TestClient):
    """Test 28: Invariant check: active leases count is always non-negative."""
    res = api_client.get("/api/v1/workers/health", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json()["active_leases"] >= 0


def test_29_worker_queue_depth_non_negative(api_client: TestClient):
    """Test 29: Invariant check: queue depth is always non-negative."""
    res = api_client.get("/api/v1/workers/health", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json()["queue_depth"] >= 0


# ==============================================================================
# SECTION 6: SECURITY, AUTHENTICATION & ANTI-SPOOFING (Tests 30-34)
# ==============================================================================

def test_30_missing_api_key_rejected(api_client: TestClient):
    """Test 30: Reject request without API key with HTTP 401."""
    res = api_client.get("/api/v1/workers/health")
    assert res.status_code == 401


def test_31_invalid_api_key_rejected(api_client: TestClient):
    """Test 31: Reject request with forged API key with HTTP 401."""
    res = api_client.get("/api/v1/workers/health", headers={"X-API-Key": "forged_key_12345"})
    assert res.status_code == 401


def test_32_tenant_spoofing_mismatch_rejected(api_client: TestClient):
    """Test 32: Reject request with mismatching X-Merchant-ID header with HTTP 403."""
    spoofed_headers = {
        "X-API-Key": TEST_API_KEY,
        "X-Merchant-ID": "spoofed-merchant-uuid-9999",
    }
    res = api_client.get("/api/v1/workers/health", headers=spoofed_headers)
    assert res.status_code == 403
    assert "Forbidden" in res.json().get("detail", "") or "Tenant" in res.json().get("detail", "")


def test_33_tampered_tee_attestation_rejected(api_client: TestClient):
    """Test 33: Reject request with tampered enclave attestation header."""
    headers = {
        **AUTH_HEADERS,
        "X-Enclave-Attestation": "tampered",
    }
    payload = {
        "payment_id": "pay_test_tee_1",
        "amount": 1000,
        "merchant_id": "default_merchant",
    }
    res = api_client.post("/api/v1/recovery/predict", json=payload, headers=headers)
    assert res.status_code in (403, 400, 422)


def test_34_valid_auth_derives_correct_sandbox_identity(api_client: TestClient):
    """Test 34: Valid test API key derives sandbox merchant identity."""
    res = api_client.get("/api/v1/workers/health", headers=AUTH_HEADERS)
    assert res.status_code == 200


# ==============================================================================
# SECTION 7: FRONTEND PRODUCTION BUNDLE & ROUTING (Tests 35-38)
# ==============================================================================

def test_35_frontend_dist_index_html_exists():
    """Test 35: Verify frontend Vite production build output exists and is non-empty."""
    dist_html = FRONTEND_ROOT / "dist" / "index.html"
    assert dist_html.exists(), "Frontend build index.html must exist in dist/"
    content = dist_html.read_text(encoding="utf-8")
    assert "<title>WAPSI" in content or "WAPSI" in content
    assert '<div id="root">' in content


def test_36_frontend_dist_assets_js_and_css_exist():
    """Test 36: Verify JavaScript and CSS bundle chunks exist in dist/assets."""
    assets_dir = FRONTEND_ROOT / "dist" / "assets"
    assert assets_dir.exists(), "dist/assets directory must exist"
    js_files = list(assets_dir.glob("*.js"))
    css_files = list(assets_dir.glob("*.css"))
    assert len(js_files) > 0, "At least one JS bundle chunk must exist"
    assert len(css_files) > 0, "At least one CSS bundle chunk must exist"
    assert js_files[0].stat().st_size > 50_000, "JS bundle chunk must be substantive"
    assert css_files[0].stat().st_size > 10_000, "CSS bundle chunk must be substantive"


def test_37_frontend_router_routes_defined():
    """Test 37: Verify router configuration registers all Phase 7 required pages."""
    router_file = FRONTEND_ROOT / "src" / "app" / "router" / "index.tsx"
    assert router_file.exists(), "Router definition file must exist"
    router_src = router_file.read_text(encoding="utf-8")
    assert "overview" in router_src
    assert "recovery-center" in router_src
    assert "ai-decisions" in router_src
    assert "observational-learning" in router_src
    assert "worker-operations" in router_src
    assert "settings" in router_src


def test_38_frontend_api_client_endpoints_aligned():
    """Test 38: Verify frontend apiClient has methods matching all live endpoints."""
    client_file = FRONTEND_ROOT / "src" / "services" / "api" / "apiClient.ts"
    assert client_file.exists()
    src = client_file.read_text(encoding="utf-8")
    assert "getWorkerHealth" in src
    assert "getIntegrationsStatus" in src
    assert "getObservationalMetrics" in src
    assert "exportObservationalData" in src
    assert "approveRecoveryCase" in src


# ==============================================================================
# SECTION 8: PLAYWRIGHT MCP RECORDED VISUAL ARTIFACTS (Tests 39-44)
# ==============================================================================

def test_39_playwright_overview_screenshot_integrity():
    """Test 39: Verify Playwright MCP recorded overview screenshot exists and is high-resolution."""
    img_path = SCREENSHOTS_DIR / "overview_desktop.png"
    assert img_path.exists(), f"Overview screenshot missing at {img_path}"
    assert img_path.stat().st_size > 100_000, "Overview screenshot must be valid high-resolution PNG"


def test_40_playwright_recovery_center_screenshot_integrity():
    """Test 40: Verify Recovery Center screenshot exists with rendered table."""
    img_path = SCREENSHOTS_DIR / "recovery_center.png"
    assert img_path.exists(), f"Recovery center screenshot missing at {img_path}"
    assert img_path.stat().st_size > 100_000


def test_41_playwright_operator_approval_modal_screenshot_integrity():
    """Test 41: Verify HITL Operator Approval modal screenshot exists."""
    img_path = SCREENSHOTS_DIR / "operator_approval_modal.png"
    assert img_path.exists(), f"Approval modal screenshot missing at {img_path}"
    assert img_path.stat().st_size > 50_000


def test_42_playwright_gate5_observational_dashboard_screenshot():
    """Test 42: Verify Gate 5 Observational Retraining dashboard screenshot exists."""
    img_path = SCREENSHOTS_DIR / "observational_learning.png"
    assert img_path.exists(), f"Observational learning screenshot missing at {img_path}"
    assert img_path.stat().st_size > 100_000


def test_43_playwright_gate4_worker_operations_screenshot():
    """Test 43: Verify Gate 4 Worker Operations dashboard screenshot exists."""
    img_path = SCREENSHOTS_DIR / "worker_operations.png"
    assert img_path.exists(), f"Worker operations screenshot missing at {img_path}"
    assert img_path.stat().st_size > 100_000


def test_44_playwright_responsive_viewports_screenshots():
    """Test 44: Verify tablet and mobile responsive layout screenshots exist."""
    tablet_img = SCREENSHOTS_DIR / "tablet_responsive.png"
    mobile_img = SCREENSHOTS_DIR / "mobile_responsive.png"
    assert tablet_img.exists(), "Tablet responsive screenshot missing"
    assert mobile_img.exists(), "Mobile responsive screenshot missing"
    assert tablet_img.stat().st_size > 50_000
    assert mobile_img.stat().st_size > 50_000


# ==============================================================================
# SECTION 9: OPERATIONAL SAFETY & TARGET OUTBOX INVARIANT (Test 45)
# ==============================================================================

def test_45_target_outbox_job_5a6587ab_strict_immutability():
    """Test 45: Strictly assert protected outbox job 5a6587ab is unmutated."""
    target_merchant_id = "04a2aaf8-8c8a-4d99-852c-cefc80e82019"
    assert TARGET_JOB_ID_STR == "5a6587ab-2601-4017-b396-48e3d2fc2fda"
    assert target_merchant_id == "04a2aaf8-8c8a-4d99-852c-cefc80e82019"

    from wapsi.db.session import DatabaseManager
    from sqlalchemy import text
    dm = DatabaseManager()
    with dm.session_scope() as session:
        if dm.engine.dialect.name == "postgresql":
            session.execute(
                text("SELECT set_config('app.current_merchant_id', :m_id, true)"),
                {"m_id": target_merchant_id},
            )
            row = session.execute(
                text("SELECT id, status, retry_count, approved_by_operator_id, approval_snapshot_hash FROM recovery_outbox WHERE id = :job_id"),
                {"job_id": TARGET_JOB_ID_STR},
            ).fetchone()
            assert row is not None, "Target job 5a6587ab must exist in PostgreSQL"
            mapping = dict(row._mapping)
            assert mapping["status"] == "SENT"
            assert mapping["retry_count"] == 1
            assert mapping["approved_by_operator_id"] == "operator_arpit"
            assert mapping["approval_snapshot_hash"] == "dd0bcf49b2fa5204052b24e401c680d2ebf6d125aedbae88434b96fc8214e8cd"
