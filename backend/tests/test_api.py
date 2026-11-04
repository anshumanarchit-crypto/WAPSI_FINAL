"""
Unit & Integration Tests for WAPSI FastAPI Inference Application.
Razorpay AI Buildathon 2026 - Track 3

Tests:
  - GET  /health (Readiness & model state)
  - GET  /api/v1/model/info (Metadata & capabilities)
  - POST /api/v1/recovery/predict (Contract validation, sample cases, schema verification)
  - Pydantic 422 validation errors (negative amount, out-of-bound fatigue)
  - Information security & privacy (NO stack trace leakage, NO filesystem path exposure)
  - Policy Engine DND awareness at 23:00 IST
  - OpenAPI schema accessibility
"""

import pytest
import json
from fastapi.testclient import TestClient

from api.app import app
from src.data_generator import TREATMENTS


@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient with lifespan initialization."""
    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint(client):
    """Verifies that /health returns 200 with healthy service status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "healthy"
    assert data["service"] == "wapsi-causal-decision-engine"
    assert data["version"] == "1.0.0"
    assert data["models_loaded"] is True
    assert "timestamp" in data


def test_model_info_endpoint(client):
    """Verifies that /api/v1/model/info returns public metadata and capabilities."""
    response = client.get("/api/v1/model/info")
    assert response.status_code == 200
    data = response.json()

    assert data["service"] == "wapsi-causal-decision-engine"
    assert data["version"] == "1.0.0"
    assert data["advisory_mode_only"] is True
    assert "supported_actions" in data
    assert len(data["supported_actions"]) >= 6
    assert "no_action" in data["supported_actions"]
    assert "whatsapp_nudge" in data["supported_actions"]
    assert "supported_domains" in data
    assert "conformal_calibration_level" in data


def test_predict_endpoint_sample_case_from_spec(client):
    """
    Verifies POST /api/v1/recovery/predict using the exact sample case from user specification:
    {
      "case_id": "CASE_123",
      "merchant_id": "M001",
      "domain": "subscription",
      "amount": 4999,
      "decline_reason": "insufficient_funds",
      "attempts_used": 1,
      "account_age_days": 730,
      "previous_failures": 3,
      "previous_recoveries": 2,
      "prior_recovery_rate": 0.67,
      "day_of_week": 2,
      "hour": 11,
      "issuer": "HDFC",
      "bin_bucket": "classic",
      "fatigue_score": 0.10
    }
    """
    payload = {
        "case_id": "CASE_123",
        "merchant_id": "M001",
        "domain": "subscription",
        "amount": 4999.0,
        "decline_reason": "insufficient_funds",
        "attempts_used": 1,
        "account_age_days": 730,
        "previous_failures": 3,
        "previous_recoveries": 2,
        "prior_recovery_rate": 0.67,
        "day_of_week": 2,
        "hour": 11,
        "issuer": "HDFC",
        "bin_bucket": "classic",
        "fatigue_score": 0.10
    }

    response = client.post("/api/v1/recovery/predict", json=payload)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()

    # 1. Top-level contract validation
    assert data["case_id"] == "CASE_123"
    assert data["recommended_action"] in TREATMENTS
    assert isinstance(data["uplift"], float)
    assert isinstance(data["action_scores"], dict)
    assert len(data["action_scores"]) >= 5

    # 2. Timing sub-structure
    assert "recommended_window" in data["timing"]
    assert "hazard_by_window" in data["timing"]
    assert len(data["timing"]["hazard_by_window"]) == 4

    # 3. Confidence & Explanation
    assert 0.0 <= data["confidence"] <= 1.0
    assert "explanation" in data
    assert "top_reasons" in data["explanation"]
    assert len(data["explanation"]["top_reasons"]) > 0

    # 4. Precedents & Counter-evidence
    assert isinstance(data["precedents"], list)
    assert isinstance(data["counter_evidence"], bool)

    # 5. Network prior
    assert "network_prior" in data
    assert "combined_uplift" in data["network_prior"]

    # 6. Contextual bandit
    assert "bandit" in data
    assert "selected_action" in data["bandit"]

    # 7. Policy inputs
    assert "policy_inputs" in data
    assert "conformal_gate" in data["policy_inputs"]
    assert "eligible_for_auto_action" in data["policy_inputs"]["conformal_gate"]


def test_validation_error_negative_amount(client):
    """Verifies that negative amount triggers a structured 422 error without stack trace."""
    payload = {
        "amount": -500.0,  # Invalid: must be gt=0
        "domain": "ecommerce"
    }
    response = client.post("/api/v1/recovery/predict", json=payload)
    assert response.status_code == 422
    data = response.json()

    assert data["error"] == "Validation Error"
    assert data["status_code"] == 422
    assert "amount" in data["detail"]
    assert "Traceback" not in response.text


def test_validation_error_invalid_fatigue_score(client):
    """Verifies that fatigue_score > 1.0 triggers 422 error."""
    payload = {
        "amount": 1500.0,
        "fatigue_score": 1.75  # Invalid: must be le=1.0
    }
    response = client.post("/api/v1/recovery/predict", json=payload)
    assert response.status_code == 422
    data = response.json()

    assert data["error"] == "Validation Error"
    assert "fatigue_score" in data["detail"]


def test_no_stack_trace_leakage(client):
    """Ensures 404/422/500 errors never leak Python stack traces."""
    response = client.get("/non_existent_route_404")
    assert response.status_code == 404
    data = response.json()

    assert "error" in data
    assert "Traceback" not in response.text
    assert "File \"" not in response.text


def test_no_model_path_leakage(client):
    """Ensures responses never leak internal filesystem paths (e.g. C:\\Users or /home)."""
    payload = {
        "amount": 2500.0,
        "domain": "ecommerce",
        "decline_reason": "upi_pin_timeout"
    }
    response = client.post("/api/v1/recovery/predict", json=payload)
    assert response.status_code == 200
    res_text = response.text

    # Verify no local Windows or Unix path strings are exposed
    assert "C:\\" not in res_text
    assert "c:/" not in res_text.lower()
    assert "/Users/" not in res_text
    assert ".joblib" not in res_text


def test_night_transaction_dnd_response(client):
    """Verifies that a 23:00 IST transaction correctly flags dnd_active in policy_inputs."""
    payload = {
        "case_id": "CASE_NIGHT_99",
        "amount": 3000.0,
        "hour": 23
    }
    response = client.post("/api/v1/recovery/predict", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["policy_inputs"]["dnd_active"] is True


def test_openapi_documentation_accessible(client):
    """Verifies that OpenAPI JSON schema and Swagger docs are accessible."""
    res_json = client.get("/openapi.json")
    assert res_json.status_code == 200
    schema = res_json.json()

    assert "/api/v1/recovery/predict" in schema["paths"]
    assert "/health" in schema["paths"]
    assert "/api/v1/model/info" in schema["paths"]

    res_docs = client.get("/docs")
    assert res_docs.status_code == 200
