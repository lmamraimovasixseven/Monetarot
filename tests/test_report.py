"""Tests for the note's generated outputs (src.report), README rendering and their checks."""

from __future__ import annotations

import ast
import json
import re
import shutil
from pathlib import Path

import numpy as np
import pytest

from src import app, check, readme, report


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
ARTIFACT = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))
# Non-result constants allowed as digits in the README template.
TEMPLATE_LITERALS = {
    "3.14": "tested Python version (Windows)",
    "3.13": "tested Python version (Linux)",
    "8503": "default dashboard port",
    "95": "confidence level of the delta-method band",
    "0": "score scale definition",
    "1": "score scale definition (−1 / +1)",
}


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("report") / "outputs"
    payload = report.run(out)
    return out, payload


def test_report_writes_every_output_file(generated):
    out, payload = generated
    assert sorted(path.name for path in out.iterdir()) == sorted(report.OUTPUT_FILES)
    assert payload["numbers"]


def test_every_number_points_to_its_artifact_field_or_derivation(generated):
    _, payload = generated
    for key, entry in payload["numbers"].items():
        source = entry["source"]
        if isinstance(source, str):
            path, pointer = source.split("#", 1)
            assert path == "model/artifact.json", key
            value = report.resolve(ARTIFACT, pointer)
            if isinstance(value, float) and not np.isfinite(value):
                value = "+Infinity"
            assert entry["value"] == value, key
        else:
            assert source["derived_from"] and source["method"], key


def test_note_numbers_cover_what_the_note_quotes(generated):
    numbers = generated[1]["numbers"]
    required = {
        "headline_score", "headline_score_band_low", "headline_score_band_high", "latest_decision_date",
        "next_round_probability_increase", "next_round_probability_hold", "next_round_probability_decrease",
        "rmse_ratio", "n_estimation", "n_holdout", "sample_holdout_start", "sample_holdout_end",
        "robustness_survivor_count", "robustness_survivors",
    }
    required |= {f"p_raw_{name}" for name in app.FEATURES} | {f"p_holm_{name}" for name in app.FEATURES}
    required |= {f"robustness_RB{i:02d}_survives" for i in range(1, 10)}
    assert required <= set(numbers)
    survivors = [c["specification_id"] for c in ARTIFACT["robustness_checks"]["checks"] if c["survives"] == "Yes"]
    assert numbers["robustness_survivors"]["value"] == (", ".join(survivors) or "none")


def test_headline_band_matches_dashboard_calculation(generated):
    numbers = generated[1]["numbers"]
    score, low, high = app.score_and_delta_band(ARTIFACT, ARTIFACT["latest_feature_vector"])
    assert numbers["headline_score"]["value"] == pytest.approx(score, abs=1e-12)
    assert numbers["headline_score_band_low"]["value"] == pytest.approx(max(-1.0, low))
    assert numbers["headline_score_band_high"]["value"] == pytest.approx(min(1.0, high))
    assert numbers["headline_score_band_low"]["value"] <= score <= numbers["headline_score_band_high"]["value"]


def test_results_table_lists_slopes_cutpoints_and_sample_sizes(generated):
    text = (generated[0] / "results_table.md").read_text(encoding="utf-8")
    table = ARTIFACT["model"]["coefficient_table"]
    for name in app.FEATURES:
        row = next(line for line in text.splitlines() if line.startswith(f"| {app.FEATURE_LABELS[name]} |"))
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        assert float(cells[1]) == pytest.approx(table[name]["coefficient_or_cutpoint"], abs=5e-5)
        assert float(cells[2]) == pytest.approx(table[name]["hc0_standard_error"], abs=5e-5)
        assert float(cells[3]) == pytest.approx(table[name]["p_value"], abs=5e-4)
        assert float(cells[4]) == pytest.approx(table[name]["p_value_holm"], abs=5e-4)
    assert text.count("| Cutpoint ") == 2
    assert f"N estimation: {ARTIFACT['sample']['estimation_n']}" in text
    assert f"N holdout: {ARTIFACT['sample']['holdout_n']}" in text
    assert all(line.count("|") == 6 for line in text.splitlines() if line.startswith("|"))


