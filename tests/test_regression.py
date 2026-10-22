"""Tests for `python run.py regression`: print-only re-estimation of the main model."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from src import regression


ROOT = Path(__file__).resolve().parents[1]
WATCHED = ["model/artifact.json", "data/processed/model_panel.csv", "data/processed/nbk_decisions_clean.csv",
           "outputs/annex_diagnostics.md", "outputs/numbers_for_note.json"]


def _hashes() -> dict[str, str]:
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in WATCHED}


def test_reestimate_matches_the_artifact_and_writes_nothing(capsys):
    before = _hashes()
    code = regression.main([])
    output = capsys.readouterr().out
    assert code == 0, output
    assert "RESULT: PASS" in output and "nothing is written" in output
    assert "PASS  estimation rows match model/artifact.json" in output
    artifact = json.loads((ROOT / "model/artifact.json").read_text(encoding="utf-8"))
    for name in artifact["model"]["coefficient_table"]:
        for item in ("estimate", "robust SE (HC0)", "p-value"):
            assert f"PASS  {name} {item}" in output, (name, item)
    assert "PASS  log-likelihood" in output
    assert _hashes() == before


def test_a_changed_main_coefficient_fails_with_exit_code_one(tmp_path, capsys):
    artifact = json.loads((ROOT / "model/artifact.json").read_text(encoding="utf-8"))
    artifact["model"]["coefficient_table"]["household_lending"]["coefficient_or_cutpoint"] += 1e-3
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    code = regression.main(["--artifact", str(path)])
    output = capsys.readouterr().out
    assert code == 1
    assert "FAIL  household_lending estimate" in output and "RESULT: FAIL" in output
    assert "PASS  household_lending robust SE (HC0)" in output


def test_run_py_regression_task_reports_the_exit_code():
    result = subprocess.run([sys.executable, "run.py", "regression"], cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RESULT: PASS" in result.stdout


def test_readme_and_demo_describe_the_regression_command():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    demo = (ROOT / "docs" / "demo_script.md").read_text(encoding="utf-8")
    assert "python run.py regression" in readme and "writes nothing" in readme
    assert "Run `python run.py regression`" in demo
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "regression:\n\t$(PYTHON) run.py regression" in makefile
