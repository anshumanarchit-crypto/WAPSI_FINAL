"""
Unit tests for WAPSI Multi-Action X-Learner.
Razorpay AI Buildathon 2026 - Track 3

Tests:
  - Model fitting, internal stage models, metadata
  - predict_action_outcomes (single case and batch DataFrame)
  - predict_uplift (single case and batch DataFrame)
  - Strict potential outcome isolation enforcement
  - Persistence roundtrip (save and load via joblib)
  - ModelRegistry integration (register and get)
  - Seed determinism
  - Recovery router integration
  - Propensity weighting and numerical stability
  - Unseen categories and missing features
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from src.data_generator import WapsiDataGenerator, RecoveryDataConfig, TREATMENTS
from src.x_learner import WAPSIXLearner
from src.model_registry import ModelRegistry
from src.recovery_router import WAPSIRecoveryRouter

ACTIVE_TREATMENTS = [t for t in TREATMENTS if t != "no_action"]
CONTROL = "no_action"


@pytest.fixture(scope="module")
def synthetic_data():
    """Generates synthetic dataset for X-Learner tests."""
    gen = WapsiDataGenerator(RecoveryDataConfig(n_samples=3000, random_seed=42))
    df_obs, df_gt = gen.generate()
    train_n = int(len(df_obs) * 0.7)
    df_train = df_obs.iloc[:train_n].copy()
    df_val = df_obs.iloc[train_n:train_n + 300].copy()
    df_test = df_obs.iloc[train_n + 300:].copy()
    return df_train, df_val, df_test, df_gt


@pytest.fixture(scope="module")
def fitted_x_learner(synthetic_data):
    """Returns a pre-fitted WAPSIXLearner on observed training data."""
    df_train, df_val, _, _ = synthetic_data
    model = WAPSIXLearner(random_seed=42)
    model.fit(df_train, df_val=df_val)
    return model


def test_x_learner_fit_and_metadata(fitted_x_learner, synthetic_data):
    """Verifies that X-Learner fits all stages and populates metadata correctly."""
    df_train, _, _, _ = synthetic_data
    model = fitted_x_learner

    assert model.is_fitted is True

    # Check Stage 1 response models
    assert model.control_action in model.mu_models_
    for act in model.active_treatments:
        assert act in model.mu_models_

    # Check Stage 3 effect models (tau_0 and tau_1)
    for act in model.active_treatments:
        assert act in model.tau_models_
        assert "tau_0" in model.tau_models_[act]
        assert "tau_1" in model.tau_models_[act]

    # Check Stage 4 propensity models
    for act in model.active_treatments:
        assert act in model.propensity_models_

    # Check metadata
    meta = model.get_metadata()
    assert meta["model_type"] == "MultiActionXLearner"
    assert meta["training_rows"] == len(df_train)
    assert meta["random_seed"] == 42
    assert len(meta["features_used"]) > 0
    assert "validation_metrics" in meta


def test_predict_action_outcomes_batch_and_single(fitted_x_learner, synthetic_data):
    """Tests action outcome probabilities for single case and batch DataFrame."""
    _, _, df_test, _ = synthetic_data
    model = fitted_x_learner

    # 1. Single dict prediction
    single_case = df_test.iloc[0].to_dict()
    single_probs = model.predict_action_outcomes(single_case)

    assert isinstance(single_probs, dict)
    assert len(single_probs) == len(TREATMENTS)
    for act in TREATMENTS:
        assert act in single_probs
        prob = single_probs[act]
        assert isinstance(prob, (float, int))
        assert 0.0 <= prob <= 1.0

    # 2. Batch DataFrame prediction
    batch_probs = model.predict_action_outcomes(df_test)
    assert isinstance(batch_probs, dict)
    for act in TREATMENTS:
        assert isinstance(batch_probs[act], np.ndarray)
        assert len(batch_probs[act]) == len(df_test)
        assert np.all(batch_probs[act] >= 0.0)
        assert np.all(batch_probs[act] <= 1.0)


def test_predict_uplift_api(fitted_x_learner, synthetic_data):
    """Tests uplift prediction API for single case and batch."""
    _, _, df_test, _ = synthetic_data
    model = fitted_x_learner

    # Single case
    single_case = df_test.iloc[0].to_dict()
    single_uplift = model.predict_uplift(single_case)

    assert isinstance(single_uplift, dict)
    assert len(single_uplift) == len(ACTIVE_TREATMENTS)
    assert CONTROL not in single_uplift  # Uplift is defined vs control

    for act in ACTIVE_TREATMENTS:
        assert act in single_uplift
        assert isinstance(single_uplift[act], (float, int))
        assert -1.0 <= single_uplift[act] <= 1.0

    # Batch DataFrame
    batch_uplift = model.predict_uplift(df_test)
    for act in ACTIVE_TREATMENTS:
        assert isinstance(batch_uplift[act], np.ndarray)
        assert len(batch_uplift[act]) == len(df_test)
        assert np.all(batch_uplift[act] >= -1.0)
        assert np.all(batch_uplift[act] <= 1.0)


def test_strict_isolation_enforcement(synthetic_data):
    """Verifies that X-Learner rejects training data with potential outcome columns."""
    _, _, _, df_gt = synthetic_data
    model = WAPSIXLearner(random_seed=42)

    # Attempt to pass ground truth DataFrame containing tau_*, y_*, p_*
    with pytest.raises(ValueError, match="Strict isolation violation"):
        model.fit(df_gt)


def test_joblib_save_and_load_roundtrip(fitted_x_learner, synthetic_data, tmp_path):
    """Tests model persistence roundtrip via joblib."""
    _, _, df_test, _ = synthetic_data
    model = fitted_x_learner

    save_path = tmp_path / "x_learner_test.joblib"
    model.save(save_path)
    assert save_path.exists()

    loaded_model = WAPSIXLearner.load(save_path)
    assert loaded_model.is_fitted is True

    # Predictions before and after save must be identical
    orig_uplifts = model.predict_uplift(df_test)
    loaded_uplifts = loaded_model.predict_uplift(df_test)

    for act in ACTIVE_TREATMENTS:
        np.testing.assert_array_almost_equal(orig_uplifts[act], loaded_uplifts[act])


def test_model_registry_integration(fitted_x_learner, synthetic_data, tmp_path):
    """Tests registering and retrieving X-Learner in ModelRegistry."""
    _, _, df_test, _ = synthetic_data
    model = fitted_x_learner

    registry = ModelRegistry(registry_dir=str(tmp_path / "model_reg"))
    art_path = registry.register_model(
        model=model,
        model_name="wapsi_x_learner",
        version="v1.0.0",
        set_as_production=True
    )
    assert Path(art_path).exists()

    retrieved = registry.get_model("wapsi_x_learner", version="production")
    assert isinstance(retrieved, WAPSIXLearner)
    assert retrieved.is_fitted is True

    # Check prediction matches
    sample = df_test.iloc[:5]
    np.testing.assert_array_almost_equal(
        model.predict_uplift(sample)["whatsapp_nudge"],
        retrieved.predict_uplift(sample)["whatsapp_nudge"]
    )


def test_determinism_with_seed(synthetic_data):
    """Tests that two X-Learner instances trained with the same seed yield identical predictions."""
    df_train, _, df_test, _ = synthetic_data

    m1 = WAPSIXLearner(random_seed=123).fit(df_train)
    m2 = WAPSIXLearner(random_seed=123).fit(df_train)

    u1 = m1.predict_uplift(df_test)
    u2 = m2.predict_uplift(df_test)

    for act in ACTIVE_TREATMENTS:
        np.testing.assert_array_almost_equal(u1[act], u2[act])


def test_recovery_router_with_x_learner(fitted_x_learner, synthetic_data):
    """Verifies that WAPSIRecoveryRouter works seamlessly with WAPSIXLearner."""
    _, _, df_test, _ = synthetic_data
    router = WAPSIRecoveryRouter(model=fitted_x_learner)

    case = df_test.iloc[0].to_dict()
    decision = router.route(case)

    assert "recommended_action" in decision
    assert "uplift" in decision
    assert "action_scores" in decision
    assert "action_rankings" in decision
    assert "baseline_outcome_probability" in decision
    assert "predicted_outcome_probability" in decision
    assert "rationale" in decision

    assert decision["recommended_action"] in TREATMENTS
    assert isinstance(decision["uplift"], (float, int))


def test_unseen_categories_handling(fitted_x_learner):
    """Verifies that preprocessor and model gracefully handle unseen categorical levels."""
    case_with_novel_cats = {
        "amount": 4999.0,
        "attempts_used": 1,
        "account_age_days": 100,
        "previous_failures": 0,
        "previous_recoveries": 2,
        "prior_recovery_rate": 1.0,
        "day_of_week": 2,
        "hour": 14,
        "fatigue_score": 0.1,
        "domain": "NEVER_SEEN_CRYPTO_DOMAIN",
        "decline_reason": "NOVEL_DECLINE_CODE",
        "issuer": "UNKNOWN_FOREIGN_BANK",
        "bin_bucket": "SUPER_PREMIUM"
    }

    uplifts = fitted_x_learner.predict_uplift(case_with_novel_cats)
    assert isinstance(uplifts, dict)
    for act in ACTIVE_TREATMENTS:
        assert isinstance(uplifts[act], (float, int))
        assert np.isfinite(uplifts[act])
