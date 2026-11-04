"""
End-to-end training and validation script for WAPSI T-Learner Baseline.
Trains on data/train.parquet, validates on data/val.parquet, registers model in models/,
and demonstrates single-instance and batch uplift inference.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import numpy as np
import pandas as pd
from src.t_learner import WAPSIUpliftModel
from src.model_registry import ModelRegistry


def main():
    print("=" * 80)
    print("WAPSI — T-Learner Baseline Training & Model Registration")
    print("Razorpay AI Buildathon 2026 — Track 3")
    print("=" * 80)

    train_path = Path("data/train.parquet")
    val_path = Path("data/val.parquet")
    test_gt_path = Path("data/ground_truth_test.parquet")

    if not train_path.exists():
        print("Dataset not found. Generating default dataset first...")
        from src.data_generator import WapsiDataGenerator, RecoveryDataConfig
        gen = WapsiDataGenerator(RecoveryDataConfig(n_samples=50000, random_seed=42))
        df_obs, df_gt = gen.generate()
        gen.split_and_export(df_obs, df_gt, "data")

    print("\n[1/4] Loading training & validation splits...")
    df_train = pd.read_parquet(train_path)
    df_val = pd.read_parquet(val_path)
    print(f"      Train samples: {len(df_train):,} | Validation samples: {len(df_val):,}")

    print("\n[2/4] Fitting Multi-Action T-Learner Baseline...")
    model = WAPSIUpliftModel(random_seed=42, model_version="1.0.0")
    model.fit(df_train=df_train, df_val=df_val)
    print("      Model training complete.")

    # Validation Metrics
    meta = model.get_metadata()
    print("\nValidation Performance Metrics (per action arm):")
    for act, m in meta["validation_metrics"].items():
        print(f"  - {act:<20}: ROC-AUC = {m['val_auc']:.4f} | Log-Loss = {m['val_log_loss']:.4f}")

    print("\n[3/4] Registering trained model in Model Registry...")
    registry = ModelRegistry(registry_dir="models")
    artifact_path = registry.register_model(
        model=model,
        model_name="wapsi_t_learner",
        version="v1.0.0",
        set_as_production=True
    )
    print(f"      Model registered and persisted at: {artifact_path}")

    print("\n[4/4] Single-Instance Causal Uplift Inference Demo:")
    sample_case = {
        "case_id": "case_demo_001",
        "domain": "ecommerce",
        "amount": 2499.0,
        "decline_reason": "upi_pin_timeout",
        "attempts_used": 1,
        "account_age_days": 180,
        "previous_failures": 1,
        "previous_recoveries": 3,
        "prior_recovery_rate": 0.75,
        "day_of_week": 2,
        "hour": 15,
        "issuer": "HDFC",
        "bin_bucket": "classic",
        "fatigue_score": 0.10
    }
    
    print("\nIncoming Payment Failure Payload:")
    print(json.dumps(sample_case, indent=2))

    action_probs = model.predict_action_outcomes(sample_case)
    uplifts = model.predict_uplift(sample_case)

    print("\nEstimated Recovery Probabilities P(Recovery | Action):")
    print(json.dumps(action_probs, indent=2))

    print("\nEstimated Incremental Uplift vs no_action (tau_a):")
    print(json.dumps(uplifts, indent=2))

    # Evaluate on ground truth test set if available
    if test_gt_path.exists():
        df_test_gt = pd.read_parquet(test_gt_path)
        test_uplifts = model.predict_uplift(df_test_gt)
        print("\nGround-Truth Test Set Evaluation (N=7,500):")
        for act in uplifts:
            true_tau = df_test_gt[f"tau_{act}"].values
            pred_tau = test_uplifts[act]
            mae = float(np.mean(np.abs(pred_tau - true_tau)))
            corr = float(np.corrcoef(pred_tau, true_tau)[0, 1])
            print(f"  - {act:<20}: ITE MAE = {mae:.4f} | Pearson Correlation = {corr:.4f}")

    print("\n" + "=" * 80)
    print("T-Learner baseline execution completed successfully.")
    print("=" * 80)


if __name__ == "__main__":
    main()
