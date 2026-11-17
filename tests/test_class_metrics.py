"""D53: per-class holdout metrics (Merton's measure); exploratory, outside the artifact, every number in the ledger."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pandas as pd
import pytest
from _tolerance import same_within_float_tolerance

from src import class_metrics, site_build

ROOT = Path(__file__).resolve().parents[1]
STORED = ROOT / "model" / "extensions" / "class_metrics.json"
ARTIFACT = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def stored() -> dict:
    return json.loads(STORED.read_text(encoding="utf-8"))


def _leaves(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _leaves(item, f"{path}/{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _leaves(item, f"{path}/{index}")
    else:
        yield path, value


def test_results_are_kept_outside_the_artifact():
    assert not any(key.startswith("class") for key in ARTIFACT)


def test_committed_results_equal_a_fresh_run(stored):
    """Probabilities come from the optimizer's fit: floats within 1e-4 (D51); counts, names and flags exactly."""
    fresh = class_metrics._clean(class_metrics.run())
    committed, rebuilt = dict(_leaves(stored)), dict(_leaves(fresh))
    assert committed.keys() == rebuilt.keys()
    for key, value in committed.items():
        if isinstance(value, float) or isinstance(rebuilt[key], float):
            assert same_within_float_tolerance(value, rebuilt[key], rel=1e-4, abs_=1e-4), key
        else:
            assert value == rebuilt[key], key


def test_same_holdout_and_definitions(stored):
    predictions = pd.read_csv(ROOT / "outputs" / "annex_predictions.csv")
    assert stored["holdout"]["n"] == ARTIFACT["sample"]["holdout_n"] == len(predictions)
    assert stored["holdout"]["start"] == ARTIFACT["sample"]["holdout_start"]
    counts = predictions.actual_decision.value_counts()
    for table in stored["forecasters"].values():
        present = [c for c in class_metrics.CLASSES if table["classes"][c]["n"]]
        assert all(table["classes"][c]["n"] == int(counts.get(c, 0)) for c in class_metrics.CLASSES)
        recalls = [table["classes"][c]["recall"] for c in present]
        assert table["classes_present"] == len(present)
        assert table["mean_class_recall"] == pytest.approx(sum(recalls) / len(present))
        assert table["merton_cp"] == pytest.approx((sum(recalls) - 1) / (len(present) - 1))
        for c in present:
            assert table["classes"][c]["correct"] == round(table["classes"][c]["recall"] * table["classes"][c]["n"])


def test_always_hold_is_a_stopped_clock(stored):
    hold = stored["forecasters"]["always_hold"]
    for c in ("Decrease", "Increase"):
        if hold["classes"][c]["n"]:
            assert hold["classes"][c]["recall"] == 0
    assert hold["classes"]["Hold"]["recall"] == 1 and hold["merton_cp"] == 0


def test_class_metrics_on_a_toy_holdout():
    probs = pd.DataFrame([[0.6, 0.3, 0.1], [0.2, 0.5, 0.3], [0.1, 0.2, 0.7], [0.5, 0.4, 0.1]], columns=class_metrics.CLASSES)
    actual = pd.Series(["Decrease", "Hold", "Increase", "Hold"])
    table = class_metrics.class_table(probs, actual)
    assert table["classes"]["Hold"]["recall"] == 0.5 and table["classes"]["Decrease"]["recall"] == 1.0
    assert table["mean_class_recall"] == pytest.approx(2.5 / 3) and table["merton_cp"] == pytest.approx(0.75)


def test_every_number_has_a_ledger_row(stored):
    with (ROOT / "ledger" / "evidence_ledger.csv").open(encoding="utf-8", newline="") as handle:
        ids = {row["id"] for row in csv.DictReader(handle)}
    numeric = {f"classm:{p.lstrip('/')}" for p, v in _leaves(stored) if isinstance(v, (int, float)) and not isinstance(v, bool)}
    assert numeric <= ids


@pytest.mark.parametrize("correct", [0, 2])
def test_headline_is_computed_from_the_results(correct):
    ledger = site_build.Ledger()
    ledger.values["classm:summary/frozen_correct_non_hold"] = str(correct)
    text = re.sub(r"<[^>]+>", "", site_build.class_metrics_headline(ledger))
    assert ("like Always Hold, picks none" in text) == (correct == 0)
    if correct:
        assert f"picks {correct} of the " in text
    assert "better" not in text


def test_site_shows_the_table_and_the_definitions():
    evidence = (ROOT / "site" / "evidence.html").read_text(encoding="utf-8")
    methods = (ROOT / "site" / "methods.html").read_text(encoding="utf-8")
    assert evidence.count('id="classes-headline"') == 1 and 'id="classes-table"' in evidence
    assert 'id="class-metric-definitions"' in methods and "Merton CP" in methods
