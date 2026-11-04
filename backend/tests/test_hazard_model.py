"""
Unit tests for WAPSI Recovery Timing Hazard Model.
Razorpay AI Buildathon 2026 - Track 3

Tests:
  - Discrete time bucket mapping functions
  - Model fitting, internal representations, and metadata
  - recommend_timing output schema and mathematical constraints (sum to 1.0)
  - recommended_window argmax consistency
  - Issuer & BIN awareness
  - Persistence roundtrip (save and load via joblib)
  - Unseen categories and missing value robustness
  - Diagnostic plot generation
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from src.data_generator import WapsiDataGenerator, RecoveryDataConfig
from src.hazard_model import (
    WAPSIHazardModel,
    TIME_WINDOWS,
    map_hours_to_window,
    generate_timing_plots
)


@pytest.fixture(scope="module")
def timing_data():
    """Generates synthetic dataset for hazard model tests."""
    gen = WapsiDataGenerator(RecoveryDataConfig(n_samples=3000, random_seed=42))
    df_obs, _ = gen.generate()
    train_n = int(len(df_obs) * 0.7)
    df_train = df_obs.iloc[:train_n].copy()
    df_test = df_obs.iloc[train_n:].copy()
    return df_train, df_test


@pytest.fixture(scope="module")
def fitted_hazard_model(timing_data):
    """Returns a pre-fitted WAPSIHazardModel."""
    df_train, _ = timing_data
    model = WAPSIHazardModel(random_seed=42)
    model.fit(df_train)
    return model


def test_map_hours_to_window():
    """Tests continuous hours to discrete window mapping logic."""
    assert map_hours_to_window(0.0) == "0-24h"
    assert map_hours_to_window(12.5) == "0-24h"
    assert map_hours_to_window(24.0) == "0-24h"
    assert map_hours_to_window(24.01) == "24-48h"
    assert map_hours_to_window(48.0) == "24-48h"
    assert map_hours_to_window(48.01) == "48-72h"
    assert map_hours_to_window(72.0) == "48-72h"
    assert map_hours_to_window(72.1) == "72h+"
    assert map_hours_to_window(120.0) == "72h+"
    assert map_hours_to_window(np.nan) == "72h+"
    assert map_hours_to_window(-5.0) == "72h+"


def test_hazard_model_fit_and_metadata(fitted_hazard_model, timing_data):
    """Verifies that hazard model fits and stores expected metadata."""
    df_train, _ = timing_data
    model = fitted_hazard_model

    assert model.is_fitted is True
    meta = model.get_metadata()

    assert meta["model_type"] == "DiscreteTimeHazardModel"
    assert meta["training_rows"] > 0
    assert meta["random_seed"] == 42
    assert "windows" in meta
    assert meta["windows"] == TIME_WINDOWS
    assert "class_distribution" in meta


def test_recommend_timing_schema(fitted_hazard_model, timing_data):
    """Tests that recommend_timing returns exact required dictionary schema."""
    _, df_test = timing_data
    model = fitted_hazard_model

    case = df_test.iloc[0].to_dict()
    res = model.recommend_timing(case)

    # Core required keys from specification
    assert "recommended_window" in res
    assert "hazard_by_window" in res
    assert "expected_hours" in res
    assert "cumulative_hazard" in res
    assert "timing_drivers" in res

    assert res["recommended_window"] in TIME_WINDOWS
    assert isinstance(res["hazard_by_window"], dict)
    for w in TIME_WINDOWS:
        assert w in res["hazard_by_window"]
        assert isinstance(res["hazard_by_window"][w], (float, int))
        assert 0.0 <= res["hazard_by_window"][w] <= 1.0


def test_hazard_probabilities_sum_to_one(fitted_hazard_model, timing_data):
    """Verifies that hazard_by_window sums to 1.00 within float rounding tolerance."""
    _, df_test = timing_data
    model = fitted_hazard_model

    for i in range(min(15, len(df_test))):
        case = df_test.iloc[i].to_dict()
        res = model.recommend_timing(case)
        total_p = sum(res["hazard_by_window"].values())
        assert abs(total_p - 1.0) < 1e-3, f"Hazard probabilities should sum to 1.0, got {total_p}"


def test_recommended_window_matches_max_hazard(fitted_hazard_model, timing_data):
    """Verifies that recommended_window matches the window with maximum hazard score."""
    _, df_test = timing_data
    model = fitted_hazard_model

    for i in range(min(15, len(df_test))):
        case = df_test.iloc[i].to_dict()
        res = model.recommend_timing(case)
        hazards = res["hazard_by_window"]
        expected_winner = max(hazards.keys(), key=lambda k: hazards[k])
        assert res["recommended_window"] == expected_winner


def test_batch_recommend_timing(fitted_hazard_model, timing_data):
    """Tests batch inference on a DataFrame."""
    _, df_test = timing_data
    model = fitted_hazard_model

    sample_df = df_test.iloc[:10].copy()
    batch_res = model.batch_recommend_timing(sample_df)

    assert isinstance(batch_res, list)
    assert len(batch_res) == 10
    for item in batch_res:
        assert item["recommended_window"] in TIME_WINDOWS
        assert len(item["hazard_by_window"]) == 4


def test_issuer_and_bin_awareness(fitted_hazard_model):
    """Verifies that different issuer/BIN/decline contexts produce distinct hazard responses."""
    model = fitted_hazard_model

    # Instant technical glitch on private bank
    instant_case = {
        "amount": 1500.0,
        "attempts_used": 1,
        "account_age_days": 200,
        "previous_failures": 0,
        "previous_recoveries": 3,
        "prior_recovery_rate": 1.0,
        "day_of_week": 1,
        "hour": 14,
        "fatigue_score": 0.05,
        "domain": "ecommerce",
        "decline_reason": "technical_gateway_error",
        "issuer": "HDFC",
        "bin_bucket": "platinum"
    }

    # Extended funds replenishment on PSU bank
    delayed_case = {
        "amount": 25000.0,
        "attempts_used": 3,
        "account_age_days": 15,
        "previous_failures": 4,
        "previous_recoveries": 0,
        "prior_recovery_rate": 0.0,
        "day_of_week": 5,
        "hour": 23,
        "fatigue_score": 0.85,
        "domain": "b2b_saas",
        "decline_reason": "insufficient_funds",
        "issuer": "SBI",
        "bin_bucket": "classic"
    }

    res_instant = model.recommend_timing(instant_case)
    res_delayed = model.recommend_timing(delayed_case)

    assert res_instant["hazard_by_window"] != res_delayed["hazard_by_window"]
    assert res_instant["timing_drivers"]["issuer"] == "HDFC"
    assert res_delayed["timing_drivers"]["issuer"] == "SBI"


def test_persistence_roundtrip(fitted_hazard_model, timing_data, tmp_path):
    """Verifies save and load persistence via joblib."""
    _, df_test = timing_data
    model = fitted_hazard_model

    save_path = tmp_path / "hazard_model.joblib"
    model.save(save_path)
    assert save_path.exists()

    loaded = WAPSIHazardModel.load(save_path)
    assert loaded.is_fitted is True

    case = df_test.iloc[0].to_dict()
    orig_res = model.recommend_timing(case)
    loaded_res = loaded.recommend_timing(case)

    assert orig_res["recommended_window"] == loaded_res["recommended_window"]
    assert orig_res["hazard_by_window"] == loaded_res["hazard_by_window"]


def test_unseen_categories_and_missing_values(fitted_hazard_model):
    """Tests inference on novel/unseen categorical values and missing fields."""
    model = fitted_hazard_model

    novel_case = {
        "domain": "UNKNOWN_WEB3_APP",
        "decline_reason": "NOVEL_DECLINE_REASON_999",
        "issuer": "FOREIGN_NEOBANK",
        "bin_bucket": "SUPER_EXCLUSIVE",
        "amount": 8000.0
    }

    res = model.recommend_timing(novel_case)
    assert res["recommended_window"] in TIME_WINDOWS
    assert len(res["hazard_by_window"]) == 4
    assert np.isfinite(res["expected_hours"])


def test_generate_timing_plots(timing_data, fitted_hazard_model, tmp_path):
    """Tests that diagnostic timing plots are generated without errors."""
    df_train, _ = timing_data
    plots_dir = tmp_path / "timing_plots"

    plot_paths = generate_timing_plots(
        df=df_train,
        hazard_model=fitted_hazard_model,
        output_dir=str(plots_dir)
    )

    assert "timing_by_decline_reason" in plot_paths
    assert "timing_by_issuer" in plot_paths
    assert "timing_by_domain" in plot_paths
    assert "timing_by_bin_bucket" in plot_paths

    for p in plot_paths.values():
        assert Path(p).exists()
        assert Path(p).stat().st_size > 0
