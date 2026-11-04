"""
WAPSI Synthetic Causal Recovery Environment & Tabular Data Generator.
Razorpay AI Buildathon 2026 - Track 3

Generates realistic payment/recovery opportunity tabular datasets with known
ground-truth Heterogeneous Treatment Effects (HTE), confounding, fatigue dynamics,
and hidden potential outcomes Y(a) strictly segregated from the training pipeline.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path
import json
import argparse
import numpy as np
import pandas as pd


# Action Space Definitions
TREATMENTS: List[str] = [
    "no_action",
    "retry_only",
    "whatsapp_nudge",
    "voice_call",
    "email",
    "incentive_link",
]

DOMAINS: List[str] = [
    "ecommerce",
    "b2b_saas",
    "travel",
    "education",
    "gaming",
    "subscription",
    "food_delivery",
]

DECLINE_REASONS: List[str] = [
    "insufficient_funds",
    "technical_gateway_error",
    "authentication_failed",
    "upi_pin_timeout",
    "card_limit_exceeded",
    "user_cancelled_checkout",
    "bank_downtime",
]

ISSUERS: List[str] = ["HDFC", "ICICI", "SBI", "AXIS", "KOTAK", "CITI", "OTHER"]

BIN_BUCKETS: List[str] = [
    "classic",
    "platinum",
    "signature",
    "corporate",
    "rupay",
    "upi_standard",
]


@dataclass
class RecoveryDataConfig:
    """Configuration for synthetic recovery data generation."""
    n_samples: int = 50000
    random_seed: int = 42
    train_ratio: float = 0.70
    val_ratio: float = 0.15
    test_ratio: float = 0.15
    output_dir: str = "data"
    export_parquet: bool = True
    export_csv: bool = True


class WapsiDataGenerator:
    """
    Realistic Data Generating Process (DGP) for Payment Recovery Causal Decisioning.
    Implements heterogeneous treatment effects across domains, issuers, amounts,
    failure reasons, customer fatigue, and diurnal cycles.
    """

    def __init__(self, config: Optional[RecoveryDataConfig] = None):
        self.config = config or RecoveryDataConfig()
        self.rng = np.random.default_rng(self.config.random_seed)

    def generate(
        self,
        n_samples: Optional[int] = None
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Generates observed dataset and hidden ground-truth potential outcomes dataset.

        Returns:
            df_observed: Contains only features, observed treatment, and factual outcome.
            df_ground_truth: Complete dataset containing true latent probabilities,
                             counterfactual potential outcomes Y(a), and optimal oracle policies.
        """
        n = n_samples or self.config.n_samples
        rng = self.rng

        # -------------------------------------------------------------
        # 1. IDENTIFIERS & DOMAIN/MERCHANT ASSIGNMENT
        # -------------------------------------------------------------
        case_ids = [f"case_{rng.integers(10000000, 99999999):08x}{i:04x}" for i in range(n)]
        
        # Unique customer pool (simulating repeat customer behavior)
        n_unique_customers = max(100, int(n * 0.45))
        customer_pool = [f"cust_{rng.integers(100000, 999999)}" for _ in range(n_unique_customers)]
        customer_ids = [customer_pool[idx] for idx in rng.integers(0, n_unique_customers, size=n)]

        domain_probs = [0.32, 0.14, 0.12, 0.10, 0.12, 0.10, 0.10]
        domains = rng.choice(DOMAINS, size=n, p=domain_probs)

        # Merchant pool segmented by domain
        merchant_names_by_domain = {
            "ecommerce": ["merch_urban_mart", "merch_trend_hub", "merch_style_kart", "merch_blitz_retail"],
            "b2b_saas": ["merch_cloud_scale", "merch_flow_ops", "merch_dev_stack", "merch_data_weave"],
            "travel": ["merch_skytrip", "merch_voyage_air", "merch_stay_luxe"],
            "education": ["merch_edupath", "merch_skill_core", "merch_acad_plus"],
            "gaming": ["merch_play_arena", "merch_game_loot", "merch_nexus_quest"],
            "subscription": ["merch_stream_pass", "merch_fit_box", "merch_news_wire"],
            "food_delivery": ["merch_quick_bite", "merch_feast_now", "merch_chef_cart"],
        }
        merchant_ids = [
            rng.choice(merchant_names_by_domain[dom]) for dom in domains
        ]

        # -------------------------------------------------------------
        # 2. CASE CONTEXT & COVARIATES (X)
        # -------------------------------------------------------------
        # Amount in INR (Domain-conditioned lognormal distribution, strictly > 0)
        amount = np.zeros(n)
        for i, dom in enumerate(domains):
            if dom == "b2b_saas":
                raw_amt = np.exp(rng.normal(loc=9.2, scale=0.9)) # median ~₹9,900
                amount[i] = np.clip(raw_amt, 1500.0, 150000.0)
            elif dom == "travel":
                raw_amt = np.exp(rng.normal(loc=8.8, scale=0.8)) # median ~₹6,600
                amount[i] = np.clip(raw_amt, 800.0, 75000.0)
            elif dom == "education":
                raw_amt = np.exp(rng.normal(loc=8.2, scale=0.8)) # median ~₹3,600
                amount[i] = np.clip(raw_amt, 499.0, 45000.0)
            elif dom == "ecommerce":
                raw_amt = np.exp(rng.normal(loc=7.6, scale=0.9)) # median ~₹2,000
                amount[i] = np.clip(raw_amt, 199.0, 35000.0)
            elif dom == "subscription":
                raw_amt = np.exp(rng.normal(loc=6.9, scale=0.6)) # median ~₹1,000
                amount[i] = np.clip(raw_amt, 149.0, 9999.0)
            elif dom == "gaming":
                raw_amt = np.exp(rng.normal(loc=6.0, scale=0.9)) # median ~₹400
                amount[i] = np.clip(raw_amt, 49.0, 8000.0)
            else: # food_delivery
                raw_amt = np.exp(rng.normal(loc=5.9, scale=0.5)) # median ~₹360
                amount[i] = np.clip(raw_amt, 99.0, 4500.0)
        amount = np.round(amount, 2)

        # Decline Reasons
        decline_probs = [0.24, 0.20, 0.16, 0.18, 0.08, 0.08, 0.06]
        decline_reasons = rng.choice(DECLINE_REASONS, size=n, p=decline_probs)

        # Issuer & BIN Bucket
        issuer_probs = [0.28, 0.22, 0.18, 0.14, 0.08, 0.04, 0.06]
        issuers = rng.choice(ISSUERS, size=n, p=issuer_probs)

        bin_probs = [0.30, 0.25, 0.12, 0.08, 0.10, 0.15]
        bin_buckets = rng.choice(BIN_BUCKETS, size=n, p=bin_probs)

        # Attempts used (1 to 4)
        attempts_used = rng.choice([1, 2, 3, 4], size=n, p=[0.60, 0.25, 0.10, 0.05])

        # Temporal Context
        day_of_week = rng.integers(0, 7, size=n)
        hour = rng.integers(0, 24, size=n)
        is_daytime = ((hour >= 9) & (hour <= 21)).astype(float)
        is_weekend = (day_of_week >= 5).astype(float)

        # Customer History & Lifetime Metrics
        account_age_days = np.clip(np.round(rng.exponential(scale=240, size=n) + 1), 1, 2500).astype(int)
        previous_failures = rng.poisson(lam=1.6, size=n)
        
        # Previous recoveries conditioned on history
        base_recovery_prop = np.clip(rng.beta(a=3, b=3, size=n), 0.05, 0.95)
        previous_recoveries = rng.binomial(n=previous_failures + 1, p=base_recovery_prop * 0.7)
        previous_recoveries = np.minimum(previous_recoveries, previous_failures + 3)

        # Prior recovery rate (strictly bounded, safe division without warnings)
        total_prev_cases = previous_failures + previous_recoveries
        prior_recovery_rate = np.zeros(n, dtype=float)
        valid_prev_mask = (total_prev_cases > 0)
        prior_recovery_rate[valid_prev_mask] = np.round(
            previous_recoveries[valid_prev_mask] / total_prev_cases[valid_prev_mask], 4
        )

        # Fatigue Score: Continuous [0.0, 1.0]
        # Increases with attempts used, previous failures, and repeat recent outreach
        latent_fatigue = (
            0.20 * (attempts_used - 1)
            + 0.10 * np.minimum(previous_failures, 5)
            + 0.15 * (1.0 - prior_recovery_rate)
            + rng.normal(loc=0.0, scale=0.08, size=n)
        )
        fatigue_score = np.clip(np.round(latent_fatigue, 4), 0.0, 1.0)

        # -------------------------------------------------------------
        # 3. LATENT POTENTIAL OUTCOMES & CAUSAL DGP
        # -------------------------------------------------------------
        # Identify organic self-curers: loyal repeat buyers with good recovery history and low friction
        is_self_curer = (
            (prior_recovery_rate >= 0.45)
            & (attempts_used <= 2)
            & (account_age_days >= 45)
            & (fatigue_score <= 0.35)
            & np.isin(decline_reasons, ["authentication_failed", "upi_pin_timeout", "user_cancelled_checkout", "technical_gateway_error"])
        ).astype(float)

        # Baseline Organic Recovery Probability: p0(x) = P(Y(no_action) = 1 | X=x)
        logit_p0 = (
            -2.20
            + 1.15 * prior_recovery_rate
            + 1.45 * is_self_curer  # Strong organic self-cure boost
            - 0.35 * np.log1p(amount / 1000.0)
            - 0.35 * (attempts_used - 1)
            - 0.50 * fatigue_score
            + 0.25 * is_daytime
            + 0.25 * (np.array(decline_reasons) == "technical_gateway_error").astype(float)
            + 0.15 * (np.array(decline_reasons) == "bank_downtime").astype(float)
            - 0.95 * (np.array(decline_reasons) == "insufficient_funds").astype(float)
            - 0.55 * (np.array(decline_reasons) == "card_limit_exceeded").astype(float)
            + 0.20 * np.isin(domains, ["subscription", "b2b_saas"]).astype(float)
        )
        p0 = 1.0 / (1.0 + np.exp(-logit_p0))
        p0 = np.clip(p0, 0.02, 0.55) # Natural recovery baseline up to 55% for self-curers

        # Heterogeneous Treatment Effects for all treatments
        p_potential = np.zeros((n, len(TREATMENTS)))
        p_potential[:, 0] = p0 # index 0 is no_action

        # Headroom multiplier: for self-curers, external nudge uplift is near-zero because they self-cure
        # For high fatigue, interactive nudge receptivity drops sharply
        intervention_receptivity = (1.0 - 0.92 * is_self_curer) * np.clip(1.0 - 0.85 * fatigue_score, 0.05, 1.0)

        # Action 1: retry_only
        # Exceptional for technical/gateway and bank downtime on tier-1 issuers (HDFC, ICICI, AXIS)
        # Near zero for self-curers (who don't need retry), insufficient funds, user cancellations
        tau_retry_raw = (
            0.52 * (np.array(decline_reasons) == "technical_gateway_error").astype(float)
            + 0.45 * (np.array(decline_reasons) == "bank_downtime").astype(float)
            + 0.12 * np.isin(issuers, ["HDFC", "ICICI", "AXIS"]).astype(float)
            - 0.15 * (attempts_used > 2).astype(float)
            - 0.25 * (np.array(decline_reasons) == "insufficient_funds").astype(float)
            - 0.20 * (np.array(decline_reasons) == "user_cancelled_checkout").astype(float)
        )
        tau_retry = np.clip(tau_retry_raw * (1.0 - 0.90 * is_self_curer), -0.05, 0.65)
        p_potential[:, 1] = np.clip(p0 + tau_retry, 0.01, 0.96)

        # Action 2: whatsapp_nudge
        # Exceptional for mobile/consumer UPI, friction/auth dropouts, ecommerce/food/gaming
        # Ineffective for hard bank outages or insufficient funds
        is_consumer_domain = np.isin(domains, ["ecommerce", "food_delivery", "gaming", "subscription"]).astype(float)
        is_friction_drop = np.isin(decline_reasons, ["upi_pin_timeout", "authentication_failed", "user_cancelled_checkout"]).astype(float)
        tau_wa_raw = (
            0.42 * is_friction_drop
            + 0.18 * is_consumer_domain
            + 0.15 * prior_recovery_rate
            + 0.10 * (amount <= 4000).astype(float)
            - 0.22 * (np.array(decline_reasons) == "bank_downtime").astype(float)
            - 0.15 * (np.array(decline_reasons) == "insufficient_funds").astype(float)
        )
        tau_wa = tau_wa_raw * intervention_receptivity * (0.4 + 0.6 * is_daytime)
        p_potential[:, 2] = np.clip(p0 + tau_wa, 0.01, 0.95)

        # Action 3: voice_call
        # High-touch: Outstanding for high ticket amounts (> ₹8,000), B2B SaaS, Education, Travel, Corporate BINs
        # Defier risk: Incur friction penalty if amount is trivial (< ₹500), fatigue is extreme (> 0.7), or user is a self-curer
        is_high_ticket = (amount >= 7500.0).astype(float)
        is_b2b_or_edu = np.isin(domains, ["b2b_saas", "education", "travel"]).astype(float)
        is_corp_bin = np.isin(bin_buckets, ["corporate", "signature", "platinum"]).astype(float)
        
        tau_voice_positive = (
            0.48 * is_high_ticket
            + 0.22 * is_b2b_or_edu
            + 0.14 * is_corp_bin
            + 0.18 * (np.array(decline_reasons) == "card_limit_exceeded").astype(float)
        ) * is_daytime * intervention_receptivity

        # Annoyance defier penalty on micro amounts, night calls, or self-curers who dislike calls
        voice_annoyance = (
            0.15 * (amount < 600.0).astype(float)
            + 0.25 * (1.0 - is_daytime)
            + 0.15 * (fatigue_score > 0.65).astype(float)
            + 0.10 * is_self_curer
        )
        tau_voice = tau_voice_positive - voice_annoyance
        p_potential[:, 3] = np.clip(p0 + tau_voice, 0.01, 0.92)

        # Action 4: email
        # Strongest for B2B SaaS, Education, formal subscription renewals, desktop workflows
        is_b2b_domain = (np.array(domains) == "b2b_saas").astype(float)
        tau_email_raw = (
            0.36 * is_b2b_domain
            + 0.20 * (np.array(domains) == "education").astype(float)
            + 0.14 * (np.array(domains) == "subscription").astype(float)
            + 0.10 * (account_age_days > 180).astype(float)
            + 0.08 * (amount >= 5000.0).astype(float)
            - 0.10 * np.isin(domains, ["food_delivery", "gaming"]).astype(float)
        )
        tau_email = tau_email_raw * (1.0 - 0.70 * is_self_curer) * (1.0 - 0.30 * fatigue_score)
        p_potential[:, 4] = np.clip(p0 + tau_email, 0.01, 0.90)

        # Action 5: incentive_link
        # Micro-incentive/discount: High uplift on user cancellations, cart dropouts, ecommerce/travel
        # Ineffective for hard bank outages, but very effective for price hesitation
        is_abandon_or_cancel = np.isin(decline_reasons, ["user_cancelled_checkout", "insufficient_funds", "card_limit_exceeded"]).astype(float)
        tau_incentive_raw = (
            0.40 * is_abandon_or_cancel
            + 0.18 * np.isin(domains, ["ecommerce", "travel", "food_delivery"]).astype(float)
            + 0.12 * ((amount >= 800.0) & (amount <= 12000.0)).astype(float)
            - 0.22 * (np.array(decline_reasons) == "bank_downtime").astype(float)
        )
        tau_incentive = tau_incentive_raw * (1.0 - 0.75 * is_self_curer) * (1.0 - 0.25 * fatigue_score)
        p_potential[:, 5] = np.clip(p0 + tau_incentive, 0.01, 0.94)

        # Realize Binary Potential Outcomes Y(a) ~ Bernoulli(p_a)
        random_uniforms = rng.uniform(size=(n, len(TREATMENTS)))
        Y_potential = (random_uniforms < p_potential).astype(int)

        # Latent Recovery Timing Potential (Hours)
        t_potential = np.zeros((n, len(TREATMENTS)))
        base_timing_hours = [18.0, 0.08, 0.75, 1.8, 8.5, 3.2]
        for idx, base_h in enumerate(base_timing_hours):
            t_potential[:, idx] = np.round(
                np.clip(rng.exponential(scale=base_h, size=n) + 0.02, 0.01, 72.0),
                2
            )

        # -------------------------------------------------------------
        # 4. OBSERVATIONAL TREATMENT ASSIGNMENT (A) WITH POLICY BIAS
        # -------------------------------------------------------------
        # Historic business heuristics governed past treatment assignment
        assignment_logits = np.zeros((n, len(TREATMENTS)))
        # Base log-propensities
        assignment_logits[:, 0] = 0.20 # no_action
        assignment_logits[:, 1] = 1.30 * np.isin(decline_reasons, ["technical_gateway_error", "bank_downtime"]).astype(float)
        assignment_logits[:, 2] = 1.10 * np.isin(domains, ["ecommerce", "food_delivery"]).astype(float) + 0.60 * is_daytime
        assignment_logits[:, 3] = 1.40 * (amount > 8000.0).astype(float) + 0.70 * (np.array(domains) == "b2b_saas").astype(float)
        assignment_logits[:, 4] = 1.00 * (np.array(domains) == "b2b_saas").astype(float) + 0.50 * (np.array(domains) == "education").astype(float)
        assignment_logits[:, 5] = 0.90 * (np.array(decline_reasons) == "user_cancelled_checkout").astype(float)

        # Add stochastic noise for overlap / common support
        assignment_logits += rng.normal(loc=0.0, scale=0.35, size=(n, len(TREATMENTS)))
        exp_logits = np.exp(assignment_logits - np.max(assignment_logits, axis=1, keepdims=True))
        propensities = exp_logits / np.sum(exp_logits, axis=1, keepdims=True)

        assigned_indices = np.array([
            rng.choice(len(TREATMENTS), p=propensities[i]) for i in range(n)
        ])
        assigned_treatments = [TREATMENTS[idx] for idx in assigned_indices]

        # -------------------------------------------------------------
        # 5. SUTVA: OBSERVED FACTUAL OUTCOME (Y_obs, T_obs)
        # -------------------------------------------------------------
        row_indices = np.arange(n)
        Y_obs = Y_potential[row_indices, assigned_indices]
        T_obs = np.where(
            Y_obs == 1,
            t_potential[row_indices, assigned_indices],
            np.nan # Unrecovered cases have no recovery timestamp
        )

        # -------------------------------------------------------------
        # 6. ASSEMBLE DATAFRAMES
        # -------------------------------------------------------------
        # Public Observed DataFrame (Exposed to Training Pipeline)
        df_observed = pd.DataFrame({
            # Identifiers
            "case_id": case_ids,
            "merchant_id": merchant_ids,
            "customer_id": customer_ids,
            # Case Context
            "domain": domains,
            "amount": amount,
            "decline_reason": decline_reasons,
            "attempts_used": attempts_used,
            "account_age_days": account_age_days,
            "previous_failures": previous_failures,
            "previous_recoveries": previous_recoveries,
            "prior_recovery_rate": prior_recovery_rate,
            "day_of_week": day_of_week,
            "hour": hour,
            "issuer": issuers,
            "bin_bucket": bin_buckets,
            "fatigue_score": fatigue_score,
            # Observed Treatment
            "treatment": assigned_treatments,
            # Observed Outcome
            "recovered": Y_obs,
            "time_to_recovery_hours": T_obs,
        })

        # Ground Truth Hidden DataFrame (Evaluation Only)
        tau_ground_truth = p_potential - p_potential[:, [0]]
        oracle_best_idx = np.argmax(p_potential, axis=1)
        oracle_best_treatment = [TREATMENTS[idx] for idx in oracle_best_idx]
        oracle_max_uplift = np.max(tau_ground_truth, axis=1)

        # Determine Customer Archetype relative to best treatment vs control
        # Always-Taker: Y(0)=1 & Y(best)=1
        # Persuadable: Y(0)=0 & Y(best)=1
        # Defier: Y(0)=1 & Y(best)=0
        # Never-Taker: Y(0)=0 & Y(best)=0
        y_0_all = Y_potential[:, 0]
        y_best_all = Y_potential[row_indices, oracle_best_idx]
        archetypes = np.where(
            (y_0_all == 1) & (y_best_all == 1), "always_taker",
            np.where(
                (y_0_all == 0) & (y_best_all == 1), "persuadable",
                np.where((y_0_all == 1) & (y_best_all == 0), "defier", "never_taker")
            )
        )

        df_ground_truth = df_observed.copy()
        # Attach Latent Potential Probabilities
        for idx, t_name in enumerate(TREATMENTS):
            df_ground_truth[f"p_{t_name}"] = np.round(p_potential[:, idx], 4)
            df_ground_truth[f"tau_{t_name}"] = np.round(tau_ground_truth[:, idx], 4)
            df_ground_truth[f"y_{t_name}"] = Y_potential[:, idx]
            df_ground_truth[f"t_{t_name}"] = t_potential[:, idx]

        df_ground_truth["optimal_treatment"] = oracle_best_treatment
        df_ground_truth["oracle_max_uplift"] = np.round(oracle_max_uplift, 4)
        df_ground_truth["customer_archetype"] = archetypes

        return df_observed, df_ground_truth

    def split_and_export(
        self,
        df_observed: pd.DataFrame,
        df_ground_truth: pd.DataFrame,
        output_dir: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Performs train/validation/test split and exports datasets to CSV/Parquet.
        Guarantees NO potential outcomes exist in train/val/test feature matrices.
        """
        out_path = Path(output_dir or self.config.output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        n = len(df_observed)
        rng = np.random.default_rng(self.config.random_seed)
        shuffled_indices = rng.permutation(n)

        n_train = int(n * self.config.train_ratio)
        n_val = int(n * self.config.val_ratio)

        train_idx = shuffled_indices[:n_train]
        val_idx = shuffled_indices[n_train:n_train + n_val]
        test_idx = shuffled_indices[n_train + n_val:]

        train_df = df_observed.iloc[train_idx].reset_index(drop=True)
        val_df = df_observed.iloc[val_idx].reset_index(drop=True)
        test_df = df_observed.iloc[test_idx].reset_index(drop=True)

        # Ground-truth evaluation files
        gt_test_df = df_ground_truth.iloc[test_idx].reset_index(drop=True)
        gt_full_df = df_ground_truth.reset_index(drop=True)

        exported_files = {}

        # Export Parquet
        if self.config.export_parquet:
            train_df.to_parquet(out_path / "train.parquet", index=False)
            val_df.to_parquet(out_path / "val.parquet", index=False)
            test_df.to_parquet(out_path / "test.parquet", index=False)
            gt_test_df.to_parquet(out_path / "ground_truth_test.parquet", index=False)
            gt_full_df.to_parquet(out_path / "ground_truth_full.parquet", index=False)
            exported_files["train_parquet"] = str(out_path / "train.parquet")
            exported_files["val_parquet"] = str(out_path / "val.parquet")
            exported_files["test_parquet"] = str(out_path / "test.parquet")
            exported_files["ground_truth_test_parquet"] = str(out_path / "ground_truth_test.parquet")

        # Export CSV
        if self.config.export_csv:
            train_df.to_csv(out_path / "train.csv", index=False)
            val_df.to_csv(out_path / "val.csv", index=False)
            test_df.to_csv(out_path / "test.csv", index=False)
            gt_test_df.to_csv(out_path / "ground_truth_test.csv", index=False)
            exported_files["train_csv"] = str(out_path / "train.csv")
            exported_files["val_csv"] = str(out_path / "val.csv")
            exported_files["test_csv"] = str(out_path / "test.csv")
            exported_files["ground_truth_test_csv"] = str(out_path / "ground_truth_test.csv")

        # Generate & save summary statistics
        summary_stats = self.compute_summary_statistics(df_observed, df_ground_truth)
        
        with open(out_path / "summary_statistics.json", "w", encoding="utf-8") as f:
            json.dump(summary_stats, f, indent=2)
        
        summary_text = self._format_summary_text(summary_stats)
        with open(out_path / "summary_statistics.txt", "w", encoding="utf-8") as f:
            f.write(summary_text)

        exported_files["summary_json"] = str(out_path / "summary_statistics.json")
        exported_files["summary_txt"] = str(out_path / "summary_statistics.txt")

        return exported_files

    def compute_summary_statistics(
        self,
        df_observed: pd.DataFrame,
        df_ground_truth: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Computes exhaustive summary statistics and ground-truth ATE metrics.
        """
        total_samples = len(df_observed)
        
        # Treatment distribution & recovery rate
        treat_counts = df_observed["treatment"].value_counts().to_dict()
        treat_rates = df_observed.groupby("treatment")["recovered"].agg(["count", "mean"]).to_dict(orient="index")
        
        treatment_summary = {}
        for t, val in treat_rates.items():
            treatment_summary[t] = {
                "count": int(val["count"]),
                "share": round(float(val["count"] / total_samples), 4),
                "recovery_rate": round(float(val["mean"]), 4)
            }

        # Domain summary
        domain_summary = {}
        for d, val in df_observed.groupby("domain")["recovered"].agg(["count", "mean"]).to_dict(orient="index").items():
            domain_summary[d] = {
                "count": int(val["count"]),
                "recovery_rate": round(float(val["mean"]), 4)
            }

        # Decline reason summary
        decline_summary = {}
        for r, val in df_observed.groupby("decline_reason")["recovered"].agg(["count", "mean"]).to_dict(orient="index").items():
            decline_summary[r] = {
                "count": int(val["count"]),
                "recovery_rate": round(float(val["mean"]), 4)
            }

        # Ground truth Average Treatment Effect (ATE) vs no_action across full population
        ground_truth_ate = {}
        p0_mean = float(df_ground_truth["p_no_action"].mean())
        for t in TREATMENTS:
            if t == "no_action":
                ground_truth_ate[t] = {"true_p_mean": round(p0_mean, 4), "true_ate_vs_no_action": 0.0}
            else:
                p_t_mean = float(df_ground_truth[f"p_{t}"].mean())
                ate = float(df_ground_truth[f"tau_{t}"].mean())
                ground_truth_ate[t] = {
                    "true_p_mean": round(p_t_mean, 4),
                    "true_ate_vs_no_action": round(ate, 4)
                }

        # Customer archetype distribution
        archetype_counts = df_ground_truth["customer_archetype"].value_counts().to_dict()
        archetype_summary = {
            arch: {
                "count": int(cnt),
                "share": round(float(cnt / total_samples), 4)
            }
            for arch, cnt in archetype_counts.items()
        }

        # Key Segment Heterogeneity: Best Treatment by Segment
        segment_heterogeneity = []
        for (dom, reason), grp in df_ground_truth.groupby(["domain", "decline_reason"]):
            opt_treat = grp["optimal_treatment"].mode()[0]
            avg_uplift = float(grp["oracle_max_uplift"].mean())
            base_rec = float(grp["p_no_action"].mean())
            segment_heterogeneity.append({
                "domain": dom,
                "decline_reason": reason,
                "case_count": len(grp),
                "baseline_organic_rate": round(base_rec, 4),
                "dominant_optimal_treatment": opt_treat,
                "mean_oracle_uplift": round(avg_uplift, 4)
            })

        return {
            "total_samples": total_samples,
            "treatment_summary": treatment_summary,
            "domain_summary": domain_summary,
            "decline_reason_summary": decline_summary,
            "ground_truth_ate": ground_truth_ate,
            "archetype_distribution": archetype_summary,
            "top_segment_heterogeneity": segment_heterogeneity[:15]
        }

    def _format_summary_text(self, stats: Dict[str, Any]) -> str:
        lines = []
        lines.append("=" * 80)
        lines.append(f"WAPSI SYNTHETIC RECOVERY ENVIRONMENT — DATASET SUMMARY (N={stats['total_samples']:,})")
        lines.append("=" * 80)

        lines.append("\n[1] TREATMENT DISTRIBUTION & OBSERVED RECOVERY RATES:")
        lines.append(f"{'Treatment':<20} | {'Count':>8} | {'Share':>7} | {'Observed Recovery Rate':>22}")
        lines.append("-" * 65)
        for t, data in stats["treatment_summary"].items():
            lines.append(f"{t:<20} | {data['count']:>8,} | {data['share']*100:>6.1f}% | {data['recovery_rate']*100:>21.2f}%")

        lines.append("\n[2] GROUND-TRUTH AVERAGE TREATMENT EFFECT (ATE vs NO_ACTION):")
        lines.append(f"{'Treatment':<20} | {'True Mean Probability':>22} | {'True ATE Uplift':>16}")
        lines.append("-" * 65)
        for t, data in stats["ground_truth_ate"].items():
            lines.append(f"{t:<20} | {data['true_p_mean']*100:>21.2f}% | {data['true_ate_vs_no_action']*100:>+15.2f}%")

        lines.append("\n[3] LATENT CAUSAL ARCHETYPE BREAKDOWN:")
        for arch, data in stats["archetype_distribution"].items():
            lines.append(f"  - {arch:<15}: {data['count']:>7,} ({data['share']*100:>5.1f}%)")

        lines.append("\n[4] RECOVERY RATE BY DOMAIN:")
        for dom, data in stats["domain_summary"].items():
            lines.append(f"  - {dom:<18}: {data['count']:>7,} cases | Recovery Rate: {data['recovery_rate']*100:>5.2f}%")

        lines.append("\n[5] RECOVERY RATE BY DECLINE REASON:")
        for r, data in stats["decline_reason_summary"].items():
            lines.append(f"  - {r:<26}: {data['count']:>7,} cases | Recovery Rate: {data['recovery_rate']*100:>5.2f}%")

        lines.append("\n" + "=" * 80)
        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate WAPSI Causal Recovery Tabular Datasets")
    parser.add_argument("--n-samples", type=int, default=50000, help="Number of recovery cases (default: 50,000)")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic random seed (default: 42)")
    parser.add_argument("--output-dir", type=str, default="data", help="Output directory for exported datasets")
    args = parser.parse_args()

    cfg = RecoveryDataConfig(
        n_samples=args.n_samples,
        random_seed=args.seed,
        output_dir=args.output_dir
    )
    generator = WapsiDataGenerator(config=cfg)

    print(f"Generating {cfg.n_samples:,} synthetic recovery cases (Seed: {cfg.random_seed})...")
    df_obs, df_gt = generator.generate()

    print(f"Splitting (70% train, 15% val, 15% test) and exporting to '{cfg.output_dir}'...")
    exports = generator.split_and_export(df_obs, df_gt)

    stats = generator.compute_summary_statistics(df_obs, df_gt)
    print("\n" + generator._format_summary_text(stats))

    print("\nExported Artifacts:")
    for k, v in exports.items():
        print(f"  - {k}: {v}")


if __name__ == "__main__":
    main()
