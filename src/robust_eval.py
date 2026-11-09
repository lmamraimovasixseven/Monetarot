"""Exploratory robustness evaluation, added after the main analysis (2026-11-06).

What this module adds, and what it does not change
--------------------------------------------------
The pre-specified ordered logit in ``src/model.py`` and its verdict (does not beat
Always Hold on the 18-decision holdout) are left untouched. This module asks how
much that verdict can be trusted and whether simple, theory-motivated changes
make the forecasts more robust. Everything here was written after the holdout
had been seen, so every holdout number it reports is labelled non-confirmatory.
Choices that need tuning (the ridge penalty) are made with time-series
cross-validation on data that precede each forecast; the holdout is never used
to choose anything.

Contents
* ``ordinal_rps`` / ``brier`` - proper scoring rules for ordinal probability
  forecasts. Unlike the log score, both are finite for Always Hold, so the
  benchmark can be scored on probabilities and not only on the expected score.
* ``dm_test`` - Diebold-Mariano test with the Harvey-Leybourne-Newbold
  small-sample correction (t distribution with n-1 df).
* ``block_bootstrap_ratio`` - moving-block bootstrap interval for the RMSE ratio.
* ``fit_ordered_logit`` - ordered logit with an optional ridge penalty on the
  standardized slopes (analytic gradient, L-BFGS-B). With a negligible penalty
  it reproduces the statsmodels estimates used by the main model.
* rolling-origin evaluation inside the estimation sample (one-step-ahead,
  refit at every decision), a fixed-origin holdout evaluation that mirrors the
  main protocol, and a recursive holdout evaluation that refits at every
  holdout decision as a real user would.
* ``anomaly_screen`` - modified z-scores (Iglewicz and Hoaglin, 1993) of monthly
  changes in every raw series, so that suspicious source values are flagged
  instead of silently driving the latest score.

Writes ``model/robust_eval.json``, ``outputs/robust_evaluation.md`` and
``outputs/robust_eval_predictions.csv``. Run with ``python run.py robust``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit
from scipy.stats import t as student_t

from src.ingest import (
    FEATURE_RULES,
    RAW_DIR,
    apply_release_lag,
    complete_month_calendar,
    read_monthly_series,
)


ROOT = Path(__file__).resolve().parents[1]
DECISIONS_PATH = ROOT / "data" / "processed" / "nbk_decisions_clean.csv"
MODEL_PANEL_PATH = ROOT / "data" / "processed" / "model_panel.csv"
OUTPUTS = ROOT / "outputs"
ROBUST_ARTIFACT_PATH = ROOT / "model" / "robust_eval.json"
MAIN_ARTIFACT_PATH = ROOT / "model" / "artifact.json"

SEED = 42
MAIN_FEATURES = list(FEATURE_RULES)
RULE_FEATURES = ["inflation", "inflation_change_3m", "real_rate", "previous_decision"]
RULE_PLUS_FEATURES = RULE_FEATURES + [f for f in MAIN_FEATURES if f != "inflation"]
FEATURE_LABELS = {
    "inflation": "Inflation",
    "exports": "Exports",
    "imports": "Imports",
    "corporate_lending": "Corporate lending",
    "household_lending": "Household lending",
    "consumption": "Consumption",
    "inflation_change_3m": "Inflation change over 3 months",
    "real_rate": "Ex-post real rate (base rate before decision − inflation)",
    "previous_decision": "Previous decision (−1/0/+1)",
}
CLASS_ORDER = ["Decrease", "Hold", "Increase"]
SCORES = np.array([-1.0, 0.0, 1.0])
SAFEGUARD_PENALTY = 1e-4      # keeps "unpenalized" fits finite under separation; negligible otherwise
LAMBDA_GRID = [SAFEGUARD_PENALTY, 0.3, 1.0, 3.0, 10.0, 30.0]
INNER_WINDOW = 12             # one-step forecasts used to pick the ridge penalty at each origin
FIRST_ORIGIN = 40             # first rolling-origin forecast uses the first 40 usable decisions
BLOCK_LENGTH = 3
BOOTSTRAP_DRAWS = 10_000
MODIFIED_Z_THRESHOLD = 3.5    # Iglewicz and Hoaglin (1993) outlier rule for the modified z-score
RATE_SERIES = {"inflation", "consumption"}  # already rates: screen first differences, not log changes
LABEL_NOTE = ("Exploratory: added on 2026-11-06 after the holdout had been seen. The pre-specified "
              "main model and its verdict are unchanged; holdout numbers here are non-confirmatory.")


class RobustEvalError(RuntimeError):
    """Raised when inputs needed for the exploratory evaluation are missing or invalid."""


# ---------------------------------------------------------------------------
# Scoring rules and forecast-comparison tests
# ---------------------------------------------------------------------------

def _as_index(actual: np.ndarray) -> np.ndarray:
    values = np.asarray(actual, dtype=int)
    if not np.isin(values, [-1, 0, 1]).all():
        raise RobustEvalError("Actual scores must be -1, 0 or +1")
    return values + 1


def ordinal_rps(probabilities: np.ndarray, actual: np.ndarray) -> np.ndarray:
    """Ranked probability score per observation (0 = perfect, 1 = worst for three classes).

    RPS = 1/(K-1) * sum_k (P(Y<=k) - 1[y<=k])^2 over the K-1 = 2 cumulative splits.
    It respects the class order, so predicting Hold for a cut is penalized less
    than predicting a hike.
    """
    probs = np.atleast_2d(np.asarray(probabilities, dtype=float))
    index = _as_index(actual)
    observed = np.zeros_like(probs)
    observed[np.arange(len(index)), index] = 1.0
    cumulative_gap = np.cumsum(probs, axis=1)[:, :2] - np.cumsum(observed, axis=1)[:, :2]
    return (cumulative_gap ** 2).sum(axis=1) / 2.0


def brier(probabilities: np.ndarray, actual: np.ndarray) -> np.ndarray:
    """Multiclass Brier score per observation (sum of squared probability errors, 0 to 2)."""
    probs = np.atleast_2d(np.asarray(probabilities, dtype=float))
    index = _as_index(actual)
    observed = np.zeros_like(probs)
    observed[np.arange(len(index)), index] = 1.0
    return ((probs - observed) ** 2).sum(axis=1)


def log_loss(probabilities: np.ndarray, actual: np.ndarray) -> np.ndarray:
    """Negative log probability of the observed class; +inf when that probability is zero."""
    probs = np.atleast_2d(np.asarray(probabilities, dtype=float))
    true_p = probs[np.arange(len(actual)), _as_index(actual)]
    with np.errstate(divide="ignore"):
        return -np.log(true_p)


def expected_score(probabilities: np.ndarray) -> np.ndarray:
    return np.atleast_2d(probabilities) @ SCORES


def dm_test(loss_model: np.ndarray, loss_benchmark: np.ndarray, horizon: int = 1) -> dict[str, Any]:
    """Diebold-Mariano test of equal expected loss, with the HLN small-sample correction.

    d_t = loss_model - loss_benchmark; negative mean d favours the model. The
    long-run variance uses the rectangular kernel with horizon-1 autocovariances
    (zero for one-step forecasts). The corrected statistic is compared with a t
    distribution with n-1 degrees of freedom (Harvey, Leybourne and Newbold, 1997).
    """
    d = np.asarray(loss_model, dtype=float) - np.asarray(loss_benchmark, dtype=float)
    n = len(d)
    if n < 3 or not np.isfinite(d).all():
        return {"n": n, "mean_loss_difference": None, "statistic": None, "p_value": None,
                "note": "not computed (fewer than 3 finite loss differences)"}
    mean = float(d.mean())
    centred = d - mean
    variance = float(centred @ centred / n)
    for lag in range(1, horizon):
        variance += 2 * float(centred[lag:] @ centred[:-lag] / n)
    if variance <= 0:
        return {"n": n, "mean_loss_difference": mean, "statistic": None, "p_value": None,
                "note": "not computed (zero variance of loss differences)"}
    dm = mean / math.sqrt(variance / n)
    correction = math.sqrt((n + 1 - 2 * horizon + horizon * (horizon - 1) / n) / n)
    statistic = dm * correction
    p_value = float(2 * student_t.sf(abs(statistic), df=n - 1))
    return {"n": n, "mean_loss_difference": mean, "statistic": float(statistic), "p_value": p_value,
            "note": "HLN-corrected DM; negative mean difference favours the model"}


def block_bootstrap_ratio(error_model: np.ndarray, error_benchmark: np.ndarray, *,
                          block_length: int = BLOCK_LENGTH, draws: int = BOOTSTRAP_DRAWS,
                          seed: int = SEED) -> dict[str, Any]:
    """Moving-block bootstrap of RMSE(model)/RMSE(benchmark) on paired forecast errors."""
    e_model = np.asarray(error_model, dtype=float)
    e_bench = np.asarray(error_benchmark, dtype=float)
    n = len(e_model)
    if n < block_length + 1:
        return {"ratio": None, "ci_low": None, "ci_high": None, "share_below_one": None}
    rng = np.random.default_rng(seed)
    blocks = math.ceil(n / block_length)
    starts = rng.integers(0, n - block_length + 1, size=(draws, blocks))
    index = (starts[:, :, None] + np.arange(block_length)[None, None, :]).reshape(draws, -1)[:, :n]
    model_ms = (e_model[index] ** 2).mean(axis=1)
    bench_ms = (e_bench[index] ** 2).mean(axis=1)
    valid = bench_ms > 0
    ratios = np.sqrt(model_ms[valid] / bench_ms[valid])
    point = math.sqrt((e_model ** 2).mean() / (e_bench ** 2).mean())
    return {
        "ratio": float(point),
        "ci_low": float(np.quantile(ratios, 0.025)),
        "ci_high": float(np.quantile(ratios, 0.975)),
        "share_below_one": float((ratios < 1).mean()),
        "block_length": block_length, "draws": int(valid.sum()), "seed": seed,
    }


# ---------------------------------------------------------------------------
# Penalized ordered logit
# ---------------------------------------------------------------------------

def _unpack(theta: np.ndarray, k: int) -> tuple[np.ndarray, float, float, float]:
    beta = theta[:k]
    c1 = theta[k]
    gap = math.exp(min(theta[k + 1], 30.0))
    return beta, c1, c1 + gap, gap


def _objective(theta: np.ndarray, x: np.ndarray, index: np.ndarray, penalty: float):
    k = x.shape[1]
    beta, c1, c2, gap = _unpack(theta, k)
    eta = x @ beta
    f1, f2 = expit(c1 - eta), expit(c2 - eta)
    d1, d2 = f1 * (1 - f1), f2 * (1 - f2)
    tiny = 1e-300
    p_low, p_mid, p_high = np.maximum(f1, tiny), np.maximum(f2 - f1, tiny), np.maximum(1 - f2, tiny)
    ll = np.where(index == 0, np.log(p_low), np.where(index == 1, np.log(p_mid), np.log(p_high)))
    # derivatives of each observation's log-likelihood
    g_c1 = np.where(index == 0, d1 / p_low, np.where(index == 1, -d1 / p_mid, 0.0))
    g_c2 = np.where(index == 0, 0.0, np.where(index == 1, d2 / p_mid, -d2 / p_high))
    g_eta = -(g_c1 + g_c2)
    value = -ll.sum() + 0.5 * penalty * float(beta @ beta) + 0.5 * SAFEGUARD_PENALTY * (c1 ** 2 + theta[k + 1] ** 2)
    grad = np.empty_like(theta)
    grad[:k] = -(x.T @ g_eta) + penalty * beta
    grad[k] = -(g_c1.sum() + g_c2.sum()) + SAFEGUARD_PENALTY * c1
    grad[k + 1] = -(g_c2.sum() * gap) + SAFEGUARD_PENALTY * theta[k + 1]
    return value, grad


def fit_ordered_logit(frame: pd.DataFrame, features: list[str], penalty: float = SAFEGUARD_PENALTY) -> dict[str, Any]:
    """Fit an ordered logit on standardized features with an L2 penalty on the slopes."""
    x_raw = frame[features].to_numpy(dtype=float)
    if not np.isfinite(x_raw).all():
        raise RobustEvalError("Features contain missing values")
    mean = x_raw.mean(axis=0)
    scale = x_raw.std(axis=0)
    scale[scale == 0] = 1.0
    x = (x_raw - mean) / scale
    index = _as_index(frame["y"].to_numpy())
    counts = np.bincount(index, minlength=3) + 0.5
    cumulative = np.cumsum(counts / counts.sum())
    c1 = math.log(cumulative[0] / (1 - cumulative[0]))
    c2 = math.log(cumulative[1] / (1 - cumulative[1]))
    start = np.r_[np.zeros(len(features)), c1, math.log(max(c2 - c1, 1e-3))]
    result = minimize(_objective, start, args=(x, index, penalty), jac=True, method="L-BFGS-B",
                      options={"maxiter": 5000, "gtol": 1e-9, "ftol": 1e-14})
    beta_std, cut1, cut2, _ = _unpack(result.x, len(features))
    # Report slopes in original units: eta = sum beta_std * (x - mean)/scale
    beta = beta_std / scale
    offset = float(beta @ mean)
    return {
        "features": list(features), "penalty": float(penalty), "converged": bool(result.success),
        "beta_standardized": beta_std, "beta": beta,
        "cutpoints": np.array([cut1 + offset, cut2 + offset]),
        "mean": mean, "scale": scale, "n": int(len(frame)),
        "neg_log_likelihood": float(result.fun),
    }


def predict_ordered_logit(fit: dict[str, Any], frame: pd.DataFrame) -> np.ndarray:
    x = frame[fit["features"]].to_numpy(dtype=float)
    eta = x @ fit["beta"]
    f1 = expit(fit["cutpoints"][0] - eta)
    f2 = expit(fit["cutpoints"][1] - eta)
    probs = np.column_stack([f1, f2 - f1, 1 - f2])
    return np.clip(probs, 0.0, 1.0)


def choose_penalty(history: pd.DataFrame, features: list[str], grid: list[float] = LAMBDA_GRID,
                   inner: int = INNER_WINDOW) -> tuple[float, dict[str, float]]:
    """Pick the ridge penalty by one-step-ahead RPS over the last ``inner`` decisions of ``history``.

    Only rows of ``history`` are used, so the choice never sees the forecast target.
    Ties go to the larger penalty (the more conservative model).
    """
    n = len(history)
    first = max(n - inner, 20)
    scores: dict[str, float] = {}
    for penalty in grid:
        losses = []
        for i in range(first, n):
            fit = fit_ordered_logit(history.iloc[:i], features, penalty)
            losses.append(ordinal_rps(predict_ordered_logit(fit, history.iloc[[i]]), history.y.iloc[[i]].to_numpy())[0])
        scores[repr(penalty)] = float(np.mean(losses))
    best = min(grid, key=lambda p: (round(scores[repr(p)], 12), -p))
    return best, scores


# ---------------------------------------------------------------------------
# Panel with policy-rule features
# ---------------------------------------------------------------------------

def build_robust_panel(model_panel_path: Path = MODEL_PANEL_PATH, decisions_path: Path = DECISIONS_PATH,
                       raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """Model panel plus features known at each decision date.

    * previous_decision - the NBK's own previous decision (-1/0/+1), known before the meeting;
    * real_rate - base rate in force before the decision minus inflation at the assumed reference month;
    * inflation_change_3m - inflation at the reference month minus inflation three months earlier.
    No value is imputed; rows with a missing feature are dropped by the caller.
    """
    panel = pd.read_csv(model_panel_path, parse_dates=["decision_date"])
    decisions = pd.read_csv(decisions_path, parse_dates=["decision_date"])
    if not panel.decision_date.equals(decisions.decision_date):
        raise RobustEvalError("model_panel.csv and nbk_decisions_clean.csv list different decision dates")
    panel = panel.sort_values("decision_date").reset_index(drop=True)
    panel["previous_decision"] = panel["y"].shift(1)
    panel["base_rate_before"] = decisions["base_rate_before"].to_numpy(dtype=float)
    panel["base_rate_after"] = decisions["base_rate_after"].to_numpy(dtype=float)
    filename, column = FEATURE_RULES["inflation"]
    monthly = complete_month_calendar(read_monthly_series(Path(raw_dir) / filename, column))
    change = (monthly - monthly.shift(3)).rename("inflation_change_3m")
    panel["inflation_change_3m"] = apply_release_lag(change, panel.decision_date).to_numpy()
    panel["real_rate"] = panel["base_rate_before"] - panel["inflation"]
    return panel


def next_decision_row(panel: pd.DataFrame) -> pd.DataFrame:
    """Feature vector for the next meeting, built the same way as the dashboard does.

    The six factors and the inflation change stay at the latest decision's values
    (future values are unknown); previous_decision becomes the latest decision and
    the real rate uses the base rate set by that decision.
    """
    latest = panel.dropna(subset=MAIN_FEATURES + ["y"]).iloc[[-1]].copy()
    row = latest.copy()
    row["previous_decision"] = float(latest["y"].iloc[0])
    row["real_rate"] = float(latest["base_rate_after"].iloc[0] - latest["inflation"].iloc[0])
    return row


# ---------------------------------------------------------------------------
# Forecasters
# ---------------------------------------------------------------------------

Forecaster = Callable[[pd.DataFrame, pd.DataFrame], tuple[np.ndarray, dict[str, Any]]]


def _always_hold(history: pd.DataFrame, target: pd.DataFrame):
    probs = np.zeros((len(target), 3))
    probs[:, 1] = 1.0
    return probs, {}


def _class_frequency(history: pd.DataFrame, target: pd.DataFrame):
    counts = np.bincount(history.y.to_numpy(dtype=int) + 1, minlength=3).astype(float)
    return np.tile(counts / counts.sum(), (len(target), 1)), {}


def _persistence(history: pd.DataFrame, target: pd.DataFrame):
    """Repeat the previous decision (a deterministic no-change-in-direction forecast)."""
    probs = np.zeros((len(target), 3))
    previous = target["previous_decision"].to_numpy(dtype=int)
    probs[np.arange(len(target)), previous + 1] = 1.0
    return probs, {}


def _ordered(features: list[str], ridge: bool) -> Forecaster:
    def forecaster(history: pd.DataFrame, target: pd.DataFrame):
        if ridge:
            penalty, cv = choose_penalty(history, features)
        else:
            penalty, cv = SAFEGUARD_PENALTY, {}
        fit = fit_ordered_logit(history, features, penalty)
        return predict_ordered_logit(fit, target), {"penalty": penalty, "converged": fit["converged"], "cv_rps": cv,
                                                    "fit": fit}
    return forecaster


SPECIFICATIONS: list[dict[str, Any]] = [
    {"id": "B0", "name": "Always Hold (pre-specified benchmark)", "kind": "benchmark", "forecaster": _always_hold},
    {"id": "B1", "name": "Class frequencies of the estimation window", "kind": "benchmark", "forecaster": _class_frequency},
    {"id": "B2", "name": "Persistence: repeat the previous decision", "kind": "benchmark", "forecaster": _persistence},
    {"id": "M0", "name": "Main ordered logit, six factors (unpenalized)", "kind": "model",
     "features": MAIN_FEATURES, "forecaster": _ordered(MAIN_FEATURES, ridge=False)},
    {"id": "M1", "name": "Main ordered logit, six factors, ridge (penalty by time-series CV)", "kind": "model",
     "features": MAIN_FEATURES, "forecaster": _ordered(MAIN_FEATURES, ridge=True)},
    {"id": "P0", "name": "Policy-rule ordered logit: inflation, its 3-month change, real rate, previous decision",
     "kind": "model", "features": RULE_FEATURES, "forecaster": _ordered(RULE_FEATURES, ridge=False)},
    {"id": "P1", "name": "Policy-rule features plus the five other factors, ridge (penalty by time-series CV)",
     "kind": "model", "features": RULE_PLUS_FEATURES, "forecaster": _ordered(RULE_PLUS_FEATURES, ridge=True)},
]


def _evaluate(spec: dict[str, Any], usable: pd.DataFrame, positions: list[int], *, refit: bool,
              origin: int | None = None) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Forecast each position from data strictly before it (refit) or before ``origin`` (fixed)."""
    probabilities, info = [], []
    fixed_cache: dict[str, Any] | None = None
    for position in positions:
        end = position if refit else origin
        history = usable.iloc[:end]
        target = usable.iloc[[position]]
        if not history.decision_date.max() < target.decision_date.iloc[0]:
            raise RobustEvalError("A forecast would use information from its own decision date or later")
        if refit or fixed_cache is None or spec["kind"] == "benchmark":
            probs, details = spec["forecaster"](history, target)
            if not refit and spec["kind"] == "model":
                fixed_cache = details
        else:
            probs = predict_ordered_logit(fixed_cache["fit"], target)
            details = fixed_cache
        probabilities.append(probs[0])
        info.append({key: value for key, value in details.items() if key != "fit"})
    return np.vstack(probabilities), info


