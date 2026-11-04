"""
WAPSI Uplift Evaluation Report Orchestrator.
Razorpay AI Buildathon 2026 - Track 3

Orchestrates:
  1. Model training on observed data (strict isolation from potential outcomes)
  2. Qini curve, Qini coefficient, random baseline evaluation
  3. Uplift curve and AUUC computation
  4. Oracle benchmarking using hidden ground-truth CATE
  5. Segment-level Qini (domain, decline reason)
  6. Per-treatment Qini and AUUC
  7. Business KPIs: rupees recovered per contact, per retry, per fatigue unit
  8. Decile lift table
  9. Plot generation (saved to evaluation/plots/uplift_plots/)
  10. Final summary: Does the model rank persuadable customers better than random?

KEY ISOLATION RULE:
  WAPSIUpliftModel.fit() is called ONLY on df_observed (no tau_* or y_* columns).
  df_ground_truth is used EXCLUSIVELY in the evaluation/oracle benchmarking phase.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib
matplotlib.use("Agg")  # Headless backend for server environments
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd

from src.data_generator import WapsiDataGenerator, RecoveryDataConfig, TREATMENTS
from src.t_learner import WAPSIUpliftModel

from evaluation.qini import (
    qini_curve, qini_coefficient, random_baseline_curve,
    oracle_qini_curve, segment_qini, multi_treatment_qini
)
from evaluation.auuc import (
    uplift_curve, random_uplift_curve, auuc,
    per_treatment_auuc, auuc_by_segment, compute_decile_lift_table
)

ACTIVE_TREATMENTS = [t for t in TREATMENTS if t != "no_action"]
DOMAIN_SEGMENTS = ["ecommerce", "b2b_saas", "subscription", "travel", "education", "gaming", "food_delivery"]
CONTROL = "no_action"


# ---------------------------------------------------------------------------
# Data Loading Helpers
# ---------------------------------------------------------------------------

def _load_or_generate_data(
    data_dir: str = "data",
    n_samples: int = 30000,
    random_seed: int = 42
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Loads train/test splits and ground truth from disk, or generates fresh data.

    Returns:
        (df_train, df_test, df_gt_test, df_gt_full) where:
        - df_train: observed training split (no potential outcomes)
        - df_test:  observed test split (no potential outcomes)
        - df_gt_test: ground truth aligned with test split (evaluation only)
        - df_gt_full: full ground truth dataset
    """
    data_path = Path(data_dir)
    train_parq = data_path / "train.parquet"
    test_parq = data_path / "test.parquet"
    gt_test_parq = data_path / "ground_truth_test.parquet"
    gt_full_parq = data_path / "ground_truth_full.parquet"

    if all(p.exists() for p in [train_parq, test_parq, gt_test_parq, gt_full_parq]):
        df_train = pd.read_parquet(train_parq)
        df_test = pd.read_parquet(test_parq)
        df_gt_test = pd.read_parquet(gt_test_parq)
        df_gt_full = pd.read_parquet(gt_full_parq)
        print(f"[Data] Loaded from disk: train={len(df_train)}, test={len(df_test)}, gt_test={len(df_gt_test)}")
    else:
        print(f"[Data] Generating {n_samples} samples (seed={random_seed})...")
        gen = WapsiDataGenerator(RecoveryDataConfig(
            n_samples=n_samples,
            random_seed=random_seed,
            output_dir=data_dir,
            export_parquet=True,
            export_csv=False
        ))
        df_obs, df_gt = gen.generate()
        gen.split_and_export(df_obs, df_gt, output_dir=data_dir)
        df_train = pd.read_parquet(train_parq)
        df_test = pd.read_parquet(test_parq)
        df_gt_test = pd.read_parquet(gt_test_parq)
        df_gt_full = pd.read_parquet(gt_full_parq)

    return df_train, df_test, df_gt_test, df_gt_full


def _train_model(df_train: pd.DataFrame, random_seed: int = 42) -> WAPSIUpliftModel:
    """
    Trains the WAPSIUpliftModel on OBSERVED data only.
    Enforces strict isolation — df_train must NOT contain potential outcome columns.
    """
    print(f"[Model] Training T-Learner on {len(df_train)} rows...")
    model = WAPSIUpliftModel(random_seed=random_seed)
    model.fit(df_train)
    print("[Model] Training complete.")
    return model


# ---------------------------------------------------------------------------
# Business KPI Computation
# ---------------------------------------------------------------------------

