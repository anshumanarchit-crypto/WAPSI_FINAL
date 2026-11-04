"""
Unit tests for LLMDecisionExplainer.
"""

import pytest
from wapsi.explain.llm_explainer import LLMDecisionExplainer
from wapsi.core.taxonomy import RecoveryAction


def test_llm_plain_english_rationale():
    dummy_decision = {
        "recommended_action": RecoveryAction.WHATSAPP_ONE_CLICK_LINK.value,
        "recommended_action_name": "WhatsApp 1-Click Recovery Link",
        "individual_treatment_effect_uplift": 0.284,
        "baseline_organic_recovery_prob": 0.140,
        "expected_action_recovery_prob": 0.424,
        "net_expected_utility_inr": 138.50,
        "timing": {"delay_human_readable": "2 minutes"}
    }
    dummy_shap = {
        "positive_drivers": [
            {"feature_name": "Error Code: UPI_APP_TIMEOUT", "shap_contribution": 0.15}
        ]
    }

    rationale = LLMDecisionExplainer.generate_plain_english_rationale(
        decision_result=dummy_decision,
        shap_result=dummy_shap
    )

    assert "WhatsApp 1-Click" in rationale
    assert "+28.4%" in rationale
    assert "₹138.50" in rationale
    assert "UPI_APP_TIMEOUT" in rationale


def test_llm_customer_copy_generation():
    event = {
        "payment_id": "pay_test_99",
        "amount_in_inr": 2499.0,
        "merchant_id": "merch_blitz_retail",
        "error_code": "UPI_APP_TIMEOUT"
    }

    copy_res = LLMDecisionExplainer.generate_customer_copy(
        event_dict=event,
        selected_action=RecoveryAction.WHATSAPP_ONE_CLICK_LINK.value
    )

    assert copy_res["channel"] == "whatsapp"
    assert "2,499.00" in copy_res["body_text"]
    assert "https://rzp.io/r/pay_test_99" in copy_res["body_text"]
