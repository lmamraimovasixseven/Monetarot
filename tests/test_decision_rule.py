"""Блок A: порог из функции потерь (ручной расчёт, монотонность) и согласованность артефакта."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from _tolerance import same_within_float_tolerance
from src import decision_rule as dr

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("false_cost, miss_cost, manual", [(1.0, 1.0, 0.5), (1.0, 3.0, 0.25), (2.0, 0.5, 0.8)])
def test_threshold_matches_the_hand_calculation(false_cost, miss_cost, manual):
    assert dr.binary_threshold(false_cost, miss_cost) == pytest.approx(manual)
    # на пороге ожидаемые потери двух действий равны
    p = dr.binary_threshold(false_cost, miss_cost)
    assert (1 - p) * false_cost == pytest.approx(p * miss_cost)


def test_threshold_decreases_as_a_missed_cut_gets_more_expensive():
    values = [row["threshold"] for row in dr.sensitivity([0.25, 0.5, 1, 2, 4, 8])]
    assert all(a > b for a, b in zip(values, values[1:]))
    with pytest.raises(ValueError):
        dr.binary_threshold(0.0, 0.0)


def test_best_action_follows_expected_losses():
    matrix = dr.load_losses()["loss_matrix"]
    assert dr.best_action({"Decrease": 0.9, "Hold": 0.1, "Increase": 0.0}, matrix) == "lengthen"
    assert dr.best_action({"Decrease": 0.0, "Hold": 0.1, "Increase": 0.9}, matrix) == "shorten"
    assert dr.best_action({"Decrease": 0.2, "Hold": 0.6, "Increase": 0.2}, matrix) == "keep"
    losses = dr.expected_losses({"Decrease": 0.5, "Hold": 0.5, "Increase": 0.0}, matrix)
    assert losses["lengthen"] == pytest.approx(0.5) and losses["keep"] == pytest.approx(0.5)


def test_artifact_and_memo_hold_the_current_rule():
    artifact = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))
    assert same_within_float_tolerance(artifact["decision"], json.loads(json.dumps(dr.build())))  # floats: D38
    memo = (ROOT / "docs" / "decision_memo.md").read_text(encoding="utf-8")
    assert f"{artifact['decision']['binary_threshold_p_cut']:.3f}" in memo
    assert "ждёт подтверждения человека" in memo and "допущение пользователя" in memo.lower()
