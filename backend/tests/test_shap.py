"""
Unit tests for CausalShapExplainer.
"""

import pytest
import pandas as pd
from wapsi.causal.t_learner import MultiActionTLearner
from wapsi.explain.shap_engine import CausalShapExplainer
from wapsi.data.generator import SyntheticRecoveryDataGenerator
from wapsi.core.taxonomy import RecoveryAction


def test_shap_explainer_local_attribution():
    gen = SyntheticRecoveryDataGenerator(random_seed=42)
    train_df, _ = gen.generate_dataset(n_samples=300)

    t_learner = MultiActionTLearner(random_seed=42)
    t_learner.fit(train_df)

    shap_explainer = CausalShapExplainer(t_learner)
    shap_explainer.initialize()

    sample_event = train_df.iloc[0].to_dict()
    explanation = shap_explainer.explain_instance(
        event_dict=sample_event,
        selected_action=RecoveryAction.WHATSAPP_ONE_CLICK_LINK.value,
        top_k=5
    )

    assert "top_features" in explanation
    assert len(explanation["top_features"]) <= 5
    assert "positive_drivers" in explanation
    assert "base_value_uplift" in explanation
