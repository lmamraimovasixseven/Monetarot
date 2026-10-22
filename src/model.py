"""Estimate the specified ordered-logit model and write reproducible diagnostics."""

from __future__ import annotations

import importlib.metadata
import json
import math
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import chi2, norm
from statsmodels.miscmodels.ordinal_model import OrderedModel
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.tools.tools import add_constant
from statsmodels.tsa.stattools import adfuller, kpss

from src.hashing import normalized_sha256
from src.ingest import (
    ASSUMED_LAG_MONTHS,
    FEATURE_RULES,
    RAW_DIR,
    apply_release_lag,
    build_model_panel,
    complete_month_calendar,
    log_level,
    log_growth_12m,
    read_monthly_series,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "processed" / "nbk_decisions_clean.csv"
MODEL_PANEL_PATH = ROOT / "data" / "processed" / "model_panel.csv"
OUTPUTS = ROOT / "outputs"
ARTIFACT_PATH = ROOT / "model" / "artifact.json"
FEATURES = list(FEATURE_RULES)
CLASS_ORDER = ["Decrease", "Hold", "Increase"]
SCORE_MAP = {"Decrease": -1, "Hold": 0, "Increase": 1}
SEED = 42
HOLDOUT_SHARE = 0.20
ALPHA = 0.05
ADF_MAX_LAG = 12


class SpecificationError(RuntimeError):
    """Raised when required model inputs or numerical conditions are invalid."""


def _scalar(value: Any) -> Any:
    """Convert numpy and pandas values to strict-JSON-compatible built-ins."""
    if value is None:
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _scalar(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, np.ndarray, pd.Series)):
        return [_scalar(item) for item in list(value)]
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write strict JSON without NaN or Infinity extension values."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_scalar(payload), indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _p_value(value: Any) -> float | None:
    """Return a finite probability or None if a test did not produce one."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) and 0 <= number <= 1 else None


def _number(value: Any) -> float | str | None:
    """Serialize finite statistics as numbers and infinite values as text."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else ("+Infinity" if number > 0 else "-Infinity")


def _new_spec(records: list[dict[str, Any]], run_id: str, name: str, kind: str,
              sample: pd.DataFrame | None) -> int:
    """Begin a log record before attempting a model or test."""
    records.append({
        "run_id": run_id,
        "spec_id": f"{run_id}-{len(records) + 1:04d}",
        "name": name,
        "kind": kind,
        "sample_n": int(len(sample)) if sample is not None else None,
        "sample_start": sample.decision_date.min().date().isoformat() if sample is not None and len(sample) else None,
        "sample_end": sample.decision_date.max().date().isoformat() if sample is not None and len(sample) else None,
        "status": "RUNNING",
        "statistic": None,
        "degrees_freedom": None,
        "p_value": None,
        "p_value_holm": None,
        "p_value_adjusted": None,
        "p_value_family": None,
        "log_likelihood": None,
        "message": "",
    })
    return len(records) - 1


def _finish_spec(records: list[dict[str, Any]], index: int, *, status: str,
                 statistic: Any = None, df: Any = None, p_value: Any = None,
                 log_likelihood: Any = None, message: Any = "") -> None:
    """Finish a log row with returned values or an explicit failure reason."""
    records[index].update({
        "status": status,
        "statistic": _number(statistic),
        "degrees_freedom": _number(df),
        "p_value": _p_value(p_value),
        "log_likelihood": _number(log_likelihood),
        "message": str(message),
    })


def _assign_p_value_families(records: list[dict[str, Any]]) -> None:
    """Apply only the pre-defined within-family Holm correction to slope tests."""
    slopes = [row for row in records if row.get("kind") == "coefficient_test"
              and row.get("name") in {"parameter:" + feature for feature in FEATURES}
              and _p_value(row.get("p_value")) is not None]
    if slopes:
        adjusted = multipletests([row["p_value"] for row in slopes], method="holm")[1]
        for row, value in zip(slopes, adjusted):
            row["p_value_family"] = "six slope-coefficient p-values (Holm across six)"
            row["p_value_adjusted"] = float(value)
            row["p_value_holm"] = float(value)  # retained for existing consumers

    robustness_groups: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        if row.get("kind") == "robustness_coefficient" and _p_value(row.get("p_value")) is not None:
            robustness_groups.setdefault(str(row.get("specification_id")), []).append(row)
    for specification_id, group in robustness_groups.items():
        adjusted = multipletests([row["p_value"] for row in group], method="holm")[1]
        for row, value in zip(group, adjusted):
            row["p_value_family"] = f"robustness specification {specification_id} coefficient p-values (Holm within specification)"
            row["p_value_adjusted"] = float(value)
            row["p_value_holm"] = float(value)

    for row in records:
        if _p_value(row.get("p_value")) is None or row in slopes or row.get("kind") == "robustness_coefficient":
            continue
        if row.get("kind") == "joint_slope_lr":
            row["p_value_family"] = "pre-specified joint LR test (single primary test; no adjustment)"
            row["p_value_adjusted"] = row["p_value"]
        elif row.get("kind") == "coefficient_test":
            row["p_value_family"] = "cutpoint coefficient tests (unadjusted; outside six-slope family)"
            row["p_value_adjusted"] = row["p_value"]
        else:
            row["p_value_family"] = "diagnostics (raw p-values; no adjustment; flag at 5%)"
            row["p_value_adjusted"] = row["p_value"]
        row["p_value_holm"] = row["p_value_adjusted"]


def _fit_ordered(frame: pd.DataFrame, seed: int = SEED, feature_names: list[str] | None = None):
    """Fit fixed ordered logit and calculate HC0 score-sandwich covariance."""
    np.random.seed(seed)
    endog = pd.Categorical(frame.y.astype(int), categories=[-1, 0, 1], ordered=True)
    feature_names = feature_names or FEATURES
    model = OrderedModel(endog, frame[feature_names].astype(float), distr="logit")
    result = model.fit(method="bfgs", maxiter=2000, disp=False, gtol=1e-8)
    params = np.asarray(result.params, dtype=float)
    score_rows = np.asarray(model.score_obs(params), dtype=float)
    hessian = np.asarray(model.hessian(params), dtype=float)
    information = -(hessian + hessian.T) / 2
    bread = np.linalg.pinv(information, hermitian=True)
    covariance = bread @ (score_rows.T @ score_rows) @ bread
    return model, result, (covariance + covariance.T) / 2


def _named_parameter_covariance(model: OrderedModel, params: np.ndarray, covariance: np.ndarray,
                                feature_names: list[str] | None = None):
    """Transform internal threshold-gap covariance to named actual cutpoints."""
    feature_names = feature_names or FEATURES
    names = [*feature_names, "cutpoint[Decrease|Hold]", "cutpoint[Hold|Increase]"]
    k = len(feature_names)

    def transform(values: np.ndarray) -> np.ndarray:
        cutpoints = np.asarray(model.transform_threshold_params(values), dtype=float)[1:-1]
        return np.r_[values[:k], cutpoints]

    estimates = transform(params)
    jacobian = np.zeros((len(estimates), len(params)))
    for column in range(len(params)):
        step = 1e-6 * max(1.0, abs(float(params[column])))
        upper, lower = params.copy(), params.copy()
        upper[column] += step
        lower[column] -= step
        jacobian[:, column] = (transform(upper) - transform(lower)) / (2 * step)
    named_cov = jacobian @ covariance @ jacobian.T
    return names, estimates, (named_cov + named_cov.T) / 2


def _predict_probabilities(model: OrderedModel, params: np.ndarray, frame: pd.DataFrame,
                           feature_names: list[str] | None = None) -> np.ndarray:
    """Predict columns ordered as Decrease, Hold, Increase."""
    feature_names = feature_names or FEATURES
    probabilities = np.asarray(
        model.predict(params, exog=frame[feature_names].astype(float), which="prob"), dtype=float
    )
    if probabilities.ndim == 1:
        probabilities = probabilities.reshape(1, -1)
    if probabilities.shape[1] != 3:
        raise SpecificationError(f"Expected 3 probabilities; received {probabilities.shape}")
    if not np.isfinite(probabilities).all() or not np.allclose(probabilities.sum(axis=1), 1.0, atol=1e-8):
        raise SpecificationError("Predicted probabilities are invalid or do not sum to one")
    return probabilities


def _log_score(probabilities: np.ndarray, actual: np.ndarray) -> float | str:
    """Compute multiclass negative mean log probability of the true class."""
    true_probability = probabilities[np.arange(len(actual)), actual.astype(int) + 1]
    return "+Infinity" if (true_probability <= 0).any() else float(-np.log(true_probability).mean())


