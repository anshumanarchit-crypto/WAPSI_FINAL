"""
WAPSI Qini Curve and Qini Coefficient Evaluation.
Razorpay AI Buildathon 2026 - Track 3

Implements Radcliffe (2007) / Gutierrez & Gerardy (2016) Qini formulation
for binary uplift model evaluation.

KEY PRINCIPLE:
  Hidden potential outcomes (tau_*, y_*) are used ONLY for oracle
  benchmarking -- never passed to the model training pipeline.
"""

from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd


def _validate_inputs(
    y_true: np.ndarray,
    treatment: np.ndarray,
    uplift_score: np.ndarray
) -> None:
    """Validates that arrays have matching shapes and expected dtypes."""
    n = len(y_true)
    if len(treatment) != n or len(uplift_score) != n:
        raise ValueError(
            f"All arrays must have the same length. Got y_true={n}, "
            f"treatment={len(treatment)}, uplift_score={len(uplift_score)}"
        )
    if np.any(np.isnan(uplift_score)):
        raise ValueError("uplift_score contains NaN values.")


def qini_curve(
    y_true: np.ndarray,
    uplift_score: np.ndarray,
    treatment: np.ndarray,
    treatment_label: str = "treatment",
    control_label: str = "no_action",
    n_bins: int = 20
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Computes the Qini curve for a binary uplift model.

    The Qini curve plots cumulative incremental gains vs. population fraction
    targeted, sorted by descending model uplift score.

    Formula per decile k:
      Qini(k) = (sum Y_treatment(k) / N_treatment(k))
              - (sum Y_control(k) / N_control(k)) * (n_t(k) / N_treatment_total)

    Args:
        y_true:           Binary outcome labels (0 or 1).
        uplift_score:     Model-estimated uplift scores (treatment - control).
        treatment:        Treatment assignment array (strings).
        treatment_label:  Value in `treatment` representing treated units.
        control_label:    Value in `treatment` representing control units.
        n_bins:           Number of decile bins.

    Returns:
        Tuple of (fractions, qini_values) both as 1D np.ndarray.
        fractions[0] = 0.0 (anchor), fractions[-1] = 1.0 (full population).
    """
    y = np.asarray(y_true, dtype=float)
    s = np.asarray(uplift_score, dtype=float)
    t = np.asarray(treatment)
    _validate_inputs(y, t, s)

    is_treated = (t == treatment_label)
    is_control = (t == control_label)

    # Sort descending by uplift score
    order = np.argsort(-s)
    y_sorted = y[order]
    t_sorted = is_treated[order]
    c_sorted = is_control[order]

    n = len(y)
    n_T_total = float(is_treated.sum())
    n_C_total = float(is_control.sum())

    fractions = np.linspace(0.0, 1.0, n_bins + 1)
    qini_vals = np.zeros(n_bins + 1)

    # Anchor at 0
    qini_vals[0] = 0.0

    if n_T_total == 0 or n_C_total == 0:
        return fractions, qini_vals

    for i, frac in enumerate(fractions[1:], start=1):
        k = max(1, int(np.floor(frac * n)))
        y_k = y_sorted[:k]
        t_k = t_sorted[:k]
        c_k = c_sorted[:k]

        n_t = float(t_k.sum())
        n_c = float(c_k.sum())

        sum_y_t = float(y_k[t_k].sum()) if n_t > 0 else 0.0
        sum_y_c = float(y_k[c_k].sum()) if n_c > 0 else 0.0

        # Radcliffe (2007) / Gutierrez & Gerardy (2016) Qini formulation:
        # Q(k) = (sum_Y_t(k) / N_T) - (sum_Y_c(k) / N_C)
        term_t = sum_y_t / n_T_total
        term_c = sum_y_c / n_C_total if n_C_total > 0 else 0.0

        qini_vals[i] = term_t - term_c

    return fractions, qini_vals


def qini_coefficient(fractions: np.ndarray, qini_vals: np.ndarray) -> float:
    """
    Computes the Qini coefficient: 2 * (AUC_model - AUC_random_diagonal).

    Q = 2 * integral(Qini_model(f) - Qini_random(f), df)

    A positive Qini coefficient means the model outperforms random targeting.

    Returns:
        float: Qini coefficient. Range approximately [-1, 1].
    """
    if len(fractions) < 2:
        return 0.0

    # Integrate using trapezoidal rule (auc_model and auc_random)
    trapz_fn = getattr(np, "trapezoid", getattr(np, "trapz", None))
    
    # Calculate random baseline values
    _, rand_vals = random_baseline_curve(len(fractions) - 1, qini_vals[-1])
    
    auc_model = float(trapz_fn(qini_vals, fractions))
    auc_random = float(trapz_fn(rand_vals, fractions))

    return round(2.0 * (auc_model - auc_random), 6)


def random_baseline_curve(
    n_bins: int,
    max_qini: float = 1.0
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Returns the random-targeting Qini baseline: a straight diagonal from
    (0, 0) to (1, max_qini).

    Args:
        n_bins:    Number of bins.
        max_qini:  Terminal value of the full Qini curve at fraction=1.0.

    Returns:
        Tuple of (fractions, random_values).
    """
    fractions = np.linspace(0.0, 1.0, n_bins + 1)
    random_vals = fractions * max_qini
    return fractions, random_vals


def oracle_qini_curve(
    tau_true: np.ndarray,
    y_true: np.ndarray,
    treatment: np.ndarray,
    treatment_label: str = "treatment",
    control_label: str = "no_action",
    n_bins: int = 20
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Computes the Oracle Qini curve using the true hidden CATE (tau_true)
    as the ranking score. Represents the theoretical upper bound on Qini.

    IMPORTANT: tau_true comes from df_ground_truth.tau_<treatment> columns.
    It is ONLY used here for benchmarking. It is NEVER passed to fit().

    Args:
        tau_true:        True CATE values (oracle ranking signal).
        y_true:          Factual binary outcomes.
        treatment:       Treatment assignment array.
        treatment_label: String label for treated units.
        control_label:   String label for control units.
        n_bins:          Number of bins.

    Returns:
        Tuple of (fractions, oracle_qini_vals).
    """
    return qini_curve(
        y_true=y_true,
        uplift_score=np.asarray(tau_true, dtype=float),
        treatment=treatment,
        treatment_label=treatment_label,
        control_label=control_label,
        n_bins=n_bins
    )


def segment_qini(
    df: pd.DataFrame,
    segment_col: str,
    uplift_score_col: str,
    y_true_col: str = "recovered",
    treatment_col: str = "treatment",
    treatment_label: str = "treatment",
    control_label: str = "no_action",
    n_bins: int = 20,
    min_segment_size: int = 50
) -> Dict[str, Dict[str, Any]]:
    """
    Computes Qini coefficient for each unique segment value in `segment_col`.

    Useful for understanding per-domain or per-decline-reason model quality.

    Args:
        df:               DataFrame containing all required columns.
        segment_col:      Column to segment by (e.g., "domain").
        uplift_score_col: Column containing model-estimated uplift scores.
        y_true_col:       Binary outcome column.
        treatment_col:    Treatment assignment column.
        treatment_label:  String value identifying treated units.
        control_label:    String value identifying control units.
        n_bins:           Number of bins for Qini curve.
        min_segment_size: Skip segments smaller than this (avoids noise).

    Returns:
        Dict mapping segment_value -> metrics dict.
    """
    results = {}
    for segment_val, grp in df.groupby(segment_col):
        if len(grp) < min_segment_size:
            continue
        n_treated = (grp[treatment_col] == treatment_label).sum()
        n_control = (grp[treatment_col] == control_label).sum()
        if n_treated < 5 or n_control < 5:
            continue

        y = grp[y_true_col].values
        s = grp[uplift_score_col].values
        t = grp[treatment_col].values

        fracs, qini_vals = qini_curve(
            y_true=y,
            uplift_score=s,
            treatment=t,
            treatment_label=treatment_label,
            control_label=control_label,
            n_bins=n_bins
        )
        q_coeff = qini_coefficient(fracs, qini_vals)

        results[str(segment_val)] = {
            "segment": str(segment_val),
            "n": int(len(grp)),
            "n_treated": int(n_treated),
            "n_control": int(n_control),
            "qini_coefficient": round(q_coeff, 6),
            "fractions": fracs.tolist(),
            "qini_values": np.round(qini_vals, 6).tolist()
        }
    return results


def multi_treatment_qini(
    df: pd.DataFrame,
    model,
    treatments: List[str],
    control: str = "no_action",
    y_true_col: str = "recovered",
    treatment_col: str = "treatment",
    n_bins: int = 20
) -> Dict[str, Dict[str, Any]]:
    """
    Runs Qini evaluation separately for each treatment arm vs. no_action.

    For each treatment, restricts the evaluation to rows where
    treatment == act OR treatment == no_action, computes model uplift
    for that action, and evaluates the Qini curve.

    Args:
        df:             Observed test DataFrame (NO potential outcome columns).
        model:          Fitted WAPSIUpliftModel instance.
        treatments:     List of active treatment names (excluding control).
        control:        Control action name.
        y_true_col:     Binary outcome column.
        treatment_col:  Treatment assignment column.
        n_bins:         Number of Qini curve bins.

    Returns:
        Dict mapping treatment name -> {qini_coefficient, fractions, qini_values, n, ...}
    """
    results = {}
    all_uplifts = model.predict_uplift(df)  # Dict[str, np.ndarray]

    for act in treatments:
        if act not in all_uplifts:
            continue

        # Restrict to binary comparison: treated with `act` OR control
        mask = ((df[treatment_col] == act) | (df[treatment_col] == control)).values
        df_sub = df[mask].copy()

        if len(df_sub) < 50:
            continue

        uplift_arr = all_uplifts[act]
        uplift_sub = uplift_arr[mask]

        y = df_sub[y_true_col].values
        t = df_sub[treatment_col].values

        fracs, qini_vals = qini_curve(
            y_true=y,
            uplift_score=uplift_sub,
            treatment=t,
            treatment_label=act,
            control_label=control,
            n_bins=n_bins
        )
        q_coeff = qini_coefficient(fracs, qini_vals)

        results[act] = {
            "treatment": act,
            "qini_coefficient": round(q_coeff, 6),
            "n": int(len(df_sub)),
            "n_treated": int((df_sub[treatment_col] == act).sum()),
            "n_control": int((df_sub[treatment_col] == control).sum()),
            "fractions": fracs.tolist(),
            "qini_values": np.round(qini_vals, 6).tolist()
        }

    return results
