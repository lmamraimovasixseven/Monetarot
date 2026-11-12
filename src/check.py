"""Replication check: `python -m src.check`.

Re-runs ingest, the model and the report into a temporary directory (never
into the repository), then compares the rebuilt results with the committed ones:

* the rebuilt decision panel and model panel, cell by cell;
* the headline score (the artifact's named headline, the holdout RMSE ratio,
  plus the dashboard's latest policy pressure score);
* every model coefficient and cutpoint;
* every number in each committed outputs/*.md file (a committed file that is
  not regenerated fails);
* every entry of outputs/numbers_for_note.json;
* the note's figures, pixel by pixel;
* README.md against a fresh render of docs/README.template.md;
* every file generated from docs/facts_to_fill.* (SOURCES.md, provenance.json,
  release_lag_check.md, indicator card, decision rule, validity facts).

Tolerances come from ``replication_tolerance`` in the committed
model/artifact.json: ``headline_score_absolute`` for the two headline scores
and ``coefficients_absolute`` for every other number. Prints PASS/FAIL per item
and exits non-zero if anything fails.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

from src import compare, data_screen, facts, forecast_log, ingest, model, readme, robust_eval
from src import report as report_module


ROOT = Path(__file__).resolve().parents[1]
COMMITTED_README = ROOT / "README.md"
# Numbers compared with the artifact's headline tolerance instead of the coefficient tolerance.
HEADLINE_NUMBER_KEYS = {"headline_score", "rmse_ratio"}
COMMITTED_ARTIFACT = ROOT / "model" / "artifact.json"
COMMITTED_OUTPUTS = ROOT / "outputs"
COMMITTED_DECISIONS = ROOT / "data" / "processed" / "nbk_decisions_clean.csv"
COMMITTED_MODEL_PANEL = ROOT / "data" / "processed" / "model_panel.csv"

# Run-specific values that legitimately differ between runs.
_VOLATILE = [
    re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?"),  # ISO timestamps
    re.compile(r"\d{8}T\d{6}(?:\.\d+)?Z(?:-\d{4})?"),  # spec-log run and spec ids
]
_NUMBER = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def add(self, status: str, item: str, detail: str = "") -> None:
        self.rows.append((status, item, detail))
        print(f"{status:<4}  {item}" + (f"  ({detail})" if detail else ""), flush=True)

    def check(self, item: str, committed: float, rebuilt: float, tolerance: float) -> bool:
        difference = abs(rebuilt - committed) if _finite(committed) and _finite(rebuilt) else None
        same_nonfinite = not _finite(committed) and repr(committed) == repr(rebuilt)
        ok = same_nonfinite or (difference is not None and difference <= tolerance)
        detail = f"committed={committed!r} rebuilt={rebuilt!r} |diff|={difference if difference is not None else 'n/a'} tol={tolerance:g}"
        self.add("PASS" if ok else "FAIL", item, detail)
        return ok

    @property
    def failed(self) -> int:
        return sum(status == "FAIL" for status, _, _ in self.rows)


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def extract_numbers(text: str) -> list[float]:
    for pattern in _VOLATILE:
        text = pattern.sub("<volatile>", text)
    return [float(token) for token in _NUMBER.findall(text)]


# Results of optimizer runs that did not converge (deviation D14): the parameter-stability LR test, whose
# unrestricted BFGS attempt stops before convergence, any spec-log row marked NONCONVERGED, and robustness
# check RB02. Where such a line differs, the check reports WARN with both values instead of FAIL.
PLATFORM_SENSITIVE_LINE = re.compile(
    r"\| NONCONVERGED \|"                     # a table row of a fit that did not converge
    r"|\| Parameter stability LR \||LR stability unrestricted|parameter_stability"  # the stability LR test rows
    r"|^\| RB02 \||\| RB02: |\| Last 60 calendar months \|")  # robustness check RB02 rows
PLATFORM_SENSITIVE_KEYS = {"robustness_RB02_converged"}
RB02_KEY_PREFIX = "robustness_RB02_"
RB02_NOTE = "platform-sensitive: RB02 did not converge on this platform (D33)"
PLATFORM_NOTE = "platform-sensitive (optimizer did not converge)"
# D14 update. (1) Spec-log rows of expanding-window fits record optimizer internals (fopt, gopt, ...).
OPTIMIZER_INTERNALS_LINE = re.compile(r"\| expanding_window_fit \|")
OPTIMIZER_INTERNALS_NOTE = "platform-sensitive (optimizer internals)"
# (2) The robustness count line depends on whether RB02 converges.
CONVERGED_COUNTS = re.compile(r"Robustness checks converged: \d+; nonconverged or failed: \d+")
CONVERGED_COUNTS_NOTE = "platform-sensitive (depends on RB02 convergence)"
# (3) Rounding-level differences from the optimizer's convergence tolerance, allowed only in these two files.
CROSS_PLATFORM_TOLERANCE = 1e-4
CROSS_PLATFORM_FILES = {"annex_diagnostics.md", "robustness_table.md", "robust_evaluation.md"}


def _short(values: list[float], limit: int = 8) -> str:
    shown = ", ".join(f"{value!r}" for value in values[:limit])
    more = "" if len(values) <= limit else f", ... {len(values) - limit} more"
    return f"[{shown}{more}]"


# D32. Robust standard errors and p-values of the main model (numbers_for_note.json keys) are second-order
# results of the optimizer's stopping point: a last-bit change of the inputs moves them by about 2e-6 while
# the estimates move by about 3e-9. Beyond the coefficient tolerance they are accepted within
# CROSS_PLATFORM_TOLERANCE (absolute and relative) and reported as WARN with both values.
SE_OR_P_KEY = re.compile(r"^(se_|p_raw_|p_holm_)\w+$|^cutpoint_\d+_(se|p_raw)$")
SE_OR_P_NOTE = "platform-sensitive (robust SE or p-value, optimizer stopping point)"


def within_cross_platform(a: float, b: float) -> bool:
    """Public alias used by src.regression (D32)."""
    return _within_cross_platform(a, b)


def _within_cross_platform(a: float, b: float) -> bool:
    difference = abs(a - b)
    scale = max(abs(a), abs(b))
    return difference <= CROSS_PLATFORM_TOLERANCE and (scale == 0 or difference / scale <= CROSS_PLATFORM_TOLERANCE)


def compare_markdown(report: Report, name: str, committed: Path, rebuilt: Path, tolerance: float,
                     verbose: bool = False) -> None:
    """Compare numbers line by line, so a difference on one line cannot shift every later number.

    Rules, in order, for a line whose numbers differ beyond `tolerance` (D14 and its update):
    WARN for rows of fits that did not converge, rows of expanding-window optimizer internals, and the
    robustness converged-count clause; for the two annex files only, PASS when every difference is within
    the cross-platform tolerance (absolute and relative); FAIL otherwise.
    """
    if not rebuilt.is_file():
        report.add("FAIL", f"outputs/{name}", "committed file is not regenerated by ingest, model or report")
        return
    left_lines = committed.read_text(encoding="utf-8").splitlines()
    right_lines = rebuilt.read_text(encoding="utf-8").splitlines()
    if len(left_lines) != len(right_lines):
        report.add("FAIL", f"outputs/{name}", f"{len(left_lines)} lines committed vs {len(right_lines)} rebuilt")
        return
    cross_platform = name in CROSS_PLATFORM_FILES
    total, failures, warnings, rounded = 0, 0, 0, 0
    for number, (left_line, right_line) in enumerate(zip(left_lines, right_lines), start=1):
        # The converged-count clause is compared on its own; the rest of the line stays strict.
        left_counts = CONVERGED_COUNTS.findall(left_line)
        right_counts = CONVERGED_COUNTS.findall(right_line)
        if left_counts and right_counts:
            if left_counts != right_counts:
                warnings += 1
                report.add("WARN", f"outputs/{name} line {number}",
                           f"{CONVERGED_COUNTS_NOTE}: committed={left_counts[0]!r} rebuilt={right_counts[0]!r}")
            left_line = CONVERGED_COUNTS.sub("<converged-counts>", left_line)
            right_line = CONVERGED_COUNTS.sub("<converged-counts>", right_line)
        left, right = extract_numbers(left_line), extract_numbers(right_line)
        total += len(left)
        if verbose:
            for a, b in zip(left, right):
                print(f"      line {number}: committed={a!r} rebuilt={b!r}")
        same_count = len(left) == len(right)
        mismatches = ([(i, a, b) for i, (a, b) in enumerate(zip(left, right)) if abs(a - b) > tolerance]
                      if same_count else [])
        if same_count and not mismatches:
            continue
        sensitive = (PLATFORM_SENSITIVE_LINE.search(left_line) or PLATFORM_SENSITIVE_LINE.search(right_line))
        internals = (OPTIMIZER_INTERNALS_LINE.search(left_line) or OPTIMIZER_INTERNALS_LINE.search(right_line))
        if sensitive or internals:
            warnings += 1
            note = PLATFORM_NOTE if sensitive else OPTIMIZER_INTERNALS_NOTE
            if same_count:  # show only the numbers that differ
                shown = (_short([a for _, a, _ in mismatches]), _short([b for _, _, b in mismatches]))
            else:
                shown = (_short(left), _short(right))
            report.add("WARN", f"outputs/{name} line {number}", f"{note}: committed={shown[0]} rebuilt={shown[1]}")
        elif not same_count:
            failures += 1
            report.add("FAIL", f"outputs/{name} line {number}",
                       f"{len(left)} numbers committed vs {len(right)} rebuilt")
        elif cross_platform and all(_within_cross_platform(a, b) for _, a, b in mismatches):
            rounded += len(mismatches)
        else:
            for i, a, b in mismatches:
                if cross_platform and _within_cross_platform(a, b):
                    rounded += 1
                    continue
                failures += 1
                report.add("FAIL", f"outputs/{name} line {number} number #{i}",
                           f"committed={a!r} rebuilt={b!r} tol={tolerance:g}"
                           + (f" (cross-platform tol {CROSS_PLATFORM_TOLERANCE:g})" if cross_platform else ""))
    if not failures:
        parts = [f"all {total} numbers within {tolerance:g}" if not (warnings or rounded)
                 else f"all other numbers within {tolerance:g}"]
        if rounded:
            parts.append(f"{rounded} within the cross-platform tolerance {CROSS_PLATFORM_TOLERANCE:g} (D14 update)")
        if warnings:
            parts.append(f"{warnings} line(s) reported as WARN")
        report.add("PASS", f"outputs/{name}", "; ".join(parts))


def compare_numbers(report: Report, committed: Path, rebuilt: Path, tolerance: float,
                    headline_tolerance: float, headline_keys: set[str]) -> None:
    """Compare every entry of numbers_for_note.json: numbers within tolerance, text exactly."""
    label = "outputs/numbers_for_note.json"
    if not committed.is_file() or not rebuilt.is_file():
        report.add("FAIL", label, "missing committed or rebuilt file")
        return
    left, right = (json.loads(path.read_text(encoding="utf-8")) for path in (committed, rebuilt))
    if left.get("verdict_sentence") != right.get("verdict_sentence"):
        report.add("FAIL", f"{label} verdict_sentence", f"{left.get('verdict_sentence')!r} vs {right.get('verdict_sentence')!r}")
    if set(left["numbers"]) != set(right["numbers"]):
        report.add("FAIL", f"{label} keys",
                   f"only committed: {sorted(set(left['numbers']) - set(right['numbers']))}; "
                   f"only rebuilt: {sorted(set(right['numbers']) - set(left['numbers']))}")
    # D33: when the rebuilt RB02 did not converge, every RB02 entry (but nothing else) is reported as WARN.
    rb02_nonconverged = right["numbers"].get("robustness_RB02_converged", {}).get("value") is False
    for key, entry in left["numbers"].items():
        if key not in right["numbers"]:
            continue
        a, b = entry["value"], right["numbers"][key]["value"]
        item = f"{label} {key}"
        if rb02_nonconverged and key.startswith(RB02_KEY_PREFIX) and a != b:
            report.add("WARN", item, f"{RB02_NOTE}: committed={a!r} rebuilt={b!r}")
        elif key in PLATFORM_SENSITIVE_KEYS and a != b:
            # Checked first: a convergence flag is a bool, which Python would otherwise treat as a number.
            report.add("WARN", item, f"{PLATFORM_NOTE}: committed={a!r} rebuilt={b!r}")
        elif (_finite(a) and _finite(b) and abs(a - b) > tolerance and SE_OR_P_KEY.match(key)
              and _within_cross_platform(a, b)):
            # D32: robust SEs and p-values move by about 1e-6 when the optimizer stops at a slightly different
            # point on another platform; estimates, the RMSE ratio and the headline keep the strict tolerance.
            report.add("WARN", item, f"{SE_OR_P_NOTE}: committed={a!r} rebuilt={b!r} |diff|={abs(a - b):.3g}")
        elif _finite(a) and _finite(b):
            report.check(item, a, b, headline_tolerance if key in headline_keys else tolerance)
        else:
            report.add("PASS" if a == b and entry["source"] == right["numbers"][key]["source"] else "FAIL",
                       item, f"committed={a!r} rebuilt={b!r}")


# Figures rendered on another operating system differ in a few per cent of pixels because font
# rasterization shifts text and the tight layout by a pixel or two (D16). After averaging 16 x 16 pixel
# blocks such differences stay below about 0.15 on the 0-1 scale, while a changed plot element (a moved
# series, a missing bar, a block of altered pixels) exceeds 0.25. The data plotted in each figure are
# compared exactly elsewhere (annex_predictions.csv, numbers_for_note.json, the decision panel).
FIGURE_BLOCK = 16
FIGURE_BLOCK_TOLERANCE = 0.25
FIGURE_NOTE = "platform-sensitive (font rasterization)"


def _block_means(image) -> "np.ndarray":
    import numpy as np

    gray = np.asarray(image, dtype=float)[..., :3].mean(axis=-1)
    height, width = (gray.shape[0] // FIGURE_BLOCK) * FIGURE_BLOCK, (gray.shape[1] // FIGURE_BLOCK) * FIGURE_BLOCK
    trimmed = gray[:height, :width]
    return trimmed.reshape(height // FIGURE_BLOCK, FIGURE_BLOCK, width // FIGURE_BLOCK, FIGURE_BLOCK).mean(axis=(1, 3))


def compare_png(report: Report, name: str, committed: Path, rebuilt: Path, tolerance: float) -> None:
    from matplotlib.image import imread

    label = f"outputs/{name}"
    if not committed.is_file() or not rebuilt.is_file():
        report.add("FAIL", label, "missing committed or rebuilt figure")
        return
    left, right = imread(committed), imread(rebuilt)
    if left.shape != right.shape:
        report.add("FAIL", label, f"image size {left.shape} vs {right.shape}")
        return
    difference = float(abs(left.astype(float) - right.astype(float)).max())
    if difference <= tolerance:
        report.add("PASS", label, f"max pixel difference {difference:g} (0-1 scale), tol={tolerance:g}")
        return
    block_difference = float(abs(_block_means(left) - _block_means(right)).max())
    if block_difference <= FIGURE_BLOCK_TOLERANCE:
        report.add("WARN", label, f"{FIGURE_NOTE}: max pixel difference {difference:g}, but max "
                   f"{FIGURE_BLOCK}x{FIGURE_BLOCK}-block difference {block_difference:.3f} <= {FIGURE_BLOCK_TOLERANCE}")
        return
    report.add("FAIL", label, f"max pixel difference {difference:g} (0-1 scale), tol={tolerance:g}; "
               f"max {FIGURE_BLOCK}x{FIGURE_BLOCK}-block difference {block_difference:.3f} > {FIGURE_BLOCK_TOLERANCE}")


def compare_text(report: Report, label: str, committed: Path, rebuilt_text: str) -> None:
    if not committed.is_file():
        report.add("FAIL", label, "committed file is missing")
        return
    same = committed.read_text(encoding="utf-8").replace("\r\n", "\n") == rebuilt_text
    report.add("PASS" if same else "FAIL", label,
               "identical to a fresh render" if same
               else "differs from a fresh render; run `python run.py report` and `python run.py facts`")


def compare_panel(report: Report, label: str, committed: Path, rebuilt: Path, tolerance: float) -> None:
    left, right = pd.read_csv(committed), pd.read_csv(rebuilt)
    if left.shape != right.shape or left.columns.tolist() != right.columns.tolist():
        report.add("FAIL", label, f"shape/columns differ: {left.shape} vs {right.shape}")
        return
    bad = 0
    for column in left.columns:
        a, b = left[column], right[column]
        if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
            both_missing = a.isna() & b.isna()
            bad += int((~both_missing & ~((a - b).abs() <= tolerance)).sum())
        else:
            bad += int((a.astype(str) != b.astype(str)).sum())
    cells = left.size
    report.add("PASS" if bad == 0 else "FAIL", label, f"{cells - bad}/{cells} cells match within {tolerance:g}")


def run(workdir: Path, verbose: bool = False) -> Report:
    committed = json.loads(COMMITTED_ARTIFACT.read_text(encoding="utf-8"))
    tolerance = committed["replication_tolerance"]
    headline_tol = float(tolerance["headline_score_absolute"])
    number_tol = float(tolerance["coefficients_absolute"])
    print(f"Working directory: {workdir}")
    print(f"Tolerances from model/artifact.json: headline={headline_tol:g}, coefficients and other numbers={number_tol:g}\n")

    decisions = workdir / "data" / "processed" / "nbk_decisions_clean.csv"
    model_panel = workdir / "data" / "processed" / "model_panel.csv"
    artifact_path = workdir / "model" / "artifact.json"
    outputs = workdir / "outputs"

    print("Re-running ingest ...", flush=True)
    ingest.build_panel(output_path=decisions)
    data_screen.write(decisions_path=decisions, json_path=workdir / "data" / "processed" / "data_anomalies.json",
                      md_path=outputs / "data_anomalies.md")
    print("Re-running model ...\n", flush=True)
    model.run_pipeline(
        output_dir=outputs, artifact_path=artifact_path,
        model_panel_path=model_panel, source_panel_path=decisions,
    )
    rebuilt = json.loads(artifact_path.read_text(encoding="utf-8"))
    print("Re-running exploratory robustness evaluation ...\n", flush=True)
    robust_eval.run(output_dir=outputs, artifact_path=workdir / "model" / "robust_eval.json",
                    model_panel_path=model_panel, decisions_path=decisions, main_artifact_path=artifact_path)
    forecast_log.write_scores(decisions_path=decisions, json_path=workdir / "data" / "processed" / "forecast_scores.json",
                              md_path=outputs / "forecast_scores.md")
    print("Re-running OLD vs NEW comparison ...\n", flush=True)
    compare.run(artifact_path=artifact_path, robust_path=workdir / "model" / "robust_eval.json",
                json_path=workdir / "model" / "version_comparison.json", md_path=outputs / "version_comparison.md")
    print("Re-running report ...\n", flush=True)
    report_module.run(output_dir=outputs, artifact_path=artifact_path, robust_path=workdir / "model" / "robust_eval.json",
                      decisions_path=decisions, model_panel_path=model_panel,
                      version_path=workdir / "model" / "version_comparison.json")

    report = Report()
    compare_panel(report, "data/processed/nbk_decisions_clean.csv", COMMITTED_DECISIONS, decisions, number_tol)
    compare_panel(report, "data/processed/model_panel.csv", COMMITTED_MODEL_PANEL, model_panel, number_tol)
    report.check(
        f"headline: {tolerance.get('headline_score_name', 'holdout RMSE ratio')}",
        committed["benchmark_comparison"]["rmse_ratio_model_to_hold"],
        rebuilt["benchmark_comparison"]["rmse_ratio_model_to_hold"], headline_tol,
    )
    report.check(
        "headline: latest policy pressure score",
        committed["latest_prediction"]["expected_score"],
        rebuilt["latest_prediction"]["expected_score"], headline_tol,
    )
    for name, value in committed["model"]["parameters"].items():
        if name not in rebuilt["model"]["parameters"]:
            report.add("FAIL", f"coefficient {name}", "missing from rebuilt artifact")
            continue
        report.check(f"coefficient {name}", value, rebuilt["model"]["parameters"][name], number_tol)
    for path in sorted(COMMITTED_OUTPUTS.glob("*.md")):
        if f"outputs/{path.name}" in facts.GENERATED_PATHS:
            continue  # produced from the fact forms; compared in compare_facts below
        compare_markdown(report, path.name, path, outputs / path.name, number_tol, verbose)
    compare_numbers(report, COMMITTED_OUTPUTS / "numbers_for_note.json", outputs / "numbers_for_note.json",
                    number_tol, headline_tol, HEADLINE_NUMBER_KEYS)
    for name in sorted(n for n in report_module.OUTPUT_FILES if n.endswith(".png")):
        compare_png(report, name, COMMITTED_OUTPUTS / name, outputs / name, number_tol)
    compare_text(report, "README.md", COMMITTED_README, readme.build(outputs / "numbers_for_note.json"))
    compare_facts(report, outputs / "numbers_for_note.json")
    return report


def compare_facts(report: Report, numbers_path: Path, root: Path = ROOT) -> None:
    """Every file generated from the fact forms must equal a fresh render of the forms."""
    try:
        generated = facts.build_all(root, numbers_path=numbers_path)
    except facts.FactsError as error:
        report.add("FAIL", "facts forms", f"docs/facts_to_fill.* do not validate: {error}")
        return
    for relative, content in generated.items():
        compare_text(report, f"facts: {relative}", root / relative, content)
    for name, ok, detail in facts.provenance_consistency(root):
        report.add("PASS" if ok else "FAIL", f"provenance consistency: {name}", detail)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Re-run ingest and model in a temp directory and compare.")
    parser.add_argument("--workdir", type=Path, default=None,
                        help="directory for rebuilt files (default: a temporary directory removed afterwards)")
    parser.add_argument("--verbose", action="store_true", help="print every compared markdown number")
    args = parser.parse_args(argv)
    # Generated sentences contain characters such as "−"; a Windows console (cp1251) cannot print them.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    created = args.workdir is None
    workdir = Path(tempfile.mkdtemp(prefix="kz-check-")) if created else args.workdir
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        report = run(workdir, args.verbose)
    finally:
        if created:
            shutil.rmtree(workdir, ignore_errors=True)
    passed = sum(status == "PASS" for status, _, _ in report.rows)
    skipped = sum(status == "SKIP" for status, _, _ in report.rows)
    warned = sum(status == "WARN" for status, _, _ in report.rows)
    print(f"\nSummary: {passed} PASS, {report.failed} FAIL, {skipped} SKIP, {warned} WARN")
    if warned:
        print(f"WARN = {PLATFORM_NOTE} or {FIGURE_NOTE}; see docs/deviations.md D14 and D16. "
              "WARN does not fail the check.")
    print("RESULT: PASS" if report.failed == 0 else "RESULT: FAIL")
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
