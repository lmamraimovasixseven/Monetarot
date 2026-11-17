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


def test_where_the_frozen_model_fails_is_computed_from_the_ledger_sources():
    """D53: interval, stability p and the share of holdout scores below zero, read from the files the ledger is built from."""
    import json

    numbers = json.loads((ROOT / "outputs" / "numbers_for_note.json").read_text(encoding="utf-8"))["numbers"]
    artifact = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))
    text = next(i["text"] for i in model_card.limits() if i["title"] == "Where the frozen model fails")
    low, high = numbers["rmse_ratio_ci_low"], numbers["rmse_ratio_ci_high"]
    relation = "includes" if float(low["value"]) <= 1 <= float(high["value"]) else "excludes"
    assert f"{low['display']}–{high['display']}, {relation} 1" in text
    assert f"p = {numbers['stability_lr_p']['display']}" in text
    track = artifact["dashboard"]["track_record"]
    scores = [s for d, s in zip(track["dates"], track["score"]) if d >= track["holdout_start"]]
    assert len(scores) == artifact["sample"]["holdout_n"]
    assert f"{sum(s < 0 for s in scores)} of {len(scores)} holdout policy pressure scores are below zero" in text


def test_unmodelled_factors_follow_the_statement_table():
    import json

    rows = json.loads((ROOT / "config" / "nbk_statement_drivers.json").read_text(encoding="utf-8"))["rows"]
    text = model_card.unmodelled_factors()
    for row in rows:
        assert ("limit_name" in row) == (row["status"] == "not_modelled")
        if "limit_name" in row:
            assert row["limit_name"] in text
