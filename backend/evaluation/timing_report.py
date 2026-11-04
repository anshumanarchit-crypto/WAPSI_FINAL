"""
WAPSI Recovery Timing Evaluation & Plot Generator.
Razorpay AI Buildathon 2026 - Track 3

Generates comprehensive timing hazard diagnostic reports and plots:
  1. Timing distribution by decline reason
  2. Timing distribution by card issuer
  3. Timing distribution by merchant domain
  4. Timing distribution by card BIN tier
  5. Sample case inference walkthrough
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime, timezone
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.hazard_model import (
    WAPSIHazardModel,
    TIME_WINDOWS,
    generate_timing_plots
)
from evaluation.uplift_report import _load_or_generate_data


def run_timing_evaluation(
    data_dir: str = "data",
    output_dir: str = "evaluation",
    plots_dir: str = "evaluation/plots/timing_plots",
    random_seed: int = 42
) -> Dict[str, Any]:
    """Runs timing hazard model training, inference evaluation, and plot generation."""
    out_path = Path(output_dir)
    plots_path = Path(plots_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    plots_path.mkdir(parents=True, exist_ok=True)

    print("[Timing] Loading dataset...")
    df_train, df_test, _, _ = _load_or_generate_data(data_dir, random_seed=random_seed)

    print(f"[Timing] Fitting WAPSIHazardModel on {len(df_train)} training rows...")
    model = WAPSIHazardModel(random_seed=random_seed)
    model.fit(df_train)

    # Save trained hazard model
    model_save_path = Path("models") / "wapsi_hazard_model_v1.0.0.joblib"
    model.save(model_save_path)
    print(f"[Timing] Persisted model to {model_save_path}")

    # Generate diagnostic plots
    print("[Timing] Generating diagnostic plots...")
    plot_paths = generate_timing_plots(
        df=df_test,
        hazard_model=model,
        output_dir=str(plots_path)
    )

    # Evaluate on test set
    print("[Timing] Running test set inference...")
    sample_cases = [
        {
            "case_id": "case_glitch_01",
            "description": "Instant Technical Gateway Error (HDFC / Platinum / Ecommerce)",
            "case": {
                "amount": 1850.0,
                "attempts_used": 1,
                "account_age_days": 120,
                "previous_failures": 0,
                "previous_recoveries": 2,
                "prior_recovery_rate": 1.0,
                "day_of_week": 2,
                "hour": 14,
                "fatigue_score": 0.05,
                "domain": "ecommerce",
                "decline_reason": "technical_gateway_error",
                "issuer": "HDFC",
                "bin_bucket": "platinum"
            }
        },
        {
            "case_id": "case_funds_02",
            "description": "Salary Replenishment Cycle (SBI / Classic / Subscription)",
            "case": {
                "amount": 4500.0,
                "attempts_used": 2,
                "account_age_days": 45,
                "previous_failures": 2,
                "previous_recoveries": 1,
                "prior_recovery_rate": 0.5,
                "day_of_week": 4,
                "hour": 21,
                "fatigue_score": 0.35,
                "domain": "subscription",
                "decline_reason": "insufficient_funds",
                "issuer": "SBI",
                "bin_bucket": "classic"
            }
        },
        {
            "case_id": "case_b2b_03",
            "description": "B2B High-Ticket Invoice Authorization (CITI / Corporate / B2B SaaS)",
            "case": {
                "amount": 48000.0,
                "attempts_used": 1,
                "account_age_days": 365,
                "previous_failures": 0,
                "previous_recoveries": 5,
                "prior_recovery_rate": 1.0,
                "day_of_week": 1,
                "hour": 11,
                "fatigue_score": 0.10,
                "domain": "b2b_saas",
                "decline_reason": "card_limit_exceeded",
                "issuer": "CITI",
                "bin_bucket": "corporate"
            }
        },
        {
            "case_id": "case_upi_04",
            "description": "Instant Food Delivery UPI Pin Timeout (ICICI / UPI / Food Delivery)",
            "case": {
                "amount": 420.0,
                "attempts_used": 1,
                "account_age_days": 90,
                "previous_failures": 1,
                "previous_recoveries": 8,
                "prior_recovery_rate": 0.89,
                "day_of_week": 6,
                "hour": 20,
                "fatigue_score": 0.15,
                "domain": "food_delivery",
                "decline_reason": "upi_pin_timeout",
                "issuer": "ICICI",
                "bin_bucket": "upi_standard"
            }
        }
    ]

    inferred_samples = []
    for sc in sample_cases:
        res = model.recommend_timing(sc["case"])
        res["case_id"] = sc["case_id"]
        res["description"] = sc["description"]
        inferred_samples.append(res)

    # Compute segment distributions
    recs_all = model.batch_recommend_timing(df_test)
    df_eval = df_test.copy()
    df_eval["recommended_window"] = [r["recommended_window"] for r in recs_all]

    decline_window_ct = pd.crosstab(
        df_eval["decline_reason"], df_eval["recommended_window"], normalize="index"
    ).to_dict(orient="index")

    issuer_window_ct = pd.crosstab(
        df_eval["issuer"], df_eval["recommended_window"], normalize="index"
    ).to_dict(orient="index")

    domain_window_ct = pd.crosstab(
        df_eval["domain"], df_eval["recommended_window"], normalize="index"
    ).to_dict(orient="index")

    results = {
        "report_timestamp": datetime.now(timezone.utc).isoformat(),
        "train_rows": len(df_train),
        "test_rows": len(df_test),
        "time_windows": TIME_WINDOWS,
        "sample_inferences": inferred_samples,
        "decline_reason_distributions": decline_window_ct,
        "issuer_distributions": issuer_window_ct,
        "domain_distributions": domain_window_ct,
        "plot_paths": plot_paths
    }

    # Save JSON report
    with open(out_path / "timing_report.json", "w", encoding="utf-8") as f:
        json.dump(json.loads(json.dumps(results, default=str)), f, indent=2)

    # Generate text report
    lines = []
    lines.append("=" * 78)
    lines.append("WAPSI RECOVERY TIMING & DISCRETE HAZARD REPORT")
    lines.append("Razorpay AI Buildathon 2026 | Track 3: Causal Recovery Router")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append("=" * 78)

    lines.append("\n[1] TIMING MODEL ARCHITECTURE")
    lines.append("  Paradigm    : Discrete-Time Hazard Estimator (Multi-Class Gradient Boosting)")
    lines.append("  Objective   : Predicts conditional recovery probability P(Window | X)")
    lines.append("  Windows     : 0-24h (Immediate), 24-48h (Next-day), 48-72h (Multi-day), 72h+ (Extended)")
    lines.append("  Key Signals : decline_reason, issuer, bin_bucket, domain, amount, diurnal features")

    lines.append("\n[2] SAMPLE CASE TIMING RECOMMENDATIONS")
    for s in inferred_samples:
        lines.append(f"\n  Case ID: {s['case_id']} ({s['description']})")
        lines.append(f"    Recommended Window : {s['recommended_window']}")
        lines.append(f"    Expected Hours     : {s['expected_hours']:.1f} hours")
        lines.append(f"    Hazard by Window   : {s['hazard_by_window']}")
        lines.append(f"    Cumulative Hazard  : {s['cumulative_hazard']}")

    lines.append("\n[3] DOMINANT TIMING WINDOWS BY DECLINE REASON")
    for reason, dist in decline_window_ct.items():
        top_w = max(dist.keys(), key=lambda k: dist[k])
        lines.append(f"  {reason:26s} -> Top Window: {top_w:8s} ({dist[top_w]:.1%})")

    lines.append("\n[4] DOMINANT TIMING WINDOWS BY CARD ISSUER")
    for issuer, dist in issuer_window_ct.items():
        top_w = max(dist.keys(), key=lambda k: dist[k])
        lines.append(f"  {issuer:10s} -> Top Window: {top_w:8s} ({dist[top_w]:.1%})")

    lines.append("\n[5] DOMINANT TIMING WINDOWS BY DOMAIN")
    for dom, dist in domain_window_ct.items():
        top_w = max(dist.keys(), key=lambda k: dist[k])
        lines.append(f"  {dom:18s} -> Top Window: {top_w:8s} ({dist[top_w]:.1%})")

    lines.append("\n" + "=" * 78)
    text_report = "\n".join(lines)

    with open(out_path / "timing_report.txt", "w", encoding="utf-8") as f:
        f.write(text_report)

    print(f"[Done] Timing report saved to {out_path}/")
    print("\n" + text_report)

    return results


if __name__ == "__main__":
    run_timing_evaluation()
