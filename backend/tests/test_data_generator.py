"""
Comprehensive test suite for WapsiDataGenerator.
Validates schema, boundary ranges, determinism, SUTVA consistency,
treatment coverage, and strict isolation of hidden potential outcomes.
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path
from src.data_generator import (
    WapsiDataGenerator,
    RecoveryDataConfig,
    TREATMENTS,
    DOMAINS,
    DECLINE_REASONS,
    ISSUERS,
    BIN_BUCKETS
)


@pytest.fixture(scope="module")
def sample_data():
    cfg = RecoveryDataConfig(n_samples=2000, random_seed=42)
    generator = WapsiDataGenerator(config=cfg)
    df_obs, df_gt = generator.generate()
    return generator, df_obs, df_gt


def test_schema_and_column_presence(sample_data):
    _, df_obs, df_gt = sample_data
    
    expected_obs_cols = [
        "case_id", "merchant_id", "customer_id",
        "domain", "amount", "decline_reason", "attempts_used",
        "account_age_days", "previous_failures", "previous_recoveries",
        "prior_recovery_rate", "day_of_week", "hour",
        "issuer", "bin_bucket", "fatigue_score",
        "treatment", "recovered", "time_to_recovery_hours"
    ]

    for col in expected_obs_cols:
        assert col in df_obs.columns, f"Missing expected column in observed dataset: {col}"

    assert len(df_obs.columns) == len(expected_obs_cols), (
        f"Observed dataset should have exactly {len(expected_obs_cols)} columns, got {len(df_obs.columns)}"
    )

    # Check potential outcome columns in ground truth dataset
    for t in TREATMENTS:
        assert f"y_{t}" in df_gt.columns
        assert f"p_{t}" in df_gt.columns
        assert f"tau_{t}" in df_gt.columns


def test_data_ranges_and_constraints(sample_data):
    _, df_obs, _ = sample_data

    # Amount must be strictly positive
    assert (df_obs["amount"] > 0.0).all(), "Found non-positive transaction amounts."
    assert df_obs["amount"].min() >= 49.0
    assert df_obs["amount"].max() <= 200000.0

    # Categorical domain constraints
    assert set(df_obs["domain"].unique()).issubset(set(DOMAINS))
    assert set(df_obs["decline_reason"].unique()).issubset(set(DECLINE_REASONS))
    assert set(df_obs["issuer"].unique()).issubset(set(ISSUERS))
    assert set(df_obs["bin_bucket"].unique()).issubset(set(BIN_BUCKETS))
    assert set(df_obs["treatment"].unique()) == set(TREATMENTS)

    # Attempts used in [1, 4]
    assert set(df_obs["attempts_used"].unique()).issubset({1, 2, 3, 4})

    # Temporal ranges
    assert (df_obs["day_of_week"] >= 0).all() and (df_obs["day_of_week"] <= 6).all()
    assert (df_obs["hour"] >= 0).all() and (df_obs["hour"] <= 23).all()

    # Prior recovery rate in [0.0, 1.0] and no NaNs / infs
    assert not df_obs["prior_recovery_rate"].isna().any()
    assert not np.isinf(df_obs["prior_recovery_rate"]).any()
    assert (df_obs["prior_recovery_rate"] >= 0.0).all() and (df_obs["prior_recovery_rate"] <= 1.0).all()

    # Fatigue score bounded in [0.0, 1.0]
    assert (df_obs["fatigue_score"] >= 0.0).all() and (df_obs["fatigue_score"] <= 1.0).all()

    # Outcome binary in {0, 1}
    assert set(df_obs["recovered"].unique()).issubset({0, 1})

    # Time to recovery: strictly positive for recovered, NaN for non-recovered
    recovered_mask = (df_obs["recovered"] == 1)
    assert (df_obs.loc[recovered_mask, "time_to_recovery_hours"] > 0.0).all()
    assert df_obs.loc[~recovered_mask, "time_to_recovery_hours"].isna().all()


def test_determinism_with_seed():
    cfg1 = RecoveryDataConfig(n_samples=500, random_seed=999)
    gen1 = WapsiDataGenerator(cfg1)
    df1_obs, df1_gt = gen1.generate()

    cfg2 = RecoveryDataConfig(n_samples=500, random_seed=999)
    gen2 = WapsiDataGenerator(cfg2)
    df2_obs, df2_gt = gen2.generate()

    pd.testing.assert_frame_equal(df1_obs, df2_obs)
    pd.testing.assert_frame_equal(df1_gt, df2_gt)


def test_sutva_potential_outcome_consistency(sample_data):
    """
    Validates Stable Unit Treatment Value Assumption (SUTVA):
    Factual observed outcome Y_obs must equal Y(A_obs) for the assigned treatment A_obs.
    """
    _, df_obs, df_gt = sample_data

    for _, row in df_gt.iterrows():
        assigned_t = row["treatment"]
        observed_y = row["recovered"]
        potential_y = row[f"y_{assigned_t}"]
        assert observed_y == potential_y, f"SUTVA violation for case {row['case_id']}: Y_obs={observed_y} != Y({assigned_t})={potential_y}"


def test_no_leakage_in_public_dataset(sample_data, tmp_path):
    generator, df_obs, df_gt = sample_data
    
    # Perform split and export to temp directory
    export_dict = generator.split_and_export(df_obs, df_gt, output_dir=str(tmp_path))

    train_df = pd.read_parquet(tmp_path / "train.parquet")
    val_df = pd.read_parquet(tmp_path / "val.parquet")
    test_df = pd.read_parquet(tmp_path / "test.parquet")

    # 1. Verify completely disjoint case IDs
    train_ids = set(train_df["case_id"])
    val_ids = set(val_df["case_id"])
    test_ids = set(test_df["case_id"])

    assert len(train_ids.intersection(val_ids)) == 0, "Leakage detected: overlapping case_id between train and val"
    assert len(train_ids.intersection(test_ids)) == 0, "Leakage detected: overlapping case_id between train and test"
    assert len(val_ids.intersection(test_ids)) == 0, "Leakage detected: overlapping case_id between val and test"

    # 2. Strict Potential Outcome Leakage Check:
    # Ensure NO hidden counterfactual columns exist in train, val, or test
    hidden_forbidden_substrings = ["y_", "p_", "tau_", "t_", "optimal_treatment", "oracle", "archetype"]
    for dataset_name, df in [("train", train_df), ("val", val_df), ("test", test_df)]:
        for col in df.columns:
            if col in ["day_of_week"]: # legitimate feature
                continue
            for forbidden in hidden_forbidden_substrings:
                if col.startswith(forbidden) or col == forbidden:
                    pytest.fail(f"Potential outcome leakage in public {dataset_name} set: '{col}' should not be exposed!")


def test_treatment_coverage_and_heterogeneity(sample_data):
    _, df_obs, df_gt = sample_data

    # Every treatment must have sufficient sample coverage
    treat_counts = df_obs["treatment"].value_counts()
    for t in TREATMENTS:
        assert treat_counts[t] >= 50, f"Treatment '{t}' has underrepresented coverage ({treat_counts.get(t, 0)} cases)"

    # Heterogeneous uplift check: mean uplift must vary across treatments
    mean_uplifts = {t: df_gt[f"tau_{t}"].mean() for t in TREATMENTS if t != "no_action"}
    uplift_values = list(mean_uplifts.values())
    assert max(uplift_values) > min(uplift_values) + 0.05, "Treatment effects are suspiciously uniform (lacks HTE)."