def _metrics(probabilities: np.ndarray, actual: np.ndarray, hold_probabilities: np.ndarray) -> dict[str, Any]:
    score = expected_score(probabilities)
    error = score - actual
    hold_error = expected_score(hold_probabilities) - actual
    rps, hold_rps = ordinal_rps(probabilities, actual), ordinal_rps(hold_probabilities, actual)
    logs = log_loss(probabilities, actual)
    rmse = float(np.sqrt(np.mean(error ** 2)))
    hold_rmse = float(np.sqrt(np.mean(hold_error ** 2)))
    return {
        "n": int(len(actual)),
        "rmse": rmse,
        "rmse_ratio_to_hold": rmse / hold_rmse if hold_rmse > 0 else None,
        "mae": float(np.mean(np.abs(error))),
        "rps": float(rps.mean()),
        "rps_skill_vs_hold": float(1 - rps.mean() / hold_rps.mean()) if hold_rps.mean() > 0 else None,
        "brier": float(brier(probabilities, actual).mean()),
        "log_score": float(logs.mean()) if np.isfinite(logs).all() else None,
        "hit_rate": float(np.mean(probabilities.argmax(axis=1) - 1 == actual)),
        "dm_squared_error_vs_hold": dm_test(error ** 2, hold_error ** 2),
        "dm_rps_vs_hold": dm_test(rps, hold_rps),
        "bootstrap_rmse_ratio_vs_hold": block_bootstrap_ratio(error, hold_error),
    }