def test_oos_comparison_shows_undefined_hold_log_score_and_artifact_verdict(generated):
    text = (generated[0] / "oos_comparison.md").read_text(encoding="utf-8")
    hold_row = next(line for line in text.splitlines() if line.startswith("| Always Hold"))
    assert hold_row.rstrip(" |").endswith("undefined¹")
    assert "¹ Always Hold assigns probability zero" in text
    comparison = ARTIFACT["benchmark_comparison"]
    assert f"RMSE ratio (ordered logit / Always Hold): {comparison['rmse_ratio_model_to_hold']:.3f}" in text
    beats = comparison["winner"] != "Always Hold" and comparison["rmse_ratio_model_to_hold"] < 1
    assert ("Ordered logit beats Always Hold" if beats else "Ordered logit does not beat Always Hold") in text
    for label in ("Ordered logit", "Always Hold", "Class-frequency comparator"):
        assert f"| {label}" in text


def test_economic_size_reproduces_artifact_probability_changes(generated):
    out, payload = generated
    numbers = payload["numbers"]
    text = (out / "economic_size.md").read_text(encoding="utf-8")
    for row in ARTIFACT["economic_size_plus_one_sd"]:
        name = row["feature"]
        change = row["probability_change"]["Increase"]["change"] - row["probability_change"]["Decrease"]["change"]
        assert numbers[f"econ_{name}_score_change"]["value"] == pytest.approx(change, abs=1e-9)
        low, high = numbers[f"econ_{name}_band_low"]["value"], numbers[f"econ_{name}_band_high"]["value"]
        assert low <= change <= high
        meaningful = (low > 0 or high < 0) and abs(change) >= numbers["econ_typical_score_move"]["value"]
        assert numbers[f"econ_{name}_meaningful"]["value"] == ("yes" if meaningful else "no")
        assert f"| {app.FEATURE_LABELS[name]} |" in text
        assert f"- **{app.FEATURE_LABELS[name]}:**" in text
    assert "**Rule.**" in text


def test_short_robustness_table_uses_a_result_blind_rule_and_reports_fragility(generated):
    out, payload = generated
    numbers = payload["numbers"]
    ids = [spec for group in report.ROBUSTNESS_CATEGORIES.values() for spec in group]
    assert sorted(ids) == sorted(c["specification_id"] for c in ARTIFACT["robustness_checks"]["checks"])
    by_id = {c["specification_id"]: c for c in ARTIFACT["robustness_checks"]["checks"]}
    for category, group in report.ROBUSTNESS_CATEGORIES.items():
        expected = next((spec for spec in group if by_id[spec]["estimator_converged"]), "none")
        assert numbers[f"robustness_short_{category.lower().replace(' ', '_')}"]["value"] == expected
    flipped = [spec for spec, c in by_id.items() if c["benchmark_conclusion"] not in {ARTIFACT["benchmark_comparison"]["winner"], "UNDETERMINED"}]
    assert numbers["robustness_flipped_benchmark_count"]["value"] == len(flipped)
    text = (out / "robustness_table_short.md").read_text(encoding="utf-8")
    assert f"in {len(flipped)} of {len(by_id)}" in text
    assert "overturns the negative result" in text
    chosen_table = text.split("## All checks")[0]
    assert sum(line.startswith("| Alternative ") for line in chosen_table.splitlines()) == 3
    assert all(f"| {spec}: " not in chosen_table or spec in {numbers[k]["value"] for k in numbers if k.startswith("robustness_short_")}
               for spec in ids)


def test_figures_are_deterministic_pngs(generated, tmp_path):
    from matplotlib.image import imread

    again = tmp_path / "again"
    report.run(again)
    for name in ("fig_history.png", "fig_oos.png", "fig_contributions.png"):
        first, second = generated[0] / name, again / name
        assert first.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert first.read_bytes() == second.read_bytes(), name
        height, width = imread(first).shape[:2]
        assert width >= 1000 and height >= 300


def test_report_reads_only_artifact_and_processed_data(tmp_path):
    for relative in ("model/artifact.json", "data/processed/nbk_decisions_clean.csv", "data/processed/model_panel.csv"):
        target = tmp_path / "inputs" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    inputs = tmp_path / "inputs"
    payload = report.run(tmp_path / "out", inputs / "model/artifact.json",
                         inputs / "data/processed/nbk_decisions_clean.csv", inputs / "data/processed/model_panel.csv")
    assert payload["inputs"] == ["model/artifact.json", "data/processed/nbk_decisions_clean.csv",
                                 "data/processed/model_panel.csv"]


