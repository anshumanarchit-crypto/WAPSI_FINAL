"""
Unit & Integration Tests for WAPSI Frontend Adapter Endpoints.
Verifies all compatibility endpoints required by the WAPSI React Frontend.
"""

import pytest
from fastapi.testclient import TestClient
from wapsi.api.app import app
from wapsi.db.service import PersistenceService
from wapsi.db.session import DatabaseManager


@pytest.fixture(autouse=True)
def isolate_persistence(monkeypatch):
    """Guarantees tests use an isolated in-memory persistence service, protecting hosted database."""
    test_db = DatabaseManager(database_url="sqlite:///:memory:")
    test_service = PersistenceService(db_manager=test_db)
    monkeypatch.setattr("wapsi.api.app.get_persistence_service", lambda: test_service)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoints(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["models_ready"] is True
    assert "tee_boundary" in data
    assert "audit_ledger_status" in data

    res_alias = client.get("/health")
    assert res_alias.status_code == 200


def test_recovery_cases_list(client):
    res = client.get("/api/v1/recovery/cases")
    assert res.status_code == 200
    data = res.json()
    assert "cases" in data
    assert "total" in data
    assert len(data["cases"]) > 0

    first_case = data["cases"][0]
    assert "caseId" in first_case
    assert "customerName" in first_case
    assert "incrementalUplift" in first_case
    assert "recommendedAction" in first_case
    assert "status" in first_case


def test_recovery_case_detail(client):
    res = client.get("/api/v1/recovery/cases/RX-48290")
    assert res.status_code == 200
    data = res.json()
    assert data["caseId"] == "RX-48290"
    assert "actionScores" in data
    assert "explanation" in data
    assert "precedents" in data
    assert "timing" in data
    assert "policy" in data


def test_decide_endpoint(client):
    payload = {
        "payment_id": "pay_test_001",
        "amount_in_inr": 2499.0,
        "payment_method": "upi",
        "error_code": "UPI_APP_TIMEOUT",
        "error_description": "UPI app response timeout",
        "merchant_id": "merch_stream_pass",
        "user_id": "usr_9981"
    }
    res = client.post("/api/v1/decide", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "decision_id" in data
    assert "recommended_action" in data
    assert "causal_metrics" in data
    assert "plain_english_rationale" in data
    assert "audit_hash" in data


def test_case_approval_and_audit(client):
    res = client.post("/api/v1/recovery/cases/RX-48290/approve", json={"action": "WHATSAPP"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "APPROVED"
    assert "audit_hash" in data

    # Verify audit ledger recorded the event
    audit_res = client.get("/api/v1/governance/audit-trail")
    assert audit_res.status_code == 200
    audit_data = audit_res.json()
    assert audit_data["integrity"] is True
    assert any("RX-48290" in e["caseId"] or "RX-48290" in e["description"] for e in audit_data["events"])


def test_simulate_recovery_learning_loop(client):
    res = client.post("/api/v1/recovery/cases/RX-48291/simulate-recovery")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "RECOVERED"
    assert data["banditOnlineUpdated"] is True
    assert "audit_hash" in data


def test_analytics_and_decisions_endpoints(client):
    res_dec = client.get("/api/v1/decisions/overview")
    assert res_dec.status_code == 200
    assert "actionDistribution" in res_dec.json()

    res_health = client.get("/api/v1/decisions/model-health")
    assert res_health.status_code == 200
    assert res_health.json()["overallScore"] >= 90

    res_analytics = client.get("/api/v1/analytics/summary")
    assert res_analytics.status_code == 200
    assert "overview" in res_analytics.json()

    res_sim = client.post("/api/v1/analytics/simulate", json={"expectedContacts": 800, "retryBudget": 2000})
    assert res_sim.status_code == 200
    assert "estimatedRecoveryLakhs" in res_sim.json()


def test_governance_endpoints(client):
    res_policies = client.get("/api/v1/governance/policies")
    assert res_policies.status_code == 200
    assert len(res_policies.json()) >= 4

    res_tee = client.get("/api/v1/governance/tee-status")
    assert res_tee.status_code == 200
    assert res_tee.json()["enclaveStatus"] == "ATTESTED"

    res_fairness = client.get("/api/v1/governance/fairness")
    assert res_fairness.status_code == 200
    assert res_fairness.json()["disparateImpact"] > 0.8