def compute_business_kpis(
    df_test: pd.DataFrame,
    model: WAPSIUpliftModel,
    treatment_col: str = "treatment",
    y_true_col: str = "recovered",
    amount_col: str = "amount",
    fatigue_col: str = "fatigue_score"
) -> Dict[str, Any]:
    """
    Computes business-oriented recovery efficiency metrics.

    Metrics:
      - Rs recovered per contact: total recovered amount / number of cases contacted
      - Rs recovered per retry attempt: for retry_only arm
      - Rs recovered per fatigue-budget unit: recovered amount / total fatigue consumed
      - Recovery rate lift over control (% improvement)

    NOTE: These are factual observed outcomes from the test set simulation.
    No fabrication — all values are computed from df_test.
    """
    kpis = {}

    # Overall population stats
    total_contacted = len(df_test[df_test[treatment_col] != CONTROL])
    total_recovered = df_test[df_test[y_true_col] == 1][amount_col].sum()
    total_recovered_contacts = df_test[
        (df_test[y_true_col] == 1) & (df_test[treatment_col] != CONTROL)
    ][amount_col].sum()

    kpis["overall"] = {
        "total_cases": int(len(df_test)),
        "total_contacted": int(total_contacted),
        "total_amount_recovered_inr": round(float(total_recovered), 2),
        "amount_recovered_from_contacted_inr": round(float(total_recovered_contacts), 2),
        "rs_per_contact": round(float(total_recovered_contacts / total_contacted), 2) if total_contacted > 0 else 0.0,
        "overall_recovery_rate": round(float(df_test[y_true_col].mean()), 4)
    }

    # Per-treatment KPIs
    per_treatment = {}
    control_mask = (df_test[treatment_col] == CONTROL)
    control_rate = float(df_test[control_mask][y_true_col].mean()) if control_mask.sum() > 0 else 0.0

    for act in ACTIVE_TREATMENTS:
        mask = (df_test[treatment_col] == act)
        n = int(mask.sum())
        if n == 0:
            continue

        grp = df_test[mask]
        n_recovered = int(grp[y_true_col].sum())
        amt_recovered = float(grp[grp[y_true_col] == 1][amount_col].sum())
        rate = float(grp[y_true_col].mean())
        fatigue_consumed = float(grp[fatigue_col].sum())

        rs_per_contact = amt_recovered / n if n > 0 else 0.0
        rs_per_fatigue_unit = amt_recovered / fatigue_consumed if fatigue_consumed > 0 else 0.0
        rate_lift_vs_control = rate - control_rate

        entry: Dict[str, Any] = {
            "n_cases": n,
            "n_recovered": n_recovered,
            "recovery_rate": round(rate, 4),
            "recovery_rate_lift_vs_control": round(rate_lift_vs_control, 4),
            "amount_recovered_inr": round(amt_recovered, 2),
            "rs_recovered_per_contact": round(rs_per_contact, 2),
            "rs_recovered_per_fatigue_unit": round(rs_per_fatigue_unit, 2)
        }

        if act == "retry_only":
            # Additional retry-specific metric
            attempts_consumed = int(grp["attempts_used"].sum())
            rs_per_retry = amt_recovered / attempts_consumed if attempts_consumed > 0 else 0.0
            entry["attempts_consumed"] = attempts_consumed
            entry["rs_recovered_per_retry_attempt"] = round(rs_per_retry, 2)

        per_treatment[act] = entry

    kpis["per_treatment"] = per_treatment
    kpis["control_baseline"] = {
        "n_cases": int(control_mask.sum()),
        "recovery_rate": round(control_rate, 4),
        "amount_recovered_inr": round(float(df_test[control_mask & (df_test[y_true_col] == 1)][amount_col].sum()), 2)
    }

    return kpis


# ---------------------------------------------------------------------------
# Model-Guided Routing Efficiency
# ---------------------------------------------------------------------------

def compute_model_routing_efficiency(
    df_test: pd.DataFrame,
    df_gt_test: pd.DataFrame,
    model: WAPSIUpliftModel,
    n_bins: int = 20
) -> Dict[str, Any]:
    """
    Evaluates the model's routing efficiency by comparing:
      - Actual uplift scores vs. oracle true CATE across all interventions
      - Overall Qini on best-action routing vs. random routing
    """
    # Predict best action per case using model
    all_uplifts = model.predict_uplift(df_test)
    uplift_matrix = pd.DataFrame({act: all_uplifts[act] for act in ACTIVE_TREATMENTS})

    # Best model action (highest uplift)
    model_best_action_idx = np.argmax(uplift_matrix.values, axis=1)
    model_best_uplift = uplift_matrix.values[
        np.arange(len(uplift_matrix)), model_best_action_idx
    ]

    # Oracle: true best CATE from ground truth
    oracle_tau_cols = [f"tau_{act}" for act in ACTIVE_TREATMENTS if f"tau_{act}" in df_gt_test.columns]
    if oracle_tau_cols:
        oracle_tau_matrix = df_gt_test[oracle_tau_cols].values
        oracle_best_uplift = np.max(oracle_tau_matrix, axis=1)
        correlation = float(np.corrcoef(model_best_uplift, oracle_best_uplift)[0, 1])
    else:
        oracle_best_uplift = np.zeros(len(df_test))
        correlation = 0.0

    # Rank correlation (Spearman)
    from scipy.stats import spearmanr
    rho, pval = spearmanr(model_best_uplift, oracle_best_uplift)

    return {
        "model_oracle_pearson_correlation": round(correlation, 4),
        "model_oracle_spearman_rho": round(float(rho), 4),
        "model_oracle_spearman_pval": round(float(pval), 6),
        "mean_model_best_uplift": round(float(model_best_uplift.mean()), 4),
        "mean_oracle_best_uplift": round(float(oracle_best_uplift.mean()), 4),
        "pct_model_best_matches_oracle": round(
            float(np.mean(
                np.array(ACTIVE_TREATMENTS)[model_best_action_idx] ==
                df_gt_test.get("optimal_treatment", pd.Series([""] * len(df_test))).values
            )), 4
        ) if "optimal_treatment" in df_gt_test.columns else None
    }


