"""Блок F: model card и пределы сайта строятся из одних фактов; есть названный прошлый провал."""

from pathlib import Path

from src import model_card

ROOT = Path(__file__).resolve().parents[1]


def test_card_equals_a_fresh_render_and_names_a_past_failure():
    text = (ROOT / "docs" / "model_card.md").read_text(encoding="utf-8")
    assert text == model_card.card(model_card.limits())
    assert "### Названный прошлый провал" in text and "UNKNOWN" not in model_card.past_failure(model_card._load(model_card.LEGACY))


def test_no_limit_claims_a_better_model():
    for item in model_card.limits():
        assert "лучше" not in item["text"].lower() and "beats" not in item["text"].lower()
