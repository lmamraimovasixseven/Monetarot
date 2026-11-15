"""Блок dashboard: значения Render-приложения для статичного сайта, без оценивания (docs/site_parity.md)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from _tolerance import same_within_float_tolerance
from src import app, dashboard_view

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))


def test_committed_block_equals_a_fresh_build():
    assert same_within_float_tolerance(ARTIFACT["dashboard"], json.loads(json.dumps(dashboard_view.build())))  # floats: D38


def test_block_values_are_the_render_values():
    block = ARTIFACT["dashboard"]
    latest = dict(zip(block["model"]["features"], block["model"]["latest"]))
    probabilities = app.ordered_probabilities(ARTIFACT, latest)
    assert same_within_float_tolerance(block["probabilities"], {k: probabilities[k] for k in app.DISPLAY_CLASSES})
    score, low, high = app.score_and_delta_band(ARTIFACT, latest)
    assert same_within_float_tolerance([block["score"], *block["band"]], [score, max(-1.0, low), min(1.0, high)])
    assert block["most_likely"] == max(probabilities, key=probabilities.get)
    assert len(block["evidence"]["robustness"]["rows"]) == len(ARTIFACT["robustness_checks"]["checks"])
    assert len(block["evidence"]["falsification"]["rows"]) == len(ARTIFACT["falsification_verdicts"])
    assert all(len(r) == len(block["contributions"]["columns"]) for r in block["contributions"]["rows"])


def test_rounds_are_reproducible_and_honest_about_missing_dates():
    rounds = ARTIFACT["dashboard"]["rounds"]
    after_latest = [d for d in rounds["dates"] if d > ARTIFACT["dashboard"]["latest_decision"]][:2] if rounds["verified"] else []
    assert rounds["default"] == after_latest + [None] * (2 - len(after_latest))
    assert (rounds["default_message"] == "") == (None not in rounds["default"])


def test_no_estimation_in_the_dashboard_or_site_code():
    for name in ("dashboard_view.py", "site_dashboard.py", "site_build.py", "site_i18n.py"):
        text = (ROOT / "src" / name).read_text(encoding="utf-8")
        assert not re.search(r"\.fit\(|\bOLS\(|minimize\(", text), name
