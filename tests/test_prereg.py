"""Блок F: заморозка, prereg-check, Reality Check (ручной расчёт) и оценка после решения."""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from src import prereg

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_files_are_unchanged_in_the_repository():
    assert prereg.check() == []


def test_check_fails_after_a_frozen_file_is_edited(tmp_path):
    for name in prereg.FROZEN_FILES:
        shutil.copy(ROOT / "prereg" / name, tmp_path / name)
    record = prereg.freeze(tmp_path, today=date(2026, 11, 13))
    assert prereg.freeze(tmp_path, today=date(2030, 1, 1)) == record, "an existing freeze is never overwritten"
    assert prereg.check(tmp_path) == []
    (tmp_path / "candidates.json").write_text("{}", encoding="utf-8")
    assert prereg.check(tmp_path) and "candidates.json changed" in prereg.check(tmp_path)[0]


def test_rate_distribution_and_quantiles_by_hand():
    steps = {"Decrease": {-0.5: 0.5, -0.25: 0.5}, "Hold": {0.0: 1.0}, "Increase": {0.25: 1.0}}
    dist = prereg.rate_distribution(10.0, {"Decrease": 0.2, "Hold": 0.7, "Increase": 0.1}, steps)
    assert dist == [(9.5, pytest.approx(0.1)), (9.75, pytest.approx(0.1)), (10.0, pytest.approx(0.7)), (10.25, pytest.approx(0.1))]
    assert sum(p for _, p in dist) == pytest.approx(1.0)
    assert prereg.quantile(dist, 0.1) == 9.5 and prereg.quantile(dist, 0.5) == 10.0 and prereg.quantile(dist, 0.9) == 10.0


def test_pinball_and_scoring_by_hand():
    assert prereg.pinball(10.0, 9.5, 0.9) == pytest.approx(0.45)
    assert prereg.pinball(9.0, 9.5, 0.9) == pytest.approx(0.05)
    block = {"probabilities": {"Decrease": 0.2, "Hold": 0.7, "Increase": 0.1}, "interval_80": [9.5, 10.0],
             "median_rate": 10.0, "benchmark_always_hold": 10.0}
    score = prereg.score_reality_check(block, 9.75, "Decrease")
    assert score["inside_80"] and score["rps_model"] == pytest.approx(((0.2 - 1) ** 2 + (0.9 - 1) ** 2) / 2)
    assert score["rps_always_hold"] == pytest.approx(0.5)


def test_artifact_holds_the_current_reality_check_linked_to_the_logged_forecast():
    artifact = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))
    fresh = json.loads(json.dumps(prereg.reality_check()))
    assert artifact["reality_check"] == fresh
    assert fresh["linked_forecast_log_row"]["target_decision_date"] == prereg.TARGET_DATE
    low, high = fresh["interval_80"]
    assert low <= fresh["median_rate"] <= high and artifact["prereg"]["unchanged"] is True
