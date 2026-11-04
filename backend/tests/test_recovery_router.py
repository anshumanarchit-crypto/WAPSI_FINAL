"""
Unit and scenario tests for WAPSIRecoveryRouter.
Validates causal uplift ranking, eligibility filtering, fallback to no_action,
and the 5 canonical deterministic decision scenarios.
"""

import pytest
import pandas as pd
from pathlib import Path
from src.data_generator import WapsiDataGenerator, RecoveryDataConfig
from src.t_learner import WAPSIUpliftModel
from src.recovery_router import WAPSIRecoveryRouter, get_deterministic_example_cases


@pytest.fixture(scope="module")
def fitted_router():
    manifest_path = Path("models/manifest.json")
    if manifest_path.exists():
        from src.model_registry import ModelRegistry
        registry = ModelRegistry("models")
        try:
            model = registry.get_model("wapsi_t_learner", "production")
            return WAPSIRecoveryRouter(model=model, enable_eligibility_rules=True)
        except Exception:
            pass

    train_path = Path("data/train.parquet")
    if train_path.exists():
        df_train = pd.read_parquet(train_path).iloc[:10000].copy()
    else:
        gen = WapsiDataGenerator(RecoveryDataConfig(n_samples=5000, random_seed=42))
        df_obs, _ = gen.generate()
        df_train = df_obs.iloc[:3500].copy()

    model = WAPSIUpliftModel(random_seed=42)
    model.fit(df_train)
    return WAPSIRecoveryRouter(model=model, enable_eligibility_rules=True)


def test_router_response_schema(fitted_router):
    sample_case = {
        "case_id": "case_test_99",
        "domain": "ecommerce",
        "amount": 1800.0,
        "decline_reason": "upi_pin_timeout",
        "attempts_used": 1,
        "account_age_days": 90,
        "previous_failures": 0,
        "previous_recoveries": 1,
        "prior_recovery_rate": 1.0,
        "day_of_week": 3,
        "hour": 14,
        "issuer": "HDFC",
        "bin_bucket": "classic",
        "fatigue_score": 0.10
    }

    res = fitted_router.route(sample_case)

    # Core required fields
    assert "recommended_action" in res
    assert "uplift" in res
    assert "action_scores" in res
    assert "action_rankings" in res
    assert "baseline_outcome_probability" in res
    assert "predicted_outcome_probability" in res
    assert "rationale" in res

    # Check action_scores dictionary format
    expected_actions = {"retry_only", "whatsapp_nudge", "voice_call", "email", "incentive_link"}
    assert set(res["action_scores"].keys()) == expected_actions
    for act, score in res["action_scores"].items():
        assert isinstance(score, float)

    # Check distinct probabilities vs uplift
    assert isinstance(res["baseline_outcome_probability"], float)
    assert isinstance(res["predicted_outcome_probability"], float)
    assert isinstance(res["uplift"], float)


def test_ranking_order_and_winner_selection(fitted_router):
    sample_case = {
        "domain": "ecommerce",
        "amount": 2500.0,
        "decline_reason": "user_cancelled_checkout",
        "attempts_used": 1,
        "account_age_days": 30,
        "previous_failures": 1,
        "previous_recoveries": 0,
        "prior_recovery_rate": 0.0,
        "day_of_week": 5,
        "hour": 18,
        "issuer": "SBI",
        "bin_bucket": "classic",
        "fatigue_score": 0.20
    }

    res = fitted_router.route(sample_case)
    rankings = res["action_rankings"]

    # Verify descending sort order by incremental uplift
    uplift_scores = [item["incremental_uplift"] for item in rankings]
    assert uplift_scores == sorted(uplift_scores, reverse=True)

    # Winner must match the top eligible action
    top_eligible = next(item for item in rankings if item["is_eligible"])
    assert res["recommended_action"] == top_eligible["action"]
    assert res["uplift"] == top_eligible["incremental_uplift"]


def test_eligibility_constraints(fitted_router):
    # Scenario A: Voice call during night hours (23:00 IST) -> voice_call must be ineligible
    case_night = {
        "domain": "b2b_saas",
        "amount": 15000.0,
        "decline_reason": "card_limit_exceeded",
        "attempts_used": 1,
        "hour": 23,  # Night hour
        "issuer": "HDFC",
        "bin_bucket": "corporate",
        "fatigue_score": 0.10
    }
    res_night = fitted_router.route(case_night)
    voice_item = next(item for item in res_night["action_rankings"] if item["action"] == "voice_call")
    assert voice_item["is_eligible"] is False
    assert any("night hours" in r for r in voice_item["ineligibility_reasons"])

    # Scenario B: User explicitly cancelled checkout -> retry_only must be ineligible
    case_cancel = {
        "domain": "ecommerce",
        "amount": 1200.0,
        "decline_reason": "user_cancelled_checkout",
        "attempts_used": 1,
        "hour": 15,
        "issuer": "ICICI",
        "bin_bucket": "classic",
        "fatigue_score": 0.15
    }
    res_cancel = fitted_router.route(case_cancel)
    retry_item = next(item for item in res_cancel["action_rankings"] if item["action"] == "retry_only")
    assert retry_item["is_eligible"] is False
    assert any("cancelled checkout" in r for r in retry_item["ineligibility_reasons"])

    # Scenario C: Merchant configuration disallows whatsapp_nudge
    merchant_cfg = {"disallowed_actions": ["whatsapp_nudge"]}
    res_merchant = fitted_router.route(case_cancel, merchant_config=merchant_cfg)
    wa_item = next(item for item in res_merchant["action_rankings"] if item["action"] == "whatsapp_nudge")
    assert wa_item["is_eligible"] is False
    assert any("merchant configuration" in r for r in wa_item["ineligibility_reasons"])


def test_5_deterministic_example_cases(fitted_router):
    examples = get_deterministic_example_cases()
    assert len(examples) == 5

    for ex in examples:
        res = fitted_router.route(ex)
        assert "recommended_action" in res
        assert "action_scores" in res
        
        # Verify Case 5 specifically: High Raw Payment Probability != High Intervention Uplift
        if ex["case_id"] == "case_ex5_organic_self_curer":
            # Baseline recovery must be high
            assert res["baseline_outcome_probability"] >= 0.30, f"Expected high baseline for loyal subscriber, got {res['baseline_outcome_probability']}"
            # Recommended action must be no_action
            assert res["recommended_action"] == "no_action"
            assert res["uplift"] == 0.0
            assert res["decision_type"] == "ORGANIC_NO_ACTION"


def test_batch_routing(fitted_router):
    df_batch = pd.DataFrame(get_deterministic_example_cases())
    results = fitted_router.batch_route(df_batch)
    
    assert len(results) == 5
    for r in results:
        assert "recommended_action" in r
        assert "uplift" in r
        assert "action_scores" in r
