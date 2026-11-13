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
from src import carry_corridor as cc

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
        f" out(res.code + '|' + res.lower + '|' + res.upper + '|' + res.kzReal);" for a, b, p, d, e, f in cases)
    script = tmp_path / "parity.js"
    script.write_text(JS.read_text(encoding="utf-8") + "\nvar res; var out = (typeof console !== 'undefined') ? "
                      "function (s) { console.log(s); } : function (s) { WScript.Echo(s); };\n" + calls + "\n", encoding="utf-8")
    lines = subprocess.run([*engine, str(script)], capture_output=True, text=True, check=True).stdout.split()
    assert len(lines) == len(cases)
    for (a, b, p, d, e, f), line in zip(cases, lines):
        code, lower, upper, kz_real = line.split("|")
        expected = cc.corridor(a, b, {"Россия": p["r"], "Китай": p["c"]}, d, e, f)
        assert int(code) == _code(expected["position"])
        assert float(lower) == pytest.approx(expected["lower"], abs=1e-6) and float(upper) == pytest.approx(expected["upper"], abs=1e-6)
        assert float(kz_real) == pytest.approx(expected["kz_real_rate"], abs=1e-6)


def test_artifact_block_reports_unknown_partners_honestly():
    block = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))["carry_corridor"]
    assert same_within_float_tolerance(block, json.loads(json.dumps(cc.build())))  # floats: D38
    if None in block["partner_real_rates"].values():
        assert block["current"]["status"].startswith("UNKNOWN") and block["fx_regression"]["status"].startswith("UNKNOWN")
