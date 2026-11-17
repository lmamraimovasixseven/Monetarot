"""Exploratory omitted-variable check (D50): results live outside the artifact and are traceable to the ledger."""

from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path

import pandas as pd
import pytest

from src import external_data, ovb_check, site_build
from src.artifact_extensions import EXTENSION_KEYS
from src.model import FEATURES

ROOT = Path(__file__).resolve().parents[1]
STORED = ROOT / "model" / "extensions" / "ovb_check.json"
ARTIFACT = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def stored() -> dict:
    return json.loads(STORED.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fresh() -> dict:
    return ovb_check._clean(ovb_check.run())


def _numbers(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _numbers(item, f"{path}/{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _numbers(item, f"{path}/{index}")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield path, value


def test_results_are_kept_outside_the_artifact():
    assert "ovb_check" not in ARTIFACT and not any(key.startswith("ovb") for key in ARTIFACT)
    assert not any(key.startswith("ovb") for key in EXTENSION_KEYS)


def test_same_sample_and_split_as_the_frozen_model(stored):
    panel = pd.read_csv(ROOT / "data" / "processed" / "model_panel.csv").dropna(subset=FEATURES + ["y"])
    sample = stored["sample"]
    assert sample["usable_n"] == len(panel) == ARTIFACT["sample"]["usable_n"]
    assert sample["holdout_n"] == math.ceil(0.2 * sample["usable_n"]) == ARTIFACT["sample"]["holdout_n"]
    assert sample["estimation_n"] + sample["holdout_n"] == sample["usable_n"]
    assert sample["holdout_start"] == ARTIFACT["sample"]["holdout_start"]


def test_frozen_fit_reproduces_the_artifact(stored):
    tolerance = ARTIFACT["replication_tolerance"]["coefficients_absolute"]
    for feature in FEATURES:
        assert abs(stored["specifications"]["frozen"]["coefficients"][feature]["estimate"]
                   - ARTIFACT["model"]["parameters"][feature]) <= tolerance
    assert abs(stored["specifications"]["frozen"]["holdout"]["rmse_ratio_to_always_hold"]
               - ARTIFACT["benchmark_comparison"]["rmse_ratio_model_to_hold"]) <= tolerance


def test_committed_results_equal_a_fresh_run(stored, fresh):
    tolerance = ARTIFACT["replication_tolerance"]["coefficients_absolute"]
    committed, rebuilt = dict(_numbers(stored)), dict(_numbers(fresh))
    assert committed.keys() == rebuilt.keys()
    for key, value in committed.items():
        assert abs(value - rebuilt[key]) <= tolerance * max(1.0, abs(value)), key


def test_summary_counts_follow_from_the_tables(stored):
    specs, changes, summary = stored["specifications"], stored["coefficient_changes"], stored["summary"]
    extended = [key for key in specs if key != "frozen"]
    flips = sum((specs[k]["coefficients"][f]["estimate"] > 0) != (specs["frozen"]["coefficients"][f]["estimate"] > 0)
                for k in extended for f in FEATURES)
    assert summary["sign_flips"] == flips == sum(r["sign_flip"] for rows in changes.values() for r in rows.values())
    assert summary["factor_comparisons"] == len(extended) * len(FEATURES)
    assert summary["controls_significant_after_holm"] == sum(specs[k]["wald_hc0"]["p_value_holm"] < stored["alpha"] for k in extended)
    frozen_meets = specs["frozen"]["holdout"]["rmse_ratio_to_always_hold"] < 1
    assert summary["holdout_conclusion_changes"] == sum(
        (specs[k]["holdout"]["rmse_ratio_to_always_hold"] < 1) != frozen_meets for k in extended)
    for key in extended:
        assert specs[key]["wald_hc0"]["p_value_holm"] >= specs[key]["wald_hc0"]["p_value"]
        assert specs[key]["wald_hc0"]["df"] == len(specs[key]["controls"]) == specs[key]["lr"]["df"]
        assert set(specs[key]["vif"]) == set(FEATURES) | set(specs[key]["controls"])
    assert stored["seed"] == ARTIFACT["seed"]


def test_ols_cross_check_signs_are_compared_with_the_ordered_logit(stored):
    ols, specs = stored["ols_cross_check"], stored["specifications"]
    for key, logit in (("six_factors", "frozen"), ("six_factors_plus_all_three", "plus_all_three")):
        assert ols[key]["n"] == stored["sample"]["estimation_n"]
        for feature in FEATURES:
            same = (ols[key]["coefficients"][feature]["estimate"] > 0) == (specs[logit]["coefficients"][feature]["estimate"] > 0)
            assert ols[key]["same_sign_as_ordered_logit"][feature] == int(same)


def test_controls_come_from_the_external_files_aligned_like_the_factors():
    config = external_data.sources()
    for name in ovb_check.CONTROLS:
        assert (external_data.EXTERNAL_DIR / config[name]["file"]).is_file()
        assert "omitted-variable" in config[name]["used_in"]
    panel = ovb_check.build_panel()
    monthly = ovb_check.control_series()
    last = panel.iloc[-1]
    month = last.decision_date.to_period("M") - ovb_check.ASSUMED_LAG_MONTHS
    for name, series in monthly.items():
        assert last[name] == pytest.approx(series[month])


def test_every_number_has_a_ledger_row(stored):
    with (ROOT / "ledger" / "evidence_ledger.csv").open(encoding="utf-8", newline="") as handle:
        ids = {row["id"] for row in csv.DictReader(handle)}
    assert {f"ovb:{path.lstrip('/')}" for path, _ in _numbers(stored)} <= ids


def _ledger(values: dict[str, str]) -> site_build.Ledger:
    ledger = site_build.Ledger()
    ledger.values.update(values)
    return ledger


@pytest.mark.parametrize("flips, sig, changes", [(0, 0, 0), (2, 1, 3)])
def test_headline_is_computed_from_the_results(flips, sig, changes):
    ledger = _ledger({"ovb:summary/sign_flips": str(flips), "ovb:summary/significance_changes": str(sig),
                      "ovb:summary/holdout_conclusion_changes": str(changes)})
    text = re.sub(r"<[^>]+>", "", site_build.ovb_headline(ledger))
    assert ("changes neither the sign nor the 5% significance" in text) == (flips == 0 and sig == 0)
    assert ("the same in every extended specification" in text) == (changes == 0)
    if flips:
        assert f"changes the sign in {flips} " in text


def test_site_shows_the_section_and_one_home_sentence():
    evidence = (ROOT / "site" / "evidence.html").read_text(encoding="utf-8")
    home = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    assert 'id="ev-ovb">Omitted-variable check</h2>' in evidence and evidence.count('id="ovb-headline"') == 1
    assert evidence.count("<svg", evidence.index('id="ev-ovb"')) - evidence.count("<svg", evidence.index("ev-power")) == 1
    step6 = home.split('id="step-6"', 1)[1].split("</section>", 1)[0]
    sentence = re.findall(r'<p id="ovb-risk">(.*?)</p>', step6, re.S)
    assert len(sentence) == 1 and home.count('id="ovb-risk"') == 1
    assert re.sub(r"<[^>]+>", "", sentence[0]).count(". ") <= 1
    for page in (ROOT / "site").glob("*.html"):
        text = page.read_text(encoding="utf-8").lower()
        assert not re.search(r"80\s*%[^.<]{0,80}export|export[^.<]{0,80}80\s*%", text), page.name
