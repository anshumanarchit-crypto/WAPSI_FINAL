"""
Benchmark script for WAPSI Causal Decisioning Engine.
Evaluates T-Learner vs X-Learner vs Random Policy against known ground truth potential outcomes.
Computes AUUC, Qini scores, and Policy Regret.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from wapsi.data.generator import SyntheticRecoveryDataGenerator
from wapsi.causal.engine import CausalDecisionEngine
from wapsi.causal.evaluation import UpliftEvaluator
from wapsi.core.taxonomy import RecoveryAction


def run_benchmark():
    print("=" * 80)
    print("WAPSI — Razorpay Recovery Router Benchmark Evaluation")
    print("Track 3: Causal Decisioning for AI Revenue Recovery (Buildathon 2026)")
    print("=" * 80)

    gen = SyntheticRecoveryDataGenerator(random_seed=42)
    print("\n[1/4] Generating synthetic benchmark dataset with known potential outcomes...")
    train_df, train_pot = gen.generate_dataset(n_samples=5000, observational_bias=True)
    val_df, val_pot = gen.generate_dataset(n_samples=2000, observational_bias=True)
    print(f"      Training samples: {len(train_df):,} | Validation samples: {len(val_df):,}")

    print("\n[2/4] Training Causal Meta-Learners (T-Learner & X-Learner) & Calibrating Pipeline...")
    engine = CausalDecisionEngine(merchant_default_margin=0.20, random_seed=42)
    engine.train_pipeline(train_df=train_df, val_df=val_df)
    print("      Training complete.")

    print("\n[3/4] Evaluating Uplift & Qini Metrics on Validation Cohort...")
    val_uplifts_t = engine.t_learner.predict_uplift(val_df)
    val_uplifts_x = engine.x_learner.predict_uplift(val_df)

    eval_actions = [
        RecoveryAction.WHATSAPP_ONE_CLICK_LINK.value,
        RecoveryAction.INSTANT_SMART_RETRY.value,
        RecoveryAction.BNPL_ALTERNATIVE_OFFER.value,
        RecoveryAction.SMS_FALLBACK_LINK.value,
    ]

    print("\n--- Action-Specific Qini & Uplift Performance ---")
    for act in eval_actions:
        y_true = val_df["recovered"].values
        t_assigned = (val_df["assigned_action"] == act).astype(int).values
        u_t = val_uplifts_t[act]
        
        qini_res = UpliftEvaluator.compute_qini_curve(y_true, t_assigned, u_t)
        print(f"Action: {act:<30} | Qini Score: {qini_res['qini_score']:>8.2f} | Norm Qini: {qini_res['normalized_qini']:>6.2f}")

    print("\n[4/4] Ground Truth Potential Outcome Recovery Benchmark:")
    gt_eval_t = UpliftEvaluator.evaluate_ground_truth(
        predicted_uplifts=val_uplifts_t,
        ground_truth_tau=val_pot["tau_ground_truth"],
        action_names=val_pot["action_names"]
    )
    
    gt_eval_x = UpliftEvaluator.evaluate_ground_truth(
        predicted_uplifts=val_uplifts_x,
        ground_truth_tau=val_pot["tau_ground_truth"],
        action_names=val_pot["action_names"]
    )

    print("\nModel Comparison (Policy Regret vs Oracle Policy):")
    print(f"  T-Learner Policy Regret:         {gt_eval_t['policy_level']['policy_regret']:.4f} (Lower is better)")
    print(f"  T-Learner Mean Achieved Uplift:  +{gt_eval_t['policy_level']['mean_achieved_uplift']*100:.2f}%")
    print(f"  T-Learner Oracle Match Rate:     {gt_eval_t['policy_level']['oracle_optimal_match_rate']*100:.2f}%\n")

    print(f"  X-Learner Policy Regret:         {gt_eval_x['policy_level']['policy_regret']:.4f}")
    print(f"  X-Learner Mean Achieved Uplift:  +{gt_eval_x['policy_level']['mean_achieved_uplift']*100:.2f}%")
    print(f"  X-Learner Oracle Match Rate:     {gt_eval_x['policy_level']['oracle_optimal_match_rate']*100:.2f}%\n")

    print("=" * 80)
    print("Benchmark execution completed successfully.")
    print("=" * 80)


if __name__ == "__main__":
    run_benchmark()