# ---------------------------------------------------------------------------
# Data anomaly screen
# ---------------------------------------------------------------------------

def anomaly_screen(raw_dir: Path = RAW_DIR, threshold: float = MODIFIED_Z_THRESHOLD) -> list[dict[str, Any]]:
    """Flag months whose change is extreme relative to the series' own history.

    Level series (trade, lending) are screened on monthly log changes; rate series
    (inflation, consumption growth) on first differences. modified z = 0.6745 *
    (x - median) / MAD. A flag is a prompt to re-check the source, not proof of an error.
    """
    flags = []
    for feature, (filename, column) in FEATURE_RULES.items():
        series = complete_month_calendar(read_monthly_series(Path(raw_dir) / filename, column))
        change = series.diff() if feature in RATE_SERIES else np.log(series.where(series > 0)).diff()
        values = change.dropna()
        median = float(values.median())
        mad = float((values - median).abs().median())
        if mad == 0:
            continue
        z = 0.6745 * (values - median) / mad
        for month, score in z[z.abs() >= threshold].items():
            flags.append({
                "feature": feature, "series_file": filename, "month": str(month),
                "value": float(series.loc[month]), "previous_value": float(series.shift(1).loc[month]),
                "change": float(change.loc[month]),
                "change_definition": "first difference" if feature in RATE_SERIES else "monthly log change",
                "modified_z": float(score),
            })
    return flags


