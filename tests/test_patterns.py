"""Блок C: тест сезонности (ответ «нет» возможен), окно STL, типы выбросов, просмотр на дату t."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import patterns

ROOT = Path(__file__).resolve().parents[1]


def _monthly(values: np.ndarray, start: str = "2015-01") -> pd.Series:
    return pd.Series(values, index=pd.period_range(start, periods=len(values), freq="M"))


def test_seasonality_yes_for_a_seasonal_series_and_no_for_noise():
    rng = np.random.default_rng(1)
    months = np.tile(np.arange(12), 10)
    seasonal = _monthly(np.where(months == 0, -8.0, 1.0) + rng.normal(0, 1, 120))
    assert patterns.seasonality_test(seasonal, draws=199)["verdict"] == "да"
    noise = patterns.seasonality_test(_monthly(rng.normal(0, 1, 120)), draws=199)
    assert noise["verdict"] in ("нет", "слабо") and noise["p_permutation"] >= 0.05


def test_permutation_test_is_reproducible_with_the_fixed_seed():
    rng = np.random.default_rng(2)
    series = _monthly(rng.normal(0, 1, 96))
    assert patterns.seasonality_test(series, draws=99) == patterns.seasonality_test(series, draws=99)


def test_stl_window_is_chosen_from_revisions_and_the_band_contains_the_value():
    rng = np.random.default_rng(3)
    months = np.tile(np.arange(12), 9)
    series = _monthly(3 * np.sin(2 * np.pi * months / 12) + rng.normal(0, 0.5, 108))
    block = patterns.choose_stl_window(series)
    assert block["chosen_window"] in patterns.STL_WINDOWS
    best = min(v["mean_abs_revision"] for v in block["windows"].values())
    assert block["windows"][str(block["chosen_window"])]["mean_abs_revision"] == best


def _flag(month: str, z: float = 5.0) -> dict:
    return {"series_file": "x.csv", "month": month, "modified_z": z}


def test_outlier_types_and_episode_grouping():
    base = np.full(60, 100.0)
    levels = _monthly(base.copy(), "2020-01")
    shifted = levels.copy(); shifted.iloc[30:] = 150.0
    assert patterns.classify_flags([_flag("2022-07")], shifted)[0]["type"] == "level_shift"
    single = levels.copy(); single.iloc[30] = 150.0
    assert patterns.classify_flags([_flag("2022-07")], single)[0]["type"] == "single"
    temporary = levels.copy(); temporary.iloc[30:33] = 150.0
    episode = patterns.classify_flags([_flag("2022-07"), _flag("2022-08"), _flag("2022-09")], temporary)
    assert len(episode) == 1 and episode[0]["months"] == 3 and episode[0]["type"] == "temporary_episode"
    januaries = [_flag(f"{y}-01") for y in (2020, 2021, 2022)]
    assert {e["type"] for e in patterns.classify_flags(januaries, levels)} == {"seasonal_break"}
    assert all(e["action"] == "помечено, не удалено" and e["known_at"] for e in episode)


def test_as_of_view_shows_only_what_was_known_at_t():
    episodes = patterns.outlier_episodes()
    view = patterns.as_of_view("2024-09-02", episodes)
    assert all(pd.Timestamp(e["known_at"]) <= pd.Timestamp("2024-09-02") for e in view["episodes"])
    assert all(s["last_month"] <= "2024-07" for s in view["series"].values() if s["last_month"])
    later = patterns.as_of_view("2026-10-27", episodes)
    assert len(later["episodes"]) >= len(view["episodes"])


def test_artifact_and_decisions_doc_agree():
    block = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))["patterns"]
    assert (ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8") == patterns.decisions_markdown(block["stl"])
    assert {v["verdict"] for v in block["seasonality"].values()} <= {"да", "нестабильно", "слабо", "нет"}
    assert "нет" in {v["verdict"] for v in block["seasonality"].values()}, "the test can answer no (inflation y/y)"
