"""
Unit tests for WAPSI Network Prior & Empirical Bayes Shrinkage Engine.
Razorpay AI Buildathon 2026 - Track 3

Tests:
  - Shrinkage weight mathematics across sample size regimes
  - Small n (10 cases) -> Network Prior dominates
  - Large n (10,000 cases) -> Merchant Evidence dominates
  - Fit on synthetic transaction data & segment priors
  - Output schema conformity & JSON serializability
  - Privacy constraint (no customer IDs or PII in learned prior state)
  - Persistence roundtrip (save and load via joblib)
"""

import pytest
import json
import numpy as np
import pandas as pd
from pathlib import Path

from src.data_generator import WapsiDataGenerator, RecoveryDataConfig, TREATMENTS
from src.network_prior import WAPSINetworkPrior, ACTIVE_TREATMENTS


@pytest.fixture(scope="module")
def network_dataset():
    """Generates synthetic dataset for network prior tests."""
    gen = WapsiDataGenerator(RecoveryDataConfig(n_samples=3000, random_seed=42))
    df_obs, _ = gen.generate()
    return df_obs


@pytest.fixture(scope="module")
def fitted_prior(network_dataset):
    """Returns a pre-fitted WAPSINetworkPrior."""
    prior = WAPSINetworkPrior(shrinkage_half_life=100.0)
    prior.fit(network_dataset)
    return prior


def test_shrinkage_weight_mathematics():
    """Verifies theoretical properties of hyperbolic shrinkage rule."""
    prior = WAPSINetworkPrior(shrinkage_half_life=100.0, shrinkage_rule="hyperbolic")

    # n = 0 -> w = 0.0
    assert prior.compute_shrinkage_weight(0) == 0.0

    # n = 10 -> w = 10 / 110 = 0.0909...
    w_10 = prior.compute_shrinkage_weight(10)
    assert abs(w_10 - (10.0 / 110.0)) < 1e-4
    assert w_10 < 0.10

    # n = 100 (half-life) -> w = 100 / 200 = 0.50
    assert abs(prior.compute_shrinkage_weight(100) - 0.50) < 1e-4

    # n = 1,000 -> w = 1000 / 1100 = 0.909...
    assert prior.compute_shrinkage_weight(1000) > 0.90

    # n = 10,000 -> w = 10000 / 10100 = 0.9901...
    w_10k = prior.compute_shrinkage_weight(10000)
    assert abs(w_10k - (10000.0 / 10100.0)) < 1e-4
    assert w_10k > 0.98


def test_alternative_shrinkage_rules():
    """Tests exponential and sigmoid shrinkage rules."""
    p_exp = WAPSINetworkPrior(shrinkage_half_life=100.0, shrinkage_rule="exponential")
    w_exp_10 = p_exp.compute_shrinkage_weight(10)
    w_exp_10k = p_exp.compute_shrinkage_weight(10000)
    assert 0.0 < w_exp_10 < 0.15
    assert w_exp_10k > 0.99

    p_sig = WAPSINetworkPrior(shrinkage_half_life=100.0, shrinkage_rule="sigmoid")
    assert abs(p_sig.compute_shrinkage_weight(100) - 0.50) < 1e-4


def test_fit_and_learned_priors(fitted_prior):
    """Verifies that network fitting computes valid positive/negative uplifts for all actions."""
    assert fitted_prior.is_fitted is True
    for act in ACTIVE_TREATMENTS:
        assert act in fitted_prior.global_network_uplifts_
        assert isinstance(fitted_prior.global_network_uplifts_[act], float)

    assert len(fitted_prior.segment_network_uplifts_) > 0
    assert len(fitted_prior.merchant_sample_counts_) > 0