# ---------------------------------------------------------------------------
# Plot Generation
# ---------------------------------------------------------------------------

def _plot_overall_qini(
    df_test: pd.DataFrame,
    df_gt_test: pd.DataFrame,
    model: WAPSIUpliftModel,
    out_dir: Path,
    n_bins: int = 20
) -> Optional[str]:
    """Plots overall Qini curve for the best recommended action."""
    all_uplifts = model.predict_uplift(df_test)

    # Use best-uplift action per case as the overall ranking signal
    uplift_matrix = np.column_stack([all_uplifts[act] for act in ACTIVE_TREATMENTS])
    overall_score = uplift_matrix.max(axis=1)
    best_act_idx = uplift_matrix.argmax(axis=1)
    # For the binary Qini: assign treatment label = actual treatment in test data
    t_arr = df_test["treatment"].values
    y_arr = df_test["recovered"].values

    # For overall Qini, use any_intervention vs no_action
    binary_t = np.where(t_arr == CONTROL, CONTROL, "intervention")

    # Score for this binary split = max uplift
    fracs, qini_vals = qini_curve(
        y_true=y_arr,
        uplift_score=overall_score,
        treatment=binary_t,
        treatment_label="intervention",
        control_label=CONTROL,
        n_bins=n_bins
    )
    rand_fracs, rand_vals = random_baseline_curve(n_bins, max_qini=float(qini_vals[-1]))
    q_coeff = qini_coefficient(fracs, qini_vals)

    # Oracle using oracle_max_uplift from ground truth
    oracle_result = None
    if "oracle_max_uplift" in df_gt_test.columns:
        oracle_tau = df_gt_test["oracle_max_uplift"].values
        o_fracs, o_vals = oracle_qini_curve(
            tau_true=oracle_tau,
            y_true=y_arr,
            treatment=binary_t,
            treatment_label="intervention",
            control_label=CONTROL,
            n_bins=n_bins
        )
        oracle_result = (o_fracs, o_vals, qini_coefficient(o_fracs, o_vals))

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.plot(fracs, qini_vals, "b-o", markersize=4, linewidth=2,
            label=f"T-Learner (Q={q_coeff:.4f})")
    ax.plot(rand_fracs, rand_vals, "gray", linewidth=1.5, linestyle="--",
            label="Random Targeting Baseline")
    if oracle_result:
        o_f, o_v, o_q = oracle_result
        ax.plot(o_f, o_v, "g--^", markersize=4, linewidth=2,
                label=f"Oracle (Q={o_q:.4f})")
    ax.fill_between(fracs, rand_vals, qini_vals, alpha=0.15, color="blue",
                    label="Model gain over random")
    ax.set_xlabel("Fraction of Population Targeted", fontsize=12)
    ax.set_ylabel("Cumulative Incremental Gains (Qini)", fontsize=12)
    ax.set_title("WAPSI Overall Qini Curve\n(T-Learner vs Oracle vs Random Targeting)", fontsize=13)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 1)
    plt.tight_layout()

    plot_path = out_dir / "overall_qini_curve.png"
    fig.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(plot_path)


