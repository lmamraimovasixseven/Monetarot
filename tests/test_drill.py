"""Блок H: каждая карточка проходит на копии; сломанный источник даёт понятную ошибку и откат."""

from __future__ import annotations

from pathlib import Path

import pytest

from src import drill
from src.hashing import normalized_sha256

ROOT = Path(__file__).resolve().parents[1]


def _hashes() -> dict[str, str]:
    return {p.name: normalized_sha256(p) for p in (ROOT / "data" / "raw").glob("*.csv")} | {
        "losses": normalized_sha256(ROOT / "config" / "decision_losses.json")}


@pytest.mark.parametrize("card", ["revision", "release", "shock", "question"])
def test_cards_pass_on_a_copy_and_leave_the_repository_untouched(card):
    before = _hashes()
    result = drill.drill(card, light=True)
    assert result["ok"], result["error"]
    assert "[ВАША ОЦЕНКА]" in result["note"] and len(result["note"].split()) <= 110
    assert _hashes() == before
    if card in ("release", "shock"):
        assert result["after"]["exports_last"] > result["before"]["exports_last"] and "ИМИТАЦИЯ" in result["change"]
    if card == "shock":
        assert result["after"]["flags"] > result["before"]["flags"]
    if card == "question":
        assert result["after"]["threshold"] < result["before"]["threshold"]


def test_broken_source_fails_loudly_and_rolls_back():
    before = _hashes()
    result = drill.drill("broken_source", light=True)
    assert not result["ok"] and "export_history.csv" in result["error"] and "Откат" in result["note"]
    assert _hashes() == before


def test_drill_doc_covers_all_cards():
    text = (ROOT / "docs" / "UPDATE_DRILL.md").read_text(encoding="utf-8")
    assert all(f"`{card}`" in text for card in drill.CARDS) and "45" in text