def test_report_refuses_an_artifact_inconsistent_with_processed_data(tmp_path):
    artifact = json.loads(json.dumps(ARTIFACT))
    artifact["benchmark_comparison"]["model"]["rmse"] += 0.01
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(report.ReportError, match="do not reproduce the stored RMSE"):
        report.run(tmp_path / "out", artifact_path=path)


def test_report_source_types_no_result_numbers():
    numbers = json.loads((OUTPUTS / "numbers_for_note.json").read_text(encoding="utf-8"))["numbers"]
    # Stated constants (such as the 2.8 power multiplier) are inputs, not results.
    def stated_constant(entry):
        return isinstance(entry["source"], dict) and entry["source"].get("derived_from") == ["stated approximation"]

    results = [entry["value"] for entry in numbers.values()
               if isinstance(entry["value"], float) and entry["value"] not in (0.0, 1.0, -1.0)
               and not stated_constant(entry)]
    tree = ast.parse((ROOT / "src" / "report.py").read_text(encoding="utf-8"))
    floats = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and type(node.value) is float]
    assert not [(c, v) for c in floats for v in results if abs(c - v) < 1e-9]


def test_committed_outputs_equal_a_fresh_report(generated):
    out, _ = generated
    tolerance = ARTIFACT["replication_tolerance"]["coefficients_absolute"]
    for name in report.OUTPUT_FILES:
        if name.endswith(".png"):
            # Figures: same size and pixel difference within tolerance, as src.check compares them, because
            # PNG bytes can differ across platforms (zlib, metadata) while the image is the same.
            result = check.Report()
            check.compare_png(result, name, OUTPUTS / name, out / name, tolerance)
            assert result.failed == 0, f"outputs/{name}: {result.rows[-1][2]}; run `python run.py report`"
            continue
        assert (OUTPUTS / name).read_bytes().replace(b"\r\n", b"\n") == (out / name).read_bytes().replace(b"\r\n", b"\n"), (
            f"outputs/{name} is stale; run `python run.py report`")


def test_a_visibly_different_figure_still_fails(tmp_path):
    import numpy as np
    from matplotlib.image import imread, imsave

    committed = OUTPUTS / "fig_oos.png"
    image = imread(committed).copy()
    height, width = image.shape[:2]
    image[height // 4: height // 2, width // 4: width // 2, :3] = 0.0  # a black block over part of the plot
    altered = tmp_path / "altered.png"
    imsave(altered, image)
    result = check.Report()
    check.compare_png(result, "fig_oos.png", committed, altered, ARTIFACT["replication_tolerance"]["coefficients_absolute"])
    assert result.failed == 1
    resized = tmp_path / "resized.png"
    imsave(resized, np.asarray(imread(committed))[: height - 10])
    result = check.Report()
    check.compare_png(result, "fig_oos.png", committed, resized, ARTIFACT["replication_tolerance"]["coefficients_absolute"])
    assert result.failed == 1 and "image size" in result.rows[-1][2]


# ------------------------------------------------------------------- README


def test_readme_is_the_render_of_the_template_and_committed_numbers():
    rendered = readme.build(OUTPUTS / "numbers_for_note.json")
    assert (ROOT / "README.md").read_text(encoding="utf-8").replace("\r\n", "\n") == rendered


def test_readme_template_contains_no_typed_result_numbers():
    template = readme.TEMPLATE_COMMENT.sub("", readme.TEMPLATE_PATH.read_text(encoding="utf-8"))
    body = readme.PLACEHOLDER.sub("", template)
    digits = re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])", body)
    unexpected = sorted({token for token in digits if token not in TEMPLATE_LITERALS})
    assert not unexpected, f"type these through numbers_for_note.json instead: {unexpected}"


def test_readme_unknown_placeholder_is_an_error():
    numbers = {"numbers": {"a": {"display": "1"}}, "verdict_sentence": "v"}
    assert readme.render("x {{a}} {{verdict_sentence}}", numbers).endswith("x 1 v")
    with pytest.raises(KeyError, match="not_a_key"):
        readme.render("{{not_a_key}}", numbers)


