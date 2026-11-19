"""Partner rates as context for the NBK base rate (D59): `python run.py partners`.

Descriptive only: nothing is estimated and nothing here enters the frozen model or the forecast. Writes
model/extensions/partner_context.json (outside model/artifact.json, like the D50 extensions), whose numbers become
`partners:` rows of the evidence ledger:

* latest stored values: each partner's nominal rate and its date (Bank of Russia key rate, China policy rate from BIS,
  ECB deposit facility rate); the real rate for Russia and China (calendar-day monthly mean minus CPI y/y, the corridor's
  definition, src/carry_corridor.partner_real_series). No euro-area inflation is stored, so the ECB rate is nominal only.
* latest spreads: NBK base rate minus each partner rate (monthly; nominal, and real for Russia and China).
* event counts: the NBK outcome at the first NBK decision after each partner rate change (definitions in DEFINITIONS),
  with n and a small-sample flag, plus a baseline (decisions with no partner change in the window before them) and the
  outcome distribution over all NBK decisions. Counts, not effects.
* export shares of the named partners (data/raw/external/kz_export_shares_2025.csv, as published) and two sums of
  stated shares.

`history()` gives the monthly series of the site's charts; they are read from the same raw files at build time and are
not ledger rows themselves (the page cites the files).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from src import carry_corridor, external_data

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "model" / "extensions" / "partner_context.json"
DECISIONS_PATH = ROOT / "data" / "processed" / "nbk_decisions_clean.csv"
TRADE_NAME = "kz_export_shares_2025"
# key: (name on the site, rate series, CPI series or None)
PARTNERS = {"ru_key_rate": ("Russia", "Bank of Russia key rate", "russia"),
            "cn_policy_rate": ("China", "China policy rate (BIS; LPR 1Y / benchmark lending rate)", "china"),
            "ecb_deposit_rate": ("ECB", "ECB deposit facility rate", None)}
WINDOW_DAYS = 60
SMALL_N = 10
OUTCOMES = {"Increase": "increase", "Hold": "hold", "Decrease": "decrease"}
GROUPS = ("rise", "cut", "mixed", "no_change_in_window", "change_matched_to_an_earlier_decision")
EURO_AREA_NAMED = ("Italy", "Netherlands")  # the named partners that use the euro
DEFINITIONS = {
    "partner_change": "a day on which the stored partner rate differs from the previous stored value (gaps skipped)",
    "matching": (f"each change is matched to the first NBK decision strictly after it, if that decision is at most {WINDOW_DAYS} "
                 "calendar days after the change; several changes of one partner matched to the same NBK decision count once"),
    "direction": "rise if every matched change of that partner was up, cut if every one was down, mixed otherwise",
    "baseline": f"NBK decisions with no change of that partner in the {WINDOW_DAYS} calendar days before them",
    "change_matched_to_an_earlier_decision": (f"NBK decisions with a partner change in the {WINDOW_DAYS} days before them that "
                                              "was matched to an earlier NBK decision"),
    "sample": f"NBK decisions whose {WINDOW_DAYS}-day window lies inside the stored partner series",
    "small_n": f"rows with n below {SMALL_N} are flagged: too few decisions to read a share",
    "reading": "descriptive counts, not causal effects and not a forecast",
}
LABEL = ("Descriptive context, added on 2026-11-19 after the freeze (D59): counts and spreads from stored files, nothing "
         "estimated; not used for the forecast. The frozen specification and its verdict do not change.")


def daily_rate(name: str, directory: Path = external_data.EXTERNAL_DIR) -> pd.Series:
    frame = external_data.read_raw(name, directory)
    value = frame.columns[1]
    series = frame.assign(date=pd.to_datetime(frame["date"])).dropna(subset=[value]).set_index("date")[value].sort_index()
    return series.astype(float)


def changes(name: str, directory: Path = external_data.EXTERNAL_DIR) -> pd.DataFrame:
    """Days on which the stored rate differs from the previous stored value (published gaps are skipped)."""
    series = daily_rate(name, directory)
    step = series.diff()
    moved = step[step.fillna(0) != 0]
    return pd.DataFrame({"date": moved.index, "change": moved.to_numpy(),
                         "direction": ["rise" if v > 0 else "cut" for v in moved.to_numpy()]})


def decisions(path: Path = DECISIONS_PATH) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["decision_date"])
    if not set(frame["decision"]) <= set(OUTCOMES):
        raise ValueError(f"unexpected NBK outcomes: {sorted(set(frame['decision']) - set(OUTCOMES))}")
    return frame[["decision_date", "decision"]].sort_values("decision_date").reset_index(drop=True)


def _counts(outcomes: list[str]) -> dict[str, int]:
    row = {"n": len(outcomes)}
    row.update({key: sum(o == name for o in outcomes) for name, key in OUTCOMES.items()})
    row["small_n"] = int(len(outcomes) < SMALL_N)
    return row


def classify(change_table: pd.DataFrame, decision_table: pd.DataFrame, first: pd.Timestamp, last: pd.Timestamp) -> pd.DataFrame:
    """One row per NBK decision of the sample with its group (GROUPS) for this partner."""
    window = pd.Timedelta(days=WINDOW_DAYS)
    dates = decision_table["decision_date"].to_numpy()
    matched: dict[pd.Timestamp, set[str]] = {}
    for row in change_table.itertuples():
        position = dates.searchsorted(row.date.to_datetime64(), side="right")  # first decision strictly after the change
        if position < len(dates) and pd.Timestamp(dates[position]) - row.date <= window:
            matched.setdefault(pd.Timestamp(dates[position]), set()).add(row.direction)
    sample = decision_table[(decision_table["decision_date"] - window >= first) & (decision_table["decision_date"] <= last)]
    groups = []
    for day in sample["decision_date"]:
        if day in matched:
            directions = matched[day]
            groups.append(next(iter(directions)) if len(directions) == 1 else "mixed")
        elif ((change_table["date"] >= day - window) & (change_table["date"] < day)).any():
            groups.append("change_matched_to_an_earlier_decision")
        else:
            groups.append("no_change_in_window")
    return sample.assign(group=groups).reset_index(drop=True)


def events(directory: Path = external_data.EXTERNAL_DIR, decisions_path: Path = DECISIONS_PATH) -> dict[str, Any]:
    table = decisions(decisions_path)
    out: dict[str, Any] = {"all_nbk_decisions": _counts(list(table["decision"])),
                           "all_nbk_decisions_period": {"first": table["decision_date"].min().date().isoformat(),
                                                        "last": table["decision_date"].max().date().isoformat()}}
    for name in PARTNERS:
        series = daily_rate(name, directory)
        change_table = changes(name, directory)
        classified = classify(change_table, table, series.index.min(), series.index.max())
        in_period = change_table[(change_table["date"] >= classified["decision_date"].min() - pd.Timedelta(days=WINDOW_DAYS))
                                 & (change_table["date"] < classified["decision_date"].max())]
        entry: dict[str, Any] = {"sample": _counts(list(classified["decision"])),
                                 "sample_period": {"first": classified["decision_date"].min().date().isoformat(),
                                                   "last": classified["decision_date"].max().date().isoformat()},
                                 "partner_changes_in_period": int(len(in_period)),
                                 "partner_rises_in_period": int((in_period["direction"] == "rise").sum()),
                                 "partner_cuts_in_period": int((in_period["direction"] == "cut").sum())}
        for group in GROUPS:
            entry[group] = _counts(list(classified.loc[classified["group"] == group, "decision"]))
        out[name] = entry
    return out


def _monthly_partner(name: str, directory: Path) -> pd.Series:
    return external_data.monthly_step_rate(external_data.read_raw(name, directory))


def history(directory: Path = external_data.EXTERNAL_DIR) -> dict[str, Any]:
    """Monthly series for the site's charts over the months of the NBK base-rate file: NBK rate and real rate, each
    partner's nominal rate (calendar-day mean) and the real rate where CPI is stored. Missing values are None."""
    frame = carry_corridor.monthly_inputs()
    real, _ = carry_corridor.partner_real_series(directory)
    months = frame.dropna(subset=["rate"]).index
    months = pd.period_range(months.min(), months.max(), freq="M")
    columns = {"nbk": frame["rate"], "nbk_real": frame["real_rate"]}
    for name, (_, _, real_key) in PARTNERS.items():
        columns[name] = _monthly_partner(name, directory)
        if real_key:
            columns[f"{name}_real"] = real[real_key]
    table = pd.concat(columns, axis=1).reindex(months)

    def values(column: str) -> list[float | None]:
        return [None if pd.isna(v) else round(float(v), 6) for v in table[column]]

    return {"months": [str(m) for m in months], **{column: values(column) for column in table.columns}}


