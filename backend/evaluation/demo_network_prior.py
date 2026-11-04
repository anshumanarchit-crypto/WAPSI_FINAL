"""
WAPSI Network Prior Demonstration & Shrinkage Visualizer.
Razorpay AI Buildathon 2026 - Track 3

Demonstrates how Empirical Bayes partial pooling solves the merchant cold-start problem:
  - Merchant with 10 cases     -> Network-heavy (w ~ 0.09)
  - Merchant with 100 cases    -> 50/50 balanced blend (w = 0.50)
  - Merchant with 10,000 cases -> Merchant-heavy (w ~ 0.99)

Saves:
  - models/wapsi_network_prior_v1.0.0.joblib
  - evaluation/plots/network_prior_shrinkage.png
  - evaluation/network_prior_demo.json
  - evaluation/network_prior_demo.txt
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

from src.network_prior import WAPSINetworkPrior, ACTIVE_TREATMENTS
from evaluation.uplift_report import _load_or_generate_data


def run_network_prior_demo(
    data_dir: str = "data",
    output_dir: str = "evaluation",
    plots_dir: str = "evaluation/plots",
    random_seed: int = 42
):
    out_path = Path(output_dir)
    plots_path = Path(plots_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    plots_path.mkdir(parents=True, exist_ok=True)

    print("[NetworkPrior Demo] Loading training dataset...")
    df_train, _, _, _ = _load_or_generate_data(data_dir, random_seed=random_seed)

    print(f"[NetworkPrior Demo] Fitting WAPSINetworkPrior on {len(df_train)} rows...")
    prior = WAPSINetworkPrior(shrinkage_half_life=100.0, shrinkage_rule="hyperbolic")
    prior.fit(df_train)

    # Persist model
    model_save_path = Path("models") / "wapsi_network_prior_v1.0.0.joblib"
    prior.save(model_save_path)
    print(f"[NetworkPrior Demo] Persisted model to: {model_save_path}")

    # Simulated Merchant Scenarios
    merchants = [
        {
            "scenario": "Cold-Start Early Startup (10 cases)",
            "merchant_id": "merch_cold_start_10",
            "observations": 10,
            "domain": "ecommerce",
            "decline_reason": "user_cancelled_checkout",
            "raw_merchant_uplifts": {
                "retry_only": 0.05,        # Noisy low sample
                "whatsapp_nudge": 0.02,    # Underestimated in small sample
                "voice_call": -0.05,
                "email": 0.00,
                "incentive_link": 0.10
            }
        },
        {
            "scenario": "Mid-Stage Merchant at Half-Life (100 cases)",
            "merchant_id": "merch_mid_growth_100",
            "observations": 100,
            "domain": "subscription",
            "decline_reason": "insufficient_funds",
            "raw_merchant_uplifts": {
                "retry_only": 0.18,
                "whatsapp_nudge": 0.22,
                "voice_call": 0.08,
                "email": 0.04,
                "incentive_link": 0.15
            }
        },
        {
            "scenario": "High-Volume Mature Enterprise (10,000 cases)",
            "merchant_id": "merch_enterprise_10000",
            "observations": 10000,
            "domain": "ecommerce",
            "decline_reason": "technical_gateway_error",
            "raw_merchant_uplifts": {
                "retry_only": 0.42,        # Custom optimized retry engine
                "whatsapp_nudge": 0.29,
                "voice_call": 0.06,
                "email": 0.03,
                "incentive_link": 0.21
            }
        }
    ]

    demo_results = []
    for m in merchants:
        shrunk = prior.shrink_all_actions(
            merchant_uplifts=m["raw_merchant_uplifts"],
            merchant_observations=m["observations"],
            domain=m["domain"],
            decline_reason=m["decline_reason"],
            merchant_id=m["merchant_id"]
        )
        demo_results.append({
            "scenario": m["scenario"],
            "input": m,
            "shrinkage_output": shrunk
        })

    # Generate Shrinkage Curve Plot
    n_range = np.logspace(0, 4.3, 200)
    w_hyperbolic = [prior.compute_shrinkage_weight(n) for n in n_range]
    
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.plot(n_range, w_hyperbolic, color="#2B5B84", linewidth=2.5, label="Empirical Bayes Hyperbolic: $w(n) = \\frac{n}{n + 100}$")
    ax.axhline(0.5, color="gray", linestyle="--", alpha=0.6, label="Half-Weight Point ($w = 0.50$ at $n_0 = 100$)")
    ax.axvline(100, color="gray", linestyle="--", alpha=0.6)

    # Highlight demo merchants
    ax.scatter([10], [prior.compute_shrinkage_weight(10)], color="#D95F02", s=100, zorder=5, label="Cold-Start ($n=10, w=0.09$)")
    ax.scatter([100], [prior.compute_shrinkage_weight(100)], color="#7570B3", s=100, zorder=5, label="Mid-Growth ($n=100, w=0.50$)")
    ax.scatter([10000], [prior.compute_shrinkage_weight(10000)], color="#1B9E77", s=100, zorder=5, label="Enterprise ($n=10,000, w=0.99$)")

    ax.set_xscale("log")
    ax.set_xlabel("Merchant Sample Size $n$ (Log Scale)", fontsize=11, fontweight="bold")
    ax.set_ylabel("Merchant Weight $w(n)$ (vs Network Weight $1-w$)", fontsize=11, fontweight="bold")
    ax.set_title("WAPSI Network Prior: Empirical Bayes Partial Pooling Transition", fontsize=13, fontweight="bold")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(loc="lower right", fontsize=10)
    ax.set_ylim(-0.05, 1.05)

    plt.tight_layout()
    plot_file = plots_path / "network_prior_shrinkage.png"
    fig.savefig(plot_file, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[NetworkPrior Demo] Saved shrinkage curve plot to: {plot_file}")

    # Save JSON artifact
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "shrinkage_half_life_n0": prior.shrinkage_half_life,
        "global_network_priors": prior.global_network_uplifts_,
        "demonstration_scenarios": demo_results,
        "architecture_classification": "Hackathon partial pooling approximation of hierarchical Bayesian system."
    }
    with open(out_path / "network_prior_demo.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    # Generate Human-Readable Text Report
    lines = []
    lines.append("=" * 80)
    lines.append("WAPSI NETWORK PRIOR & EMPIRICAL BAYES SHRINKAGE DEMO")
    lines.append("Razorpay AI Buildathon 2026 | Track 3: Causal Recovery Router")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append("=" * 80)
    lines.append("\n[1] DESIGN & ARCHITECTURE STATEMENT")
    lines.append("  Concept : Transparent empirical Bayes partial pooling (w(n) * merchant + (1-w(n)) * network).")
    lines.append("  Purpose : Eliminates cold-start vulnerability for new merchants using Razorpay collective intelligence.")
    lines.append("  Privacy : Aggregation uses strictly anonymized segment buckets; NO customer PII or raw histories shared.")
    lines.append("  Design  : Hackathon-grade deterministic partial pooling approximation of hierarchical Bayesian model.")

    lines.append("\n[2] GLOBAL NETWORK UPLIFT PRIORS")
    for act, net_up in prior.global_network_uplifts_.items():
        lines.append(f"  - {act:18s} -> Expected Network Uplift: +{net_up:.1%}")

    lines.append("\n[3] DEMONSTRATION ACROSS MERCHANT SAMPLE SIZE REGIMES")
    for dr in demo_results:
        sc = dr["scenario"]
        out = dr["shrinkage_output"]
        lines.append(f"\n--- {sc.upper()} ---")
        lines.append(f"  Merchant ID      : {out['merchant_id']}")
        lines.append(f"  Sample Size (n)  : {out['merchant_observations']} cases")
        lines.append(f"  Merchant Weight  : {out['merchant_weight']:.1%} (Network Prior Weight: {out['network_weight']:.1%})")
        lines.append("\n  Action Uplift Breakdown:")
        for act, b in out["per_action_breakdown"].items():
            lines.append(
                f"    - {act:16s} | Net Prior: {b['network_uplift']:+.2f} | "
                f"Merch Est: {b['merchant_uplift']:+.2f} | "
                f"COMBINED: {b['combined_uplift']:+.4f} (w={b['merchant_weight']:.2f})"
            )

    lines.append("\n" + "=" * 80)
    text_report = "\n".join(lines)

    with open(out_path / "network_prior_demo.txt", "w", encoding="utf-8") as f:
        f.write(text_report)

    print("\n" + text_report)
    return payload


if __name__ == "__main__":
    run_network_prior_demo()