def test_readme_covers_required_sections_and_mentions_legacy_accuracy_only_in_legacy_note():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for heading in ("## The indicator", "## Install", "## Run the site", "## Regenerate all outputs",
                    "## Checks and tolerance", "## Project structure", "## Limitations", "## Declared borrowing",
                    "## Legacy note"):
        assert heading in text, heading
    for topic in ("Always Hold", "Release-lag", "Irregular decision-date", "No data vintages",
                  "Household lending is non-stationary", "Parameter instability", "Windows", "macOS / Linux"):
        assert topic in text, topic
    current, legacy = text.split("## Legacy note", 1)
    assert "accuracy" not in current.lower()
    assert "**Legacy, not a current result.**" in legacy
    assert not re.search(r"\d", legacy), "the legacy note must not quote numbers"


# ----------------------------------------------------------- src.check parts


def test_check_fails_committed_markdown_that_is_not_regenerated(tmp_path):
    committed = tmp_path / "hand_written.md"
    committed.write_text("value 1.0\n", encoding="utf-8")
    result = check.Report()
    check.compare_markdown(result, committed.name, committed, tmp_path / "missing.md", tolerance=1e-6)
    assert result.failed == 1
    assert not any(status == "SKIP" for status, _, _ in result.rows)


def test_check_compares_numbers_and_figures(generated, tmp_path):
    out, payload = generated
    altered = json.loads(json.dumps(payload))
    altered["numbers"]["n_holdout"]["value"] += 1
    altered["numbers"]["oos_winner"]["value"] = "Ordered Logit"
    altered_path = tmp_path / "numbers.json"
    altered_path.write_text(json.dumps(altered), encoding="utf-8")
    result = check.Report()
    check.compare_numbers(result, out / "numbers_for_note.json", altered_path, 1e-6, 0.01, check.HEADLINE_NUMBER_KEYS)
    failed = {item for status, item, _ in result.rows if status == "FAIL"}
    assert failed == {"outputs/numbers_for_note.json n_holdout", "outputs/numbers_for_note.json oos_winner"}

    result = check.Report()
    check.compare_png(result, "fig_oos.png", out / "fig_oos.png", out / "fig_oos.png", 1e-6)
    check.compare_png(result, "fig_oos.png", out / "fig_oos.png", out / "fig_history.png", 1e-6)
    assert [status for status, _, _ in result.rows] == ["PASS", "FAIL"]


# ------------------------------------------------- platform-sensitive results (D14)


def _md_pair(tmp_path, committed: str, rebuilt: str):
    a, b = tmp_path / "committed.md", tmp_path / "rebuilt.md"
    a.write_text(committed, encoding="utf-8")
    b.write_text(rebuilt, encoding="utf-8")
    return a, b


ANNEX = (
    "| inflation | 0.02199296137093244 | 0.07013790331697874 |\n"
    "| Parameter stability LR | LR test of slope equality across 2015-2019 and 2020+ | 15.217553714524797 | 6.0 |\n"
    "| run | run-0074 | LR stability unrestricted ordered logit, BFGS attempt | optimizer_attempt | 70 | NONCONVERGED | -54.2 |\n"
    "| household_lending | 0.07512542007843497 | 0.02683617183658186 |\n"
)


def test_changed_main_coefficient_still_fails(tmp_path):
    result = check.Report()
    check.compare_markdown(result, "annex.md", *_md_pair(tmp_path, ANNEX, ANNEX.replace("0.02199296137093244", "0.02299296137093244")),
                           tolerance=1e-6)
    assert result.failed == 1 and not [row for row in result.rows if row[0] == "WARN"]
    result = check.Report()
    assert result.check("coefficient inflation", 0.02199296137093244, 0.02299296137093244, 1e-6) is False
    assert result.failed == 1


def test_stability_difference_of_one_thousandth_is_warn_not_fail(tmp_path):
    rebuilt = ANNEX.replace("15.217553714524797", "15.218553714524797").replace("-54.2", "-54.201")
    result = check.Report()
    check.compare_markdown(result, "annex.md", *_md_pair(tmp_path, ANNEX, rebuilt), tolerance=1e-6)
    warnings = [row for row in result.rows if row[0] == "WARN"]
    assert result.failed == 0 and len(warnings) == 2
    assert all("platform-sensitive (optimizer did not converge)" in detail for _, _, detail in warnings)
    assert "committed=[" in warnings[0][2] and "rebuilt=[" in warnings[0][2]