def latest(directory: Path = external_data.EXTERNAL_DIR, decisions_path: Path = DECISIONS_PATH) -> dict[str, Any]:
    out: dict[str, Any] = {}
    real, notes = carry_corridor.partner_real_series(directory)
    for name, (_, _, real_key) in PARTNERS.items():
        series = daily_rate(name, directory)
        entry: dict[str, Any] = {"date": series.index[-1].date().isoformat(), "nominal": float(series.iloc[-1])}
        if real_key and len(real[real_key]):
            entry["real_month"] = str(real[real_key].index[-1])
            entry["real"] = float(real[real_key].iloc[-1])
        out[name] = entry
    table = pd.read_csv(decisions_path, parse_dates=["decision_date"]).sort_values("decision_date")
    out["nbk"] = {"date": table["decision_date"].iloc[-1].date().isoformat(), "rate": float(table["base_rate_after"].iloc[-1])}
    return out


def spreads(hist: dict[str, Any]) -> dict[str, Any]:
    """NBK base rate minus each partner rate in the latest month where both are stored (nominal), and KZ real rate minus
    the partner real rate (Russia, China)."""
    frame = pd.DataFrame({k: v for k, v in hist.items() if k != "months"}, index=hist["months"])
    out: dict[str, Any] = {}
    for name, (_, _, real_key) in PARTNERS.items():
        nominal = (frame["nbk"] - frame[name]).dropna()
        entry: dict[str, Any] = {"nominal_month": nominal.index[-1], "nominal": round(float(nominal.iloc[-1]), 6)}
        if real_key:
            spread = (frame["nbk_real"] - frame[f"{name}_real"]).dropna()
            entry.update({"real_month": spread.index[-1], "real": round(float(spread.iloc[-1]), 6)})
        out[name] = entry
    return out


