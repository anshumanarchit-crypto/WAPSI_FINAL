"""
WAPSI Uplift Curve and AUUC (Area Under Uplift Curve) Evaluation.
Razorpay AI Buildathon 2026 - Track 3

Implements Devriendt et al. (2018) uplift curve and AUUC computation
for ranking uplift model quality evaluation.

KEY PRINCIPLE:
  Hidden ground-truth potential outcomes (tau_*, p_*) are used ONLY
  for oracle benchmarking and are never passed to model training.
"""

from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd


def uplift_curve(
    y_true: np.ndarray,
    uplift_score: np.ndarray,
    treatment: np.ndarray,
    treatment_label: str = "treatment",
    control_label: str = "no_action",
    n_bins: int = 20
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Computes the uplift curve (Devriendt 2018 formulation).

    At each population fraction k, the uplift curve measures:
      UC(k) = (sum Y_t(k) / n_t(k)) - (sum Y_c(k) / n_c(k))

    where subsets are sorted by descending model uplift score.

    This differs from Qini in that it plots *rate difference* (not
    normalized incremental gains), making it more interpretable as
    incremental recovery rate vs. control rate at each targeting depth.

    Args:
        y_true:           Binary outcome labels (0 or 1).
        uplift_score:     Model-estimated uplift scores.
        treatment:        Treatment assignment array.
        treatment_label:  String value for treated group.
        control_label:    String value for control group.
        n_bins:           Number of evaluation bins.

    Returns:
        Tuple of (fractions, uplift_values).
        fractions[0] = 0.0 (anchor), fractions[-1] = 1.0.
    """
    y = np.asarray(y_true, dtype=float)
    s = np.asarray(uplift_score, dtype=float)
    t = np.asarray(treatment)

    n = len(y)
    is_treated = (t == treatment_label)
    is_control = (t == control_label)

    n_T_total = float(is_treated.sum())
    n_C_total = float(is_control.sum())

    # Sort by descending uplift score
    order = np.argsort(-s)
    y_sorted = y[order]
    t_sorted = is_treated[order]
    c_sorted = is_control[order]

    fractions = np.linspace(0.0, 1.0, n_bins + 1)
    uc_vals = np.zeros(n_bins + 1)

    if n_T_total < 5 or n_C_total < 5:
        return fractions, uc_vals

    for i, frac in enumerate(fractions[1:], start=1):
        k = max(1, int(np.floor(frac * n)))
        y_k = y_sorted[:k]
        t_k = t_sorted[:k]
        c_k = c_sorted[:k]

        n_t = float(t_k.sum())
        n_c = float(c_k.sum())

        if n_t == 0 and n_c == 0:
            uc_vals[i] = 0.0
            continue

        rate_t = float(y_k[t_k].sum()) / n_t if n_t > 0 else 0.0
        rate_c = float(y_k[c_k].sum()) / n_c if n_c > 0 else 0.0
        uc_vals[i] = rate_t - rate_c

    return fractions, uc_vals


def random_uplift_curve(
    y_true: np.ndarray,
    treatment: np.ndarray,
    treatment_label: str = "treatment",
    control_label: str = "no_action",
    n_bins: int = 20
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Computes the expected uplift curve for random targeting.

    For a random ranker, the uplift curve is a horizontal line at the
    overall ATE (rate_T_total - rate_C_total) from fraction=0 to fraction=1.

    Returns:
        Tuple of (fractions, random_uplift_values).
    """
    y = np.asarray(y_true, dtype=float)
    t = np.asarray(treatment)

    is_treated = (t == treatment_label)
    is_control = (t == control_label)

    n_T = float(is_treated.sum())
    n_C = float(is_control.sum())

    rate_T = float(y[is_treated].sum()) / n_T if n_T > 0 else 0.0
    rate_C = float(y[is_control].sum()) / n_C if n_C > 0 else 0.0
    ate = rate_T - rate_C

    fractions = np.linspace(0.0, 1.0, n_bins + 1)
    random_vals = np.full(n_bins + 1, ate)
    random_vals[0] = 0.0  # anchor at origin

    return fractions, random_vals


def auuc(
    fractions: np.ndarray,
    uc_vals: np.ndarray,
    random_uc_vals: Optional[np.ndarray] = None
) -> float:
    """
    Computes Area Under Uplift Curve (AUUC) vs. the random baseline.

    AUUC = integral(UC_model(f) - UC_random(f), df)

    A positive AUUC indicates the model concentrates recoveries in
    top-ranked cases better than random assignment.

    Args:
        fractions:      Population fraction x-axis values.
        uc_vals:        Model uplift curve values.
        random_uc_vals: Optional random baseline uplift curve.
                        If None, assumes flat line at uc_vals[-1].

    Returns:
        float: AUUC value. Positive = better than random.
    """
    if len(fractions) < 2:
        return 0.0

    trapz_fn = getattr(np, "trapezoid", getattr(np, "trapz", None))
    auc_model = float(trapz_fn(uc_vals, fractions))

    if random_uc_vals is not None:
        auc_random = float(trapz_fn(random_uc_vals, fractions))
    else:
        # Flat random baseline at the population ATE
        auc_random = float(uc_vals[-1])  # area under horizontal line from 0 to 1

    return round(auc_model - auc_random, 6)


def per_treatment_auuc(
    df_observed: pd.DataFrame,
    df_ground_truth: pd.DataFrame,
    model,
    treatments: List[str],
    control: str = "no_action",
    y_true_col: str = "recovered",
    treatment_col: str = "treatment",
    n_bins: int = 20
) -> Dict[str, Dict[str, Any]]:
    """
    Computes AUUC separately for each treatment arm vs. no_action,
    and compares to the oracle (true-CATE-ranked) uplift curve.

    IMPORTANT: df_ground_truth is used ONLY to extract true tau values
    for oracle ranking. It is never merged into df_observed for model fitting.

    Args:
        df_observed:     Test split with no potential outcome columns.
        df_ground_truth: Evaluation-only ground truth (contains tau_* columns).
        model:           Fitted WAPSIUpliftModel.
        treatments:      Active treatment names.
        control:         Control action name.
        y_true_col:      Outcome column.
        treatment_col:   Treatment assignment column.
        n_bins:          Number of evaluation bins.

    Returns:
        Dict mapping treatment -> {auuc_model, auuc_oracle, fractions, uc_vals, oracle_uc_vals, ...}
    """
    all_uplifts = model.predict_uplift(df_observed)
    results = {}

    for act in treatments:
        if act not in all_uplifts:
            continue

        mask = ((df_observed[treatment_col] == act) |
                (df_observed[treatment_col] == control)).values
        df_sub_obs = df_observed[mask].copy()
        df_sub_gt = df_ground_truth[mask].copy()

        if len(df_sub_obs) < 50:
            continue

        uplift_arr = all_uplifts[act]
        uplift_sub = uplift_arr[mask]
        y = df_sub_obs[y_true_col].values
        t = df_sub_obs[treatment_col].values

        # Model uplift curve
        fracs, uc_model = uplift_curve(
            y_true=y,
            uplift_score=uplift_sub,
            treatment=t,
            treatment_label=act,
            control_label=control,
            n_bins=n_bins
        )

        # Random baseline
        _, uc_rand = random_uplift_curve(
            y_true=y,
            treatment=t,
            treatment_label=act,
            control_label=control,
            n_bins=n_bins
        )

        auuc_model = auuc(fracs, uc_model, uc_rand)

        # Oracle curve using true CATE
        tau_col = f"tau_{act}"
        oracle_result = {}
        if tau_col in df_sub_gt.columns:
            tau_true_sub = df_sub_gt[tau_col].values
            _, uc_oracle = uplift_curve(
                y_true=y,
                uplift_score=tau_true_sub,
                treatment=t,
                treatment_label=act,
                control_label=control,
                n_bins=n_bins
            )
            auuc_oracle = auuc(fracs, uc_oracle, uc_rand)
            oracle_result = {
                "auuc_oracle": round(auuc_oracle, 6),
                "oracle_uc_values": np.round(uc_oracle, 6).tolist(),
                "model_vs_oracle_gap": round(auuc_oracle - auuc_model, 6)
            }

        results[act] = {
            "treatment": act,
            "n": int(len(df_sub_obs)),
            "n_treated": int((df_sub_obs[treatment_col] == act).sum()),
            "n_control": int((df_sub_obs[treatment_col] == control).sum()),
            "auuc_model": round(auuc_model, 6),
            "fractions": fracs.tolist(),
            "model_uc_values": np.round(uc_model, 6).tolist(),
            "random_uc_values": np.round(uc_rand, 6).tolist(),
            **oracle_result
        }

    return results


def auuc_by_segment(
    df_observed: pd.DataFrame,
    df_ground_truth: pd.DataFrame,
    model,
    segment_col: str,
    treatments: List[str],
    control: str = "no_action",
    y_true_col: str = "recovered",
    treatment_col: str = "treatment",
    n_bins: int = 20,
    min_segment_size: int = 100
) -> Dict[str, Dict[str, Any]]:
    """
    Computes per-segment AUUC for each treatment arm within each segment.

    Provides granular insight: does the model rank persuadable customers
    better within specific domains like b2b_saas, subscription, etc.?

    Args:
        df_observed:     Test split with no potential outcome columns.
        df_ground_truth: Evaluation-only ground truth.
        model:           Fitted WAPSIUpliftModel.
        segment_col:     Column to segment by (e.g., "domain").
        treatments:      Active treatment names.
        control:         Control action name.
        y_true_col:      Outcome column.
        treatment_col:   Treatment assignment column.
        n_bins:          Number of bins.
        min_segment_size: Minimum rows per segment.

    Returns:
        Dict mapping segment_val -> {treatment -> auuc_metrics}
    """
    all_uplifts = model.predict_uplift(df_observed)
    results = {}

    segment_vals = df_observed[segment_col].unique()
    for seg_val in sorted(segment_vals):
        seg_mask = (df_observed[segment_col] == seg_val).values
        df_seg_obs = df_observed[seg_mask].copy()
        df_seg_gt = df_ground_truth[seg_mask].copy()

        if len(df_seg_obs) < min_segment_size:
            continue

        seg_results = {}
        for act in treatments:
            if act not in all_uplifts:
                continue

            act_mask = ((df_seg_obs[treatment_col] == act) |
                        (df_seg_obs[treatment_col] == control)).values
            df_act_obs = df_seg_obs[act_mask].copy()
            df_act_gt = df_seg_gt[act_mask].copy()

            if len(df_act_obs) < 30:
                continue
            if (df_act_obs[treatment_col] == act).sum() < 5:
                continue
            if (df_act_obs[treatment_col] == control).sum() < 5:
                continue

            uplift_arr = all_uplifts[act][seg_mask][act_mask]
            y = df_act_obs[y_true_col].values
            t = df_act_obs[treatment_col].values

            fracs, uc_model = uplift_curve(
                y_true=y,
                uplift_score=uplift_arr,
                treatment=t,
                treatment_label=act,
                control_label=control,
                n_bins=n_bins
            )
            _, uc_rand = random_uplift_curve(
                y_true=y,
                treatment=t,
                treatment_label=act,
                control_label=control,
                n_bins=n_bins
            )
            auuc_m = auuc(fracs, uc_model, uc_rand)

            seg_results[act] = {
                "n": int(len(df_act_obs)),
                "auuc_model": round(auuc_m, 6)
            }

        if seg_results:
            results[str(seg_val)] = seg_results

    return results


def compute_decile_lift_table(
    df_observed: pd.DataFrame,
    model,
    treatments: List[str],
    control: str = "no_action",
    y_true_col: str = "recovered",
    treatment_col: str = "treatment",
    n_deciles: int = 10
) -> pd.DataFrame:
    """
    Builds a decile-level lift table showing recovery rate by model score decile
    for treated vs. control subgroups.

    This is a business-interpretable summary: "The top 10% of cases ranked by
    the model have X% higher recovery rate than the control group."

    Args:
        df_observed:   Test split (no potential outcomes).
        model:         Fitted WAPSIUpliftModel.
        treatments:    Active treatment names.
        control:       Control action name.
        y_true_col:    Binary outcome column.
        treatment_col: Treatment assignment column.
        n_deciles:     Number of deciles (default 10).

    Returns:
        pd.DataFrame with columns: treatment, decile, n, recovery_rate_treated,
        recovery_rate_control, incremental_uplift_rate.
    """
    all_uplifts = model.predict_uplift(df_observed)
    rows = []

    for act in treatments:
        if act not in all_uplifts:
            continue

        mask = ((df_observed[treatment_col] == act) |
                (df_observed[treatment_col] == control)).values
        df_sub = df_observed[mask].copy()
        uplift_arr = all_uplifts[act][mask]

        if len(df_sub) < n_deciles * 10:
            continue

        df_sub = df_sub.reset_index(drop=True)
        df_sub["_uplift_score"] = uplift_arr
        df_sub["_decile"] = pd.qcut(
            df_sub["_uplift_score"], q=n_deciles,
            labels=list(range(n_deciles, 0, -1)),
            duplicates="drop"
        )

        for decile_val, grp in df_sub.groupby("_decile", observed=False):
            treated_grp = grp[grp[treatment_col] == act]
            control_grp = grp[grp[treatment_col] == control]

            rate_t = float(treated_grp[y_true_col].mean()) if len(treated_grp) > 0 else np.nan
            rate_c = float(control_grp[y_true_col].mean()) if len(control_grp) > 0 else np.nan
            incr = (rate_t - rate_c) if (not np.isnan(rate_t) and not np.isnan(rate_c)) else np.nan

            rows.append({
                "treatment": act,
                "decile": int(decile_val),
                "n": int(len(grp)),
                "n_treated": int(len(treated_grp)),
                "n_control": int(len(control_grp)),
                "recovery_rate_treated": round(rate_t, 4) if not np.isnan(rate_t) else None,
                "recovery_rate_control": round(rate_c, 4) if not np.isnan(rate_c) else None,
                "incremental_recovery_rate": round(incr, 4) if not np.isnan(incr) else None
            })

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["treatment", "decile"])