def anomalies_in_latest_inputs(flags: list[dict[str, Any]], latest_date: pd.Timestamp, lag_months: int) -> list[dict[str, Any]]:
    """Flags in a month that enters the latest score (reference month, and month-12 for growth factors)."""
    reference = latest_date.to_period("M") - lag_months
    growth = {"exports", "imports", "corporate_lending", "household_lending"}
    relevant = []
    for flag in flags:
        months = {str(reference)} | ({str(reference - 12)} if flag["feature"] in growth else set())
        # a month-to-month jump at the reference month or the month just before it moves the input
        months |= {str(reference - 1)}
        if flag["month"] in months:
            relevant.append(flag)
    return relevant


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _to_builtin(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _to_builtin(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_builtin(v) for v in value]
    if isinstance(value, np.ndarray):
        return [_to_builtin(v) for v in value.tolist()]
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    return value


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def run(output_dir: Path = OUTPUTS, artifact_path: Path = ROBUST_ARTIFACT_PATH,
        model_panel_path: Path = MODEL_PANEL_PATH, decisions_path: Path = DECISIONS_PATH,
        raw_dir: Path = RAW_DIR, main_artifact_path: Path = MAIN_ARTIFACT_PATH) -> dict[str, Any]:
    output_dir, artifact_path = Path(output_dir), Path(artifact_path)
    main_artifact = json.loads(Path(main_artifact_path).read_text(encoding="utf-8"))
    estimation_n = int(main_artifact["sample"]["estimation_n"])
    lag_months = int(main_artifact.get("assumed_release_lag_months", 2)) if isinstance(
        main_artifact.get("assumed_release_lag_months"), int) else 2

    panel = build_robust_panel(model_panel_path, decisions_path, raw_dir)
    usable = panel.dropna(subset=MAIN_FEATURES + ["y"]).reset_index(drop=True)
    missing_rule = usable[RULE_PLUS_FEATURES].isna().any(axis=1)
    if missing_rule.any():
        raise RobustEvalError(f"Policy-rule features missing for {int(missing_rule.sum())} usable decisions")
    if len(usable) != int(main_artifact["sample"]["usable_n"]):
        raise RobustEvalError("Usable sample differs from the main model's; re-run `python run.py model` first")
    holdout_positions = list(range(estimation_n, len(usable)))
    rolling_positions = list(range(FIRST_ORIGIN, estimation_n))
    actual_rolling = usable.y.to_numpy(dtype=int)[rolling_positions]
    actual_holdout = usable.y.to_numpy(dtype=int)[holdout_positions]

    designs = {
        "rolling_origin_estimation_sample": {
            "description": (f"One-step-ahead forecasts for usable decisions {FIRST_ORIGIN + 1}-{estimation_n} "
                            "(inside the estimation sample), each model refitted on all earlier decisions. "
                            "Uses no holdout data, so it is the fair basis for comparing specifications."),
            "positions": rolling_positions, "refit": True, "origin": None, "actual": actual_rolling,
        },
        "holdout_fixed_origin": {
            "description": ("Same protocol as the main model: fit once on the 70 estimation decisions, "
                            "forecast the 18 holdout decisions. Non-confirmatory (holdout already seen)."),
            "positions": holdout_positions, "refit": False, "origin": estimation_n, "actual": actual_holdout,
        },
        "holdout_recursive": {
            "description": ("Refit before every holdout decision on all earlier decisions, as a real user would. "
                            "Non-confirmatory (holdout already seen)."),
            "positions": holdout_positions, "refit": True, "origin": None, "actual": actual_holdout,
        },
    }

    results: dict[str, Any] = {}
    prediction_rows = []
    for design_name, design in designs.items():
        hold_probs, _ = _evaluate(SPECIFICATIONS[0], usable, design["positions"], refit=design["refit"],
                                  origin=design["origin"])
        rows = []
        for spec in SPECIFICATIONS:
            probs, info = _evaluate(spec, usable, design["positions"], refit=design["refit"], origin=design["origin"])
            metrics = _metrics(probs, design["actual"], hold_probs)
            penalties = [item.get("penalty") for item in info if item.get("penalty") is not None]
            converged = [item.get("converged") for item in info if item.get("converged") is not None]
            metrics.update({
                "id": spec["id"], "name": spec["name"], "kind": spec["kind"],
                "features": spec.get("features"),
                "penalties_used": sorted({float(p) for p in penalties}) if penalties else None,
                "all_fits_converged": all(converged) if converged else None,
            })
            rows.append(metrics)
            for position, prob in zip(design["positions"], probs):
                prediction_rows.append({
                    "design": design_name, "spec_id": spec["id"],
                    "decision_date": usable.decision_date.iloc[position].date().isoformat(),
                    "actual_score": int(usable.y.iloc[position]),
                    "P_Decrease": prob[0], "P_Hold": prob[1], "P_Increase": prob[2],
                    "expected_score": float(prob @ SCORES),
                })
        results[design_name] = {"description": design["description"], "n": len(design["positions"]),
                                "first_date": usable.decision_date.iloc[design["positions"][0]].date().isoformat(),
                                "last_date": usable.decision_date.iloc[design["positions"][-1]].date().isoformat(),
                                "specifications": rows}

    # Sanity check: M0 on the fixed-origin holdout must reproduce the main model.
    main_rmse = float(main_artifact["benchmark_comparison"]["model"]["rmse"])
    m0 = next(r for r in results["holdout_fixed_origin"]["specifications"] if r["id"] == "M0")
    reproduction = {"main_model_holdout_rmse": main_rmse, "m0_holdout_rmse": m0["rmse"],
                    "absolute_difference": abs(main_rmse - m0["rmse"]),
                    "passes": abs(main_rmse - m0["rmse"]) < 1e-3}

    # Forecast for the next meeting under each model specification, fitted on all usable decisions.
    next_row = next_decision_row(panel)
    next_forecasts = []
    for spec in SPECIFICATIONS:
        probs, info = spec["forecaster"](usable, next_row)
        item = {"id": spec["id"], "name": spec["name"], "kind": spec["kind"],
                "probabilities": dict(zip(CLASS_ORDER, probs[0])),
                "expected_score": float(probs[0] @ SCORES)}
        if info.get("fit") is not None:
            fit = info["fit"]
            item["penalty"] = info["penalty"]
            item["coefficients_standardized"] = dict(zip(fit["features"], fit["beta_standardized"]))
        next_forecasts.append(item)

    flags = anomaly_screen(raw_dir)
    latest_date = usable.decision_date.iloc[-1]
    relevant_flags = anomalies_in_latest_inputs(flags, latest_date, lag_months)

    artifact = {
        "label": LABEL_NOTE,
        "seed": SEED,
        "settings": {
            "first_rolling_origin": FIRST_ORIGIN, "lambda_grid": LAMBDA_GRID, "inner_window": INNER_WINDOW,
            "safeguard_penalty": SAFEGUARD_PENALTY, "bootstrap_block_length": BLOCK_LENGTH,
            "bootstrap_draws": BOOTSTRAP_DRAWS, "modified_z_threshold": MODIFIED_Z_THRESHOLD,
            "feature_labels": FEATURE_LABELS,
        },
        "designs": results,
        "reproduction_of_main_model": reproduction,
        "next_decision_forecasts": {
            "based_on_decision": latest_date.date().isoformat(),
            "previous_decision_used": int(next_row["previous_decision"].iloc[0]),
            "base_rate_used": float(next_row["base_rate_after"].iloc[0]),
            "forecasts": next_forecasts,
        },
        "anomaly_screen": {"flags": flags, "affecting_latest_score": relevant_flags,
                           "latest_decision": latest_date.date().isoformat(), "assumed_lag_months": lag_months},
    }
    artifact = _to_builtin(artifact)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                             encoding="utf-8", newline="\n")
    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(prediction_rows).to_csv(output_dir / "robust_eval_predictions.csv", index=False,
                                         float_format="%.6f", lineterminator="\n")
    (output_dir / "robust_evaluation.md").write_text(render_markdown(artifact), encoding="utf-8", newline="\n")
    return artifact


