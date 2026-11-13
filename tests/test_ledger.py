"""Блок B: в журнале доказательств есть каждое число отчёта и сайта, каждый ряд и каждый файл prereg."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from src import ledger
from src.artifact_extensions import EXTENSION_KEYS

ROOT = Path(__file__).resolve().parents[1]


def _ids() -> set[str]:
    with (ROOT / "ledger" / "evidence_ledger.csv").open(encoding="utf-8", newline="") as handle:
        return {row["id"] for row in csv.DictReader(handle)}


def test_every_number_of_the_note_is_in_the_ledger():
    numbers = json.loads((ROOT / "outputs" / "numbers_for_note.json").read_text(encoding="utf-8"))["numbers"]
    missing = sorted(f"n:{key}" for key in numbers if f"n:{key}" not in _ids())
    assert not missing, missing[:10]


def test_every_number_of_the_product_blocks_in_the_artifact_is_in_the_ledger():
    artifact = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))
    ids = _ids()
    for block in EXTENSION_KEYS - ledger.SKIP_BLOCKS:
        for path, _ in ledger._leaves(artifact.get(block, {}), ""):
            assert f"{block}:{path.lstrip('/')}" in ids, (block, path)


def test_every_raw_and_external_series_is_in_the_ledger():
    ids = _ids()
    for path in (ROOT / "data" / "raw").glob("*.csv"):
        assert f"raw:{path.name}" in ids
    for path in (ROOT / "data" / "raw" / "external").glob("*.csv"):
        assert f"external:{path.name}" in ids


def test_committed_ledger_equals_a_fresh_build():
    assert (ROOT / "ledger" / "evidence_ledger.csv").read_text(encoding="utf-8") == ledger.render(ledger.build())
