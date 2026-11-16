"""Блок E: формула коридора, ограничение по кредиту, регрессия курса, сверка браузерного движка с Python."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from _tolerance import same_within_float_tolerance
from src import carry_corridor as cc, site_i18n

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "src" / "site_assets" / "corridor.js"
CODES = {"коридор сломан": 0, "ниже коридора": 1, "выше коридора": 2, "внутри коридора": 3}


def _code(position: str) -> int:
    return next(code for prefix, code in CODES.items() if position.startswith(prefix))


def test_bounds_by_hand_and_breaking_point():
    out = cc.corridor(16.0, 9.0, {"Россия": 3.0, "Китай": 1.0}, premium=2.0, cap=6.0, credit_zero_real_rate=None)
    assert out["kz_real_rate"] == pytest.approx(7.0) and out["differentials"] == {"Россия": pytest.approx(4.0), "Китай": pytest.approx(6.0)}
    assert out["lower"] == pytest.approx(14.0) and out["upper"] == pytest.approx(18.0) and out["position"] == "внутри коридора"
    broken = cc.corridor(16.0, 9.0, {"Россия": 3.0}, premium=2.0, cap=6.0, credit_zero_real_rate=1.0)
    assert broken["upper"] == pytest.approx(10.0) and broken["binding_upper"] == "credit" and broken["position"].startswith("коридор сломан")
    assert cc.corridor(16.0, 9.0, {"Россия": None}, 2.0, 6.0, None)["status"].startswith("UNKNOWN")


def test_credit_constraint_is_used_only_when_the_slope_is_negative():
    x = np.linspace(0, 10, 60)
    frame = pd.DataFrame({"real_rate": x, "credit_growth_lead": 10 - 2 * x})
    assert cc.credit_constraint(frame)["credit_zero_real_rate"] == pytest.approx(5.0)
    assert cc.credit_constraint(frame.assign(credit_growth_lead=1 + 0.5 * x))["credit_zero_real_rate"] is None


def test_monthly_inputs_are_ordered_and_complete_before_shifting():
    frame = cc.monthly_inputs()
    assert frame.index.is_monotonic_increasing
    assert len(frame) == len(pd.period_range(frame.index.min(), frame.index.max(), freq="M"))
    corporate_last = frame["corporate"].dropna().index.max()
    assert frame["credit_growth_lead"].dropna().index.max() == corporate_last - cc.CREDIT_LEAD_MONTHS


def test_fx_regression_finds_a_planted_link_and_allows_no_link():
    rng = np.random.default_rng(0)
    index = pd.period_range("2015-01", periods=120, freq="M")
    differential = pd.Series(rng.normal(3, 2, 120), index=index)
    fx = pd.Series(np.cumsum(-1.5 * differential.shift(1).fillna(0) + rng.normal(0, 0.5, 120)), index=index)
    assert cc.fx_regression(fx, differential)["verdict"].startswith("связь значима")
    noise = pd.Series(np.cumsum(rng.normal(0, 1, 120)), index=index)
    result = cc.fx_regression(noise, differential)
    assert result["status"] == "ok" and set(result["vif"]) == {"diff", "diff2"} and len(result["ovb_compass"]) >= 3


def _js_engine() -> list[str] | None:
    if shutil.which("node"):
        return ["node"]
    if shutil.which("cscript"):
        return ["cscript", "//nologo", "//E:JScript"]
    return None


def test_browser_engine_matches_python_to_1e6(tmp_path):
    engine = _js_engine()
    if engine is None:
        pytest.skip("no JavaScript engine (node or cscript) on this machine")
    rng = np.random.default_rng(7)
    cases = []
    for _ in range(40):
        partners = {"r": float(rng.uniform(-3, 8)), "c": None if rng.random() < 0.2 else float(rng.uniform(-2, 4))}
        cases.append((float(rng.uniform(5, 20)), float(rng.uniform(2, 15)), partners, float(rng.uniform(0, 4)),
                      float(rng.uniform(2, 8)), None if rng.random() < 0.5 else float(rng.uniform(0, 8))))
    literal = lambda v: "null" if v is None else repr(v)  # noqa: E731
    calls = "\n".join(
        f"res = corridor({literal(a)}, {literal(b)}, {{r: {literal(p['r'])}, c: {literal(p['c'])}}}, {literal(d)}, {literal(e)}, {literal(f)});"
        f" out(res.code + '|' + res.lower + '|' + res.upper + '|' + res.kzReal + '|' + res.label);" for a, b, p, d, e, f in cases)
    script = tmp_path / "parity.js"
    script.write_text(JS.read_text(encoding="utf-8") + "\nvar res; var out = (typeof console !== 'undefined') ? "
                      "function (s) { console.log(s); } : function (s) { WScript.Echo(s); };\n" + calls + "\n", encoding="utf-8")
    lines = [line for line in subprocess.run([*engine, str(script)], capture_output=True, text=True, check=True).stdout.splitlines() if line.strip()]
    assert len(lines) == len(cases)
    for (a, b, p, d, e, f), line in zip(cases, lines):
        code, lower, upper, kz_real, label = line.split("|")
        expected = cc.corridor(a, b, {"Россия": p["r"], "Китай": p["c"]}, d, e, f)
        assert int(code) == _code(expected["position"])
        assert label == site_i18n.tr(expected["position"])  # the site shows the English version of the Python label (D41)
        assert float(lower) == pytest.approx(expected["lower"], abs=1e-6) and float(upper) == pytest.approx(expected["upper"], abs=1e-6)
        assert float(kz_real) == pytest.approx(expected["kz_real_rate"], abs=1e-6)


def test_artifact_block_reports_unknown_partners_honestly():
    block = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))["carry_corridor"]
    assert same_within_float_tolerance(block, json.loads(json.dumps(cc.build())))  # floats: D38
    partners = block["partner_real_rates"]
    if None in partners.values():  # D46: bounds only from both partners, never from one
        assert block["current"]["status"].startswith("UNKNOWN") and block["current"]["lower"] is None
        assert all(row["lower"] is None for row in block["premium_sensitivity"])
    else:
        assert block["current"]["status"] == "ok" and block["current"]["lower"] is not None
    has_fx = not cc.external_data.read_raw("usd_kzt").empty
    if has_fx and any(v is not None for v in partners.values()):
        assert block["fx_regression"]["status"] == "ok" or block["fx_regression"]["status"].startswith("не запускалась: выборка")
        for key, item in block["fx_regression"].get("by_partner", {}).items():  # D47: one regression per partner
            assert item["status"] == "ok" or item["status"].startswith("не запускалась"), key
            assert (item["status"] == "ok") == (partners[key] is not None and item.get("specifications", {}).get("lag1", {}).get("n", 0) >= cc.MIN_FX_MONTHS)
    else:
        assert block["fx_regression"]["status"].startswith("UNKNOWN")
    for key, value in partners.items():  # a partner's real rate is reported with its month or with an UNKNOWN note
        assert block["partner_notes"][key].startswith("месяц " if value is not None else "UNKNOWN")


# ----------------------------------------------------------------------------- D46: empty, partial and full partner data


def _write_external(directory: Path, filled: set[str]) -> None:
    """Header-only templates in `directory`; series in `filled` get synthetic monthly data (2020-01 … 2022-12)."""
    config = cc.external_data.sources()
    months = pd.period_range("2020-01", "2022-12", freq="M")
    for name, spec in config.items():
        lines = [",".join(spec["columns"])]
        if name in filled:
            if spec["columns"][0] == "year_month":
                lines += [f"{m},{3.0 + (i % 5) * 0.1:.2f}" for i, m in enumerate(months)]
            else:
                days = pd.date_range("2020-01-01", "2022-12-31", freq="D")
                lines += [f"{d.date()},{(10.0 if name.endswith('rate') or 'rate' in spec['columns'][1] else 450.0) + (d.month % 3):.2f}"
                          for d in days]
        (directory / spec["file"]).write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_partner_real_rates_for_empty_partial_and_full_data(tmp_path):
    _write_external(tmp_path, set())
    rates, notes = cc.partner_real_rates(tmp_path)
    assert rates == {"russia": None, "china": None} and all(n.startswith("UNKNOWN") for n in notes.values())

    _write_external(tmp_path, {"ru_key_rate", "ru_cpi_yoy"})
    series, notes = cc.partner_real_series(tmp_path)
    assert len(series["russia"]) and not len(series["china"]) and notes["russia"] == f"месяц {series['russia'].index[-1]}"
    assert "cn_policy_rate_daily.csv" in notes["china"] and "cn_cpi_yoy.csv" in notes["china"]
    # monthly real rate = calendar-day mean of the daily rate minus CPI y/y of the same month
    month = series["russia"].index[-1]
    rate = cc.external_data.monthly_step_rate(cc.external_data.read_raw("ru_key_rate", tmp_path))[month]
    cpi = cc.external_data.cpi_yoy(cc.external_data.read_raw("ru_cpi_yoy", tmp_path), "cpi_yoy_pct")["yoy"][month]
    assert series["russia"][month] == pytest.approx(rate - cpi)

    _write_external(tmp_path, {"ru_key_rate", "ru_cpi_yoy", "cn_policy_rate", "cn_cpi_yoy"})
    rates, _ = cc.partner_real_rates(tmp_path)
    assert all(v is not None for v in rates.values())


def test_corridor_bounds_need_both_partners():
    # The engine itself is general (the site uses it with assumed values); build() withholds partners until both exist.
    partial = cc.corridor(16.0, 9.0, {}, 2.0, 6.0, None)
    assert partial["lower"] is None and partial["status"].startswith("UNKNOWN")
    block = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))["carry_corridor"]
    if sum(v is not None for v in block["partner_real_rates"].values()) == 1:
        assert block["current"]["status"].startswith("UNKNOWN: нет реальной ставки")
        assert set(block["real_differentials"]) == {k for k, v in block["partner_real_rates"].items() if v is not None}


def test_fx_block_without_fx_data_or_partners_is_unknown(monkeypatch):
    frame = cc.monthly_inputs()
    monkeypatch.setattr(cc, "usd_kzt_monthly", lambda directory=None: pd.Series(dtype=float))
    assert cc.fx_block(frame, {"russia": pd.Series([1.0], index=pd.period_range("2020-01", periods=1, freq="M"))})["status"].startswith("UNKNOWN")
    monkeypatch.setattr(cc, "usd_kzt_monthly", lambda directory=None: pd.Series([1.0, 2.0], index=pd.period_range("2020-01", periods=2, freq="M")))
    assert cc.fx_block(frame, {"russia": pd.Series(dtype=float), "china": pd.Series(dtype=float)})["status"].startswith("UNKNOWN")


def test_fx_regression_on_a_short_sample_is_not_run_and_says_why():
    index = pd.period_range("2025-01", periods=cc.MIN_FX_MONTHS, freq="M")
    result = cc.fx_regression(pd.Series(np.arange(len(index), dtype=float), index=index), pd.Series(1.0, index=index))
    assert result["status"].startswith("не запускалась: выборка слишком короткая") and result["n"] < cc.MIN_FX_MONTHS
    assert site_i18n.tr(result["status"]).startswith("not run: sample too short")
