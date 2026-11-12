"""Data contract: what every data update must satisfy (added 2026-11-12, docs/deviations.md D28).

Nothing here uses a literal count or date. Expected values are recomputed from data/raw, the decision
calendar, the processed panels and model/artifact.json, so the tests keep passing when months or
decisions are appended correctly and fail when an update breaks a rule.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import data_screen, facts, ingest


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RAW_FILES = sorted(p.name for p in RAW.glob("*.csv"))
VALUE_COLUMNS = {filename: column for filename, column in ingest.FEATURE_RULES.values()} | {"base_rate_history.csv": "rate"}
CALENDAR = ROOT / "config" / "nbk_decision_dates.csv"
ARTIFACT = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))


def _months(frame: pd.DataFrame) -> pd.PeriodIndex:
    return pd.PeriodIndex(pd.to_datetime(frame["year_month"], format="%Y-%m", errors="raise"), freq="M")


def test_every_raw_file_is_known_to_the_pipeline():
    assert set(RAW_FILES) == set(VALUE_COLUMNS)


@pytest.mark.parametrize("name", RAW_FILES)
def test_raw_file_has_year_month_and_one_numeric_column(name):
    frame = pd.read_csv(RAW / name, dtype=str, keep_default_na=False)
    assert frame.columns.tolist() == ["year_month", VALUE_COLUMNS[name]]
    values = pd.to_numeric(frame[VALUE_COLUMNS[name]], errors="coerce")
    bad = frame.loc[values.isna(), "year_month"].tolist()
    assert not bad, f"{name}: empty or non-numeric values in months {bad}"
    assert np.isfinite(values).all()


@pytest.mark.parametrize("name", RAW_FILES)
def test_raw_months_strictly_increase_without_duplicates_or_gaps(name):
    months = _months(pd.read_csv(RAW / name, dtype=str))
    assert not months.has_duplicates, f"{name}: duplicate months"
    assert months.is_monotonic_increasing, f"{name}: months out of order"
    expected = pd.period_range(months.min(), months.max(), freq="M")
    missing = sorted(str(m) for m in set(expected) - set(months))
    assert not missing, f"{name}: missing months {missing}"


@pytest.mark.parametrize("name", RAW_FILES)
def test_units_in_the_form_agree_with_the_column_name(name):
    form = facts.load_series_facts(ROOT / "docs" / "facts_to_fill.csv", RAW_FILES, date.today())
    verdict = facts.unit_check(RAW, name, form[name]["unit"])["verdict"]
    assert "CONFLICT" not in verdict and "UNKNOWN" not in verdict, f"{name}: {verdict}"


def test_decision_calendar_is_sorted_unique_and_dates_only():
    calendar = pd.read_csv(CALENDAR, dtype=str)
    assert calendar.columns.tolist() == ["decision_date"]
    dates = pd.to_datetime(calendar["decision_date"], format="%Y-%m-%d", errors="raise")
    assert not dates.duplicated().any()
    assert dates.is_monotonic_increasing


def test_every_decision_is_in_the_panel_and_missing_reference_months_are_reported_as_dropped():
    calendar = pd.to_datetime(pd.read_csv(CALENDAR)["decision_date"])
    panel = pd.read_csv(ROOT / "data" / "processed" / "model_panel.csv", parse_dates=["decision_date"])
    assert panel["decision_date"].tolist() == calendar.tolist()
    complete = panel.dropna(subset=list(ingest.FEATURE_RULES) + ["y"])
    dropped = sorted(set(panel["decision_date"]) - set(complete["decision_date"]))
    sample = ARTIFACT["sample"]
    assert sample["usable_n"] == len(complete)
    assert sample["dropped_n"] == len(dropped)
    assert sample["dropped_decisions"] == [d.strftime("%Y-%m-%d") for d in dropped]
    # A decision whose reference month exists in every raw file (and, for growth factors, twelve months
    # earlier too) must be usable; one whose reference month is missing must be reported as dropped.
    lag = ingest.ASSUMED_LAG_MONTHS
    for when in calendar:
        reference = when.to_period("M") - lag
        needed = True
        for feature, (filename, _) in ingest.FEATURE_RULES.items():
            months = set(_months(pd.read_csv(RAW / filename, dtype=str)))
            needed &= reference in months
            if feature in ingest.LOG_GROWTH_FEATURES:
                needed &= (reference - 12) in months
        assert (when in set(complete["decision_date"])) == needed, when.date()


def test_holdout_is_the_last_ceil_twenty_percent_of_usable_decisions():
    sample = ARTIFACT["sample"]
    assert sample["holdout_n"] == math.ceil(0.2 * sample["usable_n"])
    assert sample["estimation_n"] + sample["holdout_n"] == sample["usable_n"]
    panel = pd.read_csv(ROOT / "data" / "processed" / "model_panel.csv")
    usable = panel.dropna(subset=list(ingest.FEATURE_RULES) + ["y"])["decision_date"].tolist()
    assert sample["holdout_start"] == usable[sample["estimation_n"]]
    assert sample["holdout_end"] == usable[-1] == sample["usable_end"]
    assert sample["estimation_end"] == usable[sample["estimation_n"] - 1]


def test_processed_panels_equal_a_fresh_rebuild(tmp_path):
    decisions = tmp_path / "nbk_decisions_clean.csv"
    model_panel = tmp_path / "model_panel.csv"
    ingest.build_panel(output_path=decisions)
    ingest.build_model_panel(panel_path=decisions, output_path=model_panel)
    for rebuilt, committed in ((decisions, "nbk_decisions_clean.csv"), (model_panel, "model_panel.csv")):
        left = pd.read_csv(ROOT / "data" / "processed" / committed)
        right = pd.read_csv(rebuilt)
        pd.testing.assert_frame_equal(left, right, check_exact=False, atol=1e-8, rtol=0)


def test_data_screen_output_matches_a_fresh_screen():
    committed = json.loads((ROOT / "data" / "processed" / "data_anomalies.json").read_text(encoding="utf-8"))
    fresh = data_screen.build_screen()
    assert committed == json.loads(json.dumps(fresh))
    assert committed["latest_decision"] == ARTIFACT["sample"]["usable_end"]


# ----------------------------------------------------------------- append-only guard


def _git(*args: str) -> subprocess.CompletedProcess | None:
    if not (ROOT / ".git").exists() or shutil.which("git") is None:
        return None
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True)


def _rows(text: str) -> list[str]:
    return [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]


APPEND_ONLY = ([f"data/raw/{name}" for name in RAW_FILES]
               + ["config/nbk_decision_dates.csv", "docs/nbk_announcement_dates.csv", "docs/forecast_log.csv"])


@pytest.mark.parametrize("relative", APPEND_ONLY)
def test_raw_data_is_append_only_against_git_head(relative):
    """Every row committed at HEAD must still be present, unchanged and in the same position."""
    if _git("rev-parse", "--verify", "HEAD") is None:
        pytest.skip("not a git checkout (e.g. a Download ZIP copy): nothing to compare against")
    shown = _git("show", f"HEAD:{relative}")
    if shown.returncode != 0:
        pytest.skip(f"{relative} is not in HEAD yet (a new file)")
    problems = append_only_violations(shown.stdout.decode("utf-8"), (ROOT / relative).read_text(encoding="utf-8"))
    assert not problems, f"{relative}: {problems}"


def append_only_violations(old_text: str, new_text: str) -> list[str]:
    old, new = _rows(old_text), _rows(new_text)
    problems = [f"line {i + 1} changed: {a!r} -> {b!r}" for i, (a, b) in enumerate(zip(old, new)) if a != b][:5]
    if len(new) < len(old):
        problems.append(f"{len(old) - len(new)} committed rows disappeared")
    return problems


def test_append_only_guard_detects_edits_and_deletions_but_allows_appends():
    lines = ["year_month,x", "2026-06,1.0", "2026-07,2.0"]
    old = "\n".join(lines)  # committed file without a final newline
    assert append_only_violations(old, "\n".join(lines + ["2026-08,3.0"]) + "\n") == []
    assert append_only_violations("\r\n".join(lines), old + "\n") == []
    assert append_only_violations(old, "\n".join(["year_month,x", "2026-06,1.5", "2026-07,2.0"]))
    assert append_only_violations(old, "\n".join(lines[:2]))
    assert append_only_violations(old, "\n".join([lines[0], lines[2], lines[1]]))


