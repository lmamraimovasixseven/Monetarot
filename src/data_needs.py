"""Which factor months a decision date needs: `python run.py needs [YYYY-MM-DD ...]`.

For every decision date (by default: the last decisions in config/nbk_decision_dates.csv and every
upcoming date in config/forecast_rounds.json) it prints the reference month of each factor
(decision month minus the assumed lag from config/release_lag.json), the base month twelve months
earlier for the 12-month-growth factors, and whether each month is already in data/raw. It reads
only; it never changes a file.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from src.ingest import ASSUMED_LAG_MONTHS, DECISION_DATES_PATH, FEATURE_RULES, LOG_GROWTH_FEATURES, RAW_DIR, read_monthly_series


ROOT = Path(__file__).resolve().parents[1]
ROUNDS_PATH = ROOT / "config" / "forecast_rounds.json"
RATE_FILE = ("base_rate_history.csv", "rate")


def needs_table(decision_dates: list[pd.Timestamp], raw_dir: Path = RAW_DIR,
                lag_months: int = ASSUMED_LAG_MONTHS) -> pd.DataFrame:
    available = {filename: set(read_monthly_series(Path(raw_dir) / filename, column).index)
                 for filename, column in [*FEATURE_RULES.values(), RATE_FILE]}
    rows = []
    for when in decision_dates:
        decision_month = pd.Timestamp(when).to_period("M")
        reference = decision_month - lag_months
        rows.append({"decision_date": pd.Timestamp(when).date().isoformat(), "series_file": RATE_FILE[0],
                     "role": "target (rate after the decision)", "month_needed": str(decision_month),
                     "present": decision_month in available[RATE_FILE[0]]})
        for feature, (filename, _) in FEATURE_RULES.items():
            months = [(reference, f"{feature}: reference month (decision month - {lag_months})")]
            if feature in LOG_GROWTH_FEATURES:
                months.append((reference - 12, f"{feature}: base month of the 12-month growth"))
            for month, role in months:
                rows.append({"decision_date": pd.Timestamp(when).date().isoformat(), "series_file": filename,
                             "role": role, "month_needed": str(month), "present": month in available[filename]})
    return pd.DataFrame(rows)


def default_dates(today: date | None = None, last_n: int = 2) -> list[pd.Timestamp]:
    today = today or date.today()
    calendar = pd.to_datetime(pd.read_csv(DECISION_DATES_PATH)["decision_date"]).tolist()
    upcoming = []
    if ROUNDS_PATH.is_file():
        rounds = json.loads(ROUNDS_PATH.read_text(encoding="utf-8")).get("rounds", [])
        upcoming = [pd.Timestamp(r["date"]) for r in rounds
                    if r.get("date") and pd.Timestamp(r["date"]).date() > today and pd.Timestamp(r["date"]) not in calendar]
    return calendar[-last_n:] + upcoming


def render(table: pd.DataFrame) -> str:
    lines = ["| Decision date | File | Role | Month needed | In data/raw |", "|---|---|---|---|---|"]
    for row in table.itertuples(index=False):
        lines.append(f"| {row.decision_date} | `{row.series_file}` | {row.role} | {row.month_needed} | "
                     f"{'yes' if row.present else '**MISSING**'} |")
    missing = table[~table["present"]]
    lines += ["", f"Missing months: {len(missing)}" + (
        " (" + "; ".join(f"{r.series_file} {r.month_needed}" for r in missing.drop_duplicates(
            ["series_file", "month_needed"]).itertuples(index=False)) + ")" if len(missing) else "")]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dates", nargs="*", help="decision dates YYYY-MM-DD (default: last two decisions + upcoming)")
    args = parser.parse_args(argv)
    dates = [pd.Timestamp(d) for d in args.dates] if args.dates else default_dates()
    print(render(needs_table(dates)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