def render_markdown(artifact: dict[str, Any]) -> str:
    lines = ["# Exploratory robustness evaluation", "", f"> {artifact['label']}", ""]
    rep = artifact["reproduction_of_main_model"]
    lines += [f"Implementation check: specification M0 reproduces the main model's holdout RMSE "
              f"({_fmt(rep['m0_holdout_rmse'])} vs {_fmt(rep['main_model_holdout_rmse'])}; "
              f"{'PASS' if rep['passes'] else 'FAIL'}).", ""]
    header = ("| Id | Specification | n | RMSE | RMSE ratio vs Hold | 95% block-bootstrap CI | DM p (sq. error) "
              "| RPS | RPS skill vs Hold | DM p (RPS) | Log score | Hit rate |")
    for design_name, design in artifact["designs"].items():
        title = design_name.replace("_", " ").capitalize()
        lines += [f"## {title}", "", f"{design['description']} Decisions {design['first_date']} to "
                  f"{design['last_date']} (n = {design['n']}).", "", header,
                  "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for row in design["specifications"]:
            boot = row["bootstrap_rmse_ratio_vs_hold"]
            ci = "—" if row["id"] == "B0" else f"{_fmt(boot['ci_low'])}–{_fmt(boot['ci_high'])}"
            dm_se = "—" if row["id"] == "B0" else _fmt(row["dm_squared_error_vs_hold"]["p_value"])
            dm_rps = "—" if row["id"] == "B0" else _fmt(row["dm_rps_vs_hold"]["p_value"])
            lines.append(
                f"| {row['id']} | {row['name']} | {row['n']} | {_fmt(row['rmse'])} | {_fmt(row['rmse_ratio_to_hold'])} "
                f"| {ci} | {dm_se} | {_fmt(row['rps'])} | {_fmt(row['rps_skill_vs_hold'])} | {dm_rps} "
                f"| {_fmt(row['log_score'])} | {_fmt(row['hit_rate'])} |")
        lines.append("")
    lines += [
        "Reading the table. RMSE is computed on the expected score (Decrease = −1, Hold = 0, Increase = +1), "
        "as in the main model. RPS (ranked probability score, lower is better) scores the full probability "
        "forecast and respects the class order; it is finite for Always Hold, unlike the log score (n/a = "
        "infinite because a forecast gave zero probability to an observed class). RPS skill = 1 − RPS/RPS(Hold); "
        "positive values favour the specification. DM p is the two-sided Harvey–Leybourne–Newbold-corrected "
        "Diebold–Mariano p-value against Always Hold. The bootstrap interval resamples blocks of "
        f"{artifact['settings']['bootstrap_block_length']} consecutive decisions "
        f"({artifact['settings']['bootstrap_draws']} draws, seed {artifact['seed']}). Ridge penalties are chosen "
        f"at every forecast origin by one-step RPS over the previous {artifact['settings']['inner_window']} "
        "decisions only.", ""]
    nxt = artifact["next_decision_forecasts"]
    lines += ["## Next-meeting probabilities by specification", "",
              f"All specifications are fitted on every usable decision up to {nxt['based_on_decision']}. "
              f"Factor inputs stay at their latest values; previous decision = {nxt['previous_decision_used']:+d}, "
              f"base rate = {nxt['base_rate_used']:.2f}%.", "",
              "| Id | Specification | P(Decrease) | P(Hold) | P(Increase) | Expected score |",
              "|---|---|---|---|---|---|"]
    for item in nxt["forecasts"]:
        p = item["probabilities"]
        lines.append(f"| {item['id']} | {item['name']} | {_fmt(p['Decrease'])} | {_fmt(p['Hold'])} | "
                     f"{_fmt(p['Increase'])} | {_fmt(item['expected_score'])} |")
    lines.append("")
    screen = artifact["anomaly_screen"]
    lines += ["## Raw-data anomaly screen", "",
              f"Modified z-score of monthly changes, flag at |z| ≥ {artifact['settings']['modified_z_threshold']} "
              "(Iglewicz and Hoaglin, 1993). A flag asks for the source value to be re-checked; it is not "
              "evidence of an error and nothing is changed in the data.", "",
              "| Series | Month | Value | Previous month | Change | Modified z | Enters latest score |",
              "|---|---|---|---|---|---|---|"]
    affecting = {(f["feature"], f["month"]) for f in screen["affecting_latest_score"]}
    for flag in screen["flags"]:
        lines.append(f"| {flag['series_file']} | {flag['month']} | {flag['value']:.2f} | {flag['previous_value']:.2f} "
                     f"| {flag['change']:.3f} ({flag['change_definition']}) | {flag['modified_z']:.2f} "
                     f"| {'yes' if (flag['feature'], flag['month']) in affecting else 'no'} |")
    lines += ["", "Generated by `python run.py robust` (src/robust_eval.py).", ""]
    return "\n".join(lines)


def main() -> dict[str, Any]:
    artifact = run()
    for design_name, design in artifact["designs"].items():
        print(f"\n{design_name} (n={design['n']}):")
        for row in design["specifications"]:
            print(f"  {row['id']:<3} RMSE ratio {_fmt(row['rmse_ratio_to_hold'])}  RPS {_fmt(row['rps'])}  "
                  f"RPS skill {_fmt(row['rps_skill_vs_hold'])}  DM p(RPS) {_fmt(row['dm_rps_vs_hold']['p_value'])}")
    rep = artifact["reproduction_of_main_model"]
    print(f"\nM0 reproduces main model holdout RMSE: {'PASS' if rep['passes'] else 'FAIL'} "
          f"(|diff| = {rep['absolute_difference']:.2e})")
    print(f"Anomaly flags: {len(artifact['anomaly_screen']['flags'])}; affecting latest score: "
          f"{len(artifact['anomaly_screen']['affecting_latest_score'])}")
    return artifact


if __name__ == "__main__":
    main()