def test_a_shifted_number_in_a_nonconverged_row_does_not_cascade(tmp_path):
    rebuilt = ANNEX.replace("| -54.2 |", "| -54.2 | 2 |")  # one extra number in the non-converged row
    result = check.Report()
    check.compare_markdown(result, "annex.md", *_md_pair(tmp_path, ANNEX, rebuilt), tolerance=1e-6)
    assert result.failed == 0
    assert [row[0] for row in result.rows] == ["WARN", "PASS"]


def test_prose_mentioning_nonconverged_is_still_checked_strictly(tmp_path):
    committed = "Fits marked NONCONVERGED are kept. The main 18-row holdout is unchanged.\n"
    result = check.Report()
    check.compare_markdown(result, "robustness.md", *_md_pair(tmp_path, committed, committed.replace("18-row", "17-row")),
                           tolerance=1e-6)
    assert result.failed == 1


def test_only_rb02_convergence_is_a_warn_key_in_the_numbers_file(generated, tmp_path):
    out, payload = generated
    altered = json.loads(json.dumps(payload))
    altered["numbers"]["robustness_RB02_converged"]["value"] = not altered["numbers"]["robustness_RB02_converged"]["value"]
    altered["numbers"]["stability_lr_p"]["value"] += 1e-3
    path = tmp_path / "numbers.json"
    path.write_text(json.dumps(altered), encoding="utf-8")
    result = check.Report()
    check.compare_numbers(result, out / "numbers_for_note.json", path, 1e-6, 0.01, check.HEADLINE_NUMBER_KEYS)
    statuses = {item.rsplit(" ", 1)[-1]: status for status, item, _ in result.rows if status != "PASS"}
    assert statuses == {"robustness_RB02_converged": "WARN", "stability_lr_p": "FAIL"}

# ---------------------------------------------------------- power and RB09


def test_power_note_is_computed_from_the_artifact(generated):
    out, payload = generated
    numbers = payload["numbers"]
    multiplier = numbers["power_multiplier"]["value"]
    for name in app.FEATURES:
        se = ARTIFACT["model"]["coefficient_table"][name]["hc0_standard_error"]
        estimate = ARTIFACT["model"]["coefficient_table"][name]["coefficient_or_cutpoint"]
        assert numbers[f"power_{name}_mde"]["value"] == pytest.approx(multiplier * se, abs=1e-12)
        assert numbers[f"power_{name}_ratio"]["value"] == pytest.approx(estimate / (multiplier * se), abs=1e-12)
    text = (out / "power_note.md").read_text(encoding="utf-8")
    assert f"N = {ARTIFACT['sample']['estimation_n']} decisions" in text and "× SE" in text
    assert "failure to reject a zero slope is not evidence that the factor has no effect" in text


def test_rb09_sentence_in_readme_matches_the_artifact():
    numbers = json.loads((OUTPUTS / "numbers_for_note.json").read_text(encoding="utf-8"))["numbers"]
    checks = ARTIFACT["robustness_checks"]["checks"]
    rb09 = next(check for check in checks if check["specification_id"] == "RB09")
    coefficient = next(row for row in rb09["coefficients"] if row["name"] == "household_lending")
    assert numbers["robustness_RB09_household_lending_coef"]["value"] == coefficient["estimate"]
    assert numbers["robustness_RB09_household_lending_p_holm"]["value"] == coefficient["p_value_adjusted"]
    # The README states the loss of significance as fixed prose; it must stay true.
    assert numbers["robustness_RB09_household_lending_loses_significance"]["value"] == "yes"
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "the only significant factor loses significance when its non-stationarity is removed" in readme
    assert f"Holm p {numbers['robustness_RB09_household_lending_p_holm']['display']}" in readme

# ------------------------------------------- cross-platform rules (D14 update)


def _compare(tmp_path, name, committed, rebuilt):
    a, b = tmp_path / "committed.md", tmp_path / "rebuilt.md"
    a.write_text(committed, encoding="utf-8")
    b.write_text(rebuilt, encoding="utf-8")
    result = check.Report()
    check.compare_markdown(result, name, a, b, tolerance=1e-6)
    return result


