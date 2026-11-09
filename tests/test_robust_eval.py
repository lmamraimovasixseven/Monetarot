"""Tests for the exploratory robustness evaluation (src/robust_eval.py)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import robust_eval as re_


ROOT = Path(__file__).resolve().parents[1]


def test_rps_and_brier_known_values():
    perfect = np.array([[0.0, 1.0, 0.0]])
    assert re_.ordinal_rps(perfect, np.array([0]))[0] == 0
    # Always Hold scores 0.5 on a cut or a hike: one of the two cumulative splits is fully wrong.
    assert re_.ordinal_rps(perfect, np.array([-1]))[0] == pytest.approx(0.5)
    assert re_.ordinal_rps(perfect, np.array([1]))[0] == pytest.approx(0.5)
    # A confident hike forecast for a cut is the worst possible ordinal forecast.
    assert re_.ordinal_rps(np.array([[0.0, 0.0, 1.0]]), np.array([-1]))[0] == pytest.approx(1.0)
    assert re_.brier(np.array([[0.2, 0.5, 0.3]]), np.array([0]))[0] == pytest.approx(0.04 + 0.25 + 0.09)
    assert np.isinf(re_.log_loss(perfect, np.array([1]))[0])


def test_dm_test_signs_and_degenerate_cases():
    rng = np.random.default_rng(0)
    worse = rng.normal(1.0, 0.1, 40)
    better = rng.normal(0.5, 0.1, 40)
    result = re_.dm_test(better, worse)
    assert result["mean_loss_difference"] < 0 and result["p_value"] < 0.001
    assert re_.dm_test(np.ones(5), np.ones(5))["p_value"] is None  # zero variance
    assert re_.dm_test(np.ones(2), np.zeros(2))["p_value"] is None  # too few


def test_block_bootstrap_is_seeded_and_brackets_the_point_ratio():
    rng = np.random.default_rng(1)
    e1, e2 = rng.normal(size=30), rng.normal(size=30)
    first = re_.block_bootstrap_ratio(e1, e2, draws=2000)
    second = re_.block_bootstrap_ratio(e1, e2, draws=2000)
    assert first == second
    assert first["ci_low"] <= first["ratio"] <= first["ci_high"]


def test_unpenalized_fit_matches_statsmodels():
    from statsmodels.miscmodels.ordinal_model import OrderedModel

    panel = re_.build_robust_panel()
    usable = panel.dropna(subset=re_.MAIN_FEATURES + ["y"]).reset_index(drop=True).iloc[:70]
    ours = re_.fit_ordered_logit(usable, re_.MAIN_FEATURES)
    endog = pd.Categorical(usable.y.astype(int), categories=[-1, 0, 1], ordered=True)
    reference = OrderedModel(endog, usable[re_.MAIN_FEATURES].astype(float), distr="logit").fit(
        method="bfgs", maxiter=2000, disp=False, gtol=1e-8)
    assert np.allclose(ours["beta"], np.asarray(reference.params)[:6], atol=2e-3)
    probs_ours = re_.predict_ordered_logit(ours, usable)
    probs_ref = np.asarray(reference.predict(usable[re_.MAIN_FEATURES].astype(float)))
    assert np.allclose(probs_ours, probs_ref, atol=1e-3)


def test_ridge_shrinks_toward_class_frequencies():
    panel = re_.build_robust_panel()
    usable = panel.dropna(subset=re_.MAIN_FEATURES + ["y"]).reset_index(drop=True).iloc[:70]
    light = re_.fit_ordered_logit(usable, re_.MAIN_FEATURES, 1e-4)
    heavy = re_.fit_ordered_logit(usable, re_.MAIN_FEATURES, 1e6)
    assert np.abs(heavy["beta_standardized"]).max() < 1e-3 < np.abs(light["beta_standardized"]).max()
    frequencies = np.bincount(usable.y.to_numpy(dtype=int) + 1, minlength=3) / len(usable)
    assert np.allclose(re_.predict_ordered_logit(heavy, usable.iloc[[0]])[0], frequencies, atol=0.02)


def test_policy_rule_features_use_only_information_before_the_decision():
    panel = re_.build_robust_panel()
    # previous_decision is the previous row's outcome, never the current one
    assert panel.previous_decision.iloc[1:].to_numpy().tolist() == panel.y.iloc[:-1].to_numpy().tolist()
    # real rate uses the rate in force BEFORE the decision
    decisions = pd.read_csv(re_.DECISIONS_PATH)
    assert np.allclose(panel.real_rate + panel.inflation, decisions.base_rate_before, equal_nan=True)


def test_evaluation_never_uses_the_target_row(monkeypatch):
    panel = re_.build_robust_panel()
    usable = panel.dropna(subset=re_.MAIN_FEATURES + ["y"]).reset_index(drop=True)
    seen = []

    def spy(history, target):
        seen.append((history.decision_date.max(), target.decision_date.iloc[0]))
        return np.tile([0.2, 0.6, 0.2], (len(target), 1)), {}

    spec = {"id": "X", "kind": "benchmark", "forecaster": spy}
    re_._evaluate(spec, usable, list(range(40, 50)), refit=True)
    re_._evaluate(spec, usable, list(range(70, 75)), refit=False, origin=70)
    assert seen and all(history_end < target for history_end, target in seen)


def test_anomaly_screen_flags_an_injected_spike(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    for filename, _ in re_.FEATURE_RULES.values():
        (raw / filename).write_bytes((ROOT / "data" / "raw" / filename).read_bytes())
    filename, column = re_.FEATURE_RULES["imports"]
    frame = pd.read_csv(raw / filename)
    frame.loc[60, column] = frame.loc[60, column] * 5
    frame.to_csv(raw / filename, index=False)
    flags = re_.anomaly_screen(raw)
    assert any(f["feature"] == "imports" and f["month"] == frame.loc[60, "year_month"] for f in flags)


def test_committed_robust_artifact_is_consistent():
    artifact = json.loads(re_.ROBUST_ARTIFACT_PATH.read_text(encoding="utf-8"))
    assert artifact["reproduction_of_main_model"]["passes"]
    assert "after the holdout had been seen" in artifact["label"]
    designs = artifact["designs"]
    assert designs["rolling_origin_estimation_sample"]["last_date"] < designs["holdout_fixed_origin"]["first_date"]
    for design in designs.values():
        ids = [row["id"] for row in design["specifications"]]
        assert ids == ["B0", "B1", "B2", "M0", "M1", "P0", "P1"]
    for forecast in artifact["next_decision_forecasts"]["forecasts"]:
        assert sum(forecast["probabilities"].values()) == pytest.approx(1.0)
    markdown = (ROOT / "outputs" / "robust_evaluation.md").read_text(encoding="utf-8")
    assert markdown == re_.render_markdown(artifact)
