"""
Unit tests for SyntheticRecoveryDataGenerator and Causal DGP.
"""

import pytest
import numpy as np
import pandas as pd
from wapsi.data.generator import SyntheticRecoveryDataGenerator
from wapsi.core.taxonomy import RecoveryAction, ErrorCategory


def test_synthetic_data_generator_shapes_and_columns():
    gen = SyntheticRecoveryDataGenerator(random_seed=42)
    df, pot = gen.generate_dataset(n_samples=200, observational_bias=True)

    assert len(df) == 200
    assert "payment_id" in df.columns
    assert "amount_in_inr" in df.columns
    assert "recovered" in df.columns
    assert "assigned_action" in df.columns
    assert "recovery_delay_sec" in df.columns

    # Verify potential outcomes dictionary
    assert "Y_potential" in pot
    assert "prob_potential" in pot
    assert "tau_ground_truth" in pot
    assert "timing_potential_sec" in pot
    
    n_actions = len(RecoveryAction)
    assert pot["Y_potential"].shape == (200, n_actions)
    assert pot["prob_potential"].shape == (200, n_actions)
    assert pot["tau_ground_truth"].shape == (200, n_actions)


def test_potential_outcomes_consistency():
    gen = SyntheticRecoveryDataGenerator(random_seed=123)
    df, pot = gen.generate_dataset(n_samples=300, observational_bias=False)

    # SUTVA check: observed outcome must match Y(A) for assigned action A
    assigned_indices = df["assigned_action_idx"].values
    observed_y = df["recovered"].values
    y_potential = pot["Y_potential"]

    for i in range(len(df)):
        act_idx = assigned_indices[i]
        assert observed_y[i] == y_potential[i, act_idx]


def test_generator_determinism():
    gen1 = SyntheticRecoveryDataGenerator(random_seed=999)
    df1, pot1 = gen1.generate_dataset(n_samples=100)

    gen2 = SyntheticRecoveryDataGenerator(random_seed=999)
    df2, pot2 = gen2.generate_dataset(n_samples=100)

    assert np.allclose(df1["amount_in_inr"].values, df2["amount_in_inr"].values)
    assert np.allclose(pot1["tau_ground_truth"], pot2["tau_ground_truth"])
