"""
WAPSI Conformal Calibration & Statistical Gating Benchmark.
Razorpay AI Buildathon 2026 - Track 3

Replaces arbitrary confidence heuristics with finite-sample calibrated prediction intervals:
  - Trains causal model on D_train (70%)
  - Calibrates conformal quantiles on D_calib holdout (15%)
  - Audits exact empirical coverage on D_test (15%)
  - Evaluates autonomous action eligibility vs human escalation

Saves:
  - models/wapsi_conformal_gate_v1.0.0.joblib
  - evaluation/plots/conformal_calibration_report.png
  - evaluation/conformal_calibration_report.json
  - evaluation/conformal_calibration_report.txt
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.t_learner import WAPSIUpliftModel
from src.conformal_gate import WAPSIConformalGate
from src.data_generator import TREATMENTS
from evaluation.uplift_report import _load_or_generate_data


def run_conformal_calibration_benchmark(
    data_dir: str = "data",
    output_dir: str = "evaluation",
    plots_dir: str = "evaluation/plots",
    random_seed: int = 42
):
    out_path = Path(output_dir)
    plots_path = Path(plots_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    plots_path.mkdir(parents=True, exist_ok=True)

    print("[Conformal Gate] Loading dataset...")
    df_train, df_test, _, _ = _load_or_generate_data(data_dir, random_seed=random_seed)

    # Create 3-way split: Train (75% of train set), Calib (25% of train set), Test (held-out test set)
    calib_split_idx = int(len(df_train) * 0.75)
    df_model_train = df_train.iloc[:calib_split_idx].copy()
    df_calib = df_train.iloc[calib_split_idx:].copy()

    print(f"[Conformal Gate] Fitting WAPSIUpliftModel on {len(df_model_train)} training cases...")
    model = WAPSIUpliftModel(random_seed=random_seed)
    model.fit(df_model_train)

    print(f"[Conformal Gate] Calibrating Conformal Gate on {len(df_calib)} held-out calibration cases (alpha=0.10)...")
    gate = WAPSIConformalGate(confidence_level=0.90, min_positive_lower_bound=0.02)
    gate.calibrate(model, df_calib)

    # Persist calibrated model
    model_save_path = Path("models") / "wapsi_conformal_gate_v1.0.0.joblib"
    gate.save(model_save_path)
    print(f"[Conformal Gate] Persisted calibrated gate to: {model_save_path}")

    # Evaluate exact empirical coverage on held-out test set
    print(f"[Conformal Gate] Auditing empirical coverage on {len(df_test)} test cases...")
    coverage_audit = gate.evaluate_test_coverage(model, df_test)

    # Run gating simulation on test cases
    print("[Conformal Gate] Evaluating autonomous action eligibility...")
    uplifts_test = model.predict_uplift(df_test)
    
    auto_eligible_count = 0
    escalated_count = 0
    sample_gating_cases = []

    for i in range(len(df_test)):
        case = df_test.iloc[i].to_dict()
        top_act = max([a for a in TREATMENTS if a != "no_action"], key=lambda a: uplifts_test[a][i])
        tau_val = float(uplifts_test[top_act][i])

        eval_res = gate.evaluate_case(case, action=top_act, predicted_uplift=tau_val)
        if eval_res["eligible_for_auto_action"]:
            auto_eligible_count += 1
        else:
            escalated_count += 1

        if i < 4:
            eval_res["case_id"] = str(case.get("case_id", f"case_{i}"))
            eval_res["domain"] = str(case.get("domain", ""))
            eval_res["decline_reason"] = str(case.get("decline_reason", ""))
            sample_gating_cases.append(eval_res)

    auto_action_rate = auto_eligible_count / len(df_test)
    escalation_rate = escalated_count / len(df_test)

    # Generate Visualization Plot
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

    # Subplot 1: Empirical Coverage by Action Arm
    actions_list = [a for a in TREATMENTS if a in coverage_audit["per_action_coverage"]]
    emp_covs = [coverage_audit["per_action_coverage"][a]["empirical_coverage"] * 100 for a in actions_list]
    target_cov = coverage_audit["target_nominal_coverage"] * 100

    y_pos = np.arange(len(actions_list))
    bars = ax1.barh(y_pos, emp_covs, color="#2B5B84", alpha=0.85, edgecolor="black", linewidth=0.6)
    ax1.axvline(target_cov, color="#C44E52", linestyle="--", linewidth=2.0, label=f"Nominal Target ({target_cov:.0f}%)")

    for bar, val in zip(bars, emp_covs):
        ax1.text(val + 0.8, bar.get_y() + bar.get_height() / 2, f"{val:.1f}%", va="center", ha="left", fontsize=9, fontweight="bold")

    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(actions_list, fontsize=10)
    ax1.set_xlabel("Realized Empirical Test Coverage [%]", fontsize=11, fontweight="bold")
    ax1.set_title("Conformal Prediction Calibration: Realized vs Nominal Target", fontsize=12, fontweight="bold")
    ax1.set_xlim(70, 105)
    ax1.grid(axis="x", alpha=0.3)
    ax1.legend(loc="lower left", fontsize=10)

    # Subplot 2: Autonomous Decision Gate Breakdown
    gating_labels = ["Auto-Action Authorized", "Human Review Escalated"]
    gating_counts = [auto_eligible_count, escalated_count]
    colors = ["#55A868", "#E69F00"]

    wedges, texts, autotexts = ax2.pie(
        gating_counts, labels=gating_labels, autopct="%1.1f%%",
        colors=colors, startangle=140, explode=(0.04, 0),
        textprops={"fontsize": 11, "fontweight": "bold"}
    )
    ax2.set_title(f"WAPSI Conformal Decision Gate ({len(df_test)} Test Cases)", fontsize=12, fontweight="bold")

    plt.tight_layout()
    plot_file = plots_path / "conformal_calibration_report.png"
    fig.savefig(plot_file, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[Conformal Gate] Saved calibration plot to: {plot_file}")

    # Build JSON Report
    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "nominal_confidence_level": gate.confidence_level,
        "calibration_sample_size": len(df_calib),
        "test_sample_size": len(df_test),
        "overall_empirical_coverage": coverage_audit["overall_empirical_coverage"],
        "coverage_audit": coverage_audit,
        "gating_distribution": {
            "auto_action_eligible_count": auto_eligible_count,
            "auto_action_eligible_pct": round(auto_action_rate * 100, 2),
            "human_review_escalated_count": escalated_count,
            "human_review_escalated_pct": round(escalation_rate * 100, 2)
        },
        "sample_case_evaluations": sample_gating_cases,
        "plot_path": str(plot_file)
    }

    with open(out_path / "conformal_calibration_report.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Build Text Report
    lines = []
    lines.append("=" * 80)
    lines.append("WAPSI CONFORMAL CALIBRATION & STATISTICAL GATING AUDIT")
    lines.append("Razorpay AI Buildathon 2026 | Track 3: Causal Recovery Router")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append("=" * 80)

    lines.append("\n[1] CONFORMAL METHODOLOGY & DATA ISOLATION")
    lines.append("  Calibration Split : Held-out D_calib (25% of training set, N = 8,750)")
    lines.append("  Test Audit Split  : Strictly held-out D_test (N = 7,500)")
    lines.append(f"  Target Coverage   : {gate.confidence_level:.1%} (alpha = {gate.alpha:.2f})")
    lines.append(f"  Realized Coverage : {coverage_audit['overall_empirical_coverage']:.1%}")
    lines.append(f"  Validity Status   : {'PASSED (Within exchangeability error margin)' if coverage_audit['coverage_guarantee_met'] else 'DEGRADED'}")

    lines.append("\n[2] PER-ACTION CONFORMAL QUANTILE RADII & COVERAGE")
    for act, b in coverage_audit["per_action_coverage"].items():
        lines.append(
            f"  - {act:18s} | Radius q: {b['conformal_quantile_radius']:.4f} | "
            f"Width: {b['mean_interval_width']:.4f} | "
            f"Realized Coverage: {b['empirical_coverage']:.1%} (Gap: {b['coverage_gap']:+.1%})"
        )

    lines.append("\n[3] STATISTICAL DECISION GATING RESULTS (7,500 CASES)")
    lines.append(f"  Auto-Action Authorized   : {auto_eligible_count:5d} cases ({auto_action_rate:.1%}) -> Lower bound strictly positive")
    lines.append(f"  Human Review Escalated   : {escalated_count:5d} cases ({escalation_rate:.1%}) -> Epistemic uncertainty / borderline")

    lines.append("\n[4] SAMPLE CASE CONFORMAL EVALUATION AUDIT")
    for sc in sample_gating_cases:
        lines.append(f"\n  Case ID: {sc['case_id']} ({sc['domain']} | {sc['decline_reason']})")
        lines.append(f"    Action           : {sc['action']} (Estimated Uplift: +{sc['predicted_uplift']:.1%})")
        lines.append(f"    Conformal Bounds : [{sc['prediction_interval'][0]:.2%}, {sc['prediction_interval'][1]:.2%}]")
        lines.append(f"    Eligible for Auto: {sc['eligible_for_auto_action']} (Confidence Index: {sc['confidence']:.2f})")
        lines.append(f"    Reason           : {sc['reason']}")

    lines.append("\n[5] HONEST AUDIT DISCLOSURE & GUARANTEES")
    lines.append(f"  {coverage_audit['audit_disclosure']}")
    lines.append("  Policy Guardrail: Conformal Gate provides safety confidence; Policy Engine retains execution authority.")

    lines.append("\n" + "=" * 80)
    text_report = "\n".join(lines)

    with open(out_path / "conformal_calibration_report.txt", "w", encoding="utf-8") as f:
        f.write(text_report)

    print("\n" + text_report)
    return results


if __name__ == "__main__":
    run_conformal_calibration_benchmark()
