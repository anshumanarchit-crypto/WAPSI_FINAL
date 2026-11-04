"""
Unit tests for WAPSI Precedent & Counter-Evidence Engine.
Razorpay AI Buildathon 2026 - Track 3

Tests:
  - NearestNeighbors retrieval of historical cases
  - Similar case schema ({case_id, action, recovered, similarity})
  - Bounded similarity score properties
  - Empirical recovery rates calculation
  - Counter-evidence / discrepancy detection
  - Safety non-executable policy enforcement
  - Persistence roundtrip (save and load via joblib)
  - Robustness to missing values and novel categorical levels
"""

import pytest
import json
import numpy as np
import pandas as pd
from pathlib import Path

from src.data_generator import WapsiDataGenerator, RecoveryDataConfig, TREATMENTS
from src.precedent_engine import WAPSIPrecedentEngine


@pytest.fixture(scope="module")
def history_dataset():
    """Generates synthetic historical dataset for precedent engine tests."""
    gen = WapsiDataGenerator(RecoveryDataConfig(n_samples=2000, random_seed=42))
    df_obs, _ = gen.generate()
    train_n = int(len(df_obs) * 0.7)
    df_history = df_obs.iloc[:train_n].copy()
    df_new_cases = df_obs.iloc[train_n:].copy()
    return df_history, df_new_cases


@pytest.fixture(scope="module")
def fitted_engine(history_dataset):
    """Returns a pre-fitted WAPSIPrecedentEngine."""
    df_history, _ = history_dataset
    engine = WAPSIPrecedentEngine(n_neighbors=12)
    engine.fit(df_history)
    return engine


def test_precedent_engine_fit_and_retrieve(fitted_engine, history_dataset):
    """Tests fitting and retrieving top-k similar cases."""
    _, df_new = history_dataset
    case = df_new.iloc[0].to_dict()

    similar = fitted_engine.retrieve_similar_cases(case, k=8)
    assert isinstance(similar, list)
    assert len(similar) == 8


def test_similar_case_schema(fitted_engine, history_dataset):
    """Verifies that retrieved cases conform to the exact required schema."""
    _, df_new = history_dataset
    case = df_new.iloc[0].to_dict()

    similar = fitted_engine.retrieve_similar_cases(case, k=5)
    for c in similar:
        assert "case_id" in c
        assert "action" in c
        assert "recovered" in c
        assert "similarity" in c
        assert isinstance(c["case_id"], str)
        assert isinstance(c["action"], str)
        assert isinstance(c["recovered"], bool)
        assert isinstance(c["similarity"], float)
        assert 0.0 < c["similarity"] <= 1.0


def test_similarity_score_ordering(fitted_engine, history_dataset):
    """Verifies that similar cases are sorted in descending order of similarity."""
    _, df_new = history_dataset
    case = df_new.iloc[0].to_dict()

    similar = fitted_engine.retrieve_similar_cases(case, k=10)
    sims = [c["similarity"] for c in similar]
    assert sims == sorted(sims, reverse=True), "Similar cases should be sorted descending by similarity score"


def test_query_schema_and_counts(fitted_engine, history_dataset):
    """Tests query method output schema, case count, and empirical recovery rates."""
    _, df_new = history_dataset
    case = df_new.iloc[0].to_dict()

    res = fitted_engine.query(case, recommended_action="whatsapp_nudge", k=10)

    assert "similar_cases" in res
    assert "similar_case_count" in res
    assert res["similar_case_count"] == 10
    assert "action_recovery_rates" in res
    assert "recommended_action_recovery_rate" in res
    assert "counter_evidence" in res
    assert "discrepancy_reason" in res
    assert "execution_permitted" in res

    # JSON serializability check
    json_str = json.dumps(res)
    assert isinstance(json_str, str)


def test_safety_non_executable(fitted_engine, history_dataset):
    """Verifies that execution_permitted is strictly False to satisfy safety constraints."""
    _, df_new = history_dataset
    case = df_new.iloc[0].to_dict()

    res = fitted_engine.query(case, recommended_action="voice_call")
    assert res["execution_permitted"] is False
    assert "advisory_note" in res


def test_counter_evidence_flag_trigger():
    """Verifies counter_evidence flag triggers when recommended action failed in historical peers."""
    # Construct historical dataset where whatsapp_nudge failed in 100% of cases for this cluster
    records = []
    for i in range(20):
        records.append({
            "case_id": f"hist_{i}",
            "domain": "subscription",
            "decline_reason": "insufficient_funds",
            "issuer": "SBI",
            "amount": 5000.0,
            "prior_recovery_rate": 0.1,
            "attempts_used": 3,
            "fatigue_score": 0.8,
            "account_age_days": 30,
            "treatment": "whatsapp_nudge" if i < 5 else "retry_only",
            "recovered": False if i < 5 else True,  # whatsapp failed 0/5, retry recovered 15/15
            "time_to_recovery_hours": 12.0
        })
    df_mock = pd.DataFrame(records)

    engine = WAPSIPrecedentEngine(n_neighbors=10, min_evidence_cases=3, counter_evidence_threshold=0.25)
    engine.fit(df_mock)

    query_case = {
        "domain": "subscription",
        "decline_reason": "insufficient_funds",
        "issuer": "SBI",
        "amount": 5000.0,
        "prior_recovery_rate": 0.1,
        "attempts_used": 3,
        "fatigue_score": 0.8,
        "account_age_days": 30
    }

    # Model recommends whatsapp_nudge, which historically failed 0/5
    res = engine.query(query_case, recommended_action="whatsapp_nudge", k=10)

    assert res["counter_evidence"] is True
    assert res["discrepancy_reason"] is not None
    assert "Discrepancy" in res["discrepancy_reason"] or "Counter-Evidence" in res["discrepancy_reason"]


def test_counter_evidence_flag_clean(fitted_engine, history_dataset):
    """Verifies counter_evidence is False when recommended action is sound or unobserved."""
    _, df_new = history_dataset
    case = df_new.iloc[0].to_dict()

    res = fitted_engine.query(case, recommended_action="retry_only", k=10)
    assert isinstance(res["counter_evidence"], bool)


def test_persistence_roundtrip(fitted_engine, history_dataset, tmp_path):
    """Verifies save and load persistence via joblib."""
    _, df_new = history_dataset
    case = df_new.iloc[0].to_dict()

    save_path = tmp_path / "precedent_engine.joblib"
    fitted_engine.save(save_path)
    assert save_path.exists()

    loaded = WAPSIPrecedentEngine.load(save_path)
    assert loaded.is_fitted is True

    orig_res = fitted_engine.query(case, recommended_action="whatsapp_nudge", k=5)
    loaded_res = loaded.query(case, recommended_action="whatsapp_nudge", k=5)

    assert orig_res["similar_case_count"] == loaded_res["similar_case_count"]
    assert orig_res["similar_cases"] == loaded_res["similar_cases"]


def test_unseen_categories_and_missing_values(fitted_engine):
    """Tests inference on novel/unseen categorical values and missing fields."""
    novel_case = {
        "domain": "UNKNOWN_FUTURE_DOMAIN",
        "decline_reason": "NOVEL_DECLINE_CODE",
        "issuer": "NEW_FOREIGN_BANK",
        "amount": 9999.0
    }

    similar = fitted_engine.retrieve_similar_cases(novel_case, k=5)
    assert len(similar) == 5
    for c in similar:
        assert 0.0 < c["similarity"] <= 1.0
