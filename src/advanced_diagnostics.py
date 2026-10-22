"""Exploratory diagnostics for lending-series breaks and feature specifications.

Raw monthly source series are deliberately not reconstructed here. When those
files are absent, the available decision-date panel is analyzed and the
frequency limitation is recorded in every report.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import f as f_distribution
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score

from src.legacy_classifier import CLASS_ORDER, FEATURES, make_model


LENDING_FEATURES = ("corporate_lending", "household_lending")
MIN_SEGMENT = 10
BOOTSTRAP_REPLICATES = 199


def decision_growth(data: pd.DataFrame, feature: str) -> pd.Series:
    """Past-to-current percentage change between observed decision rows."""
    ordered = data.sort_values("decision_date")
    values = pd.to_numeric(ordered[feature], errors="coerce")
    growth = values.pct_change(fill_method=None) * 100.0
    return pd.Series(growth.to_numpy(), index=ordered.index, name=f"{feature}_decision_interval_pct")


def _design(time: np.ndarray, split: int | None, trend: bool) -> np.ndarray:
    time = np.asarray(time, dtype=float)
    n = len(time)
    span = float(np.ptp(time))
    time = (time - time.mean()) / (span if span > 0 else 1.0)
    if split is None:
        return np.column_stack([np.ones(n), time]) if trend else np.ones((n, 1))
    after = (np.arange(len(time)) >= split).astype(float)
    if trend:
        return np.column_stack([np.ones(n), time, after, time * after])
    return np.column_stack([np.ones(n), after])


def _rss(y: np.ndarray, x: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    coef, _, _, _ = np.linalg.lstsq(x, y, rcond=None)
    residuals = y - x @ coef
    return float(residuals @ residuals), coef, residuals


def _sup_f(y: np.ndarray, trend: bool, candidates: list[int], time: np.ndarray) -> tuple[float, int, float, float]:
    null_x = _design(time, None, trend)
    null_rss, _, _ = _rss(y, null_x)
    best = (-np.inf, candidates[0], np.nan, np.nan)
    null_k = null_x.shape[1]
    for split in candidates:
        alt_x = _design(time, split, trend)
        alt_rss, _, _ = _rss(y, alt_x)
        added = alt_x.shape[1] - null_k
        denom_df = len(y) - alt_x.shape[1]
        if added <= 0 or denom_df <= 0 or alt_rss <= 0:
            continue
        statistic = max(0.0, (null_rss - alt_rss) / added / (alt_rss / denom_df))
        pvalue = float(f_distribution.sf(statistic, added, denom_df))
        if statistic > best[0]:
            best = (statistic, split, pvalue, alt_rss)
    return best


def _circular_block_resample(values: np.ndarray, block: int, rng: np.random.Generator) -> np.ndarray:
    n = len(values)
    starts = rng.integers(0, n, size=math.ceil(n / block))
    return np.concatenate([values[(start + np.arange(block)) % n] for start in starts])[:n]


def _break_test(values: pd.Series, dates: pd.Series, trend: bool, seed: int, replicates: int) -> dict:
    y = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(y)
    y = y[valid]
    used_dates = pd.to_datetime(dates.iloc[np.flatnonzero(valid)])
    n = len(y)
    if n < 2 * MIN_SEGMENT + 2:
        return {"status": "NOT EVALUABLE: too few observations", "n": n}
    trim = max(MIN_SEGMENT, int(np.ceil(0.15 * n)))
    candidates = list(range(trim, n - trim + 1))
    time = (used_dates - used_dates.min()).dt.days.to_numpy(dtype=float) / 365.25
    observed, split, nominal_p, _ = _sup_f(y, trend, candidates, time)
    null_rss, null_coef, residuals = _rss(y, _design(time, None, trend))
    fitted = _design(time, None, trend) @ null_coef
    residuals = residuals - residuals.mean()
    block_size = max(2, int(round(n ** (1 / 3))))
    rng = np.random.default_rng(seed)
    exceed = 0
    for _ in range(replicates):
        simulated = fitted + _circular_block_resample(residuals, block_size, rng)
        statistic, _, _, _ = _sup_f(simulated, trend, candidates, time)
        exceed += statistic >= observed
    return {
        "status": "EXPLORATORY BLOCK-BOOTSTRAP SUP-F",
        "n": n,
        "selected_index": int(split),
        "sup_f_statistic": float(observed),
        "pointwise_f_pvalue_not_for_inference": float(nominal_p),
        "moving_block_bootstrap_pvalue": float((exceed + 1) / (replicates + 1)),
        "bootstrap_replicates": int(replicates),
        "block_length": int(block_size),
        "null_hypothesis": "No unknown break: common mean" if not trend else "No unknown break: common intercept and linear trend",
        "alternative": "One unknown break in mean" if not trend else "One unknown break with separate intercepts and linear slopes",
        "trim_observations_each_side": int(trim),
        "null_rss": float(null_rss),
        "limitation": "Decision-date observations only; residual block bootstrap is exploratory with this small, irregularly spaced sample.",
    }


def _slope_by_segment(frame: pd.DataFrame, feature: str, split_date: pd.Timestamp) -> dict:
    rows = []
    for label, part in (("before", frame.loc[frame.decision_date < split_date]), ("after", frame.loc[frame.decision_date >= split_date])):
        vals = pd.to_numeric(part[feature], errors="coerce")
        valid = vals.notna()
        if int(valid.sum()) < 3:
            slope = None
        else:
            years = (part.loc[valid, "decision_date"] - part.loc[valid, "decision_date"].min()).dt.days.to_numpy() / 365.25
            slope = float(np.polyfit(years, vals.loc[valid].to_numpy(dtype=float), 1)[0])
        rows.append({"segment": label, "n": int(valid.sum()), "slope_per_year": slope})
    return {row["segment"]: row for row in rows}


def structural_break_diagnostics(data: pd.DataFrame, bootstrap_replicates: int = BOOTSTRAP_REPLICATES) -> tuple[pd.DataFrame, dict]:
    """Unknown-break scans for levels, log levels, and decision-interval growth."""
    frame = data.sort_values("decision_date").reset_index(drop=True).copy()
    frame["decision_date"] = pd.to_datetime(frame["decision_date"])
    candidates_out = []
    reports = []
    quality = {}
    for feature_no, feature in enumerate(LENDING_FEATURES):
        values = pd.to_numeric(frame[feature], errors="coerce")
        growth = values.pct_change(fill_method=None) * 100
        quality[feature] = {
            "n": int(len(frame)), "missing": int(values.isna().sum()),
            "duplicate_dates": int(frame.decision_date.duplicated().sum()),
            "negative_values": int((values < 0).sum()),
            "zero_values": int((values == 0).sum()),
            "anomalous_decision_interval_growth_abs_over_6_mad": int(
                (growth.sub(growth.median()).abs() > 6 * (growth.sub(growth.median()).abs().median() or np.inf)).sum()
            ),
        }
        forms = {"level": values, "log_level": np.log(values.where(values > 0)), "decision_interval_growth_pct": growth}
        for form_no, (form, series) in enumerate(forms.items()):
            clean = series.dropna()
            if clean.empty:
                continue
            for trend_no, trend in enumerate((False, True)):
                result = _break_test(clean, frame.loc[clean.index, "decision_date"], trend, seed=20261015 + feature_no * 100 + form_no * 10 + trend_no, replicates=bootstrap_replicates)
                chosen_pos = result.get("selected_index")
                candidate_dates = clean.index.to_list()
                if chosen_pos is not None and 0 <= chosen_pos < len(candidate_dates):
                    chosen_date = frame.loc[candidate_dates[chosen_pos], "decision_date"]
                    result["selected_date"] = chosen_date.strftime("%Y-%m-%d")
                    result["segment_slopes"] = _slope_by_segment(frame, feature, chosen_date) if form == "level" else None
                else:
                    chosen_date = None
                    result["selected_date"] = None
                    result["segment_slopes"] = None
                base = {"feature": feature, "form": form, "test": "mean" if not trend else "intercept_and_trend", **result}
                reports.append(base)
                if result.get("status", "").startswith("EXPLORATORY"):
                    for index, date in enumerate(candidate_dates):
                        if index < max(MIN_SEGMENT, int(np.ceil(0.15 * len(clean))) or 0) or index >= len(clean) - max(MIN_SEGMENT, int(np.ceil(0.15 * len(clean)))):
                            continue
                        # The saved table enumerates admissible candidate dates; p-values are for the max statistic, not each row.
                        candidates_out.append({"feature": feature, "form": form, "candidate_date": frame.loc[date, "decision_date"].strftime("%Y-%m-%d"), "selected_by_sup_f": bool(index == chosen_pos), "sup_f_statistic": result["sup_f_statistic"], "bootstrap_pvalue_for_unknown_break_scan": result["moving_block_bootstrap_pvalue"], "test": base["test"]})
    source_root = __import__("pathlib").Path(__file__).resolve().parents[1] / "data" / "raw"
    expected_sources = ["loans_legal_entities_history.csv", "loans_individuals_history.csv"]
    raw_sources_present = {name: (source_root / name).is_file() for name in expected_sources}
    all_raw_sources_present = all(raw_sources_present.values())
    workbook_files = list(source_root.rglob("*.xlsx")) + list(source_root.rglob("*.xls")) if source_root.exists() else []
    metadata = {
        "sample": (
            "Processed decision-date panel only; raw monthly lending files are present but are not used in this diagnostic."
            if all_raw_sources_present
            else "Processed decision-date panel only; one or more raw monthly lending files are absent from the working tree."
        ),
        "raw_monthly_sources_present": raw_sources_present,
        "excel_workbooks_present": [path.name for path in workbook_files],
        "frequency_limitation": "Growth is percent change between adjacent NBK decision observations, not monthly or annual growth. This diagnostic does not use the raw monthly lending files to estimate monthly-series breaks.",
        "multiple_testing_limitation": "Unknown-break bootstrap p-values account for scanning candidate dates within each series/form, but are not adjusted across features and transformations.",
        "stationarity": "ADF/KPSS were not applied to the monthly source series in this diagnostic. The analyzed processed panel is irregularly spaced at NBK decision dates; standard regular-frequency interpretations would be misleading, and break tests do not establish stationarity.",
        "unit_evidence": "Supplied raw CSVs are available, but publisher provenance and measurement units are not authenticated; header-based unit hints remain unverified.",
        "series_quality": quality,
        "tests": reports,
    }
    return pd.DataFrame(candidates_out), metadata


def alternative_specifications(data: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Fixed diagnostic feature transforms evaluated on the same chronological windows."""
    ordered = data.sort_values("decision_date").reset_index(drop=True).copy()
    transformed = {"Current six levels": (ordered[FEATURES].copy(), FEATURES)}
    for feature in LENDING_FEATURES:
        if (pd.to_numeric(ordered[feature], errors="coerce") <= 0).any():
            break
    else:
        logged = ordered[FEATURES].copy()
        for feature in LENDING_FEATURES:
            logged[feature] = np.log(pd.to_numeric(ordered[feature], errors="coerce"))
        transformed["Log lending levels (diagnostic)"] = (logged, FEATURES)
    growth = ordered[FEATURES].copy()
    for feature in LENDING_FEATURES:
        growth[feature] = pd.to_numeric(ordered[feature], errors="coerce").pct_change(fill_method=None) * 100
    transformed["Decision-interval lending growth (diagnostic)"] = (growth, FEATURES)

    rows, prediction_rows = [], []
    latest = ordered.decision_date.max()
    for months in (24, 36, 48):
        cutoff = latest - pd.DateOffset(months=months)
        for spec_name, (matrix, columns) in transformed.items():
            complete = matrix[columns].notna().all(axis=1)
            train_mask = (ordered.decision_date < cutoff) & complete
            test_mask = (ordered.decision_date >= cutoff) & complete
            train_idx, test_idx = ordered.index[train_mask], ordered.index[test_mask]
            train, test = ordered.loc[train_idx], ordered.loc[test_idx]
            if len(train) < 10 or len(test) == 0 or train.decision.nunique() < 2:
                rows.append({"period_months": months, "specification": spec_name, "model": "all", "status": "NOT EVALUABLE", "train_n": len(train), "test_n": len(test)})
                continue
            if set(train_idx).intersection(test_idx) or train.decision_date.max() >= test.decision_date.min():
                raise AssertionError("Alternative specification split is not chronological")
            x_train = matrix.loc[train_idx, columns]
            x_test = matrix.loc[test_idx, columns]
            actual = test.decision.to_numpy()
            models = [("Hold benchmark", np.repeat("Hold", len(test)), None, None)]
            for name in ("Logistic Regression", "Random Forest"):
                model = make_model(name)
                model.fit(x_train, train.decision.to_numpy())
                predicted = model.predict(x_test)
                proba = model.predict_proba(x_test) if hasattr(model, "predict_proba") else None
                models.append((name, predicted, proba, model))
                if proba is not None:
                    class_positions = {label: list(model.classes_).index(label) for label in CLASS_ORDER if label in model.classes_}
                    for row_i, row_index in enumerate(test_idx):
                        entry = {"period_months": months, "specification": spec_name, "decision_date": ordered.loc[row_index, "decision_date"].strftime("%Y-%m-%d"), "actual": ordered.loc[row_index, "decision"]}
                        entry[f"predicted_{name}"] = str(predicted[row_i])
                        for label in CLASS_ORDER:
                            entry[f"probability_{name}_{label}"] = float(proba[row_i, class_positions[label]]) if label in class_positions else np.nan
                        prediction_rows.append(entry)
            for name, predicted, proba, fitted_model in models:
                matrix_values = confusion_matrix(actual, predicted, labels=CLASS_ORDER)
                record = {
                    "period_months": months, "specification": spec_name, "model": name,
                    "status": "EVALUATED", "train_n": int(len(train)), "test_n": int(len(test)),
                    "train_start": train.decision_date.min().strftime("%Y-%m-%d"), "train_end": train.decision_date.max().strftime("%Y-%m-%d"),
                    "test_start": test.decision_date.min().strftime("%Y-%m-%d"), "test_end": test.decision_date.max().strftime("%Y-%m-%d"),
                    "train_test_overlap": False,
                    "accuracy": float(accuracy_score(actual, predicted)),
                    "balanced_accuracy": float(balanced_accuracy_score(actual, predicted)),
                    "macro_f1": float(f1_score(actual, predicted, labels=CLASS_ORDER, average="macro", zero_division=0)),
                    "confusion_matrix_labels": list(CLASS_ORDER), "confusion_matrix_actual_rows_predicted_columns": matrix_values.tolist(),
                    "predicted_class_counts": {label: int(np.sum(predicted == label)) for label in CLASS_ORDER},
                    "actual_class_counts": {label: int(np.sum(actual == label)) for label in CLASS_ORDER},
                    "multiclass_brier": None,
                    "note": "Diagnostic comparison only; no specification is selected from the final-test scores.",
                }
                if proba is not None:
                    one_hot = np.column_stack([actual == label for label in fitted_model.classes_]).astype(float)
                    record["multiclass_brier"] = float(np.mean(np.sum((proba - one_hot) ** 2, axis=1)))
                rows.append(record)
    return pd.DataFrame(rows), prediction_rows