def _plot_per_treatment_qini(
    per_treatment_q: Dict[str, Any],
    out_dir: Path
) -> Optional[str]:
    """Multi-panel Qini curve plot, one panel per treatment."""
    acts = [a for a in ACTIVE_TREATMENTS if a in per_treatment_q]
    if not acts:
        return None

    n_cols = 3
    n_rows = int(np.ceil(len(acts) / n_cols))
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(14, 4 * n_rows))
    axes = np.array(axes).flatten()

    for idx, act in enumerate(acts):
        ax = axes[idx]
        res = per_treatment_q[act]
        fracs = np.array(res["fractions"])
        qini_vals = np.array(res["qini_values"])
        q_coeff = res["qini_coefficient"]
        rand_fracs, rand_vals = random_baseline_curve(len(fracs) - 1, float(qini_vals[-1]))

        ax.plot(fracs, qini_vals, "b-o", markersize=3, linewidth=1.8,
                label=f"T-Learner (Q={q_coeff:.4f})")
        ax.plot(rand_fracs, rand_vals, "gray", linewidth=1.2, linestyle="--",
                label="Random")
        ax.fill_between(fracs, rand_vals, qini_vals, alpha=0.12, color="blue")
        ax.set_title(f"{act.replace('_', ' ').title()}", fontsize=10)
        ax.set_xlabel("Fraction Targeted", fontsize=8)
        ax.set_ylabel("Qini", fontsize=8)
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(0, 1)

    for idx in range(len(acts), len(axes)):
        axes[idx].set_visible(False)

    fig.suptitle("WAPSI Per-Treatment Qini Curves (T-Learner vs Random)", fontsize=13, y=1.01)
    plt.tight_layout()
    plot_path = out_dir / "per_treatment_qini.png"
    fig.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(plot_path)


def _plot_auuc_comparison(
    per_treatment_auuc_res: Dict[str, Any],
    out_dir: Path
) -> Optional[str]:
    """Bar chart comparing AUUC model vs oracle per treatment."""
    acts = [a for a in ACTIVE_TREATMENTS if a in per_treatment_auuc_res]
    if not acts:
        return None

    model_auucs = [per_treatment_auuc_res[a]["auuc_model"] for a in acts]
    oracle_auucs = [per_treatment_auuc_res[a].get("auuc_oracle", 0.0) for a in acts]

    x = np.arange(len(acts))
    width = 0.35

    fig, ax = plt.subplots(figsize=(11, 5))
    bars_m = ax.bar(x - width / 2, model_auucs, width, label="T-Learner AUUC", color="#4C72B0", alpha=0.85)
    bars_o = ax.bar(x + width / 2, oracle_auucs, width, label="Oracle AUUC", color="#55A868", alpha=0.85)

    # Annotate bars
    for bar in bars_m:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2., h + 0.001, f"{h:.4f}",
                ha="center", va="bottom", fontsize=8)
    for bar in bars_o:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2., h + 0.001, f"{h:.4f}",
                ha="center", va="bottom", fontsize=8)

    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xticks(x)
    ax.set_xticklabels([a.replace("_", "\n") for a in acts], fontsize=9)
    ax.set_ylabel("AUUC vs Random Baseline", fontsize=11)
    ax.set_title("WAPSI AUUC: T-Learner vs Oracle Per Treatment", fontsize=13)
    ax.legend(fontsize=10)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()

    plot_path = out_dir / "auuc_model_vs_oracle.png"
    fig.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(plot_path)


def _plot_segment_qini(
    segment_qini_res: Dict[str, Any],
    out_dir: Path,
    title: str = "Domain-Segment Qini Coefficients"
) -> Optional[str]:
    """Bar chart of Qini coefficients by domain segment."""
    if not segment_qini_res:
        return None

    segments = sorted(segment_qini_res.keys())
    coeffs = [segment_qini_res[s]["qini_coefficient"] for s in segments]
    colors = ["#4C72B0" if c >= 0 else "#C44E52" for c in coeffs]

    fig, ax = plt.subplots(figsize=(10, 4))
    bars = ax.bar(segments, coeffs, color=colors, alpha=0.85)
    for bar, coeff in zip(bars, coeffs):
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2., h + 0.0005,
                f"{coeff:.4f}", ha="center", va="bottom", fontsize=8)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xlabel("Domain Segment", fontsize=11)
    ax.set_ylabel("Qini Coefficient", fontsize=11)
    ax.set_title(title, fontsize=12)
    ax.tick_params(axis="x", labelsize=9)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()

    plot_path = out_dir / "segment_qini_by_domain.png"
    fig.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(plot_path)


