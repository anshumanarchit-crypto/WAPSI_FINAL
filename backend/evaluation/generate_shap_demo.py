"""
WAPSI SHAP Local Explanation Demonstration.
Razorpay AI Buildathon 2026 - Track 3

Demonstrates deterministic local SHAP causal attribution on a real-world payment failure:
Answers the question: "WHY did WAPSI choose this recovery action?"

Saves:
  - evaluation/plots/shap_plots/demo_case_shap.png
  - evaluation/shap_explanation_demo.json
  - evaluation/shap_explanation_demo.txt
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.t_learner import WAPSIUpliftModel
from src.explainability import WAPSIShapExplainer
from evaluation.uplift_report import _load_or_generate_data


def run_shap_demonstration(
    data_dir: str = "data",
    output_dir: str = "evaluation",
    plots_dir: str = "evaluation/plots/shap_plots",
    random_seed: int = 42
):
    """Runs deterministic local SHAP attribution and saves plot and JSON artifacts."""
    out_path = Path(output_dir)
    plots_path = Path(plots_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    plots_path.mkdir(parents=True, exist_ok=True)

    print("[SHAP Demo] Loading training dataset...")
    df_train, df_test, _, _ = _load_or_generate_data(data_dir, random_seed=random_seed)

    print(f"[SHAP Demo] Fitting WAPSIUpliftModel on {len(df_train)} rows...")
    model = WAPSIUpliftModel(random_seed=random_seed)
    model.fit(df_train)

    print("[SHAP Demo] Initializing WAPSIShapExplainer...")
    explainer = WAPSIShapExplainer(model).initialize()

    # Deterministic Demonstration Case: Ecommerce Cart Drop / User Cancellation
    demo_case = {
        "case_id": "case_razorpay_demo_8821",
        "domain": "ecommerce",
        "amount": 3499.0,
        "decline_reason": "user_cancelled_checkout",
        "attempts_used": 1,
        "account_age_days": 180,
        "previous_failures": 0,
        "previous_recoveries": 4,
        "prior_recovery_rate": 0.85,
        "day_of_week": 2,
        "hour": 15,
        "issuer": "HDFC",
        "bin_bucket": "platinum",
        "fatigue_score": 0.10
    }

    print(f"[SHAP Demo] Generating local explanation for {demo_case['case_id']}...")
    explanation = explainer.explain_case(demo_case, action="whatsapp_nudge", top_k=6)

    # Save SHAP plot
    plot_file = plots_path / "demo_case_shap.png"
    saved_plot = explainer.generate_shap_plot(
        case=demo_case,
        action="whatsapp_nudge",
        save_path=str(plot_file),
        top_k=6
    )
    print(f"[SHAP Demo] Saved local attribution plot to: {saved_plot}")

    # Additional Demo Case: Technical Gateway Failure -> Smart Retry
    technical_case = {
        "case_id": "case_razorpay_demo_9942",
        "domain": "travel",
        "amount": 12500.0,
        "decline_reason": "technical_gateway_error",
        "attempts_used": 1,
        "account_age_days": 240,
        "previous_failures": 1,
        "previous_recoveries": 3,
        "prior_recovery_rate": 0.75,
        "day_of_week": 4,
        "hour": 11,
        "issuer": "ICICI",
        "bin_bucket": "corporate",
        "fatigue_score": 0.05
    }
    tech_explanation = explainer.explain_case(technical_case, action="retry_only", top_k=6)

    tech_plot_file = plots_path / "demo_technical_retry_shap.png"
    explainer.generate_shap_plot(
        case=technical_case,
        action="retry_only",
        save_path=str(tech_plot_file),
        top_k=6
    )

    demo_results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "primary_demo_case": {
            "input_case": demo_case,
            "explanation": explanation,
            "plot_path": str(plot_file)
        },
        "secondary_technical_case": {
            "input_case": technical_case,
            "explanation": tech_explanation,
            "plot_path": str(tech_plot_file)
        }
    }

    # Save JSON artifact
    json_path = out_path / "shap_explanation_demo.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(demo_results, f, indent=2)
    print(f"[SHAP Demo] Saved JSON demo payload to: {json_path}")

    # Generate Human-Readable Text Summary
    lines = []
    lines.append("=" * 80)
    lines.append("WAPSI LOCAL CAUSAL ATTRIBUTION DEMO (SHAP TreeExplainer)")
    lines.append("Razorpay AI Buildathon 2026 | Track 3: Causal Recovery Decision Engine")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append("=" * 80)

    lines.append("\n[DEMO 1] HIGH-VALUE ECOMMERCE USER CANCELLATION")
    lines.append(f"  Case ID          : {demo_case['case_id']}")
    lines.append(f"  Chosen Action    : {explanation['action']}")
    lines.append(f"  Predicted Uplift : +{explanation['predicted_uplift']:.1%} incremental recovery likelihood")
    lines.append(f"  Base Population  : +{explanation['base_uplift']:.1%}")
    lines.append("\n  Top Decision Reasons (Ranked by Absolute SHAP Impact):")
    for r in explanation["top_reasons"]:
        sign = "+" if r["impact"] > 0 else ""
        lines.append(f"    - {r['feature']:22s} = {str(r['value']):12s} -> {sign}{r['impact']:.4f} uplift impact")

    lines.append(f"\n  UI Decision Rationale:")
    lines.append(f"    \"{explanation['rationale']}\"")
    lines.append(f"  Visual Artifact : {saved_plot}")

    lines.append("\n" + "-" * 80)
    lines.append("\n[DEMO 2] HIGH-TICKET TRAVEL GATEWAY ERROR")
    lines.append(f"  Case ID          : {technical_case['case_id']}")
    lines.append(f"  Chosen Action    : {tech_explanation['action']}")
    lines.append(f"  Predicted Uplift : +{tech_explanation['predicted_uplift']:.1%} incremental recovery likelihood")
    lines.append("\n  Top Decision Reasons:")
    for r in tech_explanation["top_reasons"]:
        sign = "+" if r["impact"] > 0 else ""
        lines.append(f"    - {r['feature']:22s} = {str(r['value']):12s} -> {sign}{r['impact']:.4f} uplift impact")

    lines.append(f"\n  UI Decision Rationale:")
    lines.append(f"    \"{tech_explanation['rationale']}\"")

    lines.append("\n" + "=" * 80)
    text_summary = "\n".join(lines)

    txt_path = out_path / "shap_explanation_demo.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text_summary)

    print("\n" + text_summary)
    return demo_results


if __name__ == "__main__":
    run_shap_demonstration()