def detailed_error_analysis(data: pd.DataFrame, period_predictions: pd.DataFrame, months: int = 24) -> pd.DataFrame:
    """Join saved-style OOS errors to lending levels, interval growth and train ranges."""
    frame = period_predictions.loc[period_predictions.test_period_months == months].copy()
    if frame.empty:
        return frame
    source = data.sort_values("decision_date").copy()
    source["decision_date"] = pd.to_datetime(source.decision_date)
    for feature in LENDING_FEATURES:
        source[f"{feature}_decision_interval_growth_pct"] = source[feature].pct_change(fill_method=None) * 100
    out = frame.merge(source, on="decision_date", how="left", suffixes=("", "_source"), validate="one_to_one")
    cutoff = source.decision_date.max() - pd.DateOffset(months=months)
    train = source.loc[source.decision_date < cutoff]
    for feature in LENDING_FEATURES:
        low, high = train[feature].min(), train[feature].max()
        out[f"{feature}_outside_train_range"] = (out[feature] < low) | (out[feature] > high)
    out["out_of_range_feature_count"] = out[[f"{feature}_outside_train_range" for feature in LENDING_FEATURES]].sum(axis=1)
    out["Logistic Regression correct"] = out["predicted_Logistic Regression"] == out["actual"]
    out["Random Forest correct"] = out["predicted_Random Forest"] == out["actual"]
    for name in ("Logistic Regression", "Random Forest"):
        cols = [f"probability_{name}_{label}" for label in CLASS_ORDER]
        if set(cols).issubset(out.columns):
            out[f"{name} max_probability"] = out[cols].max(axis=1)
    return out
