"""
Unit and integration tests for Causal Meta-Learners (T-Learner, X-Learner) and Uplift Evaluation.
"""

import pytest
import numpy as np
import pandas as pd
from wapsi.data.generator import SyntheticRecoveryDataGenerator
from wapsi.causal.t_learner import MultiActionTLearner
from wapsi.causal.x_learner import MultiActionXLearner
from wapsi.causal.evaluation import UpliftEvaluator
from wapsi.causal.engine import CausalDecisionEngine
from wapsi.core.taxonomy import RecoveryAction


@pytest.fixture(scope="module")
def sample_datasets():
    gen = SyntheticRecoveryDataGenerator(random_seed=42)
    train_df, train_pot = gen.generate_dataset(n_samples=600, observational_bias=True)
    val_df, val_pot = gen.generate_dataset(n_samples=250, observational_bias=True)
    return train_df, train_pot, val_df, val_pot


def test_t_learner_fit_predict(sample_datasets):
    train_df, _, val_df, _ = sample_datasets
    t_learner = MultiActionTLearner(random_seed=42)
    t_learner.fit(train_df)

    assert t_learner.is_fitted
    probs = t_learner.predict_probabilities(val_df)
    uplifts = t_learner.predict_uplift(val_df)

    assert len(probs) == len(RecoveryAction)
    assert len(uplifts) == len(RecoveryAction)
    
    # Control uplift must be identically zero
    assert np.allclose(uplifts[RecoveryAction.NO_ACTION.value], 0.0)

    # Probabilities must be bounded in (0, 1)
    for act, p in probs.items():
        assert np.all(p >= 0.0) and np.all(p <= 1.0)


def test_x_learner_fit_predict(sample_datasets):
    train_df, _, val_df, _ = sample_datasets
    x_learner = MultiActionXLearner(random_seed=42)
    x_learner.fit(train_df)

    assert x_learner.is_fitted
    uplifts = x_learner.predict_uplift(val_df)
    probs = x_learner.predict_probabilities(val_df)

    assert len(uplifts) == len(RecoveryAction)
    assert np.allclose(uplifts[RecoveryAction.NO_ACTION.value], 0.0)
    for act, p in probs.items():
        assert np.all(p >= 0.0) and np.all(p <= 1.0)


def test_qini_and_auuc_evaluation(sample_datasets):
    _, _, val_df, _ = sample_datasets
    y_true = val_df["recovered"].values
    t_flag = (val_df["assigned_action"] == RecoveryAction.WHATSAPP_ONE_CLICK_LINK.value).astype(int).values
    dummy_scores = np.random.default_rng(42).uniform(0, 1, size=len(val_df))

    qini_res = UpliftEvaluator.compute_qini_curve(
        y_true=y_true,
        treatment=t_flag,
        uplift_score=dummy_scores,
        n_bins=20
    )

    assert "qini_score" in qini_res
    assert "population_fraction" in qini_res
    assert len(qini_res["population_fraction"]) > 0

    deciles = UpliftEvaluator.compute_uplift_deciles(
        y_true=y_true,
        treatment=t_flag,
        uplift_score=dummy_scores,
        n_deciles=5
    )
    assert len(deciles) == 5


def test_causal_decision_engine_decide(sample_datasets):
    train_df, _, val_df, _ = sample_datasets
    engine = CausalDecisionEngine(random_seed=42)
    engine.train_pipeline(train_df=train_df, val_df=val_df)

    sample_event = val_df.iloc[0].to_dict()
    decision = engine.decide(sample_event)

    assert "recommended_action" in decision
    assert "net_expected_utility_inr" in decision
    assert "conformal_uplift_interval" in decision
    assert "all_action_rankings" in decision
    assert len(decision["all_action_rankings"]) == len(RecoveryAction)