def _plot_business_kpis(
    kpis: Dict[str, Any],
    out_dir: Path
) -> Optional[str]:
    """Bar chart of Rs recovered per contact per action."""
    per_treatment = kpis.get("per_treatment", {})
    if not per_treatment:
        return None

    acts = sorted(per_treatment.keys())
    rs_per_contact = [per_treatment[a].get("rs_recovered_per_contact", 0.0) for a in acts]
    colors = plt.cm.tab10(np.linspace(0, 1, len(acts)))

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(acts, rs_per_contact, color=colors, alpha=0.85)
    for bar, val in zip(bars, rs_per_contact):
        ax.text(bar.get_x() + bar.get_width() / 2., bar.get_height() + 5,
                f"₹{val:,.0f}", ha="center", va="bottom", fontsize=9)
    ax.set_xlabel("Recovery Action", fontsize=11)
    ax.set_ylabel("₹ Recovered per Contact (Test Set)", fontsize=11)
    ax.set_title("WAPSI Business KPI: ₹ Recovered per Contact by Action\n(Factual Test Set Outcomes — No Fabrication)", fontsize=12)
    ax.set_xticks(range(len(acts)))
    ax.set_xticklabels([a.replace("_", "\n") for a in acts], fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()

    plot_path = out_dir / "business_kpis_rs_per_contact.png"
    fig.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(plot_path)


def _plot_uplift_curves_per_treatment(
    per_treatment_auuc_res: Dict[str, Any],
    out_dir: Path
) -> Optional[str]:
    """Multi-panel uplift curve (model vs oracle vs random) per treatment."""
    acts = [a for a in ACTIVE_TREATMENTS if a in per_treatment_auuc_res]
    if not acts:
        return None

    n_cols = 3
    n_rows = int(np.ceil(len(acts) / n_cols))
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(14, 4 * n_rows))
    axes = np.array(axes).flatten()

    for idx, act in enumerate(acts):
        ax = axes[idx]
        res = per_treatment_auuc_res[act]
        fracs = np.array(res["fractions"])
        uc_model = np.array(res["model_uc_values"])
        uc_rand = np.array(res["random_uc_values"])

        ax.plot(fracs, uc_model, "b-o", markersize=3, linewidth=1.8,
                label=f"T-Learner (AUUC={res['auuc_model']:.4f})")
        ax.plot(fracs, uc_rand, "gray", linewidth=1.2, linestyle="--",
                label="Random")

        if "oracle_uc_values" in res:
            uc_oracle = np.array(res["oracle_uc_values"])
            ax.plot(fracs, uc_oracle, "g--^", markersize=3, linewidth=1.8,
                    label=f"Oracle (AUUC={res.get('auuc_oracle', 0):.4f})")

        ax.fill_between(fracs, uc_rand, uc_model, alpha=0.12, color="blue")
        ax.set_title(f"{act.replace('_', ' ').title()}", fontsize=10)
        ax.set_xlabel("Fraction Targeted", fontsize=8)
        ax.set_ylabel("Incremental Rate", fontsize=8)
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(0, 1)

    for idx in range(len(acts), len(axes)):
        axes[idx].set_visible(False)

    fig.suptitle("WAPSI Uplift Curves: T-Learner vs Oracle vs Random (Per Treatment)", fontsize=12, y=1.01)
    plt.tight_layout()
    plot_path = out_dir / "uplift_curves_per_treatment.png"
    fig.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(plot_path)


# ---------------------------------------------------------------------------
# Summary Text Generator
# ---------------------------------------------------------------------------

