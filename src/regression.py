"""Print-only re-estimation of the main model: `python run.py regression` (or `python -m src.regression`).

Re-fits the main ordered logit on the estimation sample recorded in model/artifact.json, using the
same fitting code as `python run.py model` (src/model.py), and compares every estimate, robust (HC0)
standard error and p-value, plus the log-likelihood, with the artifact line by line at the artifact's
coefficient tolerance. It rebuilds the model panel in memory from data/processed/nbk_decisions_clean.csv
and data/raw/ exactly as the model pipeline does, reads model/artifact.json, and writes nothing to the
repository. Exit code 0 when every line matches, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from src.ingest import DECISIONS_PATH, RAW_DIR, build_model_panel
from src.model import FEATURES, SEED, _fit_ordered, _named_parameter_covariance


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = ROOT / "model" / "artifact.json"


def build_panel_in_memory() -> pd.DataFrame:
    """The model panel exactly as `python run.py model` builds it (from data/processed and data/raw).

    The CSV copy in data/processed is not bit-identical (pandas rounds the last binary digit), and the
    optimizer amplifies that to about 1e-6 in the cutpoint standard errors, so the panel is rebuilt
    in memory. build_model_panel always writes its output, so it writes to a temporary folder that is
    deleted afterwards; nothing in the repository is written.
    """
    with tempfile.TemporaryDirectory(prefix="kz-regression-") as folder:
        panel = build_model_panel(panel_path=DECISIONS_PATH, raw_dir=RAW_DIR, output_path=Path(folder) / "panel.csv")
    panel["decision_date"] = pd.to_datetime(panel["decision_date"], errors="raise")
    return panel


def reestimate(artifact: dict, panel_path: Path | None = None) -> dict:
    """Fit the main model on the artifact's estimation rows; return named estimates, SEs, p-values, llf."""
    panel = (build_panel_in_memory() if panel_path is None
             else pd.read_csv(panel_path, parse_dates=["decision_date"]))
    usable = panel.dropna(subset=FEATURES + ["y"]).reset_index(drop=True)
    rows = pd.to_datetime(artifact["sample"]["estimation_rows"])
    train = usable.loc[usable["decision_date"].isin(rows)].reset_index(drop=True)
    model, fitted, covariance = _fit_ordered(train, int(artifact.get("seed", SEED)))
    names, estimates, named_cov = _named_parameter_covariance(model, np.asarray(fitted.params, dtype=float), covariance)
    standard_errors = np.sqrt(np.maximum(np.diag(named_cov), 0.0))
    p_values = [float(2 * norm.sf(abs(estimate / se))) if se > 0 else math.nan
                for estimate, se in zip(estimates, standard_errors)]
    return {
        "n_rows": len(train),
        "rows_match": len(train) == len(rows) and list(train["decision_date"]) == list(rows),
        "parameters": {name: {"estimate": float(e), "se": float(s), "p_value": p}
                       for name, e, s, p in zip(names, estimates, standard_errors, p_values)},
        "log_likelihood": float(fitted.llf),
    }


def compare(artifact: dict, rebuilt: dict, tolerance: float) -> list[tuple[str, str, float, float, float]]:
    """Rows of (status, item, committed, rebuilt, |difference|)."""
    lines = []

    def add(item: str, committed: float, value: float) -> None:
        difference = abs(value - committed)
        lines.append(("PASS" if difference <= tolerance else "FAIL", item, committed, value, difference))

    table = artifact["model"]["coefficient_table"]
    for name, entry in table.items():
        new = rebuilt["parameters"].get(name)
        if new is None:
            lines.append(("FAIL", f"{name}: missing from the re-estimate", math.nan, math.nan, math.nan))
            continue
        add(f"{name} estimate", float(entry["coefficient_or_cutpoint"]), new["estimate"])
        add(f"{name} robust SE (HC0)", float(entry["hc0_standard_error"]), new["se"])
        add(f"{name} p-value", float(entry["p_value"]), new["p_value"])
    add("log-likelihood", float(artifact["model"]["log_likelihood"]), rebuilt["log_likelihood"])
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Re-estimate the main model in memory and compare with the artifact.")
    parser.add_argument("--artifact", type=Path, default=ARTIFACT_PATH)
    parser.add_argument("--panel", type=Path, default=None,
                        help="read this model-panel CSV instead of rebuilding the panel in memory")
    args = parser.parse_args(argv)

    artifact = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
    tolerance = float(artifact["replication_tolerance"]["coefficients_absolute"])
    rebuilt = reestimate(artifact, args.panel)
    print(f"Main ordered logit re-estimated in memory on {rebuilt['n_rows']} estimation rows "
          f"(seed {artifact.get('seed', SEED)}); nothing is written. Tolerance {tolerance:g} (model/artifact.json).")
    rows_ok = rebuilt["rows_match"]
    print(f"{'PASS' if rows_ok else 'FAIL'}  estimation rows match model/artifact.json "
          f"(sample.estimation_rows, n = {len(artifact['sample']['estimation_rows'])})")
    lines = compare(artifact, rebuilt, tolerance)
    for status, item, committed, value, difference in lines:
        print(f"{status}  {item:<42} committed={committed!r} rebuilt={value!r} |diff|={difference:.3g}")
    failed = sum(status == "FAIL" for status, *_ in lines) + (0 if rows_ok else 1)
    print(f"\nSummary: {len(lines) + 1 - failed} PASS, {failed} FAIL")
    print("RESULT: PASS" if failed == 0 else "RESULT: FAIL")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
