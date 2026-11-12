"""Raw-data jump screen, run on every data update by `python run.py data` (src.ingest.main).

Moved here from src/robust_eval.py on 2026-11-12 (docs/deviations.md, D28) so that the screen runs
whenever data are added, not only with the exploratory stress tests. The method is unchanged:
modified z-scores (Iglewicz and Hoaglin, 1993) of monthly changes (log changes for level series,
first differences for rate series). A flag asks for the source value to be re-checked; flagged
values are never altered.

Writes data/processed/data_anomalies.json (read by the dashboard warning) and
outputs/data_anomalies.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.ingest import (
    ASSUMED_LAG_MONTHS,
    DECISIONS_PATH,
    FEATURE_RULES,
    LOG_GROWTH_FEATURES,
    RAW_DIR,
    complete_month_calendar,
    read_monthly_series,
)


ROOT = Path(__file__).resolve().parents[1]
SCREEN_JSON_PATH = ROOT / "data" / "processed" / "data_anomalies.json"
SCREEN_MD_PATH = ROOT / "outputs" / "data_anomalies.md"
MODIFIED_Z_THRESHOLD = 3.5    # Iglewicz and Hoaglin (1993) outlier rule for the modified z-score
RATE_SERIES = {"inflation", "consumption"}  # already rates: screen first differences, not log changes


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
    """Flags in a month whose change enters the latest score.

    Level factors: a jump at the reference month or the month before it. Growth factors
    (12-month log growth): 100 * (log x_t - log x_{t-12}) is the sum of the monthly log
    changes of months t-11 ... t, so a flagged change in any of those twelve months moves
    the input (a level shift persists in the 12-month growth for a year), as does a flag at
    month t-12 itself (the base month).
    """
    reference = latest_date.to_period("M") - lag_months
    growth = set(LOG_GROWTH_FEATURES)
    relevant = []
    for flag in flags:
        if flag["feature"] in growth:
            months = {str(reference - k) for k in range(0, 13)}
        else:
            months = {str(reference), str(reference - 1)}
        if flag["month"] in months:
            relevant.append(flag)
    return relevant


def latest_complete_decision(decisions_path: Path = DECISIONS_PATH) -> pd.Timestamp:
    """The latest decision whose six factors are all present at decision month minus the assumed lag."""
    panel = pd.read_csv(decisions_path, parse_dates=["decision_date"])
    complete = panel.dropna(subset=list(FEATURE_RULES))
    return complete["decision_date"].iloc[-1]


def build_screen(raw_dir: Path = RAW_DIR, decisions_path: Path = DECISIONS_PATH,
                 lag_months: int = ASSUMED_LAG_MONTHS) -> dict[str, Any]:
    flags = anomaly_screen(raw_dir)
    latest = latest_complete_decision(decisions_path)
    return {
        "generated_by": "python run.py data (src/data_screen.py)",
        "method": "modified z-score of monthly changes (log change for levels, first difference for rates)",
        "modified_z_threshold": MODIFIED_Z_THRESHOLD,
        "latest_decision": latest.date().isoformat(),
        "assumed_lag_months": lag_months,
        "flags": flags,
        "affecting_latest_score": anomalies_in_latest_inputs(flags, latest, lag_months),
    }


def render_markdown(screen: dict[str, Any]) -> str:
    affecting = {(f["feature"], f["month"]) for f in screen["affecting_latest_score"]}
    lines = ["# Raw-data jump screen", "",
             f"Modified z-score of monthly changes (log change for level series, first difference for rate series), "
             f"flag at |z| ≥ {screen['modified_z_threshold']} (Iglewicz and Hoaglin, 1993). A flag asks for the source "
             "value to be re-checked against the publisher; it is not evidence of an error, and flagged values are "
             f"never changed. Latest decision with all six factors: {screen['latest_decision']} (factor month = "
             f"decision month minus {screen['assumed_lag_months']}).", "",
             f"Flagged months: {len(screen['flags'])}; entering the latest score: {len(affecting)}.", "",
             "| Series | Month | Value | Previous month | Change | Modified z | Enters latest score |",
             "|---|---|---|---|---|---|---|"]
    for flag in screen["flags"]:
        lines.append(f"| {flag['series_file']} | {flag['month']} | {flag['value']:.2f} | {flag['previous_value']:.2f} "
                     f"| {flag['change']:.3f} ({flag['change_definition']}) | {flag['modified_z']:.2f} "
                     f"| {'yes' if (flag['feature'], flag['month']) in affecting else 'no'} |")
    lines += ["", "Generated by `python run.py data` (src/data_screen.py).", ""]
    return "\n".join(lines)


def write(raw_dir: Path = RAW_DIR, decisions_path: Path = DECISIONS_PATH,
          json_path: Path = SCREEN_JSON_PATH, md_path: Path = SCREEN_MD_PATH) -> dict[str, Any]:
    screen = build_screen(raw_dir, decisions_path)
    Path(json_path).parent.mkdir(parents=True, exist_ok=True)
    Path(json_path).write_text(json.dumps(screen, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                               encoding="utf-8", newline="\n")
    Path(md_path).parent.mkdir(parents=True, exist_ok=True)
    Path(md_path).write_text(render_markdown(screen), encoding="utf-8", newline="\n")
    return screen


if __name__ == "__main__":
    result = write()
    print(f"Anomaly flags: {len(result['flags'])}; affecting latest score: {len(result['affecting_latest_score'])}")