def trade(directory: Path = external_data.EXTERNAL_DIR, config_path: Path = external_data.CONFIG_PATH) -> dict[str, Any]:
    spec = json.loads(Path(config_path).read_text(encoding="utf-8"))["context"][TRADE_NAME]
    frame = pd.read_csv(Path(directory) / spec["file"])
    if frame.columns.tolist() != spec["columns"]:
        raise ValueError(f"{spec['file']}: columns must be {spec['columns']}")
    shares_rows = frame[frame["unit"] == "percent of exports"]
    shares = {row.item: float(row.value) for row in shares_rows.itertuples()}
    total = frame.loc[frame["item"] == "Total exports", "value"]
    year = re.search(r"\b(\d{4})\b", spec["frequency"])
    return {"year": int(year.group(1)) if year else None,
            "shares_pct": {item.lower(): value for item, value in shares.items()},
            "total_exports_mln_usd": float(total.iloc[0]) if len(total) else None,
            # Arithmetic on stated shares, rounded to the one decimal of the source.
            "sums_pct": {"russia_and_china": round(shares["Russia"] + shares["China"], 1),
                         "named_euro_area_partners": round(sum(shares[c] for c in EURO_AREA_NAMED), 1)},
            "named_partners": len(shares)}


def build(directory: Path = external_data.EXTERNAL_DIR, decisions_path: Path = DECISIONS_PATH) -> dict[str, Any]:
    hist = history(directory)
    return {"label": LABEL, "window_days": WINDOW_DAYS, "small_n_threshold": SMALL_N, "definitions": DEFINITIONS,
            "partners": {name: {"site_name": site, "series": series} for name, (site, series, _) in PARTNERS.items()},
            "latest": latest(directory, decisions_path), "spreads": spreads(hist),
            "events": events(directory, decisions_path), "trade": trade(directory)}


def main() -> int:
    result = build()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)}: " + json.dumps({k: v["sample"]["n"] for k, v in result["events"].items()
                                                                   if isinstance(v, dict) and "sample" in v}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
