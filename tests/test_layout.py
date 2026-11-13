"""Блок G: раскладка по брифу и одна команда обновления."""

from pathlib import Path

from src import root_docs

ROOT = Path(__file__).resolve().parents[1]


def test_brief_layout_exists():
    for relative in ("README.md", "AI_USE.md", "CONTRIBUTIONS.md", "DECLARATION.md", "data/raw", "data/processed",
                     "ledger/evidence_ledger.csv", "prereg/prereg.md", "src", "model/artifact.json", "site/index.html"):
        assert (ROOT / relative).exists(), relative


def test_root_documents_are_current_copies_of_docs():
    for target, source in root_docs.COPIES.items():
        assert (ROOT / target).read_text(encoding="utf-8") == root_docs.render(source), target


def test_update_runs_every_stage_in_order():
    import run

    modules = [command[2] for command in run.TASKS["update"]]
    order = ["src.ingest", "src.model", "src.robust_eval", "src.report", "src.facts", "src.decision_rule", "src.prereg",
             "src.forecast_desk", "src.carry_corridor", "src.patterns", "src.model_card", "src.forecast_log", "src.ledger",
             "src.site_build", "src.root_docs", "src.traps"]
    positions = [modules.index(m) for m in order]
    assert positions == sorted(positions)
    assert "update:" in (ROOT / "Makefile").read_text(encoding="utf-8")