def _generate_text_report(
    metrics: Dict[str, Any],
    kpis: Dict[str, Any],
    routing_efficiency: Dict[str, Any],
    per_treatment_q: Dict[str, Any],
    per_treatment_auuc_res: Dict[str, Any],
    segment_qini_res: Dict[str, Any]
) -> str:
    """
    Generates a human-readable text report of the WAPSI uplift evaluation.
    Includes a final verdict on whether the model ranks persuadable customers
    better than random targeting.
    """
    lines = []
    lines.append("=" * 78)
    lines.append("WAPSI UPLIFT EVALUATION REPORT")
    lines.append("Razorpay AI Buildathon 2026 | Causal Recovery Decision Engine")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append("=" * 78)

    # Model info
    lines.append("\n[1] EVALUATION SETUP")
    lines.append(f"  Train rows    : {metrics.get('train_rows', 'N/A')}")
    lines.append(f"  Test rows     : {metrics.get('test_rows', 'N/A')}")
    lines.append(f"  Evaluation    : T-Learner vs Oracle (hidden CATE) vs Random Targeting")
    lines.append(f"  Isolation     : Model trained on observed data ONLY (no tau_* or y_* columns)")

    # Overall Qini
    lines.append("\n[2] OVERALL QINI COEFFICIENT (Best-Action vs No-Action)")
    oq = metrics.get("overall_qini", {})
    lines.append(f"  T-Learner Qini coefficient : {oq.get('model_qini_coefficient', 'N/A')}")
    lines.append(f"  Oracle Qini coefficient    : {oq.get('oracle_qini_coefficient', 'N/A')}")
    lines.append(f"  Interpretation: Positive Qini = model prioritizes persuadable cases better than random")

    # Per-treatment Qini
    lines.append("\n[3] PER-TREATMENT QINI COEFFICIENTS")
    for act in ACTIVE_TREATMENTS:
        if act in per_treatment_q:
            q = per_treatment_q[act]
            lines.append(f"  {act:20s}: Qini={q['qini_coefficient']:+.4f}  (n={q['n']}, "
                         f"n_treated={q['n_treated']}, n_control={q['n_control']})")

    # AUUC
    lines.append("\n[4] AUUC (Area Under Uplift Curve vs Random Baseline)")
    for act in ACTIVE_TREATMENTS:
        if act in per_treatment_auuc_res:
            a = per_treatment_auuc_res[act]
            oracle_str = f", Oracle AUUC={a.get('auuc_oracle', 'N/A')}" if "auuc_oracle" in a else ""
            lines.append(f"  {act:20s}: AUUC={a['auuc_model']:+.6f}{oracle_str}")

    # Routing efficiency
    lines.append("\n[5] MODEL ROUTING EFFICIENCY (vs Oracle CATE Ranking)")
    re = routing_efficiency
    lines.append(f"  Pearson corr (model uplift vs oracle CATE) : {re.get('model_oracle_pearson_correlation', 'N/A')}")
    lines.append(f"  Spearman rho (model uplift vs oracle CATE)  : {re.get('model_oracle_spearman_rho', 'N/A')}")
    lines.append(f"  Best-action match rate (model vs oracle)    : {re.get('pct_model_best_matches_oracle', 'N/A')}")

    # Segment Qini
    lines.append("\n[6] SEGMENT-LEVEL QINI BY DOMAIN")
    for seg, sq in sorted(segment_qini_res.items()):
        lines.append(f"  {seg:15s}: Qini={sq['qini_coefficient']:+.4f}  (n={sq['n']})")

    # Business KPIs
    lines.append("\n[7] BUSINESS KPIs (Factual Test Set -- No Fabrication)")
    lines.append(f"  Control (no_action) recovery rate: "
                 f"{kpis['control_baseline']['recovery_rate']:.1%}")
    for act in ACTIVE_TREATMENTS:
        if act in kpis.get("per_treatment", {}):
            kp = kpis["per_treatment"][act]
            lines.append(
                f"  {act:20s}: "
                f"rate={kp['recovery_rate']:.1%} "
                f"(+{kp['recovery_rate_lift_vs_control']:.1%} vs control), "
                f"Rs/contact=Rs.{kp['rs_recovered_per_contact']:,.0f}, "
                f"Rs/fatigue=Rs.{kp['rs_recovered_per_fatigue_unit']:,.0f}"
            )
            if "rs_recovered_per_retry_attempt" in kp:
                lines.append(f"    {'':20s}  Rs/retry=Rs.{kp['rs_recovered_per_retry_attempt']:,.0f}")

    # Final verdict
    lines.append("\n" + "=" * 78)
    lines.append("FINAL VERDICT: Does WAPSI rank persuadable customers better than random?")
    lines.append("=" * 78)
    pos_qini_count = sum(
        1 for a in ACTIVE_TREATMENTS
        if a in per_treatment_q and per_treatment_q[a]["qini_coefficient"] > 0
    )
    pos_auuc_count = sum(
        1 for a in ACTIVE_TREATMENTS
        if a in per_treatment_auuc_res and per_treatment_auuc_res[a]["auuc_model"] > 0
    )
    total_acts = len(ACTIVE_TREATMENTS)

    lines.append(f"\n  {pos_qini_count}/{total_acts} treatment arms show POSITIVE Qini coefficient")
    lines.append(f"  {pos_auuc_count}/{total_acts} treatment arms show POSITIVE AUUC vs random")

    rho = routing_efficiency.get("model_oracle_spearman_rho", 0.0) or 0.0
    if pos_qini_count >= total_acts // 2 and rho > 0.1:
        verdict = "YES -- WAPSI's T-Learner ranks persuadable customers significantly better than random targeting."
        interpretation = (
            "The model successfully identifies cases where intervention creates incremental recovery, "
            "rather than merely identifying customers who would recover anyway. "
            f"The Spearman rank correlation with oracle CATE is {rho:.3f}, confirming meaningful causal signal extraction."
        )
    elif pos_qini_count > 0:
        verdict = "PARTIALLY -- The model shows positive lift for some treatment arms."
        interpretation = (
            "Uplift ranking is better than random for a subset of treatments. "
            "Performance improvement is expected with more training data or a DR/R-Learner upgrade."
        )
    else:
        verdict = "NO -- The model does not demonstrate significant uplift ranking above random."
        interpretation = (
            "The T-Learner baseline has insufficient signal to rank persuadable customers. "
            "This may indicate dataset size, confounding, or model complexity issues."
        )

    lines.append(f"\n  VERDICT: {verdict}")
    lines.append(f"\n  {interpretation}")
    lines.append("\n" + "=" * 78)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main Report Runner
# ---------------------------------------------------------------------------

