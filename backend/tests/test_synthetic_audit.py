"""
Pytest test suite for WAPSI Synthetic Causal Environment Statistical Audit.
Validates all 10 causal inference engineering requirements, heterogeneous treatment effect
distributions, and WAPSI core thesis quadrants.
"""

import pytest
import pandas as pd
from evaluation.synthetic_audit import SyntheticCausalAuditor


@pytest.fixture(scope="module")
def audit_results(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("audit_output")
    auditor = SyntheticCausalAuditor(data_path="data/ground_truth_full.parquet")
    report = auditor.run_full_audit(output_dir=str(out_dir))
    return report


def test_q1_treatment_representation(audit_results):
    q1 = audit_results["q1_treatment_representation"]
    assert q1["is_passed"] is True, "Treatment arms are insufficiently represented"
    for t, data in q1["treatment_breakdown"].items():
        assert data["share"] >= 0.08, f"Treatment '{t}' has too low share: {data['share']*100:.1f}%"


def test_q2_treatment_effects_and_heterogeneity(audit_results):
    q2 = audit_results["q2_treatment_effects_and_hte"]
    assert q2["is_passed"] is True, "Treatment effects lack significant heterogeneous variance"
    for t, m in q2["overall_hte_metrics"].items():
        assert m["true_std"] >= 0.04, f"Treatment '{t}' CATE standard deviation is too small ({m['true_std']})"
        assert m["iqr"] > 0.05, f"Treatment '{t}' IQR is too small ({m['iqr']})"


def test_q3_whatsapp_heterogeneity(audit_results):
    q3 = audit_results["q3_whatsapp_heterogeneity"]
    assert q3["is_passed"] is True
    assert q3["share_high_uplift_over_20pct"] > 0.15, "WhatsApp lacks high-uplift cases"
    assert q3["share_low_uplift_under_5pct"] > 0.10, "WhatsApp lacks low-uplift / ineffective cases"
    assert q3["mean_uplift_on_upi_pin_timeout"] > q3["mean_uplift_on_bank_downtime"] + 0.15


def test_q4_retry_vs_whatsapp_segment_dominance(audit_results):
    q4 = audit_results["q4_retry_vs_whatsapp_dominance"]
    assert q4["is_passed"] is True
    # On technical errors, retry should beat WhatsApp
    assert q4["tech_gateway_retry_beats_whatsapp_share"] > 0.70
    # On UPI friction, WhatsApp should beat retry
    assert q4["upi_pin_timeout_whatsapp_beats_retry_share"] > 0.70


def test_q5_fatigue_decay_audit(audit_results):
    q5 = audit_results["q5_fatigue_impact"]
    assert q5["is_passed"] is True
    assert q5["whatsapp_decay_pct"] > 35.0, "Fatigue does not significantly degrade WhatsApp uplift"


def test_q6_prior_recovery_history(audit_results):
    q6 = audit_results["q6_prior_recovery_history"]
    assert q6["is_passed"] is True
    assert q6["correlation_prior_rate_with_p0"] > 0.25, "Prior recovery history does not influence baseline recovery"


def test_q7_issuer_timing(audit_results):
    q7 = audit_results["q7_issuer_timing_effects"]
    assert q7["is_passed"] is True
    assert len(q7["timing_by_issuer"]) >= 5


def test_q8_no_leakage_and_balanced_difficulty(audit_results):
    q8 = audit_results["q8_leakage_and_difficulty"]
    assert q8["is_passed"] is True
    # Baseline AUC must be between 0.65 and 0.85 (learnable but non-trivial)
    assert 0.65 <= q8["baseline_factual_auc"] <= 0.85, f"Unbalanced difficulty: AUC = {q8['baseline_factual_auc']}"


def test_q9_no_global_action_dominance(audit_results):
    q9 = audit_results["q9_global_action_dominance"]
    assert q9["is_passed"] is True
    assert q9["max_single_action_share"] < 0.55, f"Single action dominates unrealistically: {q9['max_single_action_share']}"


def test_q10_wapsi_core_thesis_quadrants(audit_results):
    q10 = audit_results["q10_wapsi_thesis_quadrants"]
    assert q10["is_passed"] is True
    assert q10["case_a_high_base_low_uplift_share"] >= 0.02, "Case A (Self-Curers: High Base, Low Uplift) is missing"
    assert q10["case_b_low_base_high_uplift_share"] >= 0.15, "Case B (Persuadables: Low Base, High Uplift) is missing"
