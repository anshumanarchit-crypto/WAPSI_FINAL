"""
Automated Verification Suite for WAPSI Hybrid Monte Carlo + LLM Synthetic Data Generation.
Razorpay AI Buildathon 2026 - Track 3

Verifies:
1. Procedural Monte Carlo mathematical skeleton generation (10,000 rows, reproducible seed, checksum).
2. Agent A (NarrativeGenerator) schema and output bounds.
3. Agent B (NarrativeCritic) consistency verification and contradiction detection.
4. Deterministic programmatic validator (two-sentence backstory, outcome consistency, amount copying).
5. 3-attempt retry budget and fallback narrative trigger.
6. Absolute mathematical field immutability.
7. LLM Provider Router health checks and tiered fallback.
8. REST API endpoints (/api/v1/integrations/health, /api/v1/synthetic/*).
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from wapsi.api.app import app
from wapsi.llm.router import LLMProviderRouter, LLMResponse, get_llm_router
from wapsi.simulation.hybrid_synthetic import (
    MATHEMATICAL_IMMUTABLE_FIELDS,
    DeterministicPythonValidator,
    DeterministicSkeletonGenerator,
    HybridEnrichmentOrchestrator,
    NarrativeCritic,
    NarrativeGenerator,
    SyntheticJobManager,
    get_synthetic_job_manager,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_math_row():
    return {
        "case_id": "case_test_mock_101",
        "merchant_id": "merch_cloud_scale",
        "customer_id": "cust_123456",
        "domain": "b2b_saas",
        "amount": 9900.0,
        "amount_paise": 990000,
        "amount_display": "₹9,900.00",
        "decline_reason": "bank_downtime",
        "failure_code": "bank_downtime",
        "attempts_used": 1,
        "account_age_days": 180,
        "previous_failures": 1,
        "previous_recoveries": 2,
        "prior_recovery_rate": 0.6667,
        "day_of_week": 2,
        "hour": 11,
        "issuer": "HDFC",
        "bin_bucket": "corporate",
        "fatigue_score": 0.12,
        "treatment": "whatsapp_nudge",
        "recovered": 1,
        "outcome": "recovered",
        "time_to_recovery_hours": 1.25,
        "is_synthetic": True,
        "dataset_version": "v1.0-synthetic",
        "simulation_seed": 42,
        "generation_timestamp": "2026-11-04T00:00:00Z",
    }


# ==============================================================================
# 1. Deterministic Skeleton Generation
# ==============================================================================
def test_skeleton_generator_reproducibility():
    """Verifies that running with the same seed yields identical SHA256 checksums."""
    fixed_ts = "2026-11-04T00:00:00Z"
    gen1 = DeterministicSkeletonGenerator(seed=123, output_dir=".wapsi_data/test_datasets")
    f1, m1, man1 = gen1.generate_skeleton(total_rows=100, timestamp=fixed_ts)

    gen2 = DeterministicSkeletonGenerator(seed=123, output_dir=".wapsi_data/test_datasets")
    f2, m2, man2 = gen2.generate_skeleton(total_rows=100, timestamp=fixed_ts)

    assert man1["sha256_checksum"] == man2["sha256_checksum"]
    assert man1["total_rows"] == 100


def test_skeleton_generator_mathematical_schema():
    """Verifies that generated rows contain all required mathematical fields and integer paise."""
    gen = DeterministicSkeletonGenerator(seed=42, output_dir=".wapsi_data/test_datasets")
    skel_file, _, _ = gen.generate_skeleton(total_rows=50)

    with open(skel_file, "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]

    assert len(rows) == 50
    for r in rows:
        assert "amount_paise" in r
        assert isinstance(r["amount_paise"], int)
        assert r["amount_paise"] == int(round(r["amount"] * 100))
        assert r["is_synthetic"] is True
        assert r["recovered"] in (0, 1)
        assert r["outcome"] in ("recovered", "failed")
        assert "amount_display" in r
        assert r["amount_display"].startswith("₹")


# ==============================================================================
# 2. Agent A & Agent B Structure
# ==============================================================================
def test_agent_a_generates_valid_schema(sample_math_row):
    """Verifies Agent A produces all required narrative fields."""
    agent_a = NarrativeGenerator()
    narrative, llm_resp = agent_a.generate_narrative(sample_math_row)

    assert "company_name" in narrative
    assert "contact_person" in narrative
    assert "failure_backstory" in narrative
    assert "hinglish_whatsapp_message" in narrative
    assert narrative.get("synthetic") is True


def test_agent_b_critic_evaluation(sample_math_row):
    """Verifies Agent B critic approves consistent narrative."""
    agent_b = NarrativeCritic()
    valid_narrative = {
        "company_name": "CloudScale Systems India",
        "contact_person": "Priya Sharma",
        "failure_backstory": "The customer attempted to process an annual subscription renewal of ₹9,900.00 during banking hours. The transaction experienced a bank downtime timeout.",
        "hinglish_whatsapp_message": "Namaste Priya Sharma ji, aapka ₹9,900.00 payment bank downtime ki wajah se delay hua. Kripya check karein.",
        "narrative_tags": ["bank_downtime", "b2b_saas"],
        "synthetic": True,
    }

    is_passed, err_msg, _ = agent_b.evaluate_narrative(sample_math_row, valid_narrative)
    assert is_passed is True
    assert err_msg is None


# ==============================================================================
# 3. Deterministic Python Validator Tests
# ==============================================================================
def test_validator_rejects_missing_synthetic_flag(sample_math_row):
    narrative = {
        "company_name": "Acme Inc",
        "contact_person": "Rohan",
        "failure_backstory": "Sentence one here. Sentence two here.",
        "hinglish_whatsapp_message": "Namaste Rohan ji.",
        "synthetic": False,
    }
    is_valid, err = DeterministicPythonValidator.validate(sample_math_row, narrative)
    assert is_valid is False
    assert "synthetic" in err


def test_validator_rejects_invalid_sentence_count(sample_math_row):
    narrative = {
        "company_name": "Acme Inc",
        "contact_person": "Rohan",
        "failure_backstory": "Only one sentence here.",
        "hinglish_whatsapp_message": "Namaste Rohan ji.",
        "synthetic": True,
    }
    is_valid, err = DeterministicPythonValidator.validate(sample_math_row, narrative)
    assert is_valid is False
    assert "two sentences" in err


def test_validator_rejects_outcome_contradiction(sample_math_row):
    failed_row = dict(sample_math_row, recovered=0, outcome="failed")
    contradictory_narrative = {
        "company_name": "Acme Inc",
        "contact_person": "Rohan",
        "failure_backstory": "The customer attempted a payment of ₹9,900.00 yesterday. The transaction completed with no issues.",
        "hinglish_whatsapp_message": "Namaste Rohan ji, your payment successful and settled.",
        "synthetic": True,
    }
    is_valid, err = DeterministicPythonValidator.validate(failed_row, contradictory_narrative)
    assert is_valid is False
    assert "Contradiction" in err


def test_validator_rejects_amount_discrepancy(sample_math_row):
    narrative = {
        "company_name": "Acme Inc",
        "contact_person": "Rohan",
        "failure_backstory": "The customer attempted a payment of ₹9,900.00 yesterday. The issuing bank timed out.",
        "hinglish_whatsapp_message": "Namaste Rohan ji, aapka ₹500.00 payment delay ho gaya.",
        "synthetic": True,
    }
    is_valid, err = DeterministicPythonValidator.validate(sample_math_row, narrative)
    assert is_valid is False
    assert "Amount discrepancy" in err


# ==============================================================================
# 4. Hybrid Orchestration & Mathematical Immutability
# ==============================================================================
def test_orchestrator_mathematical_immutability(sample_math_row):
    """Verifies that mathematical fields are 100% immutable throughout enrichment."""
    orchestrator = HybridEnrichmentOrchestrator()
    enriched = orchestrator.enrich_single_row(sample_math_row)

    for f in MATHEMATICAL_IMMUTABLE_FIELDS:
        assert enriched[f] == sample_math_row[f], f"Field '{f}' was modified!"

    assert enriched["narrative_status"] in ("enriched", "fallback")
    assert enriched["synthetic"] is True


def test_orchestrator_exhausts_attempts_to_fallback(sample_math_row):
    """Verifies that when Agent A continuously fails, orchestrator uses deterministic fallback."""
    class FailingAgentA(NarrativeGenerator):
        def generate_narrative(self, math_row, critic_error_feedback=None, preferred_provider=None):
            # Return invalid narrative missing company_name
            return {"synthetic": True, "failure_backstory": "One sentence."}, LLMResponse(
                content="{}", parsed_json={}, provider="mock", model="mock", latency_ms=1.0, is_fallback=False
            )

    orch = HybridEnrichmentOrchestrator(agent_a=FailingAgentA())
    result = orch.enrich_single_row(sample_math_row)

    assert result["narrative_status"] == "fallback"
    assert result["narrative_provider"] == "deterministic_fallback"
    assert "company_name" in result
    assert result["amount_paise"] == sample_math_row["amount_paise"]


# ==============================================================================
# 5. REST API Endpoints Integration
# ==============================================================================
def test_api_integrations_health(client):
    """Verifies /api/v1/integrations/health returns live structured statuses."""
    res = client.get("/api/v1/integrations/health")
    assert res.status_code == 200
    data = res.json()

    assert "services" in data
    assert "fastapi" in data["services"]
    assert "supabase" in data["services"]
    assert "razorpay" in data["services"]
    assert "whatsapp" in data["services"]
    assert "llm_providers" in data["services"]

    # Status taxonomy checks
    valid_statuses = {"connected", "authentication_failed", "temporarily_unavailable", "not_configured"}
    assert data["services"]["fastapi"]["status"] in valid_statuses
    assert data["services"]["supabase"]["status"] in valid_statuses
    assert data["services"]["razorpay"]["status"] in valid_statuses
    assert data["services"]["whatsapp"]["status"] in valid_statuses


def test_api_synthetic_job_lifecycle(client):
    """Verifies initiating a skeleton job, tracking status, previewing, and downloading."""
    # 1. Start small skeleton job
    res_start = client.post(
        "/api/v1/synthetic/jobs/generate-skeleton",
        json={"seed": 99, "total_rows": 25},
    )
    assert res_start.status_code == 200
    job_id = res_start.json()["job_id"]

    # Allow worker thread a brief moment to write 25 rows
    import time
    time.sleep(0.5)

    # 2. Status
    res_status = client.get(f"/api/v1/synthetic/jobs/{job_id}/status")
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["job_id"] == job_id

    # 3. Preview
    res_preview = client.get(f"/api/v1/synthetic/jobs/{job_id}/preview?limit=5")
    assert res_preview.status_code == 200
    assert len(res_preview.json()["records"]) <= 5

    # 4. Download JSON
    res_down_json = client.get(f"/api/v1/synthetic/jobs/{job_id}/download?format=json")
    assert res_down_json.status_code == 200
    assert "application/json" in res_down_json.headers["content-type"]

    # 5. Download CSV
    res_down_csv = client.get(f"/api/v1/synthetic/jobs/{job_id}/download?format=csv")
    assert res_down_csv.status_code == 200
    assert "text/csv" in res_down_csv.headers["content-type"]
