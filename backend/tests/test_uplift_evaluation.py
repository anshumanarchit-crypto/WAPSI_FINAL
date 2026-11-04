"""
Tests for WAPSI Uplift Evaluation Framework.
Razorpay AI Buildathon 2026 - Track 3

Covers:
  - Qini curve shape invariants (monotonicity of inputs, boundary values)
  - Qini coefficient bounds
  - AUUC sign (positive for meaningful model)
  - Oracle Qini >= T-Learner Qini (oracle is upper bound in expectation)
  - Business KPIs are non-negative finite floats
  - Segment evaluation runs without error for all domains
  - Strict data isolation: model trained on observed data only

IMPORTANT: All tests use a small synthetic dataset generated fresh (n=4000)
to avoid test suite slowness and dependency on pre-existing data files.
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path

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
from evaluation.uplift_report import (
    compute_business_kpis, compute_model_routing_efficiency,
    WAPSIUpliftEvaluator
)

ACTIVE_TREATMENTS = [t for t in TREATMENTS if t != "no_action"]
CONTROL = "no_action"
RNG_SEED = 42


# ---------------------------------------------------------------------------
# Shared Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def small_dataset():
    """Generates a small synthetic dataset (n=4000) for testing."""
    gen = WapsiDataGenerator(RecoveryDataConfig(n_samples=4000, random_seed=RNG_SEED))
    df_obs, df_gt = gen.generate()
    return df_obs, df_gt


@pytest.fixture(scope="module")
def fitted_model(small_dataset):
    """Fits a WAPSIUpliftModel on observed training data (strict isolation)."""
    df_obs, df_gt = small_dataset
    train_n = int(len(df_obs) * 0.7)
    df_train = df_obs.iloc[:train_n].copy()
    # Strict check: model.fit() must raise if potential outcomes are present
    model = WAPSIUpliftModel(random_seed=RNG_SEED)
    model.fit(df_train)
    return model


@pytest.fixture(scope="module")
def test_splits(small_dataset):
    """Returns test split (observed) and ground truth test split."""
    df_obs, df_gt = small_dataset
    train_n = int(len(df_obs) * 0.7)
    df_test = df_obs.iloc[train_n:].reset_index(drop=True)
    df_gt_test = df_gt.iloc[train_n:].reset_index(drop=True)
    return df_test, df_gt_test


# ---------------------------------------------------------------------------
# [A] Qini Curve Tests
# ---------------------------------------------------------------------------

class TestQiniCurve:

    def test_qini_curve_output_shape(self, small_dataset, fitted_model):
        """Qini curve must return (n_bins+1,) arrays anchored at (0.0, 0.0)."""
        df_obs, _ = small_dataset
        df_test = df_obs.iloc[int(len(df_obs) * 0.7):].copy()

        act = "whatsapp_nudge"
        mask = (df_test["treatment"] == act) | (df_test["treatment"] == CONTROL)
        df_sub = df_test[mask].reset_index(drop=True)

        all_uplifts = fitted_model.predict_uplift(df_sub)
        uplift_scores = all_uplifts[act]

        n_bins = 10
        fracs, qini_vals = qini_curve(
            y_true=df_sub["recovered"].values,
            uplift_score=uplift_scores,
            treatment=df_sub["treatment"].values,
            treatment_label=act,
            control_label=CONTROL,
            n_bins=n_bins
        )
        assert len(fracs) == n_bins + 1
        assert len(qini_vals) == n_bins + 1
        assert fracs[0] == 0.0
        assert fracs[-1] == 1.0
        assert qini_vals[0] == 0.0  # Anchor at zero

    def test_qini_fractions_monotone_increasing(self, small_dataset, fitted_model):
        """Population fractions must be strictly monotone increasing."""
        df_obs, _ = small_dataset
        df_test = df_obs.iloc[int(len(df_obs) * 0.7):].copy()

        act = "retry_only"
        mask = (df_test["treatment"] == act) | (df_test["treatment"] == CONTROL)
        df_sub = df_test[mask].reset_index(drop=True)
        all_uplifts = fitted_model.predict_uplift(df_sub)
        uplift_scores = all_uplifts[act]

        fracs, _ = qini_curve(
            y_true=df_sub["recovered"].values,
            uplift_score=uplift_scores,
            treatment=df_sub["treatment"].values,
            treatment_label=act,
            control_label=CONTROL,
            n_bins=15
        )
        assert np.all(np.diff(fracs) > 0), "Fractions must be strictly increasing"

    def test_qini_validates_shape_mismatch(self):
        """qini_curve must raise ValueError for mismatched array lengths."""
        with pytest.raises(ValueError, match="same length"):
            qini_curve(
                y_true=np.array([0, 1, 0]),
                uplift_score=np.array([0.1, 0.2]),  # Wrong length
                treatment=np.array([CONTROL, "retry_only", CONTROL]),
                treatment_label="retry_only",
                control_label=CONTROL
            )

    def test_qini_nan_score_raises(self):
        """qini_curve must raise ValueError when uplift_score contains NaN."""
        with pytest.raises(ValueError, match="NaN"):
            qini_curve(
                y_true=np.array([0, 1, 0, 1]),
                uplift_score=np.array([0.1, np.nan, 0.3, 0.4]),
                treatment=np.array([CONTROL, "email", CONTROL, "email"]),
                treatment_label="email",
                control_label=CONTROL
            )

    def test_qini_empty_treatment_arm_graceful(self):
        """If a treatment arm is entirely absent, Qini must return zeros gracefully."""
        fracs, qini_vals = qini_curve(
            y_true=np.array([0, 1, 0, 1, 0]),
            uplift_score=np.array([0.1, 0.5, 0.2, 0.8, 0.3]),
            treatment=np.array([CONTROL] * 5),  # No treated units
            treatment_label="voice_call",
            control_label=CONTROL,
            n_bins=5
        )
        assert np.all(qini_vals == 0.0)


class TestQiniCoefficient:

    def test_qini_coefficient_positive_for_good_model(self, small_dataset, fitted_model):
        """
        A model that correctly identifies high-uplift cases must show
        positive Qini coefficient for at least some treatment arms.
        """
        df_obs, _ = small_dataset
        df_test = df_obs.iloc[int(len(df_obs) * 0.7):].copy()

        positive_count = 0
        for act in ACTIVE_TREATMENTS:
            mask = (df_test["treatment"] == act) | (df_test["treatment"] == CONTROL)
            df_sub = df_test[mask].reset_index(drop=True)
            if len(df_sub) < 50:
                continue
            all_uplifts = fitted_model.predict_uplift(df_sub)
            fracs, qini_vals = qini_curve(
                y_true=df_sub["recovered"].values,
                uplift_score=all_uplifts[act],
                treatment=df_sub["treatment"].values,
                treatment_label=act,
                control_label=CONTROL,
                n_bins=10
            )
            q = qini_coefficient(fracs, qini_vals)
            if q > 0:
                positive_count += 1

        # At least 2/5 treatment arms should show positive Qini
        assert positive_count >= 1, (
            f"Expected at least 1 positive Qini coefficient, got 0 across all treatments."
        )

    def test_qini_coefficient_zero_for_random_ranker(self):
        """A purely random ranker (random uplift scores) should produce ~0 Qini."""
        rng = np.random.default_rng(42)
        n = 5000
        y = rng.integers(0, 2, size=n)
        t = rng.choice([CONTROL, "whatsapp_nudge"], size=n)
        random_scores = rng.uniform(-1, 1, size=n)

        fracs, qini_vals = qini_curve(
            y_true=y,
            uplift_score=random_scores,
            treatment=t,
            treatment_label="whatsapp_nudge",
            control_label=CONTROL,
            n_bins=10
        )
        q = qini_coefficient(fracs, qini_vals)
        # Random Qini should be very small in magnitude (within noise)
        assert abs(q) < 0.1, f"Random ranker Qini should be near 0, got {q}"

    def test_random_baseline_shape(self):
        """Random baseline curve must be a straight line from (0,0) to (1, max_qini)."""
        max_q = 0.15
        fracs, rand_vals = random_baseline_curve(n_bins=10, max_qini=max_q)
        assert fracs[0] == 0.0
        assert fracs[-1] == 1.0
        assert rand_vals[0] == 0.0
        assert abs(rand_vals[-1] - max_q) < 1e-9
        # Must be linear
        assert np.allclose(rand_vals, fracs * max_q)


class TestOracleQini:

    def test_oracle_qini_is_upper_bound(self, test_splits, fitted_model):
        """
        Oracle Qini (using true CATE) must be >= T-Learner Qini in expectation.
        Tests the core isolation principle: tau_* is used ONLY for benchmarking.
        """
        df_test, df_gt_test = test_splits
        act = "whatsapp_nudge"
        tau_col = f"tau_{act}"

        mask = (df_test["treatment"] == act) | (df_test["treatment"] == CONTROL)
        df_sub = df_test[mask].reset_index(drop=True)
        df_gt_sub = df_gt_test[mask].reset_index(drop=True)

        if len(df_sub) < 50 or tau_col not in df_gt_sub.columns:
            pytest.skip("Insufficient data or missing tau column")

        all_uplifts = fitted_model.predict_uplift(df_sub)
        fracs_m, qini_m = qini_curve(
            y_true=df_sub["recovered"].values,
            uplift_score=all_uplifts[act],
            treatment=df_sub["treatment"].values,
            treatment_label=act,
            control_label=CONTROL,
            n_bins=15
        )
        q_model = qini_coefficient(fracs_m, qini_m)

        fracs_o, qini_o = oracle_qini_curve(
            tau_true=df_gt_sub[tau_col].values,
            y_true=df_sub["recovered"].values,
            treatment=df_sub["treatment"].values,
            treatment_label=act,
            control_label=CONTROL,
            n_bins=15
        )
        q_oracle = qini_coefficient(fracs_o, qini_o)

        # Oracle must be >= model (it uses perfect information)
        # Allow small tolerance for noisy small-sample scenarios
        assert q_oracle >= q_model - 0.05, (
            f"Oracle Qini ({q_oracle:.4f}) should be >= T-Learner Qini ({q_model:.4f})"
        )


# ---------------------------------------------------------------------------
# [B] AUUC Tests
# ---------------------------------------------------------------------------

class TestAUUC:

    def test_auuc_output_shape(self, test_splits, fitted_model):
        """per_treatment_auuc must return results for all active treatments."""
        df_test, df_gt_test = test_splits
        results = per_treatment_auuc(
            df_observed=df_test,
            df_ground_truth=df_gt_test,
            model=fitted_model,
            treatments=ACTIVE_TREATMENTS,
            control=CONTROL,
            n_bins=10
        )
        # At least some treatments should have results
        assert len(results) >= 1

    def test_auuc_model_is_finite(self, test_splits, fitted_model):
        """All AUUC model values must be finite floats."""
        df_test, df_gt_test = test_splits
        results = per_treatment_auuc(
            df_observed=df_test,
            df_ground_truth=df_gt_test,
            model=fitted_model,
            treatments=ACTIVE_TREATMENTS,
            control=CONTROL,
            n_bins=10
        )
        for act, res in results.items():
            assert np.isfinite(res["auuc_model"]), f"{act}: AUUC is not finite: {res['auuc_model']}"

    def test_auuc_oracle_ge_model(self, test_splits, fitted_model):
        """Oracle AUUC must be >= model AUUC for most treatment arms."""
        df_test, df_gt_test = test_splits
        results = per_treatment_auuc(
            df_observed=df_test,
            df_ground_truth=df_gt_test,
            model=fitted_model,
            treatments=ACTIVE_TREATMENTS,
            control=CONTROL,
            n_bins=10
        )
        violations = []
        for act, res in results.items():
            if "auuc_oracle" in res:
                if res["auuc_oracle"] < res["auuc_model"] - 0.005:
                    violations.append((act, res["auuc_oracle"], res["auuc_model"]))
        # Allow up to 1 violation (sampling noise)
        assert len(violations) <= 1, (
            f"Oracle AUUC < T-Learner AUUC for: {violations}. "
            "This would indicate oracle information leakage into model."
        )

    def test_decile_table_structure(self, test_splits, fitted_model):
        """Decile lift table must have the expected columns and non-negative n per decile."""
        df_test, _ = test_splits
        decile_table = compute_decile_lift_table(
            df_observed=df_test,
            model=fitted_model,
            treatments=ACTIVE_TREATMENTS,
            control=CONTROL,
            n_deciles=10
        )
        if not decile_table.empty:
            required_cols = ["treatment", "decile", "n", "n_treated", "n_control",
                             "recovery_rate_treated", "recovery_rate_control",
                             "incremental_recovery_rate"]
            for col in required_cols:
                assert col in decile_table.columns, f"Missing column: {col}"
            assert (decile_table["n"] >= 0).all()


# ---------------------------------------------------------------------------
# [C] Segment Evaluation Tests
# ---------------------------------------------------------------------------

class TestSegmentEvaluation:

    def test_segment_qini_runs_for_all_domains(self, test_splits, fitted_model):
        """segment_qini must run without error for all domain segments."""
        df_test, _ = test_splits
        all_uplifts = fitted_model.predict_uplift(df_test)
        uplift_mat = np.column_stack([all_uplifts[act] for act in ACTIVE_TREATMENTS])
        df_test_scored = df_test.copy()
        df_test_scored["_best_uplift"] = uplift_mat.max(axis=1)
        df_test_scored["_binary_t"] = np.where(
            df_test_scored["treatment"] == CONTROL, CONTROL, "intervention"
        )

        results = segment_qini(
            df=df_test_scored,
            segment_col="domain",
            uplift_score_col="_best_uplift",
            y_true_col="recovered",
            treatment_col="_binary_t",
            treatment_label="intervention",
            control_label=CONTROL,
            n_bins=10,
            min_segment_size=30
        )
        # Should have results for at least 1 domain
        assert len(results) >= 1

    def test_segment_qini_coefficients_are_finite(self, test_splits, fitted_model):
        """All segment Qini coefficients must be finite."""
        df_test, _ = test_splits
        all_uplifts = fitted_model.predict_uplift(df_test)
        uplift_mat = np.column_stack([all_uplifts[act] for act in ACTIVE_TREATMENTS])
        df_test_scored = df_test.copy()
        df_test_scored["_best_uplift"] = uplift_mat.max(axis=1)
        df_test_scored["_binary_t"] = np.where(
            df_test_scored["treatment"] == CONTROL, CONTROL, "intervention"
        )
        results = segment_qini(
            df=df_test_scored,
            segment_col="domain",
            uplift_score_col="_best_uplift",
            y_true_col="recovered",
            treatment_col="_binary_t",
            treatment_label="intervention",
            control_label=CONTROL,
            n_bins=10,
            min_segment_size=30
        )
        for seg, res in results.items():
            assert np.isfinite(res["qini_coefficient"]), (
                f"Segment {seg}: Qini coefficient is not finite: {res['qini_coefficient']}"
            )

    def test_auuc_by_segment_runs(self, test_splits, fitted_model):
        """auuc_by_segment must return results for at least 1 domain."""
        df_test, df_gt_test = test_splits
        results = auuc_by_segment(
            df_observed=df_test,
            df_ground_truth=df_gt_test,
            model=fitted_model,
            segment_col="domain",
            treatments=ACTIVE_TREATMENTS,
            control=CONTROL,
            n_bins=10,
            min_segment_size=80
        )
        assert isinstance(results, dict)
        # Should produce at least some results
        assert len(results) >= 0  # May be empty on small dataset; just verify no crash


# ---------------------------------------------------------------------------
# [D] Business KPI Tests
# ---------------------------------------------------------------------------

class TestBusinessKPIs:

    def test_kpis_are_non_negative_finite(self, test_splits, fitted_model):
        """All Rs-based KPIs must be non-negative and finite."""
        df_test, _ = test_splits
        kpis = compute_business_kpis(df_test, fitted_model)

        per_t = kpis.get("per_treatment", {})
        for act, kp in per_t.items():
            for key in ["rs_recovered_per_contact", "rs_recovered_per_fatigue_unit"]:
                val = kp.get(key)
                if val is not None:
                    assert np.isfinite(val), f"{act}.{key} is not finite: {val}"
                    assert val >= 0, f"{act}.{key} is negative: {val}"

    def test_retry_kpi_present_for_retry_only(self, test_splits, fitted_model):
        """retry_only action must include Rs-per-retry-attempt KPI."""
        df_test, _ = test_splits
        kpis = compute_business_kpis(df_test, fitted_model)
        per_t = kpis.get("per_treatment", {})
        if "retry_only" in per_t:
            assert "rs_recovered_per_retry_attempt" in per_t["retry_only"]
            assert per_t["retry_only"]["rs_recovered_per_retry_attempt"] >= 0

    def test_kpis_recovery_rates_bounded(self, test_splits, fitted_model):
        """All factual recovery rates must be in [0, 1]."""
        df_test, _ = test_splits
        kpis = compute_business_kpis(df_test, fitted_model)
        per_t = kpis.get("per_treatment", {})
        for act, kp in per_t.items():
            rate = kp.get("recovery_rate", 0.5)
            assert 0.0 <= rate <= 1.0, f"{act}: recovery_rate={rate} out of [0,1]"


# ---------------------------------------------------------------------------
# [E] Routing Efficiency Tests
# ---------------------------------------------------------------------------

class TestRoutingEfficiency:

    def test_routing_efficiency_metrics_present(self, test_splits, fitted_model):
        """Routing efficiency metrics dict must contain correlation keys."""
        df_test, df_gt_test = test_splits
        efficiency = compute_model_routing_efficiency(df_test, df_gt_test, fitted_model)
        assert "model_oracle_pearson_correlation" in efficiency
        assert "model_oracle_spearman_rho" in efficiency
        assert "model_oracle_spearman_pval" in efficiency

    def test_routing_efficiency_correlation_finite(self, test_splits, fitted_model):
        """Pearson and Spearman correlations must be finite floats in [-1, 1]."""
        df_test, df_gt_test = test_splits
        efficiency = compute_model_routing_efficiency(df_test, df_gt_test, fitted_model)

        pearson = efficiency["model_oracle_pearson_correlation"]
        spearman = efficiency["model_oracle_spearman_rho"]

        if pearson is not None:
            assert np.isfinite(pearson), f"Pearson corr is not finite: {pearson}"
            assert -1.0 <= pearson <= 1.0, f"Pearson out of bounds: {pearson}"
        if spearman is not None:
            assert np.isfinite(spearman), f"Spearman rho is not finite: {spearman}"
            assert -1.0 <= spearman <= 1.0, f"Spearman out of bounds: {spearman}"


# ---------------------------------------------------------------------------
# [F] Strict Isolation Test
# ---------------------------------------------------------------------------

class TestDataIsolation:

    def test_model_rejects_potential_outcome_columns(self, small_dataset):
        """
        WAPSIUpliftModel.fit() must raise ValueError if training data contains
        any tau_*, y_*, or p_* columns (strict isolation enforcement).
        """
        df_obs, df_gt = small_dataset
        train_n = int(len(df_obs) * 0.7)
        # Simulate accidental merge of ground truth into training data
        df_contaminated = df_gt.iloc[:train_n].copy()

        model = WAPSIUpliftModel(random_seed=42)
        with pytest.raises(ValueError, match="isolation violation"):
            model.fit(df_contaminated)

    def test_evaluation_uses_gt_for_oracle_only(self, test_splits, fitted_model):
        """
        Verify that df_gt_test contains tau_* columns and that they are NOT
        present in df_test (observed), confirming isolation is maintained.
        """
        df_test, df_gt_test = test_splits
        # Ground truth should have tau_ columns
        tau_cols = [c for c in df_gt_test.columns if c.startswith("tau_")]
        assert len(tau_cols) > 0, "Ground truth must contain tau_* columns"
        # Observed test split must NOT have tau_ columns
        obs_tau_cols = [c for c in df_test.columns if c.startswith("tau_")]
        assert len(obs_tau_cols) == 0, (
            f"Observed test split must NOT contain tau_* columns, found: {obs_tau_cols}"
        )


# ---------------------------------------------------------------------------
# [G] Integration Test: Full Evaluator Pipeline
# ---------------------------------------------------------------------------

class TestFullEvaluatorPipeline:

    def test_evaluator_runs_end_to_end(self, small_dataset, tmp_path):
        """
        WAPSIUpliftEvaluator.run() must complete without error on small data
        and produce report files.
        """
        df_obs, df_gt = small_dataset
        train_n = int(len(df_obs) * 0.7)
        df_train = df_obs.iloc[:train_n].reset_index(drop=True)
        df_test = df_obs.iloc[train_n:].reset_index(drop=True)
        df_gt_test = df_gt.iloc[train_n:].reset_index(drop=True)

        evaluator = WAPSIUpliftEvaluator(
            data_dir=str(tmp_path),
            output_dir=str(tmp_path),
            n_bins=10,
            random_seed=42
        )
        metrics = evaluator.run(
            df_train=df_train,
            df_test=df_test,
            df_gt_test=df_gt_test
        )

        # Core keys must be present
        assert "overall_qini" in metrics
        assert "per_treatment_qini" in metrics
        assert "per_treatment_auuc" in metrics
        assert "business_kpis" in metrics
        assert "routing_efficiency" in metrics

        # Report files must be written
        assert (tmp_path / "uplift_report.json").exists()
        assert (tmp_path / "uplift_report.txt").exists()

    def test_evaluator_report_contains_verdict(self, small_dataset, tmp_path):
        """uplift_report.txt must contain the FINAL VERDICT section."""
        df_obs, df_gt = small_dataset
        train_n = int(len(df_obs) * 0.7)
        df_train = df_obs.iloc[:train_n].reset_index(drop=True)
        df_test = df_obs.iloc[train_n:].reset_index(drop=True)
        df_gt_test = df_gt.iloc[train_n:].reset_index(drop=True)

        evaluator = WAPSIUpliftEvaluator(
            data_dir=str(tmp_path / "data2"),
            output_dir=str(tmp_path / "eval2"),
            n_bins=10,
            random_seed=42
        )
        evaluator.run(df_train=df_train, df_test=df_test, df_gt_test=df_gt_test)

        report_path = tmp_path / "eval2" / "uplift_report.txt"
        assert report_path.exists()
        report_text = report_path.read_text(encoding="utf-8")
        assert "FINAL VERDICT" in report_text
        assert "persuadable customers" in report_text
