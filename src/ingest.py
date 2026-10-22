"""Build the decision-date panel from the supplied monthly source files."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
DECISIONS_PATH = ROOT / "data" / "processed" / "nbk_decisions_clean.csv"
MODEL_PANEL_PATH = ROOT / "data" / "processed" / "model_panel.csv"
DECISION_DATES_PATH = ROOT / "config" / "nbk_decision_dates.csv"
CHECK_PATH = ROOT / "outputs" / "rebuild_check.csv"
RELEASE_LAG_CONFIG = ROOT / "config" / "release_lag.json"


def assumed_release_lag_months(path: Path = RELEASE_LAG_CONFIG) -> int:
    """Read the assumed decision-month offset from config; it is an assumption, not a measured lag."""
    value = json.loads(Path(path).read_text(encoding="utf-8")).get("assumed_release_lag_months")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{Path(path).name}: assumed_release_lag_months must be a non-negative integer")
    return value


ASSUMED_LAG_MONTHS = assumed_release_lag_months()

FEATURE_RULES = {
    "inflation": ("inflation_history.csv", "inflation"),
    "exports": ("export_history.csv", "exports_thousand_usd"),
    "imports": ("import_history.csv", "imports_thousand_usd"),
    "corporate_lending": ("loans_legal_entities_history.csv", "loans_legal_entities_mln_kzt"),
    "household_lending": ("loans_individuals_history.csv", "loans_individuals_mln_kzt"),
    "consumption": ("consumption_history_updated.csv", "consumption_yoy"),
}
# Model-panel factors that enter as 12-month log growth; the others enter as levels.
LOG_GROWTH_FEATURES = {"exports", "imports", "corporate_lending", "household_lending"}
OUTPUT_COLUMNS = [
    "decision_date", "base_rate_before", "base_rate_after", "decision",
    "inflation", "exports", "imports", "corporate_lending", "household_lending", "consumption",
]


def read_monthly_series(path: Path, value_column: str) -> pd.Series:
    """Read a numeric ``year_month`` series indexed by unique monthly periods."""
    frame = pd.read_csv(path)
    expected_columns = ["year_month", value_column]
    if frame.columns.tolist() != expected_columns:
        raise ValueError(f"{path.name} columns must be {expected_columns}; got {frame.columns.tolist()}")
    periods = pd.PeriodIndex(pd.to_datetime(frame["year_month"], format="%Y-%m", errors="raise"), freq="M")
    values = pd.to_numeric(frame[value_column], errors="coerce")
    invalid = frame[value_column].notna() & values.isna()
    if invalid.any():
        rows = (np.flatnonzero(invalid.to_numpy()) + 2).tolist()
        raise ValueError(f"{path.name} has non-numeric values at CSV rows {rows}")
    series = pd.Series(values.to_numpy(dtype=float), index=periods, name=value_column).sort_index()
    if series.index.has_duplicates:
        raise ValueError(f"{path.name} has duplicate months")
    return series


def complete_month_calendar(series: pd.Series) -> pd.Series:
    """Reindex to all calendar months between endpoints; leave gaps as NaN."""
    if series.empty:
        return series.copy()
    return series.reindex(pd.period_range(series.index.min(), series.index.max(), freq="M")).rename(series.name)


def growth_rate(series: pd.Series) -> pd.Series:
    """Return one-calendar-month percent growth; gaps and zero denominators yield NaN."""
    monthly = complete_month_calendar(series)
    previous = monthly.shift(1)
    result = (monthly.div(previous).sub(1).mul(100)).where(previous.ne(0))
    return result.rename(series.name)


def log_level(series: pd.Series) -> pd.Series:
    """Return the natural logarithm of positive levels; nonpositive values become NaN."""
    return np.log(series.where(series > 0)).rename(series.name)


def first_difference(series: pd.Series) -> pd.Series:
    """Return the first difference over adjacent calendar months; gaps remain NaN."""
    return complete_month_calendar(series).diff().rename(series.name)


def log_growth_12m(series: pd.Series) -> pd.Series:
    """Return 12-month log growth in percent, preserving missing months.

    The source is first reindexed to calendar months. The calculation is
    ``100 * (log(x_t) - log(x_{t-12}))``; nonpositive values or a missing value
    in either month produce NaN. No gap is interpolated or forward-filled.
    """
    monthly = complete_month_calendar(series)
    logged = log_level(monthly)
    return (logged - logged.shift(12)).mul(100).rename(series.name)


def apply_release_lag(
    series: pd.Series,
    decision_dates: pd.Series,
    lag_months: int = ASSUMED_LAG_MONTHS,
) -> pd.Series:
    """Align monthly data to the decision month minus the assumed release lag.

    The default comes from config/release_lag.json; it is the project's
    reconstruction assumption, not a verified series publication lag.
    Missing reference months remain NaN.
    """
    return align_to_decision_months(series, decision_dates, lag_months=lag_months)


def build_model_panel(
    panel_path: Path | None = None,
    raw_dir: Path | None = None,
    output_path: Path | None = None,
) -> pd.DataFrame:
    """Build a model-ready panel with the specified levels and 12-month logs.

    Inflation and consumption are retained as levels. Exports, imports, and
    both lending series use 12-month log growth. Each factor is then aligned
    to decision month minus two (an unverified timing assumption). The target
    score is mapped from the existing decision label; target-rate columns are
    intentionally excluded from the returned predictors and output file.
    """
    panel_path = Path(panel_path) if panel_path is not None else DECISIONS_PATH
    raw_dir = Path(raw_dir) if raw_dir is not None else RAW_DIR
    output_path = Path(output_path) if output_path is not None else MODEL_PANEL_PATH
    decisions = pd.read_csv(panel_path, parse_dates=["decision_date"])
    required = {"decision_date", "decision", *FEATURE_RULES.keys()}
    missing = sorted(required.difference(decisions.columns))
    if missing:
        raise ValueError(f"Decision panel is missing columns: {missing}")
    dates = pd.to_datetime(decisions["decision_date"], errors="raise")
    if dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError("Decision dates must be unique and chronological")

    records = pd.DataFrame({"decision_date": dates.dt.strftime("%Y-%m-%d")})
    labels = decisions["decision"].astype(str).str.strip().str.title()
    score_map = {"Decrease": -1, "Hold": 0, "Increase": 1}
    unknown = sorted(set(labels).difference(score_map))
    if unknown:
        raise ValueError(f"Unsupported decision labels: {unknown}")
    records["decision"] = labels.to_numpy()
    records["y"] = labels.map(score_map).astype("int64").to_numpy()

    log_growth_features = LOG_GROWTH_FEATURES
    for feature, (filename, source_column) in FEATURE_RULES.items():
        source = read_monthly_series(raw_dir / filename, source_column)
        transformed = log_growth_12m(source) if feature in log_growth_features else source
        records[feature] = apply_release_lag(transformed, dates, lag_months=ASSUMED_LAG_MONTHS).to_numpy()

    output_columns = ["decision_date", "decision", "y", *FEATURE_RULES.keys()]
    result = records[output_columns]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    return result


def align_to_decision_months(series: pd.Series, decision_dates: pd.Series,
                              lag_months: int = ASSUMED_LAG_MONTHS) -> pd.Series:
    """Select raw level at decision calendar month minus the configured assumed lag.

    The two-month offset is the established panel reconstruction convention, not
    verified publication timing. Missing source months remain missing.
    """
    if lag_months < 0:
        raise ValueError("lag_months must be non-negative")
    dates = pd.to_datetime(decision_dates, errors="raise")
    reference_months = dates.dt.to_period("M") - lag_months
    lookup = complete_month_calendar(series)
    return pd.Series(reference_months.map(lookup), index=decision_dates.index, dtype=float, name=series.name)


def build_base_rate_targets(rate_series: pd.Series, decision_dates: pd.Series) -> pd.DataFrame:
    """Map decision-month rate as ``base_rate_after`` and derive its class.

    ``base_rate_before`` is the previous decision's mapped rate; for the first
    decision it is the rate in the immediately preceding calendar month.
    """
    dates = pd.to_datetime(decision_dates, errors="raise")
    rate_months = complete_month_calendar(rate_series)
    decision_periods = dates.dt.to_period("M")
    after = decision_periods.map(rate_months).astype(float)
    before = after.shift(1)
    if len(before):
        before.iloc[0] = rate_months.get(decision_periods.iloc[0] - 1, np.nan)
    labels = pd.Series(pd.NA, index=after.index, dtype="string")
    labels.loc[after > before] = "Increase"
    labels.loc[after < before] = "Decrease"
    labels.loc[after.eq(before) & after.notna() & before.notna()] = "Hold"
    return pd.DataFrame({"base_rate_before": before, "base_rate_after": after, "decision": labels})


def build_panel(
    raw_dir: Path | None = None,
    decision_dates: pd.Series | None = None,
    decision_dates_path: Path | None = None,
    output_path: Path | None = None,
) -> pd.DataFrame:
    """Build and write the canonical panel using raw levels at decision month −2.

    All six factors are aligned as untransformed levels at decision calendar
    month minus two. The lag is a project convention, not confirmed release lag.
    Household lending is rounded to eight decimal places to reproduce the
    existing panel's stored precision; this does not change its level scale.
    Rate targets use ``build_base_rate_targets``. No growth, log, difference,
    imputation, or future target columns are used as factor transformations.
    """
    raw_dir = Path(raw_dir) if raw_dir is not None else RAW_DIR
    decision_dates_path = Path(decision_dates_path) if decision_dates_path is not None else DECISION_DATES_PATH
    output_path = Path(output_path) if output_path is not None else DECISIONS_PATH
    if decision_dates is None:
        schedule = pd.read_csv(decision_dates_path)
        if schedule.columns.tolist() != ["decision_date"]:
            raise ValueError("Decision date calendar must contain only decision_date")
        decision_dates = pd.to_datetime(schedule["decision_date"], errors="raise")
    dates = pd.to_datetime(pd.Series(decision_dates).reset_index(drop=True), errors="raise")
    if dates.duplicated().any():
        raise ValueError("Decision dates must be unique")
    if not dates.is_monotonic_increasing:
        raise ValueError("Decision dates must be in chronological order")

    panel = pd.DataFrame({"decision_date": dates.dt.strftime("%Y-%m-%d")})
    rates = read_monthly_series(raw_dir / "base_rate_history.csv", "rate")
    targets = build_base_rate_targets(rates, dates)
    for column in targets:
        panel[column] = targets[column].to_numpy()
    for feature, (filename, source_column) in FEATURE_RULES.items():
        source = read_monthly_series(raw_dir / filename, source_column)
        aligned = align_to_decision_months(source, dates, lag_months=ASSUMED_LAG_MONTHS)
        if feature == "household_lending":
            aligned = aligned.round(8)
        panel[feature] = aligned.to_numpy()
    panel = panel[OUTPUT_COLUMNS]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(output_path, index=False)
    return panel


def compare_cells(original: pd.DataFrame, rebuilt: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """Compare cells row-wise, allowing 1e-8 numeric serialization precision."""
    if original.columns.tolist() != rebuilt.columns.tolist():
        raise ValueError("Original and rebuilt columns or their order do not match")
    left, right = original.copy(), rebuilt.copy()
    left["decision_date"] = pd.to_datetime(left["decision_date"], errors="raise")
    right["decision_date"] = pd.to_datetime(right["decision_date"], errors="raise")
    if not left["decision_date"].equals(right["decision_date"]):
        raise ValueError("Original and rebuilt decision dates do not match row for row")
    records, matches, differences = [], 0, 0
    for row_index in range(len(left)):
        date = left.at[row_index, "decision_date"]
        for column in left.columns:
            if column == "decision_date":
                continue
            a, b = left.at[row_index, column], right.at[row_index, column]
            both_missing = pd.isna(a) and pd.isna(b)
            numeric_pair = pd.api.types.is_number(a) and pd.api.types.is_number(b)
            if both_missing:
                same, delta = True, 0.0
            elif numeric_pair:
                same = bool(np.isclose(float(a), float(b), rtol=0.0, atol=1e-8))
                delta = float(b) - float(a)
            else:
                same = a == b
                delta = 0.0 if same else 1.0
            matches += int(same)
            differences += int(not same)
            records.append({"date": date.strftime("%Y-%m-%d"), "column": column, "original": a,
                            "rebuilt": b, "difference": delta})
    return pd.DataFrame(records, columns=["date", "column", "original", "rebuilt", "difference"]), matches, differences


def main() -> tuple[int, int]:
    """Rebuild the canonical panel and report its cellwise comparison to a baseline."""
    reference_path = Path(os.environ.get("NBK_REBUILD_REFERENCE", DECISIONS_PATH))
    original = None
    if reference_path.exists():
        original = pd.read_csv(reference_path, parse_dates=["decision_date"])
        if original.columns.tolist() != OUTPUT_COLUMNS:
            raise ValueError(f"Unexpected reference-panel columns: {original.columns.tolist()}")
    panel = build_panel()
    print(f"Decision rows: {len(panel)}")
    print(f"Panel: {DECISIONS_PATH.relative_to(ROOT)}")
    if original is None:
        print("No reference panel available; rebuild comparison was not generated.")
        return 0, 0
    check, matching, differing = compare_cells(original, panel)
    CHECK_PATH.parent.mkdir(parents=True, exist_ok=True)
    check.to_csv(CHECK_PATH, index=False)
    print(f"Compared cells (excluding the date key): {len(check)}")
    print(f"Matching cells: {matching}")
    print(f"Differing cells: {differing}")
    print(f"Comparison: {CHECK_PATH.relative_to(ROOT)}")
    return matching, differing


if __name__ == "__main__":
    main()