def _falsification_verdicts(joint_statistic: float, joint_p_raw: float,
                            rmse_ratio: float | None,
                            parameter_rows: list[dict[str, Any]],
                            joint_p_adjusted: float | None) -> list[dict[str, Any]]:
    """Evaluate the three model-spec falsification rules without altering them."""
    sign_rows = [row for row in parameter_rows if row["name"] in FEATURES]
    opposite = [row for row in sign_rows if row["estimate"] < 0 and row["p_value"] < ALPHA]
    opposite_adjusted = [row for row in sign_rows if row["estimate"] < 0
                         and row.get("p_value_adjusted") is not None
                         and row["p_value_adjusted"] < ALPHA]
    return [
        {
            "rule": "Joint LR test of all six slopes is not rejected at 10% (raw p-value)",
            "statistic": joint_statistic,
            "threshold": "raw p >= 0.10",
            "verdict": "falsified" if joint_p_raw >= 0.10 else "not falsified",
            "raw_p_value": joint_p_raw,
            "adjusted_p_value": joint_p_adjusted,
            "p_value_family": "pre-specified joint LR test (single primary test; no adjustment)",
            "adjusted_transparency_verdict": "falsified" if joint_p_adjusted is not None and joint_p_adjusted >= 0.10 else "not falsified",
        },
        {
            "rule": "Any factor has an opposite-sign coefficient significant at 5% (raw p-value)",
            "statistic": ", ".join(row["name"] for row in opposite) or "no opposite-sign significant factors",
            "threshold": "opposite sign and raw p < 0.05",
            "verdict": "falsified" if opposite else "not falsified",
            "raw_p_value": {row["name"]: row["p_value"] for row in sign_rows},
            "adjusted_p_value": {row["name"]: row.get("p_value_adjusted") for row in sign_rows},
            "p_value_family": "six slope-coefficient p-values (Holm across six)",
            "adjusted_transparency_verdict": "falsified" if opposite_adjusted else "not falsified",
        },
        {
            "rule": "Holdout expected-score RMSE ratio is >= 1",
            "statistic": rmse_ratio,
            "threshold": "RMSE_model / RMSE_Always_Hold >= 1",
            "verdict": "falsified" if rmse_ratio is not None and rmse_ratio >= 1 else "not falsified",
            "raw_p_value": "not applicable",
            "adjusted_p_value": "not applicable",
            "p_value_family": "not applicable (RMSE criterion has no p-value)",
            "adjusted_transparency_verdict": "same rule; p-value adjustment not applicable",
        },
    ]