class WAPSIUpliftEvaluator:
    """
    End-to-end WAPSI uplift evaluation orchestrator.

    Enforces strict data isolation: model training uses observed data only,
    oracle benchmarking uses hidden ground truth only for ranking comparison.
    """

    def __init__(
        self,
        data_dir: str = "data",
        output_dir: str = "evaluation",
        n_bins: int = 20,
        random_seed: int = 42
    ):
        self.data_dir = data_dir
        self.output_dir = Path(output_dir)
        self.plots_dir = self.output_dir / "plots" / "uplift_plots"
        self.n_bins = n_bins
        self.random_seed = random_seed
        self.model: Optional[WAPSIUpliftModel] = None

    def run(
        self,
        model: Optional[WAPSIUpliftModel] = None,
        df_train: Optional[pd.DataFrame] = None,
        df_test: Optional[pd.DataFrame] = None,
        df_gt_test: Optional[pd.DataFrame] = None
    ) -> Dict[str, Any]:
        """
        Runs the full evaluation pipeline.

        Args:
            model:      Pre-fitted WAPSIUpliftModel (optional — trains from scratch if None).
            df_train:   Training data (optional, used only if model is None).
            df_test:    Test split observed data (no potential outcomes).
            df_gt_test: Ground truth test split (evaluation only).

        Returns:
            Dict with all computed metrics, KPIs, and plot paths.
        """
        self.plots_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Load data
        if df_test is None or df_gt_test is None:
            df_train_loaded, df_test, df_gt_test, _ = _load_or_generate_data(
                self.data_dir, random_seed=self.random_seed
            )
            if df_train is None:
                df_train = df_train_loaded

        # Step 2: Train model (isolation enforced inside WAPSIUpliftModel.fit)
        if model is None:
            if df_train is None:
                raise ValueError("Either 'model' or 'df_train' must be provided.")
            self.model = _train_model(df_train, self.random_seed)
        else:
            self.model = model

        # Step 3: Per-treatment Qini (binary comparison for each arm)
        print("[Eval] Computing per-treatment Qini curves...")
        per_treatment_q = multi_treatment_qini(
            df=df_test,
            model=self.model,
            treatments=ACTIVE_TREATMENTS,
            control=CONTROL,
            n_bins=self.n_bins
        )

        # Step 4: Per-treatment AUUC with oracle comparison
        print("[Eval] Computing per-treatment AUUC (model vs oracle)...")
        per_treatment_auuc_res = per_treatment_auuc(
            df_observed=df_test,
            df_ground_truth=df_gt_test,
            model=self.model,
            treatments=ACTIVE_TREATMENTS,
            control=CONTROL,
            n_bins=self.n_bins
        )

        # Step 5: Segment-level Qini (domain-level)
        print("[Eval] Computing segment-level Qini by domain...")
        # Use best-action uplift score for overall segment ranking
        all_uplifts = self.model.predict_uplift(df_test)
        uplift_matrix = np.column_stack([all_uplifts[act] for act in ACTIVE_TREATMENTS])
        df_test_scored = df_test.copy()
        df_test_scored["_best_uplift"] = uplift_matrix.max(axis=1)
        df_test_scored["_binary_treatment"] = np.where(
            df_test_scored["treatment"] == CONTROL, CONTROL, "intervention"
        )

        segment_qini_res = segment_qini(
            df=df_test_scored,
            segment_col="domain",
            uplift_score_col="_best_uplift",
            y_true_col="recovered",
            treatment_col="_binary_treatment",
            treatment_label="intervention",
            control_label=CONTROL,
            n_bins=self.n_bins,
            min_segment_size=50
        )

        # Step 6: Routing efficiency vs oracle
        print("[Eval] Computing model routing efficiency vs oracle CATE...")
        routing_efficiency = compute_model_routing_efficiency(
            df_test, df_gt_test, self.model, self.n_bins
        )

        # Step 7: Business KPIs
        print("[Eval] Computing business KPIs...")
        kpis = compute_business_kpis(df_test, self.model)

        # Step 8: Decile lift table
        print("[Eval] Computing decile lift table...")
        decile_table = compute_decile_lift_table(
            df_test, self.model, ACTIVE_TREATMENTS, CONTROL
        )

        # Step 9: Overall Qini metrics
        all_uplifts_full = self.model.predict_uplift(df_test)
        uplift_mat = np.column_stack([all_uplifts_full[act] for act in ACTIVE_TREATMENTS])
        overall_score = uplift_mat.max(axis=1)
        binary_t = np.where(df_test["treatment"].values == CONTROL, CONTROL, "intervention")

        fracs_overall, qini_overall = qini_curve(
            y_true=df_test["recovered"].values,
            uplift_score=overall_score,
            treatment=binary_t,
            treatment_label="intervention",
            control_label=CONTROL,
            n_bins=self.n_bins
        )
        model_q_coeff = qini_coefficient(fracs_overall, qini_overall)

        oracle_q_coeff = None
        if "oracle_max_uplift" in df_gt_test.columns:
            o_fracs, o_vals = oracle_qini_curve(
                tau_true=df_gt_test["oracle_max_uplift"].values,
                y_true=df_test["recovered"].values,
                treatment=binary_t,
                treatment_label="intervention",
                control_label=CONTROL,
                n_bins=self.n_bins
            )
            oracle_q_coeff = qini_coefficient(o_fracs, o_vals)

        overall_qini_metrics = {
            "model_qini_coefficient": round(model_q_coeff, 6),
            "oracle_qini_coefficient": round(oracle_q_coeff, 6) if oracle_q_coeff is not None else None,
            "fractions": fracs_overall.tolist(),
            "model_qini_values": np.round(qini_overall, 6).tolist()
        }

        # Step 10: Generate plots
        print("[Plots] Generating evaluation plots...")
        plot_paths = {}
        try:
            plot_paths["overall_qini"] = _plot_overall_qini(
                df_test, df_gt_test, self.model, self.plots_dir, self.n_bins
            )
        except Exception as e:
            print(f"[Plots] Warning: overall_qini plot failed: {e}")

        try:
            plot_paths["per_treatment_qini"] = _plot_per_treatment_qini(
                per_treatment_q, self.plots_dir
            )
        except Exception as e:
            print(f"[Plots] Warning: per_treatment_qini plot failed: {e}")

        try:
            plot_paths["auuc_comparison"] = _plot_auuc_comparison(
                per_treatment_auuc_res, self.plots_dir
            )
        except Exception as e:
            print(f"[Plots] Warning: auuc_comparison plot failed: {e}")

        try:
            plot_paths["segment_qini"] = _plot_segment_qini(
                segment_qini_res, self.plots_dir
            )
        except Exception as e:
            print(f"[Plots] Warning: segment_qini plot failed: {e}")

        try:
            plot_paths["business_kpis"] = _plot_business_kpis(kpis, self.plots_dir)
        except Exception as e:
            print(f"[Plots] Warning: business_kpis plot failed: {e}")

        try:
            plot_paths["uplift_curves"] = _plot_uplift_curves_per_treatment(
                per_treatment_auuc_res, self.plots_dir
            )
        except Exception as e:
            print(f"[Plots] Warning: uplift_curves plot failed: {e}")

        # Step 11: Assemble full metrics dict
        metrics = {
            "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
            "train_rows": len(df_train) if df_train is not None else "N/A",
            "test_rows": int(len(df_test)),
            "overall_qini": overall_qini_metrics,
            "per_treatment_qini": per_treatment_q,
            "per_treatment_auuc": per_treatment_auuc_res,
            "segment_qini_by_domain": segment_qini_res,
            "routing_efficiency": routing_efficiency,
            "business_kpis": kpis,
            "plot_paths": plot_paths
        }

        # Step 12: Save reports
        print("[Report] Writing uplift_report.json and uplift_report.txt...")
        report_json_path = self.output_dir / "uplift_report.json"
        # Ensure the dict is JSON-serializable (convert DataFrame to records)
        serializable_metrics = json.loads(json.dumps(metrics, default=lambda x: str(x)))
        with open(report_json_path, "w", encoding="utf-8") as f:
            json.dump(serializable_metrics, f, indent=2)

        text_report = _generate_text_report(
            metrics, kpis, routing_efficiency,
            per_treatment_q, per_treatment_auuc_res, segment_qini_res
        )
        with open(self.output_dir / "uplift_report.txt", "w", encoding="utf-8") as f:
            f.write(text_report)

        # Step 13: Save decile lift table
        if not decile_table.empty:
            decile_table.to_csv(self.output_dir / "decile_lift_table.csv", index=False)

        print(f"[Done] Uplift report saved to {self.output_dir}/")
        print("\n" + text_report)

        return metrics