def test_shrink_action_uplift_schema(fitted_prior):
    """Tests the exact contract and schema required for single action shrinkage."""
    res = fitted_prior.shrink_action_uplift(
        action="whatsapp_nudge",
        merchant_uplift=0.19,
        merchant_observations=30
    )

    assert "action" in res
    assert "network_uplift" in res
    assert "merchant_uplift" in res
    assert "merchant_observations" in res
    assert "merchant_weight" in res
    assert "combined_uplift" in res

    assert res["action"] == "whatsapp_nudge"
    assert res["merchant_observations"] == 30
    assert isinstance(res["merchant_weight"], float)
    assert isinstance(res["combined_uplift"], float)


def test_cold_start_merchant_10_cases_network_heavy(fitted_prior):
    """
    Demonstration Requirement:
    Merchant with 10 cases -> network-heavy (w ~ 0.09)
    """
    res = fitted_prior.shrink_action_uplift(
        action="whatsapp_nudge",
        merchant_uplift=0.02,     # Merchant estimated only +2% due to small noisy sample
        merchant_observations=10
    )

    # Merchant weight is low (~0.09), Network prior dominates (~0.91)
    assert res["merchant_weight"] < 0.12
    net_up = res["network_uplift"]
    # Combined uplift is closer to network prior than merchant estimate
    assert abs(res["combined_uplift"] - net_up) < abs(res["combined_uplift"] - 0.02)


def test_high_volume_merchant_10000_cases_merchant_heavy(fitted_prior):
    """
    Demonstration Requirement:
    Merchant with 10,000 cases -> merchant-heavy (w ~ 0.99)
    """
    res = fitted_prior.shrink_action_uplift(
        action="whatsapp_nudge",
        merchant_uplift=0.35,     # Large mature merchant has strong observed +35% uplift
        merchant_observations=10000
    )

    # Merchant weight is very high (> 0.98)
    assert res["merchant_weight"] > 0.98
    # Combined uplift is essentially equal to merchant estimate
    assert abs(res["combined_uplift"] - 0.35) < 0.01


def test_shrink_all_actions_multi_action(fitted_prior):
    """Tests shrinkage across all active recovery actions simultaneously."""
    raw_uplifts = {
        "retry_only": 0.15,
        "whatsapp_nudge": 0.28,
        "voice_call": 0.05,
        "email": 0.02,
        "incentive_link": 0.18
    }

    res = fitted_prior.shrink_all_actions(
        merchant_uplifts=raw_uplifts,
        merchant_observations=25,
        merchant_id="merch_startup_99"
    )

    assert res["merchant_id"] == "merch_startup_99"
    assert res["merchant_observations"] == 25
    assert "shrunk_uplifts" in res
    assert len(res["shrunk_uplifts"]) == len(raw_uplifts)
    assert "per_action_breakdown" in res


def test_privacy_guarantee(fitted_prior):
    """Verifies that no customer identifiers or PII exist in the prior's internal state."""
    state_str = json.dumps(fitted_prior.global_network_uplifts_) + json.dumps(fitted_prior.segment_network_uplifts_)
    assert "customer_id" not in state_str
    assert "cust_" not in state_str


def test_persistence_roundtrip(fitted_prior, tmp_path):
    """Verifies save and load persistence via joblib."""
    save_path = tmp_path / "network_prior.joblib"
    fitted_prior.save(save_path)
    assert save_path.exists()

    loaded = WAPSINetworkPrior.load(save_path)
    assert loaded.is_fitted is True
    assert loaded.global_network_uplifts_ == fitted_prior.global_network_uplifts_

    res_orig = fitted_prior.shrink_action_uplift("retry_only", 0.12, 50)
    res_loaded = loaded.shrink_action_uplift("retry_only", 0.12, 50)
    assert res_orig == res_loaded


def test_frontend_safe_json_serialization(fitted_prior):
    """Verifies that the entire shrinkage payload serializes to clean JSON."""
    raw_uplifts = {"whatsapp_nudge": 0.22, "retry_only": 0.14}
    res = fitted_prior.shrink_all_actions(raw_uplifts, 40)
    json_str = json.dumps(res)
    assert isinstance(json_str, str)
    loaded = json.loads(json_str)
    assert loaded["merchant_observations"] == 40
