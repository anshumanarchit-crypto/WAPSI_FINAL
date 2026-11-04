"""
Unit tests for WAPSI SHAP-Based Causal Explainability Engine.
Razorpay AI Buildathon 2026 - Track 3

Tests:
  - Explainer initialization on T-Learner and X-Learner
  - explain_case output schema and frontend-safe JSON serializability
  - top_reasons, top_positive_features, and top_negative_features structure
  - Determinism on identical inputs
  - Specific action explanation vs default winner
  - SHAP attribution plot generation to disk
"""

import pytest
import json
import numpy as np
import pandas as pd
from pathlib import Path

from src.data_generator import WapsiDataGenerator, RecoveryDataConfig, TREATMENTS
from src.t_learner import WAPSIUpliftModel
from src.x_learner import WAPSIXLearner
from src.explainability import WAPSIShapExplainer

ACTIVE_TREATMENTS = [t for t in TREATMENTS if t != "no_action"]


@pytest.fixture(scope="module")
def causal_dataset():
    """Generates synthetic dataset for explainability tests."""
    gen = WapsiDataGenerator(RecoveryDataConfig(n_samples=2500, random_seed=42))
    df_obs, _ = gen.generate()
    train_n = int(len(df_obs) * 0.7)
    df_train = df_obs.iloc[:train_n].copy()
    df_test = df_obs.iloc[train_n:].copy()
    return df_train, df_test


@pytest.fixture(scope="module")
def fitted_t_learner(causal_dataset):
    """Returns a pre-fitted WAPSIUpliftModel."""
    df_train, _ = causal_dataset
    model = WAPSIUpliftModel(random_seed=42)
    model.fit(df_train)
    return model


@pytest.fixture(scope="module")
def fitted_x_learner(causal_dataset):
    """Returns a pre-fitted WAPSIXLearner."""
    df_train, _ = causal_dataset
    model = WAPSIXLearner(random_seed=42)
    model.fit(df_train)
    return model


def test_explainer_initialization_t_learner(fitted_t_learner):
    """Tests that WAPSIShapExplainer initializes TreeExplainers for T-Learner."""
    explainer = WAPSIShapExplainer(fitted_t_learner)
    assert explainer.is_initialized is False
    explainer.initialize()
    assert explainer.is_initialized is True
    assert len(explainer.explainers_) == len(TREATMENTS)


def test_explainer_initialization_x_learner(fitted_x_learner):
    """Tests that WAPSIShapExplainer initializes for X-Learner."""
    explainer = WAPSIShapExplainer(fitted_x_learner)
    explainer.initialize()
    assert explainer.is_initialized is True
    assert len(explainer.explainers_) > 0


def test_explain_case_schema(fitted_t_learner, causal_dataset):
    """Tests that explain_case returns the exact required dictionary schema."""
    _, df_test = causal_dataset
    explainer = WAPSIShapExplainer(fitted_t_learner).initialize()

    case = df_test.iloc[0].to_dict()
    res = explainer.explain_case(case)

    assert "action" in res
    assert "predicted_uplift" in res
    assert "base_uplift" in res
    assert "top_reasons" in res
    assert "top_positive_features" in res
    assert "top_negative_features" in res
    assert "rationale" in res

    assert res["action"] in TREATMENTS
    assert isinstance(res["predicted_uplift"], (float, int))
    assert isinstance(res["base_uplift"], (float, int))
    assert isinstance(res["top_reasons"], list)
    assert len(res["top_reasons"]) > 0


def test_top_reasons_item_structure(fitted_t_learner, causal_dataset):
    """Tests that each reason in top_reasons conforms to {feature, value, impact}."""
    _, df_test = causal_dataset
    explainer = WAPSIShapExplainer(fitted_t_learner).initialize()

    case = df_test.iloc[0].to_dict()
    res = explainer.explain_case(case, top_k=4)

    for item in res["top_reasons"]:
        assert "feature" in item
        assert "value" in item
        assert "impact" in item
        assert isinstance(item["feature"], str)
        assert isinstance(item["impact"], (float, int))


def test_frontend_safe_json_serializability(fitted_t_learner, causal_dataset):
    """Verifies that the entire explanation payload serializes cleanly to standard JSON."""
    _, df_test = causal_dataset
    explainer = WAPSIShapExplainer(fitted_t_learner).initialize()

    for i in range(min(10, len(df_test))):
        case = df_test.iloc[i].to_dict()
        res = explainer.explain_case(case)

        # Standard json.dumps must not raise TypeError (no numpy types, np.nan, or inf)
        json_str = json.dumps(res)
        assert isinstance(json_str, str)
        loaded = json.loads(json_str)
        assert loaded["action"] == res["action"]


def test_explain_specific_action(fitted_t_learner, causal_dataset):
    """Verifies that passing a specific action explains that action."""
    _, df_test = causal_dataset
    explainer = WAPSIShapExplainer(fitted_t_learner).initialize()

    case = df_test.iloc[0].to_dict()
    res_whatsapp = explainer.explain_case(case, action="whatsapp_nudge")
    res_retry = explainer.explain_case(case, action="retry_only")

    assert res_whatsapp["action"] == "whatsapp_nudge"
    assert res_retry["action"] == "retry_only"


def test_positive_and_negative_separation(fitted_t_learner, causal_dataset):
    """Verifies positive features have positive impact and negative have negative impact."""
    _, df_test = causal_dataset
    explainer = WAPSIShapExplainer(fitted_t_learner).initialize()

    case = df_test.iloc[0].to_dict()
    res = explainer.explain_case(case)

    for p in res["top_positive_features"]:
        assert p["impact"] > 0, f"Positive feature should have impact > 0, got {p['impact']}"

    for n in res["top_negative_features"]:
        assert n["impact"] < 0, f"Negative feature should have impact < 0, got {n['impact']}"


def test_deterministic_behavior(fitted_t_learner, causal_dataset):
    """Verifies that repeated explanations on the same case produce identical SHAP values."""
    _, df_test = causal_dataset
    explainer = WAPSIShapExplainer(fitted_t_learner).initialize()

    case = df_test.iloc[0].to_dict()
    res1 = explainer.explain_case(case, action="whatsapp_nudge")
    res2 = explainer.explain_case(case, action="whatsapp_nudge")

    assert res1["top_reasons"] == res2["top_reasons"]
    assert res1["predicted_uplift"] == res2["predicted_uplift"]


def test_generate_shap_plot_artifact(fitted_t_learner, causal_dataset, tmp_path):
    """Tests generating and saving local SHAP attribution plot."""
    _, df_test = causal_dataset
    explainer = WAPSIShapExplainer(fitted_t_learner).initialize()

    case = df_test.iloc[0].to_dict()
    plot_path = tmp_path / "test_demo_shap.png"

    saved_path = explainer.generate_shap_plot(
        case=case,
        action="whatsapp_nudge",
        save_path=str(plot_path)
    )

    assert Path(saved_path).exists()
    assert Path(saved_path).stat().st_size > 0