def run_uplift_evaluation(
    data_dir: str = "data",
    output_dir: str = "evaluation",
    n_bins: int = 20,
    random_seed: int = 42,
    model: Optional[WAPSIUpliftModel] = None,
    df_train: Optional[pd.DataFrame] = None,
    df_test: Optional[pd.DataFrame] = None,
    df_gt_test: Optional[pd.DataFrame] = None
) -> Dict[str, Any]:
    """
    Convenience function to run the full WAPSI uplift evaluation pipeline.

    Args:
        data_dir:    Directory containing parquet data files.
        output_dir:  Directory to write evaluation reports and plots.
        n_bins:      Number of bins for Qini/uplift curves.
        random_seed: RNG seed for model training.
        model:       Pre-fitted model (optional).
        df_train:    Training data (optional if model is provided).
        df_test:     Test observations (optional, loaded from disk if absent).
        df_gt_test:  Ground truth test (optional, loaded from disk if absent).

    Returns:
        Full metrics dictionary.
    """
    evaluator = WAPSIUpliftEvaluator(
        data_dir=data_dir,
        output_dir=output_dir,
        n_bins=n_bins,
        random_seed=random_seed
    )
    return evaluator.run(
        model=model,
        df_train=df_train,
        df_test=df_test,
        df_gt_test=df_gt_test
    )


if __name__ == "__main__":
    run_uplift_evaluation(
        data_dir="data",
        output_dir="evaluation",
        n_bins=20,
        random_seed=42
    )
