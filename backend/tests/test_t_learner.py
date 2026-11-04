"""
Unit and integration tests for WAPSI T-Learner baseline and Model Registry.
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path
from src.data_generator import WapsiDataGenerator, RecoveryDataConfig, TREATMENTS
from src.t_learner import WAPSIUpliftModel, WAPSIFeaturePreprocessor
from src.model_registry import ModelRegistry


@pytest.fixture(scope="module")
def sample_splits():
    gen = WapsiDataGenerator(RecoveryDataConfig(n_samples=2500, random_seed=42))
    df_obs, df_gt = gen.generate()
    
    # Clean train and validation splits without potential outcomes
    train_df = df_obs.iloc[:1750].copy()
    val_df = df_obs.iloc[1750:].copy()
    return train_df, val_df, df_gt


def test_t_learner_fit_and_metadata(sample_splits):
    train_df, val_df, _ = sample_splits
    
    model = WAPSIUpliftModel(random_seed=42, model_version="1.0.0")
    model.fit(df_train=train_df, df_val=val_df)

    assert model.is_fitted is True
    assert len(model.models_) == len(TREATMENTS)

    # Validate metadata
    meta = model.get_metadata()
    assert meta["model_type"] == "MultiActionTLearner"
    assert meta["model_version"] == "1.0.0"
    assert meta["training_rows"] == 1750
    assert meta["random_seed"] == 42
    assert "training_timestamp" in meta
    assert len(meta["features_used"]) > 10
    assert meta["control_action"] == "no_action"
    assert "validation_metrics" in meta


def test_predict_action_outcomes_batch_and_single(sample_splits):
    train_df, val_df, _ = sample_splits
    model = WAPSIUpliftModel(random_seed=42)
    model.fit(train_df)

    # Batch DataFrame prediction
    batch_probs = model.predict_action_outcomes(val_df)
    assert len(batch_probs) == len(TREATMENTS)
    for act in TREATMENTS:
        assert isinstance(batch_probs[act], np.ndarray)
        assert len(batch_probs[act]) == len(val_df)
        assert (batch_probs[act] >= 0.0).all() and (batch_probs[act] <= 1.0).all()

    # Single dictionary prediction
    single_case = val_df.iloc[0].to_dict()
    single_probs = model.predict_action_outcomes(single_case)
    assert len(single_probs) == len(TREATMENTS)
    for act in TREATMENTS:
        assert isinstance(single_probs[act], float)
        assert 0.0 <= single_probs[act] <= 1.0


def test_predict_uplift_api(sample_splits):
    train_df, val_df, _ = sample_splits
    model = WAPSIUpliftModel(random_seed=42)
    model.fit(train_df)

    # Test single dictionary payload
    sample_case = {
        "domain": "ecommerce",
        "amount": 2499.0,
        "decline_reason": "upi_pin_timeout",
        "attempts_used": 1,
        "account_age_days": 120,
        "previous_failures": 1,
        "previous_recoveries": 2,
        "prior_recovery_rate": 0.6667,
        "day_of_week": 2,
        "hour": 14,
        "issuer": "HDFC",
        "bin_bucket": "classic",
        "fatigue_score": 0.15
    }

    uplifts = model.predict_uplift(sample_case)
    
    # Must contain exact 5 active treatments relative to no_action
    expected_keys = {"retry_only", "whatsapp_nudge", "voice_call", "email", "incentive_link"}
    assert set(uplifts.keys()) == expected_keys

    # Each value must be a Python float
    for action, tau_val in uplifts.items():
        assert isinstance(tau_val, float), f"Expected float for '{action}', got {type(tau_val)}"
        assert -1.0 <= tau_val <= 1.0

    # On UPI timeout in ecommerce, WhatsApp and Incentive should have positive uplift
    assert uplifts["whatsapp_nudge"] > 0.0


def test_strict_isolation_enforcement(sample_splits):
    train_df, _, df_gt = sample_splits
    model = WAPSIUpliftModel()

    # Attempting to fit on a dataset with potential outcomes must raise ValueError
    with pytest.raises(ValueError, match="Strict isolation violation"):
        model.fit(df_train=df_gt)


def test_joblib_save_and_load_roundtrip(sample_splits, tmp_path):
    train_df, val_df, _ = sample_splits
    model = WAPSIUpliftModel(random_seed=42)
    model.fit(train_df)

    sample_dict = val_df.iloc[0].to_dict()
    orig_uplifts = model.predict_uplift(sample_dict)

    # Save to disk
    save_file = tmp_path / "wapsi_t_learner_test.joblib"
    model.save(save_file)
    assert save_file.exists()

    # Load from disk
    loaded_model = WAPSIUpliftModel.load(save_file)
    assert loaded_model.is_fitted is True
    
    loaded_uplifts = loaded_model.predict_uplift(sample_dict)
    assert orig_uplifts == loaded_uplifts


def test_model_registry_integration(sample_splits, tmp_path):
    train_df, val_df, _ = sample_splits
    registry = ModelRegistry(registry_dir=str(tmp_path / "models"))

    model = WAPSIUpliftModel(random_seed=42, model_version="1.0.0")
    model.fit(train_df, df_val=val_df)

    # Register model
    artifact_path = registry.register_model(
        model=model,
        model_name="wapsi_t_learner",
        version="v1.0.0",
        set_as_production=True
    )
    assert Path(artifact_path).exists()

    # List models
    models_list = registry.list_models()
    assert len(models_list) == 1
    assert models_list[0]["version"] == "v1.0.0"
    assert models_list[0]["is_production"] is True

    # Retrieve model
    loaded_prod = registry.get_model(model_name="wapsi_t_learner", version="production")
    assert loaded_prod.is_fitted is True
    
    sample_case = val_df.iloc[0].to_dict()
    uplifts = loaded_prod.predict_uplift(sample_case)
    assert "whatsapp_nudge" in uplifts


def test_determinism_with_seed(sample_splits):
    train_df, val_df, _ = sample_splits
    
    m1 = WAPSIUpliftModel(random_seed=123)
    m1.fit(train_df)

    m2 = WAPSIUpliftModel(random_seed=123)
    m2.fit(train_df)

    p1 = m1.predict_uplift(val_df)
    p2 = m2.predict_uplift(val_df)

    for act in p1:
        np.testing.assert_array_almost_equal(p1[act], p2[act])
