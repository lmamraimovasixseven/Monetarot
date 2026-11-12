"""Forecast log (docs/development_plan.md): log before the decision, never after; score once decided."""

from __future__ import annotations

import csv
import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src import forecast_log as fl


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def files(tmp_path):
    shutil.copy(ROOT / "model" / "artifact.json", tmp_path / "artifact.json")
    shutil.copytree(ROOT / "data" / "raw", tmp_path / "raw")
    shutil.copy(ROOT / "config" / "nbk_decision_dates.csv", tmp_path / "calendar.csv")
    (tmp_path / "rounds.json").write_text(json.dumps({"verified": True, "rounds": [
        {"date": "2030-01-10"}, {"date": "2030-03-07"}]}), encoding="utf-8")
    return tmp_path


def _log(files, now, **kwargs):
    return fl.append_forecast(now=now, log_path=files / "log.csv", artifact_path=files / "artifact.json",
                              rounds_path=files / "rounds.json", calendar_path=files / "calendar.csv",
                              raw_dir=files / "raw", root=files, **kwargs)


def test_log_records_the_artifact_forecast_hashes_and_the_next_future_round(files):
    entry = _log(files, datetime(2029, 12, 1, 12, 0, tzinfo=timezone.utc))
    artifact = json.loads((files / "artifact.json").read_text(encoding="utf-8"))
    assert entry["target_decision_date"] == "2030-01-10"
    assert entry["based_on_decision"] == artifact["latest_prediction"]["date"]
    for name in fl.CLASS_ORDER:
        assert float(entry[f"p_{name.lower()}"]) == pytest.approx(artifact["latest_prediction"]["class_probabilities"][name], abs=1e-6)
    assert float(entry["expected_score"]) == pytest.approx(artifact["latest_prediction"]["expected_score"], abs=1e-6)
    assert entry["artifact_sha256"] == fl.normalized_sha256(files / "artifact.json")
    assert entry["data_sha256"] == fl.data_sha256(files / "raw", files / "calendar.csv")
    assert entry["git_commit"] == "UNKNOWN"  # the temporary folder is not a git checkout
    with (files / "log.csv").open(encoding="utf-8", newline="") as handle:
        assert list(csv.DictReader(handle)) == [entry]


def test_log_refuses_late_duplicate_and_already_decided_forecasts(files):
    now = datetime(2029, 12, 1, tzinfo=timezone.utc)
    _log(files, now)
    with pytest.raises(fl.ForecastLogError, match="already logged"):
        _log(files, now)
    with pytest.raises(fl.ForecastLogError, match="too late"):
        _log(files, now, target=date(2029, 12, 1))
    calendar = (files / "calendar.csv").read_text(encoding="utf-8").rstrip("\n") + "\n2030-03-10\n"
    (files / "calendar.csv").write_text(calendar, encoding="utf-8")
    with pytest.raises(fl.ForecastLogError, match="already in the decision calendar"):
        _log(files, now, target=date(2030, 3, 7))


def test_logging_appends_and_never_rewrites_earlier_rows(files):
    first = _log(files, datetime(2029, 12, 1, tzinfo=timezone.utc))
    before = (files / "log.csv").read_text(encoding="utf-8")
    second = _log(files, datetime(2030, 2, 1, tzinfo=timezone.utc))
    after = (files / "log.csv").read_text(encoding="utf-8")
    assert after.startswith(before) and first["target_decision_date"] != second["target_decision_date"]


def test_scoring_matches_the_effective_date_and_computes_rps_squared_error_and_hit(files, tmp_path):
    _log(files, datetime(2029, 12, 1, tzinfo=timezone.utc))
    decisions = tmp_path / "decisions.csv"
    decisions.write_text("decision_date,decision\n2029-11-01,Hold\n2030-01-13,Decrease\n", encoding="utf-8")
    summary = fl.score_log(files / "log.csv", decisions)
    assert summary["n_logged"] == 1 and summary["n_scored"] == 1
    row = summary["scored"][0]
    entry = fl.read_log(files / "log.csv")[0]
    probs = [float(entry[f"p_{n.lower()}"]) for n in fl.CLASS_ORDER]
    assert row["effective_date"] == "2030-01-13" and row["actual"] == "Decrease"
    assert row["rps_model"] == pytest.approx(((probs[0] - 1) ** 2 + (probs[0] + probs[1] - 1) ** 2) / 2)
    assert row["rps_always_hold"] == pytest.approx(0.5)
    assert row["squared_error_model"] == pytest.approx((float(entry["expected_score"]) + 1) ** 2)
    assert row["hit"] == (max(probs) == probs[0])
    assert summary["rmse_always_hold"] == pytest.approx(1.0)


def test_unscored_forecast_is_reported_but_not_scored(files, tmp_path):
    _log(files, datetime(2029, 12, 1, tzinfo=timezone.utc))
    decisions = tmp_path / "decisions.csv"
    decisions.write_text("decision_date,decision\n2029-11-01,Hold\n", encoding="utf-8")
    summary = fl.score_log(files / "log.csv", decisions)
    assert summary["n_logged"] == 1 and summary["n_scored"] == 0 and "rmse_model" not in summary


def test_committed_log_is_consistent_with_the_committed_scores():
    log = ROOT / "docs" / "forecast_log.csv"
    if not log.is_file():
        pytest.skip("no forecast logged yet")
    rows = fl.read_log(log)
    for row in rows:
        assert row["logged_at_utc"][:10] < row["target_decision_date"], "a forecast must be logged before its date"
    committed = json.loads((ROOT / "data" / "processed" / "forecast_scores.json").read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(fl.score_log(log)))