EXPANDING = "| run | run-0077 | expanding ordered logit n=42 | expanding_window_fit | 42 | COMPLETED | fopt=55.12345 | gopt=0.00123 |\n"


def test_group1_expanding_window_internals_are_warn_and_only_for_that_row_type(tmp_path):
    rebuilt = EXPANDING.replace("55.12345", "55.17857").replace("0.00123", "0.00124")  # ~1e-3 relative
    result = _compare(tmp_path, "annex_diagnostics.md", EXPANDING, rebuilt)
    warnings = [row for row in result.rows if row[0] == "WARN"]
    assert result.failed == 0 and len(warnings) == 1
    assert "platform-sensitive (optimizer internals)" in warnings[0][2]
    other = EXPANDING.replace("expanding_window_fit", "coefficient_test")
    result = _compare(tmp_path, "annex_diagnostics.md", other,
                      other.replace("55.12345", "55.17857").replace("0.00123", "0.00124"))
    assert result.failed >= 1 and not [row for row in result.rows if row[0] == "WARN"]


def test_group2_rounding_level_differences_pass_in_the_two_annex_files_only(tmp_path):
    cases = [
        ("annex_diagnostics.md", "| cutpoint[Hold|Increase] | 3.3149380105299433 | 0.7455704247902439 | 4.446176914 |\n",
         "4.446176914", "4.446171656"),
        ("robustness_table.md", "| RB04 | inflation | -0.0116 | 0.8698067868 |\n", "0.8698067868", "0.8698081716"),
        ("robustness_table.md", "| RB07 | corporate_lending | -0.0704 | 0.7840220150 |\n", "0.7840220150", "0.7840233510"),
    ]
    for name, line, old, new in cases:
        result = _compare(tmp_path, name, line, line.replace(old, new))
        assert result.failed == 0 and not [row for row in result.rows if row[0] == "WARN"], (name, old)
        assert "cross-platform tolerance" in result.rows[-1][2]
        # The same rounding-level difference anywhere else is still a FAIL at 1e-6.
        result = _compare(tmp_path, "results_table.md", line, line.replace(old, new))
        assert result.failed == 1, (name, old)
    # A difference of 1e-3 is larger than the allowance and fails even in the annex files.
    line = cases[0][1]
    result = _compare(tmp_path, "annex_diagnostics.md", line, line.replace("4.446176914", "4.447176914"))
    assert result.failed == 1


def test_group3_converged_counts_are_warn_but_the_rest_of_the_line_stays_strict(tmp_path):
    line = ("Total specifications: 10 (one primary specification plus 9 requested robustness specifications). "
            "Robustness checks converged: 8; nonconverged or failed: 1.\n")
    linux = line.replace("converged: 8; nonconverged or failed: 1", "converged: 9; nonconverged or failed: 0")
    result = _compare(tmp_path, "robustness_table.md", line, linux)
    warnings = [row for row in result.rows if row[0] == "WARN"]
    assert result.failed == 0 and len(warnings) == 1 and "depends on RB02 convergence" in warnings[0][2]
    result = _compare(tmp_path, "robustness_table.md", line, linux.replace("Total specifications: 10", "Total specifications: 11"))
    assert result.failed == 1


def test_main_results_still_fail_at_one_thousandth(tmp_path):
    results = (OUTPUTS / "results_table.md").read_text(encoding="utf-8")
    oos = (OUTPUTS / "oos_comparison.md").read_text(encoding="utf-8")
    household = next(line for line in results.splitlines() if line.startswith("| Household lending |"))
    cells = [cell.strip() for cell in household.strip("|").split("|")]
    for name, text, old, new in [
        ("results_table.md", results, household, household.replace(cells[1], f"{float(cells[1]) + 1e-3:.4f}", 1)),
        ("results_table.md", results, household, household.replace(cells[4], f"{float(cells[4]) + 1e-3:.3f}", 1)),
        ("oos_comparison.md", oos, "RMSE ratio (ordered logit / Always Hold): 1.002",
         "RMSE ratio (ordered logit / Always Hold): 1.003"),
    ]:
        assert old in text and old != new
        result = _compare(tmp_path, name, text, text.replace(old, new, 1))
        assert result.failed >= 1, (name, new)