def _write_falsification_markdown(path: Path, verdicts: list[dict[str, Any]]) -> None:
    """Write the spec's three falsification verdicts and adjusted transparency view."""
    rows = []
    for row in verdicts:
        rows.append({
            "rule": row["rule"], "statistic": row["statistic"], "threshold": row["threshold"],
            "verdict": row["verdict"], "raw p-value": row["raw_p_value"],
            "adjusted p-value": row["adjusted_p_value"],
            "p-value family": row["p_value_family"],
            "adjusted transparency verdict": row["adjusted_transparency_verdict"],
        })
    lines = ["# Falsification verdicts", "", "Rules are evaluated as written in `docs/model_spec.md`. The primary joint LR decision uses its raw p-value. The adjusted column is shown for transparency; it does not replace the specified rule.", ""]
    lines.extend(_markdown_table(pd.DataFrame(rows)))
    lines.extend(["", "The finite class-frequency log-score comparator is secondary and was added after the specification freeze. The pre-specified winner remains determined only by expected-score RMSE versus Always Hold.", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def _write_robustness_markdown(path: Path, checks: list[dict[str, Any]], total_specifications: int) -> None:
    """Render the requested robustness summaries without selecting a model."""
    summary_columns = [
        "specification_id", "name", "estimator", "status", "n_usable", "estimation_n", "holdout_n",
        "holdout_start", "holdout_end", "rmse_model", "rmse_hold", "rmse_ratio_model_to_hold",
        "benchmark_conclusion", "same_signs_as_primary", "same_benchmark_conclusion_as_primary",
        "feature_transformations", "survives",
    ]
    coefficient_rows = []
    for check in checks:
        for coefficient in check.get("coefficients", []):
            coefficient_rows.append({
                "specification_id": check["specification_id"], "specification": check["name"],
                "coefficient": coefficient["name"], "estimate": coefficient["estimate"],
                "sign": "positive" if coefficient["estimate"] > 0 else "negative" if coefficient["estimate"] < 0 else "zero",
                "robust_se": coefficient.get("robust_se"), "raw_p_value": coefficient.get("p_value"),
                "adjusted_p_value": coefficient.get("p_value_adjusted"),
                "significant_at_5pct_adjusted": coefficient.get("significant_at_5pct_adjusted"),
                "p_value_family": coefficient.get("p_value_family", "not available"),
            })
    summaries = pd.DataFrame(checks).reindex(columns=summary_columns)
    coefficient_table = pd.DataFrame(coefficient_rows)
    lines = [
        "# Robustness checks", "",
        f"Total specifications: {total_specifications} (one primary specification plus {len(checks)} requested robustness specifications). Robustness checks converged: {sum(row['status'] == 'COMPLETED' for row in checks)}; nonconverged or failed: {sum(row['status'] != 'COMPLETED' for row in checks)}.",
        "Each robustness variant uses a chronological 80/20 split within its own usable sample; coefficients are fit on the earlier portion only. All comparisons use Always Hold on the same variant-specific holdout dates. The main 18-row holdout and main model are unchanged. `Survives?` means all factor coefficient signs match the primary ordered logit and the variant reaches the same model-versus-Hold RMSE conclusion. These checks are descriptive and are not used to select a final model. NONCONVERGED checks retain their reported diagnostic estimates and scores but should not be treated as successful fits.",
        "For binary logit, the equivalent expected score is P(Increase) × 1 + P(not Increase) × 0, evaluated against the observed ordinal score -1/0/+1.", "",
        "## Specification-level results", "",
    ]
    if "feature_transformations" in summaries:
        summaries["feature_transformations"] = summaries["feature_transformations"].map(
            lambda value: "; ".join(f"{feature}: {transform}" for feature, transform in value.items())
            if isinstance(value, dict) else value
        )
    lines.extend(_markdown_table(summaries))
    lines.extend(["", "## Coefficients and within-specification inference", ""])
    lines.extend(_markdown_table(coefficient_table))
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def _score_metrics(predicted: np.ndarray, actual: np.ndarray) -> dict[str, float]:
    """Compute RMSE and MAE for the expected ordinal score."""
    error = np.asarray(predicted, dtype=float) - np.asarray(actual, dtype=float)
    return {"rmse": float(np.sqrt(np.mean(error ** 2))), "mae": float(np.mean(np.abs(error)))}


def _log_growth_window(series: pd.Series, months: int) -> pd.Series:
    """Calculate 100 times log change over a fixed number of calendar months."""
    monthly = complete_month_calendar(series)
    logged = log_level(monthly)
    return (logged - logged.shift(months)).mul(100).rename(series.name)


def _robustness_panel(base_panel: pd.DataFrame, raw_dir: Path, *, lag_months: int = ASSUMED_LAG_MONTHS,
                      growth_months: int = 12, inflation_ma_months: int | None = None,
                      first_difference_features: tuple[str, ...] = ()) -> pd.DataFrame:
    """Rebuild alternative fixed feature definitions at scheduled decision dates."""
    dates = pd.to_datetime(base_panel["decision_date"], errors="raise")
    result = pd.DataFrame({
        "decision_date": dates,
        "decision": base_panel["decision"].astype(str).to_numpy(),
        "y": base_panel["y"].astype(int).to_numpy(),
    })
    growth_features = {"exports", "imports", "corporate_lending", "household_lending"}
    for feature, (filename, source_column) in FEATURE_RULES.items():
        source = read_monthly_series(raw_dir / filename, source_column)
        if feature == "inflation" and inflation_ma_months:
            monthly = complete_month_calendar(source)
            transformed = monthly.rolling(inflation_ma_months, min_periods=inflation_ma_months).mean()
        elif feature in growth_features:
            transformed = (log_growth_12m(source) if growth_months == 12
                           else _log_growth_window(source, growth_months))
        else:
            transformed = source
        if feature in first_difference_features:
            transformed = complete_month_calendar(transformed).diff()
        result[feature] = apply_release_lag(transformed, dates, lag_months=lag_months).to_numpy()
    return result


def _robustness_definitions(usable: pd.DataFrame, raw_dir: Path) -> list[dict[str, Any]]:
    """Return the pre-specified alternate samples and feature definitions."""
    definitions = [
        {"specification_id": "RB01", "name": "Drop decision years 2020-2022", "kind": "sample", "base": usable.loc[~pd.to_datetime(usable.decision_date).dt.year.between(2020, 2022)].copy()},
    ]
    last_date = pd.to_datetime(usable.decision_date).max()
    cutoff = last_date - pd.DateOffset(months=60)
    definitions.append({"specification_id": "RB02", "name": "Last 60 calendar months", "kind": "sample", "base": usable.loc[pd.to_datetime(usable.decision_date) >= cutoff].copy()})

    base_panel = usable[["decision_date", "decision", "y"]].copy()
    feature_variants = [
        ("RB03", "Binary logit: Increase vs not Increase", "binary", {}),
        ("RB04", "Ordered logit: 3-month trailing inflation average", "ordered", {"inflation_ma_months": 3}),
        ("RB05", "Ordered logit: 6-month trailing inflation average", "ordered", {"inflation_ma_months": 6}),
        ("RB06", "Ordered logit: release lag 1 month", "ordered", {"lag_months": 1}),
        ("RB07", "Ordered logit: release lag 3 months", "ordered", {"lag_months": 3}),
        ("RB08", "Ordered logit: 3-month log growth for exports and lending", "ordered", {"growth_months": 3}),
        ("RB09", "Differenced non-stationary factors", "ordered", {
            "first_difference_features": ("household_lending", "corporate_lending", "inflation"),
        }),
    ]
    for specification_id, name, estimator, kwargs in feature_variants:
        feature_transformations = None
        if specification_id == "RB09":
            feature_transformations = {
                "household_lending": "first difference of 12-month log growth",
                "corporate_lending": "first difference of 12-month log growth",
                "inflation": "first difference of inflation",
                "other factors": "main-model transformations unchanged",
            }
        definitions.append({"specification_id": specification_id, "name": name, "kind": estimator,
                            "base": _robustness_panel(base_panel, raw_dir, **kwargs),
                            "feature_transformations": feature_transformations})
    return definitions


def _run_robustness_checks(usable: pd.DataFrame, raw_dir: Path,
                           primary_coefficients: list[dict[str, Any]],
                           primary_winner: str, records: list[dict[str, Any]],
                           run_id: str) -> list[dict[str, Any]]:
    """Fit all requested alternate variants on chronological 80/20 splits only."""
    primary_signs = {row["name"]: int(np.sign(row["estimate"])) for row in primary_coefficients
                     if row["name"] in FEATURES}
    primary_beats_hold = primary_winner != "Always Hold"
    results = []
    for definition in _robustness_definitions(usable, raw_dir):
        spec_id, name = definition["specification_id"], definition["name"]
        frame = definition["base"].copy()
        frame["decision_date"] = pd.to_datetime(frame.decision_date, errors="raise")
        frame = frame.dropna(subset=FEATURES + ["y"]).sort_values("decision_date").reset_index(drop=True)
        spec_log_index = _new_spec(records, run_id, name, "robustness_specification", frame)
        records[spec_log_index]["specification_id"] = spec_id
        result_row: dict[str, Any] = {
            "specification_id": spec_id, "name": name,
            "estimator": "Binary Logit" if definition["kind"] == "binary" else "Ordered Logit",
            "feature_transformations": definition.get("feature_transformations"),
            "n_usable": int(len(frame)), "sample_start": frame.decision_date.min().date().isoformat() if len(frame) else None,
            "sample_end": frame.decision_date.max().date().isoformat() if len(frame) else None,
            "estimation_n": 0, "holdout_n": 0, "coefficients": [], "status": "NOT RUN",
            "rmse_model": None, "rmse_hold": None, "rmse_ratio_model_to_hold": None,
            "benchmark_conclusion": "UNDETERMINED", "same_signs_as_primary": False,
            "same_benchmark_conclusion_as_primary": False, "survives": "No",
        }
        try:
            if len(frame) < 10:
                raise SpecificationError(f"Too few usable observations for chronological holdout: n={len(frame)}")
            holdout_n = int(math.ceil(HOLDOUT_SHARE * len(frame)))
            train = frame.iloc[:-holdout_n].copy().reset_index(drop=True)
            holdout = frame.iloc[-holdout_n:].copy().reset_index(drop=True)
            if not train.decision_date.max() < holdout.decision_date.min():
                raise SpecificationError("Robustness estimation and holdout dates overlap")
            if definition["kind"] == "binary":
                target = (train.decision == "Increase").astype(int)
                if target.nunique() != 2:
                    raise SpecificationError("Binary estimation sample must contain both target classes")
                design = sm.add_constant(train[FEATURES].astype(float), has_constant="add")
                fitted = sm.Logit(target, design).fit(disp=False, maxiter=2000, cov_type="HC0")
                converged = bool(fitted.mle_retvals.get("converged", False))
                holdout_design = sm.add_constant(holdout[FEATURES].astype(float), has_constant="add")
                increase_probability = np.asarray(fitted.predict(holdout_design), dtype=float)
                predicted_score = increase_probability  # P(Increase)*1 + P(not Increase)*0
                coefficients = []
                for feature in FEATURES:
                    estimate = float(fitted.params[feature])
                    se = float(fitted.bse[feature])
                    p_value = float(fitted.pvalues[feature])
                    coefficients.append({"name": feature, "estimate": estimate, "robust_se": se,
                                         "z_statistic": estimate / se if se > 0 else None,
                                         "p_value": p_value, "p_value_adjusted": None,
                                         "_record_index": None})
            else:
                ordered_model, fitted, covariance = _fit_ordered(train, seed=SEED)
                converged = bool(fitted.mle_retvals.get("converged", False))
                params = np.asarray(fitted.params, dtype=float)
                p = len(FEATURES)
                slope_se = np.sqrt(np.maximum(np.diag(covariance)[:p], 0))
                coefficients = []
                for feature, estimate, se in zip(FEATURES, params[:p], slope_se):
                    p_value = float(2 * norm.sf(abs(estimate / se))) if se > 0 else None
                    coefficients.append({"name": feature, "estimate": float(estimate), "robust_se": float(se),
                                         "z_statistic": float(estimate / se) if se > 0 else None,
                                         "p_value": p_value, "p_value_adjusted": None,
                                         "_record_index": None})
                probabilities = _predict_probabilities(ordered_model, params, holdout)
                predicted_score = probabilities[:, 2] - probabilities[:, 0]
            actual = holdout.y.to_numpy(dtype=int)
            model_metrics = _score_metrics(predicted_score, actual)
            hold_metrics = _score_metrics(np.zeros(len(actual)), actual)
            ratio = model_metrics["rmse"] / hold_metrics["rmse"] if hold_metrics["rmse"] > 0 else None
            conclusion = "Model beats Hold" if ratio is not None and ratio < 1 else "Always Hold"
            sign_map = {item["name"]: int(np.sign(item["estimate"])) for item in coefficients}
            same_signs = sign_map == primary_signs
            same_conclusion = (conclusion == "Model beats Hold") == primary_beats_hold
            result_row.update({
                "estimation_n": int(len(train)), "holdout_n": int(len(holdout)),
                "estimation_start": train.decision_date.min().date().isoformat(),
                "estimation_end": train.decision_date.max().date().isoformat(),
                "holdout_start": holdout.decision_date.min().date().isoformat(),
                "holdout_end": holdout.decision_date.max().date().isoformat(),
                "rmse_model": model_metrics["rmse"], "rmse_hold": hold_metrics["rmse"],
                "rmse_ratio_model_to_hold": ratio, "benchmark_conclusion": conclusion,
                "same_signs_as_primary": same_signs,
                "same_benchmark_conclusion_as_primary": same_conclusion,
                "survives": "Yes" if same_signs and same_conclusion else "No",
                "coefficients": coefficients,
                "estimator_converged": converged,
                "status": "COMPLETED" if converged else "NONCONVERGED",
                "binary_score_definition": "P(Increase)*1 + P(not Increase)*0, compared with actual ordinal score -1/0/+1" if definition["kind"] == "binary" else None,
            })
            for coefficient in coefficients:
                estimate = coefficient["estimate"]
                coefficient["sign"] = (
                    "positive" if estimate > 0 else "negative" if estimate < 0 else "zero"
                )
                row_index = _new_spec(records, run_id, f"{spec_id}: coefficient {coefficient['name']}",
                                      "robustness_coefficient", train)
                records[row_index]["specification_id"] = spec_id
                _finish_spec(records, row_index, status="COMPLETED", statistic=coefficient["z_statistic"],
                             p_value=coefficient["p_value"], message="HC0 robust coefficient test")
                coefficient["_record_index"] = row_index
            _finish_spec(records, spec_log_index, status=result_row["status"], statistic=ratio,
                         message=f"rmse_model={model_metrics['rmse']:.12g}; rmse_hold={hold_metrics['rmse']:.12g}; survives={result_row['survives']}")
        except Exception as exc:
            result_row["status"] = "FAILED"
            result_row["failure_reason"] = str(exc)
            _finish_spec(records, spec_log_index, status="FAILED", message=exc)
        results.append(result_row)
    return results


def _build_raw_level_panel(decision_panel: pd.DataFrame, raw_dir: Path,
                           lag_months: int = ASSUMED_LAG_MONTHS) -> pd.DataFrame:
    """Align untransformed monthly factor levels at decision month minus the configured assumed lag."""
    dates = pd.to_datetime(decision_panel.decision_date, errors="raise")
    output = pd.DataFrame({"decision_date": dates})
    for feature, (filename, source_column) in FEATURE_RULES.items():
        source = read_monthly_series(raw_dir / filename, source_column)
        output[feature] = apply_release_lag(source, dates, lag_months=lag_months).to_numpy()
    return output


def _run_unit_root_tests(train: pd.DataFrame, raw_panel: pd.DataFrame,
                         records: list[dict[str, Any]], run_id: str) -> list[dict[str, Any]]:
    """Run ADF with AIC lag/maxlag 12 and KPSS on train-only levels and inputs."""
    rows = []
    raw_train = raw_panel[raw_panel.decision_date.isin(train.decision_date)].reset_index(drop=True)
    for feature in FEATURES:
        for form, frame in (("transformed_model_input", train), ("raw_level", raw_train)):
            series = pd.to_numeric(frame[feature], errors="coerce").dropna().astype(float)
            for test_name in ("ADF", "KPSS"):
                idx = _new_spec(records, run_id, f"{feature}:{form}:{test_name}", "unit_root", train)
                row = {
                    "feature": feature, "form": form, "test": test_name, "n": len(series),
                    "statistic": None, "p_value": None, "p_value_holm": None,
                    "p_value_adjusted": None, "p_value_family": "diagnostics (raw; no adjustment)", "lags": None,
                    "lag_method": "AIC" if test_name == "ADF" else "auto",
                    "max_lag": ADF_MAX_LAG if test_name == "ADF" else None,
                    "interpretation": "",
                }
                try:
                    if len(series) < 25 or series.nunique() < 2:
                        raise ValueError("Insufficient nonconstant observations")
                    with warnings.catch_warnings(record=True) as caught:
                        warnings.simplefilter("always")
                        if test_name == "ADF":
                            result = adfuller(series.to_numpy(), maxlag=ADF_MAX_LAG, autolag="AIC", regression="c", result_object=False)
                            statistic, p_value, used_lags = float(result[0]), float(result[1]), int(result[2])
                            interpretation = "unit root rejected at 5%" if p_value < ALPHA else "unit root not rejected at 5%"
                        else:
                            statistic, p_value, used_lags, _ = kpss(series.to_numpy(), regression="c", nlags="auto", result_object=False)
                            statistic, p_value, used_lags = float(statistic), float(p_value), int(used_lags)
                            interpretation = "stationarity rejected at 5%" if p_value < ALPHA else "stationarity not rejected at 5%"
                    row.update({"statistic": statistic, "p_value": p_value, "lags": used_lags, "interpretation": interpretation, "warning": "; ".join(str(w.message) for w in caught)})
                    _finish_spec(records, idx, status="COMPLETED", statistic=statistic, p_value=p_value, message=row["warning"])
                except Exception as exc:
                    row.update({"interpretation": "NOT APPLICABLE / FAILED: " + str(exc), "warning": ""})
                    _finish_spec(records, idx, status="FAILED", message=exc)
                rows.append(row)
    return rows


def _trend_break_lr(values: pd.Series, dates: pd.Series, year: int):
    """LR test for an intercept and linear-trend break at a fixed calendar year."""
    frame = pd.DataFrame({"value": values.reset_index(drop=True), "date": pd.to_datetime(dates).reset_index(drop=True)}).dropna().sort_values("date")
    split_date = pd.Timestamp(year=year, month=1, day=1)
    pre = int((frame.date < split_date).sum())
    post = int((frame.date >= split_date).sum())
    if min(pre, post) < 8:
        raise ValueError(f"fewer than 8 observations on one side of {year}")
    t = (frame.date - frame.date.min()).dt.days.to_numpy(dtype=float) / 365.25
    after = (frame.date >= split_date).to_numpy(dtype=float)
    restricted = np.column_stack([np.ones(len(frame)), t])
    unrestricted = np.column_stack([np.ones(len(frame)), t, after, t * after])
    y = frame.value.to_numpy(dtype=float)
    rss0 = np.sum((y - restricted @ np.linalg.lstsq(restricted, y, rcond=None)[0]) ** 2)
    rss1 = np.sum((y - unrestricted @ np.linalg.lstsq(unrestricted, y, rcond=None)[0]) ** 2)
    if rss0 <= 0 or rss1 <= 0:
        raise ValueError("nonpositive residual sum of squares")
    n = len(frame)
    ll0 = -0.5 * n * (math.log(2 * math.pi) + 1 + math.log(rss0 / n))
    ll1 = -0.5 * n * (math.log(2 * math.pi) + 1 + math.log(rss1 / n))
    statistic = max(0.0, float(2 * (ll1 - ll0)))
    return statistic, float(chi2.sf(statistic, 2)), pre, post


def _run_break_tests(train: pd.DataFrame, raw_panel: pd.DataFrame,
                     records: list[dict[str, Any]], run_id: str) -> list[dict[str, Any]]:
    """Run split-sample LR checks at 2015, 2020, and 2022 on both factor forms."""
    raw_train = raw_panel[raw_panel.decision_date.isin(train.decision_date)].reset_index(drop=True)
    rows = []
    for feature in FEATURES:
        for form, frame in (("transformed_model_input", train), ("raw_level", raw_train)):
            for year in (2015, 2020, 2022):
                idx = _new_spec(records, run_id, f"{feature}:{form}:break_{year}", "break_lr", frame)
                row = {"feature": feature, "form": form, "break_year": year, "method": "Gaussian linear-trend split-sample LR; intercept and trend shift", "n_pre": None, "n_post": None, "statistic": None, "df": 2, "p_value": None, "p_value_holm": None, "p_value_adjusted": None, "p_value_family": "diagnostics (raw; no adjustment)", "status": ""}
                try:
                    statistic, p_value, n_pre, n_post = _trend_break_lr(frame[feature], frame.decision_date, year)
                    row.update({"n_pre": n_pre, "n_post": n_post, "statistic": statistic, "p_value": p_value, "status": "COMPLETED"})
                    _finish_spec(records, idx, status="COMPLETED", statistic=statistic, df=2, p_value=p_value)
                except Exception as exc:
                    row.update({"status": "NOT APPLICABLE", "reason": str(exc)})
                    _finish_spec(records, idx, status="NOT APPLICABLE", message=exc)
                rows.append(row)
    return rows


def _vif_table(train: pd.DataFrame) -> list[dict[str, Any]]:
    """Calculate VIF; it is descriptive and has no inferential p-value."""
    design = add_constant(train[FEATURES].astype(float), has_constant="add").to_numpy()
    rows = []
    for column, feature in enumerate(FEATURES, start=1):
        try:
            value = float(variance_inflation_factor(design, column))
        except Exception:
            value = float("inf")
        rows.append({"feature": feature, "statistic": _number(value), "p_value": "not applicable (descriptive VIF)", "pass_fail": "PASS" if np.isfinite(value) and value < 5 else "FAIL", "threshold": "VIF < 5"})
    return rows


def _brant_type_wald(train: pd.DataFrame, records: list[dict[str, Any]], run_id: str):
    """Test equal slopes in the two cumulative logits using joint sandwich Wald."""
    y = train.y.to_numpy(dtype=int)
    x = train[FEATURES].astype(float).to_numpy()
    design = np.column_stack([np.ones(len(x)), x])
    equations = [((y > -1).astype(float), "P(Y>-1)"), ((y > 0).astype(float), "P(Y>0)")]
    estimates, scores, breads = [], [], []
    for binary, name in equations:
        idx = _new_spec(records, run_id, "Brant component " + name, "proportional_odds_component", train)
        try:
            fitted = sm.Logit(binary, design).fit(disp=False, maxiter=1000)
            probability = np.asarray(fitted.predict(design), dtype=float)
            score_rows = design * (binary - probability)[:, None]
            information = design.T @ (design * (probability * (1 - probability))[:, None])
            estimates.append(np.asarray(fitted.params, dtype=float))
            scores.append(score_rows)
            breads.append(np.linalg.pinv(information, hermitian=True))
            _finish_spec(records, idx, status="COMPLETED", log_likelihood=float(fitted.llf))
        except Exception as exc:
            _finish_spec(records, idx, status="FAILED", message=exc)
            raise
    p = design.shape[1]
    bread = np.zeros((2 * p, 2 * p))
    bread[:p, :p], bread[p:, p:] = breads
    stacked = np.column_stack(scores)
    covariance = bread @ stacked.T @ stacked @ bread
    covariance = (covariance + covariance.T) / 2
    contrast = np.zeros((len(FEATURES), 2 * p))
    contrast[:, 1:p] = np.eye(len(FEATURES))
    contrast[:, p + 1:] = -np.eye(len(FEATURES))
    difference = contrast @ np.concatenate(estimates)
    difference_cov = contrast @ covariance @ contrast.T
    statistic = float(difference @ np.linalg.pinv(difference_cov, hermitian=True) @ difference)
    p_value = float(chi2.sf(statistic, len(FEATURES)))
    return {"name": "Brant-type robust Wald equality of cumulative-logit slopes", "statistic": statistic, "df": len(FEATURES), "p_value": p_value, "pass_fail": "PASS" if p_value >= ALPHA else "FAIL", "interpretation": "fail to reject proportional odds" if p_value >= ALPHA else "evidence against proportional odds"}


def _expanding_coefficient_rows(train: pd.DataFrame, records: list[dict[str, Any]], run_id: str):
    """Estimate fixed ordered-logit design on expanding prefixes of training rows."""
    rows = []
    sizes = sorted(set(max(20, int(math.floor(len(train) * share))) for share in (0.60, 0.80, 1.0)))
    for size in sizes:
        window = train.iloc[:size].copy()
        idx = _new_spec(records, run_id, f"expanding ordered logit n={size}", "expanding_window_fit", window)
        try:
            _, fitted, covariance = _fit_ordered(window)
            params = np.asarray(fitted.params, dtype=float)
            se = np.sqrt(np.maximum(np.diag(covariance)[:len(FEATURES)], 0))
            for feature, estimate, std_error in zip(FEATURES, params[:len(FEATURES)], se):
                rows.append({"sample_n": size, "sample_start": window.decision_date.min().date().isoformat(), "sample_end": window.decision_date.max().date().isoformat(), "feature": feature, "coefficient": float(estimate), "hc0_se": float(std_error), "status": "COMPLETED"})
            _finish_spec(records, idx, status="COMPLETED" if fitted.mle_retvals.get("converged", False) else "NONCONVERGED", log_likelihood=float(fitted.llf), message=str(fitted.mle_retvals))
        except Exception as exc:
            for feature in FEATURES:
                rows.append({"sample_n": size, "sample_start": window.decision_date.min().date().isoformat(), "sample_end": window.decision_date.max().date().isoformat(), "feature": feature, "coefficient": None, "hc0_se": None, "status": "FAILED: " + str(exc)})
            _finish_spec(records, idx, status="FAILED", message=exc)
    return rows


def _economic_size(model: OrderedModel, params: np.ndarray, covariance: np.ndarray, train: pd.DataFrame):
    """Compute +1 SD probability changes and finite-difference delta intervals."""
    means = train[FEATURES].mean()
    stds = train[FEATURES].std(ddof=1)
    baseline = pd.DataFrame([{feature: float(means[feature]) for feature in FEATURES}])
    rows = []
    for feature in FEATURES:
        shifted = baseline.copy()
        sd = float(stds[feature])
        shifted.loc[0, feature] += sd
        base_probability = _predict_probabilities(model, params, baseline)[0]
        shifted_probability = _predict_probabilities(model, params, shifted)[0]
        changes = {}
        for class_index, label in ((2, "Increase"), (0, "Decrease")):
            estimate = float(shifted_probability[class_index] - base_probability[class_index])
            gradient = np.zeros(len(params))
            for j, parameter in enumerate(params):
                step = 1e-5 * max(1.0, abs(float(parameter)))
                upper, lower = params.copy(), params.copy()
                upper[j] += step
                lower[j] -= step
                delta_upper = (_predict_probabilities(model, upper, shifted)[0, class_index]
                               - _predict_probabilities(model, upper, baseline)[0, class_index])
                delta_lower = (_predict_probabilities(model, lower, shifted)[0, class_index]
                               - _predict_probabilities(model, lower, baseline)[0, class_index])
                gradient[j] = (delta_upper - delta_lower) / (2 * step)
            variance = float(gradient @ covariance @ gradient)
            std_error = math.sqrt(max(0.0, variance))
            changes[label] = {
                "change": estimate,
                "ci_95_low": estimate - 1.96 * std_error,
                "ci_95_high": estimate + 1.96 * std_error,
                "delta_method_se": std_error,
            }
        rows.append({"feature": feature, "move": "+1 estimation-sample SD, other factors at their means", "sd": sd, "probability_change": changes})
    return rows


def _latest_contributions(model: OrderedModel, params: np.ndarray, panel: pd.DataFrame):
    """Decompose the latest expected-score change with one-factor counterfactuals."""
    if len(panel) < 2:
        return []
    latest = panel.iloc[[-1]].copy()
    previous = panel.iloc[-2]
    latest_probabilities = _predict_probabilities(model, params, latest)[0]
    latest_score = float(latest_probabilities[2] - latest_probabilities[0])
    rows = []
    for feature in FEATURES:
        counterfactual = latest.copy()
        counterfactual.loc[counterfactual.index[0], feature] = float(previous[feature])
        p = _predict_probabilities(model, params, counterfactual)[0]
        counterfactual_score = float(p[2] - p[0])
        rows.append({
            "feature": feature,
            "latest_value": float(latest.iloc[0][feature]),
            "previous_usable_decision_value": float(previous[feature]),
            "expected_score_contribution_to_latest_change": latest_score - counterfactual_score,
            "method": "latest expected score minus one-factor counterfactual reset to prior usable decision; contributions are not additive",
        })
    return rows


def _markdown_table(frame: pd.DataFrame) -> list[str]:
    """Render a DataFrame as a Markdown table without an extra dependency."""
    if frame.empty:
        return ["No rows."]
    headers = [str(column) for column in frame.columns]
    values = frame.fillna("not available").astype(str).values.tolist()
    escape = lambda value: value.replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(escape(value) for value in headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    lines.extend("| " + " | ".join(escape(value) for value in row) + " |" for row in values)
    return lines


def _write_diagnostics_markdown(path: Path, sample: dict[str, Any], tables: dict[str, pd.DataFrame]):
    """Write the full diagnostics annex from generated tables."""
    roots = tables.get("Unit-root tests on training sample", pd.DataFrame())
    rejected_both = []
    rejected_neither = []
    both_nonstationary = []
    both_stationary = []
    if not roots.empty:
        transformed = roots[roots.get("form", pd.Series(dtype=str)) == "transformed_model_input"]
        for feature, group in transformed.groupby("feature"):
            adf = group[group["test"] == "ADF"]
            kpss_result = group[group["test"] == "KPSS"]
            if len(adf) and len(kpss_result):
                adf_rejects_unit_root = float(adf.iloc[0]["p_value"]) < ALPHA
                kpss_rejects_stationarity = float(kpss_result.iloc[0]["p_value"]) < ALPHA
                if adf_rejects_unit_root and kpss_rejects_stationarity:
                    rejected_both.append(str(feature))
                elif not adf_rejects_unit_root and not kpss_rejects_stationarity:
                    rejected_neither.append(str(feature))
                elif not adf_rejects_unit_root and kpss_rejects_stationarity:
                    both_nonstationary.append(str(feature))
                else:
                    both_stationary.append(str(feature))
    list_text = lambda items: ", ".join(items) if items else "none"
    lines = [
        "# Ordered-logit model diagnostics annex", "",
        f"Generated at {sample['estimation_timestamp_utc']} UTC. No holdout outcomes were used for fitting or selection.", "",
        "## Sample and chronology", "",
        f"Usable observations: {sample['usable_n']}; dropped: {sample['dropped_n']}; estimation: {sample['estimation_n']}; holdout: {sample['holdout_n']}.",
        f"Estimation: {sample['estimation_start']} to {sample['estimation_end']}; holdout: {sample['holdout_start']} to {sample['holdout_end']}.",
        f"Dropped decision dates: {', '.join(sample['dropped_decisions']) or 'none'}.",
        "The recent holdout overlaps the prior exploratory 24-month backtest and is not a fresh untouched holdout.", "",
        "## P-value families and multiplicity", "",
        f"Holm adjustment is limited to the six slope-coefficient p-values. The pre-specified joint LR test is a single primary test with no adjustment. Diagnostics use raw p-values with no adjustment and 5% flags. Additional robustness specifications estimated: {sample.get('robustness_specification_count', 0)}; coefficient p-values are Holm-adjusted within each specification. Each reported inferential p-value includes raw and adjusted values and its family name.", "",
    ]
    for title, frame in tables.items():
        lines.extend([f"## {title}", ""])
        lines.extend(_markdown_table(frame))
        lines.append("")
    lines.extend([
        "## Limitations of the unit-root tests", "",
        f"Unit-root tests use decision-date observations, not a monthly series. Decision dates are irregularly spaced, and the full transformed panel contains {sample['usable_n']} usable observations (the reported tests use the {sample['estimation_n']}-row estimation sample). The small sample limits test power. At the 5% raw-p-value threshold, both ADF's unit-root null and KPSS's stationarity null are rejected for: {list_text(rejected_both)} (opposed evidence); neither null is rejected for: {list_text(rejected_neither)} (mixed/inconclusive ADF/KPSS results); both tests point against stationarity for: {list_text(both_nonstationary)}; both support stationarity for: {list_text(both_stationary)}. Thus the mixed/inconclusive factors are {list_text(rejected_neither)}. These checks are diagnostics only and do not use monthly tests.", "",
        "The assumption that all regressors are I(0) is not supported for household lending: ADF does not reject a unit root and KPSS rejects stationarity. The evidence is ambiguous for inflation and corporate lending, where neither test rejects its null of unit root or stationarity, respectively.", "",
    ])
    lines.extend([
        "## Interpretation limits", "",
        "Decision-month-minus-two is an assumed alignment, not a verified release lag. Actual source publication lags remain UNKNOWN. HC0 is a score-based sandwich covariance. VIF is descriptive. Conventional OLS heteroskedasticity and residual-normality tests are not applicable to this ordinal likelihood model. The score RMSE ratio below one favors ordered logit; a ratio at or above one means Always Hold wins or ties. The deterministic Always Hold log score is infinite if any non-Hold class occurs.", "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def _write_spec_log(path: Path, records: list[dict[str, Any]], append: bool) -> None:
    """Write every successful and failed model/test attempt to a CSV log."""
    path.parent.mkdir(parents=True, exist_ok=True)
    current = pd.DataFrame(records)
    if "p_value_family" not in current:
        current["p_value_family"] = None
    if "p_value_adjusted" not in current:
        current["p_value_adjusted"] = None
    if append and path.exists():
        previous = pd.read_csv(path)
        current = pd.concat([previous, current], ignore_index=True)
    # Reconcile earlier rows in the persistent log to the same explicit families.
    for column in ("p_value", "p_value_holm", "p_value_adjusted", "p_value_family"):
        if column not in current:
            current[column] = np.nan
    for _, indices in current.groupby("run_id", dropna=False).groups.items():
        slope_indices = [i for i in indices
                         if current.at[i, "kind"] == "coefficient_test"
                         and current.at[i, "name"] in {"parameter:" + feature for feature in FEATURES}
                         and _p_value(current.at[i, "p_value"]) is not None]
        if slope_indices:
            values = [float(current.at[i, "p_value"]) for i in slope_indices]
            adjusted = multipletests(values, method="holm")[1]
            for i, value in zip(slope_indices, adjusted):
                current.at[i, "p_value_adjusted"] = float(value)
                current.at[i, "p_value_holm"] = float(value)
                current.at[i, "p_value_family"] = "six slope-coefficient p-values (Holm across six)"
        robustness_indices = [i for i in indices
                              if current.at[i, "kind"] == "robustness_coefficient"
                              and _p_value(current.at[i, "p_value"]) is not None]
        if robustness_indices:
            for specification_id in current.loc[robustness_indices, "specification_id"].dropna().unique():
                spec_indices = [i for i in robustness_indices
                                if current.at[i, "specification_id"] == specification_id]
                adjusted = multipletests([float(current.at[i, "p_value"]) for i in spec_indices], method="holm")[1]
                for i, value in zip(spec_indices, adjusted):
                    current.at[i, "p_value_adjusted"] = float(value)
                    current.at[i, "p_value_holm"] = float(value)
                    current.at[i, "p_value_family"] = f"robustness specification {specification_id} coefficient p-values (Holm within specification)"
        for i in indices:
            if (_p_value(current.at[i, "p_value"]) is None or i in slope_indices
                    or current.at[i, "kind"] == "robustness_coefficient"):
                continue
            kind = current.at[i, "kind"]
            if kind == "joint_slope_lr":
                family = "pre-specified joint LR test (single primary test; no adjustment)"
            elif kind == "coefficient_test":
                family = "cutpoint coefficient tests (unadjusted; outside six-slope family)"
            else:
                family = "diagnostics (raw p-values; no adjustment; flag at 5%)"
            current.at[i, "p_value_adjusted"] = float(current.at[i, "p_value"])
            current.at[i, "p_value_holm"] = float(current.at[i, "p_value"])
            current.at[i, "p_value_family"] = family
    current.to_csv(path, index=False)


def run_pipeline(
    output_dir: Path | str = OUTPUTS,
    artifact_path: Path | str = ARTIFACT_PATH,
    model_panel_path: Path | str = MODEL_PANEL_PATH,
    source_panel_path: Path | str = DATA_PATH,
    raw_dir: Path | str = RAW_DIR,
    append_spec_log: bool = False,
) -> dict[str, Any]:
    """Build the model panel, fit the fixed specification, evaluate, and save artifacts."""
    output_dir, artifact_path = Path(output_dir), Path(artifact_path)
    model_panel_path, source_panel_path, raw_dir = Path(model_panel_path), Path(source_panel_path), Path(raw_dir)
    if not source_panel_path.is_file():
        raise FileNotFoundError(source_panel_path)
    source_hash = normalized_sha256(source_panel_path)
    full_panel = build_model_panel(panel_path=source_panel_path, raw_dir=raw_dir, output_path=model_panel_path)
    usable = full_panel.dropna(subset=FEATURES + ["y"]).copy().reset_index(drop=True)
    usable["decision_date"] = pd.to_datetime(usable.decision_date, errors="raise")
    if len(usable) < 40:
        raise SpecificationError(f"Only {len(usable)} usable observations remain; at least 40 are required")
    if usable.decision_date.duplicated().any() or not usable.decision_date.is_monotonic_increasing:
        raise SpecificationError("Usable decisions must be unique and chronologically ordered")

    holdout_n = int(math.ceil(HOLDOUT_SHARE * len(usable)))
    estimation_n = len(usable) - holdout_n
    train, holdout = usable.iloc[:estimation_n].copy().reset_index(drop=True), usable.iloc[estimation_n:].copy().reset_index(drop=True)
    if not train.decision_date.max() < holdout.decision_date.min():
        raise SpecificationError("Estimation and holdout dates overlap")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    records: list[dict[str, Any]] = []
    fit_id = _new_spec(records, run_id, "Ordered logit, six specified factors", "primary_model", train)
    try:
        model, fitted, robust_cov = _fit_ordered(train, SEED)
        _finish_spec(records, fit_id, status="COMPLETED" if fitted.mle_retvals.get("converged", False) else "NONCONVERGED",
                     log_likelihood=float(fitted.llf), message=f"optimizer=bfgs; converged={fitted.mle_retvals.get('converged')}; warnflag={fitted.mle_retvals.get('warnflag')}")
    except Exception as exc:
        _finish_spec(records, fit_id, status="FAILED", message=exc)
        _write_spec_log(output_dir / "spec_log.csv", records, append_spec_log)
        raise

    params = np.asarray(fitted.params, dtype=float)
    parameter_names, parameter_estimates, named_cov = _named_parameter_covariance(model, params, robust_cov)
    parameter_se = np.sqrt(np.maximum(np.diag(named_cov), 0))
    parameter_rows = []
    for name, estimate, std_error in zip(parameter_names, parameter_estimates, parameter_se):
        z = float(estimate / std_error) if std_error > 0 else None
        p_value = float(2 * norm.sf(abs(z))) if z is not None else None
        idx = _new_spec(records, run_id, "parameter:" + name, "coefficient_test", train)
        _finish_spec(records, idx, status="COMPLETED", statistic=z, p_value=p_value, message="HC0 robust Wald z")
        parameter_rows.append({"name": name, "estimate": float(estimate), "hc0_se": float(std_error), "z_statistic": z, "p_value": p_value, "p_value_holm": None})

    counts = train.decision.value_counts().reindex(CLASS_ORDER, fill_value=0)
    null_log_likelihood = float(sum(n * math.log(n / len(train)) for n in counts if n > 0))
    joint_lr = max(0.0, float(2 * (fitted.llf - null_log_likelihood)))
    joint_p = float(chi2.sf(joint_lr, len(FEATURES)))
    joint_id = _new_spec(records, run_id, "Joint LR test: all six slopes = 0", "joint_slope_lr", train)
    _finish_spec(records, joint_id, status="COMPLETED", statistic=joint_lr, df=len(FEATURES), p_value=joint_p,
                 log_likelihood=float(fitted.llf), message=f"intercept-only ordered-logit null log-likelihood={null_log_likelihood:.12g}")

    raw_panel = _build_raw_level_panel(full_panel, raw_dir)
    root_rows = _run_unit_root_tests(train, raw_panel, records, run_id)
    break_rows = _run_break_tests(train, raw_panel, records, run_id)
    vif_rows = _vif_table(train)

    proportional_id = _new_spec(records, run_id, "Brant-type proportional-odds equality test", "proportional_odds_test", train)
    try:
        proportional = _brant_type_wald(train, records, run_id)
        _finish_spec(records, proportional_id, status="COMPLETED", statistic=proportional["statistic"], df=proportional["df"], p_value=proportional["p_value"], message=proportional["interpretation"])
    except Exception as exc:
        proportional = {"name": "Brant-type cumulative-logit slope equality", "statistic": "not applicable", "df": len(FEATURES), "p_value": "not applicable", "pass_fail": "NOT APPLICABLE", "reason": str(exc)}
        _finish_spec(records, proportional_id, status="FAILED", message=exc)

    # Stability interaction is fixed at the documented calendar split and uses estimation rows only.
    stable_fit_id = _new_spec(records, run_id, "LR stability unrestricted ordered logit, BFGS attempt", "optimizer_attempt", train)
    stable_test_id = _new_spec(records, run_id, "LR test of slopes equal: 2015-2019 vs 2020+", "parameter_stability_lr", train)
    post = (train.decision_date.dt.year >= 2020).astype(float).to_numpy()
    expanded = train[FEATURES].astype(float).copy()
    for feature in FEATURES:
        expanded[feature + ":post2020"] = expanded[feature].to_numpy() * post
    try:
        endog = pd.Categorical(train.y.astype(int), categories=[-1, 0, 1], ordered=True)
        stability_model = OrderedModel(endog, expanded, distr="logit")
        start = np.r_[params[:len(FEATURES)], np.zeros(len(FEATURES)), params[len(FEATURES):]]
        stability_fit = stability_model.fit(start_params=start, method="bfgs", maxiter=2000, disp=False, gtol=1e-8)
        _finish_spec(records, stable_fit_id, status="COMPLETED" if stability_fit.mle_retvals.get("converged", False) else "NONCONVERGED",
                     log_likelihood=float(stability_fit.llf), message=f"optimizer=bfgs; converged={stability_fit.mle_retvals.get('converged')}; warnflag={stability_fit.mle_retvals.get('warnflag')}")
        if not stability_fit.mle_retvals.get("converged", False):
            retry_id = _new_spec(records, run_id, "LR stability unrestricted model retry with L-BFGS", "parameter_stability_optimizer_retry", train)
            stability_fit = stability_model.fit(start_params=np.asarray(stability_fit.params), method="lbfgs", maxiter=4000, disp=False, pgtol=1e-8)
            _finish_spec(records, retry_id, status="COMPLETED" if stability_fit.mle_retvals.get("converged", False) else "NONCONVERGED",
                         log_likelihood=float(stability_fit.llf), message=f"optimizer=lbfgs; converged={stability_fit.mle_retvals.get('converged')}; warnflag={stability_fit.mle_retvals.get('warnflag')}")
            if not stability_fit.mle_retvals.get("converged", False):
                raise RuntimeError("Both BFGS and L-BFGS failed to converge for the stability interaction model")
        stability_lr = max(0.0, float(2 * (stability_fit.llf - fitted.llf)))
        stability_p = float(chi2.sf(stability_lr, len(FEATURES)))
        stability = {"name": "LR test of slope equality across 2015-2019 and 2020+", "statistic": stability_lr, "df": len(FEATURES), "p_value": stability_p, "pass_fail": "PASS" if stability_p >= ALPHA else "FAIL", "groups_n": {"2015-2019": int((post == 0).sum()), "2020+": int((post == 1).sum())}, "unrestricted_log_likelihood": float(stability_fit.llf)}
        _finish_spec(records, stable_test_id, status="COMPLETED",
                     statistic=stability_lr, df=len(FEATURES), p_value=stability_p, log_likelihood=float(stability_fit.llf), message=f"optimizer=lbfgs after BFGS nonconvergence; converged={stability_fit.mle_retvals.get('converged')}")
    except Exception as exc:
        if records[stable_fit_id]["status"] == "RUNNING":
            _finish_spec(records, stable_fit_id, status="FAILED", message=exc)
        _finish_spec(records, stable_test_id, status="FAILED", message=exc)
        stability = {"name": "LR test of slope equality across 2015-2019 and 2020+", "statistic": "not applicable", "df": len(FEATURES), "p_value": "not applicable", "pass_fail": "NOT APPLICABLE", "groups_n": {"2015-2019": int((post == 0).sum()), "2020+": int((post == 1).sum())}, "reason": str(exc)}
    expanding_rows = _expanding_coefficient_rows(train, records, run_id)

    probabilities = _predict_probabilities(model, params, holdout)
    actual = holdout.y.to_numpy(dtype=int)
    expected_score = probabilities[:, 2] - probabilities[:, 0]
    model_metrics = _score_metrics(expected_score, actual)
    hold_metrics = _score_metrics(np.zeros(len(actual)), actual)
    ratio = model_metrics["rmse"] / hold_metrics["rmse"] if hold_metrics["rmse"] > 0 else None
    model_log_score = _log_score(probabilities, actual)
    baseline_probabilities = np.zeros_like(probabilities)
    baseline_probabilities[:, 1] = 1
    baseline_log_score = _log_score(baseline_probabilities, actual)
    training_class_counts = train.decision.value_counts().reindex(CLASS_ORDER, fill_value=0)
    class_frequency_probabilities = (training_class_counts / len(train)).to_numpy(dtype=float)
    frequency_probabilities = np.tile(class_frequency_probabilities, (len(actual), 1))
    class_frequency_log_score = _log_score(frequency_probabilities, actual)
    winner = "Ordered Logit" if ratio is not None and ratio < 1 else "Always Hold" if ratio is not None else "UNDETERMINED: benchmark RMSE is zero"
    comparison = {
        "metric_target": "expected ordinal score: Decrease=-1, Hold=0, Increase=+1",
        "model": {**model_metrics, "log_score": model_log_score},
        "benchmark_always_hold": {**hold_metrics, "log_score": baseline_log_score},
        "class_frequency_comparator_secondary": {
            "label": "added after the specification freeze, secondary",
            "source_sample": "estimation sample only",
            "class_order": CLASS_ORDER,
            "training_class_counts": {str(k): int(v) for k, v in training_class_counts.items()},
            "probabilities": {str(k): float(v) for k, v in zip(CLASS_ORDER, class_frequency_probabilities)},
            "log_score": class_frequency_log_score,
        },
        "rmse_ratio_model_to_hold": ratio,
        "winner": winner,
        "model_class_probabilities_order": CLASS_ORDER,
        "holdout_n": len(holdout),
        "actual_score_distribution": {str(k): int(v) for k, v in holdout.y.value_counts().sort_index().items()},
    }
    robustness_checks = _run_robustness_checks(
        usable, raw_dir, parameter_rows, winner, records, run_id
    )
    total_specifications = 1 + len(robustness_checks)

    # Ljung-Box is applied to standardized Pearson residuals on estimation rows.
    train_probabilities = _predict_probabilities(model, params, train)
    score_values = np.array([-1.0, 0.0, 1.0])
    mean_score = train_probabilities @ score_values
    variance_score = train_probabilities @ (score_values ** 2) - mean_score ** 2
    residuals = (train.y.to_numpy(dtype=float) - mean_score) / np.sqrt(np.maximum(variance_score, 1e-12))
    ljung_lag = min(10, max(1, len(residuals) // 5))
    lb_id = _new_spec(records, run_id, f"Ljung-Box Pearson score residual lag {ljung_lag}", "serial_correlation", train)
    try:
        lb = acorr_ljungbox(residuals, lags=[ljung_lag], return_df=True)
        lb_stat, lb_p = float(lb.lb_stat.iloc[0]), float(lb.lb_pvalue.iloc[0])
        serial = {"name": "Ljung-Box on standardized Pearson score residuals", "statistic": lb_stat, "df": ljung_lag, "p_value": lb_p, "lag": ljung_lag, "pass_fail": "PASS" if lb_p >= ALPHA else "FAIL", "residual_definition": "(observed score - expected score) / sqrt(model score variance)"}
        _finish_spec(records, lb_id, status="COMPLETED", statistic=lb_stat, df=ljung_lag, p_value=lb_p)
    except Exception as exc:
        serial = {"name": "Ljung-Box on Pearson score residuals", "statistic": "not applicable", "df": ljung_lag, "p_value": "not applicable", "pass_fail": "NOT APPLICABLE", "reason": str(exc)}
        _finish_spec(records, lb_id, status="FAILED", message=exc)

    _assign_p_value_families(records)
    def p_record(name: str):
        found = [row for row in records if row["name"] == name]
        return found[-1] if found else {}
    for row in parameter_rows:
        rec = p_record("parameter:" + row["name"])
        row["p_value_family"] = rec.get("p_value_family")
        row["p_value_adjusted"] = rec.get("p_value_adjusted")
        row["p_value_holm"] = rec.get("p_value_holm")
    for check in robustness_checks:
        for coefficient in check.get("coefficients", []):
            row_index = coefficient.pop("_record_index", None)
            if row_index is not None:
                rec = records[row_index]
                coefficient["p_value_family"] = rec.get("p_value_family")
                coefficient["p_value_adjusted"] = rec.get("p_value_adjusted")
            adjusted_p = coefficient.get("p_value_adjusted")
            coefficient["significant_at_5pct_adjusted"] = (
                bool(adjusted_p < ALPHA) if isinstance(adjusted_p, (int, float)) else None
            )
    for rows, kind in ((root_rows, "unit_root"), (break_rows, "break_lr")):
        candidates = [row for row in records if row["kind"] == kind]
        for row, record in zip(rows, candidates):
            row["p_value_holm"] = record["p_value_holm"]
            row["p_value_adjusted"] = record["p_value_adjusted"]
            row["p_value_family"] = record["p_value_family"]
            if kind == "break_lr":
                row["pass_fail"] = ("PASS" if row["p_value"] is not None and row["p_value"] >= ALPHA else "FAIL") if row["status"] == "COMPLETED" else "NOT APPLICABLE"
            else:
                if row["p_value"] is None:
                    row["pass_fail"] = "NOT APPLICABLE"
                elif row["test"] == "ADF":
                    row["pass_fail"] = "PASS" if row["p_value"] < ALPHA else "FAIL"
                else:
                    row["pass_fail"] = "PASS" if row["p_value"] >= ALPHA else "FAIL"
    for diagnostic, name in ((proportional, "Brant-type proportional-odds equality test"),
                             (stability, "LR test of slopes equal: 2015-2019 vs 2020+"),
                             (serial, f"Ljung-Box Pearson score residual lag {ljung_lag}")):
        rec = p_record(name)
        diagnostic["p_value_family"] = rec.get("p_value_family", "diagnostics (raw; no adjustment)")
        diagnostic["p_value_adjusted"] = rec.get("p_value_adjusted", diagnostic.get("p_value"))
        diagnostic["p_value_holm"] = rec.get("p_value_holm", diagnostic.get("p_value"))
        if isinstance(diagnostic.get("p_value"), (int, float)):
            diagnostic["pass_fail"] = "PASS" if diagnostic["p_value"] >= ALPHA else "FAIL"
    joint_rec = p_record("Joint LR test: all six slopes = 0")
    joint_p_adjusted = joint_rec.get("p_value_adjusted", joint_p)
    joint_diag = {"name": "Joint LR test of all six slopes", "statistic": joint_lr, "df": len(FEATURES), "p_value": joint_p, "p_value_holm": joint_p_adjusted, "p_value_adjusted": joint_p_adjusted, "p_value_family": joint_rec.get("p_value_family"), "pass_fail": "PASS" if joint_p < 0.10 else "FAIL", "criterion": "reject zero-joint-slope null at 10% using raw p-value"}
    sign_failures = [row["name"] for row in parameter_rows if row["name"] in FEATURES and row["estimate"] < 0 and row["p_value"] < ALPHA]
    sign_diag = {"name": "Expected-sign check", "statistic": len(sign_failures), "p_value": "not applicable (joint sign diagnostic)", "p_value_holm": "not applicable", "p_value_adjusted": "not applicable", "p_value_family": "six slope-coefficient p-values (Holm across six)", "pass_fail": "FAIL" if sign_failures else "PASS", "opposite_sign_significant_features": sign_failures, "expected_signs": {feature: "+" for feature in FEATURES}, "rule": "fail if coefficient is negative and raw p < 0.05; adjusted p shown for transparency"}
    not_applicable = [
        {"name": "Conventional OLS heteroskedasticity test", "statistic": "not applicable", "p_value": "not applicable", "pass_fail": "NOT APPLICABLE", "reason": "the dependent variable is ordinal/discrete, so OLS residual variance assumptions do not apply; HC0 sandwich covariance is used"},
        {"name": "Residual normality test", "statistic": "not applicable", "p_value": "not applicable", "pass_fail": "NOT APPLICABLE", "reason": "ordered logit has no normal observed-residual assumption; its latent link distribution is logistic"},
    ]
    diagnostics = {
        "vif": vif_rows,
        "parameter_stability": stability,
        "expanding_window_coefficients": expanding_rows,
        "proportional_odds": proportional,
        "serial_correlation": serial,
        "joint_slope_lr": joint_diag,
        "expected_sign_check": sign_diag,
        "not_applicable_tests": not_applicable,
        "estimation_converged": bool(fitted.mle_retvals.get("converged", False)),
        "estimation_convergence_details": _scalar(fitted.mle_retvals),
        "covariance_type": "HC0 score-based sandwich",
        "p_value_families": {
            "slope_coefficients": "Holm adjustment across the six slope-coefficient p-values only",
            "joint_slope_lr": "single pre-specified primary test; no adjustment",
            "diagnostics": "raw p-values, no adjustment, flagged at 5%",
            "robustness_specifications": "report specification count; Holm-adjust coefficient p-values only within each specification",
            "robustness_specification_count": len(robustness_checks),
            "total_specifications_including_primary": total_specifications,
            "cutpoints": "reported raw, not included in the six-slope inferential family",
        },
    }

    named_cov = (named_cov + named_cov.T) / 2
    probabilities_latest = _predict_probabilities(model, params, usable.iloc[[-1]])[0]
    latest_vector = {feature: float(usable.iloc[-1][feature]) for feature in FEATURES}
    economic_rows = _economic_size(model, params, robust_cov, train)
    contributions = _latest_contributions(model, params, usable)
    usable_dates = set(usable.decision_date.dt.strftime("%Y-%m-%d"))
    dropped_dates = full_panel.loc[~full_panel.decision_date.astype(str).isin(usable_dates), "decision_date"].astype(str).tolist()
    sample = {
        "usable_n": len(usable), "dropped_n": len(full_panel) - len(usable), "estimation_n": len(train), "holdout_n": len(holdout),
        "usable_start": usable.decision_date.min().date().isoformat(), "usable_end": usable.decision_date.max().date().isoformat(),
        "estimation_start": train.decision_date.min().date().isoformat(), "estimation_end": train.decision_date.max().date().isoformat(),
        "holdout_start": holdout.decision_date.min().date().isoformat(), "holdout_end": holdout.decision_date.max().date().isoformat(),
        "dropped_decisions": dropped_dates,
        "estimation_rows": train.decision_date.dt.strftime("%Y-%m-%d").tolist(),
        "holdout_rows": holdout.decision_date.dt.strftime("%Y-%m-%d").tolist(),
    }
    package_versions = {}
    for package in ("numpy", "pandas", "scipy", "statsmodels"):
        try:
            package_versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            package_versions[package] = "UNKNOWN"
    units = {
        "inflation": "year-on-year rate per draft spec; exact definition and units UNKNOWN",
        "consumption": "year-on-year rate per draft spec; exact definition and units UNKNOWN",
        "exports": "12-month log change, percent; underlying source units UNKNOWN",
        "imports": "12-month log change, percent; underlying source units UNKNOWN",
        "corporate_lending": "12-month log change, percent; underlying source units UNKNOWN",
        "household_lending": "12-month log change, percent; underlying source units UNKNOWN",
    }
    parameter_records = {
        row["name"]: {
            "coefficient_or_cutpoint": row["estimate"],
            "hc0_standard_error": row["hc0_se"],
            "p_value": row["p_value"],
            "p_value_holm": row["p_value_holm"],
            "p_value_adjusted": row["p_value_adjusted"],
            "p_value_family": row["p_value_family"],
        }
        for row in parameter_rows
    }
    artifact = {
        "schema_version": 1,
        "model": {
            "name": "Ordered Logit",
            "link": "logit",
            "feature_names": FEATURES,
            "class_order": CLASS_ORDER,
            "score_map": SCORE_MAP,
            "parameters": {name: float(value) for name, value in zip(parameter_names, parameter_estimates)},
            "coefficient_table": parameter_records,
            "covariance_names": parameter_names,
            "covariance_hc0": named_cov.tolist(),
            "log_likelihood": float(fitted.llf),
            "pseudo_r2_mcfadden": float(1 - fitted.llf / null_log_likelihood),
            "cutpoints": {name: float(value) for name, value in zip(parameter_names[-2:], parameter_estimates[-2:])},
        },
        "sample": sample,
        "estimation_timestamp_utc": timestamp,
        "seed": SEED,
        "diagnostics": diagnostics,
        "benchmark_comparison": comparison,
        "robustness_checks": {
            "total_specifications_including_primary": total_specifications,
            "robustness_specification_count": len(robustness_checks),
            "selection_prohibited": True,
            "checks": robustness_checks,
        },
        "falsification_verdicts": _falsification_verdicts(
            joint_lr, joint_p, ratio, parameter_rows, joint_p_adjusted
        ),
        "economic_size_plus_one_sd": economic_rows,
        "per_factor_contribution_to_latest_score_change": contributions,
        "units": units,
        "latest_feature_vector": latest_vector,
        "latest_prediction": {
            "date": usable.decision_date.iloc[-1].date().isoformat(),
            "expected_score": float(probabilities_latest[2] - probabilities_latest[0]),
            "class_probabilities": {name: float(value) for name, value in zip(CLASS_ORDER, probabilities_latest)},
            "class_order": CLASS_ORDER,
        },
        "package_versions": package_versions,
        "data_sha256_normalized_crlf_to_lf": source_hash,
        "replication_tolerance": {"coefficients_absolute": 1e-6, "headline_score_absolute": 0.01, "headline_score_name": "holdout RMSE ratio"},
        "specification": {
            "source": "docs/model_spec.md",
            "transformation": "inflation and consumption levels; 12-month log growth on exports, imports, corporate lending, household lending; all aligned to decision month minus two (assumption)",
            "holdout_fraction": HOLDOUT_SHARE,
            "holdout_rule": "ceil(20 percent of usable n), last observations chronologically",
            "prior_exploration_disclosed": True,
            "not_preregistered": True,
        },
    }

    prediction_table = pd.DataFrame(probabilities, columns=["P_" + label for label in CLASS_ORDER])
    true_p = probabilities[np.arange(len(actual)), actual + 1]
    prediction_table.insert(0, "decision_date", holdout.decision_date.dt.strftime("%Y-%m-%d"))
    prediction_table.insert(1, "actual_decision", holdout.decision.to_numpy())
    prediction_table.insert(2, "actual_score", actual)
    prediction_table.insert(3, "expected_score", expected_score)
    prediction_table.insert(4, "predicted_class", np.asarray(CLASS_ORDER)[probabilities.argmax(axis=1)])
    prediction_table["model_log_score_contribution"] = -np.log(np.clip(true_p, np.finfo(float).tiny, 1.0))
    prediction_table["benchmark_prediction"] = "Hold"
    prediction_table["benchmark_score"] = 0

    diagnostics_rows = [
        {"diagnostic": "Joint LR all slopes", **joint_diag},
        {"diagnostic": "Parameter stability LR", **stability},
        {"diagnostic": "Proportional odds", **proportional},
        {"diagnostic": "Serial correlation", **serial},
        {"diagnostic": "Expected sign", **sign_diag},
        *[{"diagnostic": item["name"], **item} for item in not_applicable],
    ]
    unit_df, break_df = pd.DataFrame(root_rows), pd.DataFrame(break_rows)
    parameter_df, vif_df = pd.DataFrame(parameter_rows), pd.DataFrame(vif_rows)
    expanding_df, economic_df = pd.DataFrame(expanding_rows), pd.DataFrame(economic_rows)
    comparison_df = pd.DataFrame([
        {"model": "Ordered Logit", **comparison["model"]},
        {"model": "Always Hold", **comparison["benchmark_always_hold"]},
        {"model": "Class-frequency probabilities (secondary, post-freeze)", **comparison["class_frequency_comparator_secondary"]},
    ])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "annex_unit_roots.csv").parent.mkdir(parents=True, exist_ok=True)
    unit_df.to_csv(output_dir / "annex_unit_roots.csv", index=False)
    prediction_table.to_csv(output_dir / "annex_predictions.csv", index=False)
    _write_spec_log(output_dir / "spec_log.csv", records, append_spec_log)
    _write_json(artifact_path, artifact)
    _write_diagnostics_markdown(output_dir / "annex_diagnostics.md", sample | {
        "estimation_timestamp_utc": timestamp,
        "robustness_specification_count": len(robustness_checks),
    }, {
        "Holdout comparison": comparison_df,
        "Coefficients, cutpoints, and HC0 inference": parameter_df,
        "Diagnostics with statistic, p-value, and decision": pd.DataFrame(diagnostics_rows),
        "VIF": vif_df,
        "Unit-root tests on training sample": unit_df,
        "Structural-break checks": break_df,
        "Expanding-window coefficients": expanding_df,
        "Economic size and delta-method intervals": economic_df,
        "Holdout predictions": prediction_table,
        "Specification and test log": pd.DataFrame(records),
    })
    _write_falsification_markdown(output_dir / "falsification_verdicts.md", artifact["falsification_verdicts"])
    _write_robustness_markdown(output_dir / "robustness_table.md", robustness_checks, total_specifications)
    artifact["diagnostics"]["unit_root_tests"] = root_rows
    artifact["diagnostics"]["structural_break_checks"] = break_rows
    artifact["diagnostics"]["parameters"] = parameter_rows
    artifact["diagnostics"]["economic_size_plus_one_sd"] = economic_rows
    _write_json(artifact_path, artifact)
    return artifact


def main() -> dict[str, Any]:
    """Execute the documented model pipeline and print its primary results."""
    artifact = run_pipeline(append_spec_log=True)
    sample = artifact["sample"]
    comparison = artifact["benchmark_comparison"]
    print(f"Model panel: {MODEL_PANEL_PATH.relative_to(ROOT)}")
    print(f"Usable={sample['usable_n']}, dropped={sample['dropped_n']}, estimation={sample['estimation_n']}, holdout={sample['holdout_n']}")
    print("Dropped decision dates: " + (", ".join(sample["dropped_decisions"]) or "none"))
    print(f"Ordered Logit RMSE={comparison['model']['rmse']:.6f}; Always Hold RMSE={comparison['benchmark_always_hold']['rmse']:.6f}; ratio={comparison['rmse_ratio_model_to_hold']}; winner={comparison['winner']}")
    print(f"Artifact: {ARTIFACT_PATH.relative_to(ROOT)}")
    print(f"Diagnostics: {(OUTPUTS / 'annex_diagnostics.md').relative_to(ROOT)}")
    print(f"Unit-root results: {(OUTPUTS / 'annex_unit_roots.csv').relative_to(ROOT)}")
    print(f"Specification log: {(OUTPUTS / 'spec_log.csv').relative_to(ROOT)}")
    print(f"Robustness checks: {artifact['robustness_checks']['robustness_specification_count']}; total specifications including primary: {artifact['robustness_checks']['total_specifications_including_primary']}")
    return artifact


if __name__ == "__main__":
    main()
