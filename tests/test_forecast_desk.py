"""Блок D: cutoff, горизонты, AR(1), y/y из m/m, ловушки, журнал прогнозов."""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import forecast_desk as fd
from src import traps

ROOT = Path(__file__).resolve().parents[1]


def _series(n: int = 100, seed: int = 1) -> pd.Series:
    rng = np.random.default_rng(seed)
    y = [5.0]
    for _ in range(n - 1):
        y.append(1.0 + 0.8 * y[-1] + rng.normal(0, 0.3))
    return pd.Series(y, index=pd.period_range("2015-01", periods=n, freq="M"), name="synthetic")


@pytest.mark.parametrize("method", ["naive", "seasonal_naive", "mean12", "ar1", "ses", "holt_damped", "arima_110"])
def test_values_after_cutoff_do_not_move_the_forecast(method):
    series = _series()
    cutoff = series.index[70]
    changed = series.copy()
    changed[changed.index > cutoff] += 1000.0
    a, b = fd.forecast(series, cutoff, 3, method), fd.forecast(changed, cutoff, 3, method)
    assert a["point"] == pytest.approx(b["point"]) and a["n_used"] == 71
    assert a["target_months"] == [str(cutoff + i) for i in (1, 2, 3)]


def test_any_horizon_gives_a_point_and_an_ordered_interval():
    out = fd.forecast(_series(), "2022-06", 7, "ar1")
    assert len(out["point"]) == 7
    assert all(lo < p < hi for lo, p, hi in zip(out["lower_80"], out["point"], out["upper_80"]))
    widths = np.subtract(out["upper_80"], out["lower_80"])
    assert all(a <= b + 1e-12 for a, b in zip(widths, widths[1:])), "interval widens with the horizon"


def test_ar1_parameters_and_half_life_in_words():
    params = fd.ar1_parameters(_series(2000, seed=3).to_numpy())
    assert params["phi"] == pytest.approx(0.8, abs=0.03) and params["mean"] == pytest.approx(5.0, abs=0.2)
    assert params["half_life_months"] == pytest.approx(math.log(0.5) / math.log(params["phi"]))
    assert "уменьшается вдвое" in fd.half_life_words(params)


def test_yoy_from_mom_and_required_mom_arithmetic():
    assert fd.yoy_from_mom([1.0] * 12) == pytest.approx((1.01 ** 12 - 1) * 100)
    known = [1.0] * 9
    required = fd.required_mom_for_year_end(known, 12.0)
    assert (1.01 ** 9) * (1 + required / 100) ** 3 == pytest.approx(1.12)
    with pytest.raises(ValueError):
        fd.yoy_from_mom([1.0] * 11)


def test_aicc_is_compared_only_within_the_same_d():
    report = fd.differencing_report(_series(120))
    for d in {m["d"] for m in report["models"].values()}:
        group = [m for m in report["models"].values() if m["d"] == d and m["aicc"] is not None]
        assert sum(m["chosen_within_d"] for m in group) == 1
        assert min(m["delta_aicc"] for m in group) == pytest.approx(0.0)


def test_traps_pass_on_the_committed_desk_and_catch_a_planted_leak(tmp_path):
    assert traps.run() == []
    shutil.copytree(fd.OUT_DIR, tmp_path / "desk")
    path = tmp_path / "desk" / "backtest_inflation_yoy.csv"
    frame = pd.read_csv(path, dtype={"origin": str, "target_month": str})
    frame.loc[(frame["method"] == "naive") & (frame["h"] == 1), "point"] += 0.5  # как если бы точка знала будущее
    frame.to_csv(path, index=False)
    assert any(p.startswith("1 full-sample") for p in traps.run(out_dir=tmp_path / "desk", samples=50))


def test_forecast_ledger_is_append_only_without_duplicates(tmp_path):
    row = {"run_utc": "2026-11-13T00:00:00+00:00", "series": "s", "cutoff": "2026-09", "h": 1, "target_month": "2026-10",
           "method": "naive", "point": "1", "lower_80": "0", "upper_80": "2", "interval_method": "model formula",
           "candidates_sha256": "abc", "status": "ok"}
    path = tmp_path / "ledger.csv"
    assert fd.append_forecast_ledger([row], path) == 1
    before = path.read_text(encoding="utf-8")
    assert fd.append_forecast_ledger([row, {**row, "h": 2, "target_month": "2026-11"}], path) == 1
    assert path.read_text(encoding="utf-8").startswith(before)


def test_desk_records_models_windows_label_and_frozen_hash():
    desk = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))["forecast_desk"]
    frozen = json.loads((ROOT / "prereg" / "freeze.json").read_text(encoding="utf-8"))["sha256"]["candidates.json"]
    assert desk["candidates_sha256"] == frozen and desk["label"] == "revised-data backtest"
    assert desk["models_tried"] == len(json.loads(fd.CANDIDATES_PATH.read_text(encoding="utf-8"))["candidates"])
    assert desk["series"]["usd_kzt"]["status"].startswith("UNKNOWN") or desk["series"]["usd_kzt"]["status"] == "ok"
    for name, result in desk["series"].items():
        if result.get("status") == "ok":
            assert result["first_origin_observations"] >= 60 and result["n_observations"] >= 60
