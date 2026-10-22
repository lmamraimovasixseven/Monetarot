"""Generate every table, figure and number the 4-page note uses: `python -m src.report`.

Reads only model/artifact.json and data/processed/, writes only to outputs/:

* results_table.md      coefficients, HC0 SE, raw and Holm p, cutpoints, N
* oos_comparison.md     holdout RMSE / MAE / log score vs Always Hold and the
                        class-frequency comparator, RMSE ratio and verdict
* fig_history.png       decision history with the model score
* fig_oos.png           holdout expected score vs actual vs Always Hold
* fig_contributions.png three largest driver contributions to the latest change
* numbers_for_note.json every number the note quotes, each with its source

Predictions are recomputed from the stored parameters with the dashboard's
own formulas (src.app); nothing is estimated here. No result is typed by hand:
every value is read from the artifact or derived from it, and its source is
recorded next to it.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from pathlib import Path
from typing import Any

import matplotlib
from streamlit.logger import get_logger

# src.app's st.cache_data decorators log a harmless "No runtime found" outside Streamlit.
get_logger("streamlit.runtime.caching.cache_data_api").setLevel(logging.ERROR)

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from statistics import NormalDist  # noqa: E402

from src.app import (  # noqa: E402
    FEATURE_LABELS,
    FEATURES,
    ordered_probabilities,
    policy_pressure_score,
    score_and_delta_band,
    score_gradient,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = ROOT / "model" / "artifact.json"
DECISIONS_PATH = ROOT / "data" / "processed" / "nbk_decisions_clean.csv"
MODEL_PANEL_PATH = ROOT / "data" / "processed" / "model_panel.csv"
OUTPUTS = ROOT / "outputs"
SCORE_MAP = {"Decrease": -1, "Hold": 0, "Increase": 1}
SCORE_AXIS_LABEL = "Decision score\n(−1 cut, 0 hold, +1 hike)"
CUTPOINTS = ["cutpoint[Decrease|Hold]", "cutpoint[Hold|Increase]"]
TOP_DRIVERS = 3
OUTPUT_FILES = [
    "results_table.md", "oos_comparison.md", "economic_size.md", "robustness_table_short.md", "power_note.md",
    "fig_history.png", "fig_oos.png", "fig_contributions.png", "numbers_for_note.json",
]
# Classification of RB01-RB09 into the three required kinds of check. The short
# table shows, per kind, the first check in id order whose estimator converged;
# the rule never looks at the check's result.
ROBUSTNESS_CATEGORIES = {
    "Alternative sample": ["RB01", "RB02"],
    "Alternative specification": ["RB03", "RB06", "RB07"],
    "Alternative measure": ["RB04", "RB05", "RB08", "RB09"],
}
# Power: minimum detectable effect = (z_0.975 + z_0.80) x SE, the conventional 1.96 + 0.84 = 2.8 approximation.
POWER_MULTIPLIER = 2.8
POWER_ALPHA = 0.05
ROBUSTNESS_SELECTION_RULE = ("For each kind of check, the first specification in id order whose estimator "
                             "converged. The rule does not look at RMSE ratios, signs or survival.")
# Readable at a 4-page note's single-column width.
FIGURE_STYLE = {
    "font.size": 9, "axes.labelsize": 9, "axes.titlesize": 9, "legend.fontsize": 8,
    "xtick.labelsize": 8, "ytick.labelsize": 8, "font.family": "DejaVu Sans",
    "axes.spines.top": False, "axes.spines.right": False, "svg.hashsalt": "kz-base-rate-model",
}
FIGURE_WIDTH_INCHES = 6.3
FIGURE_DPI = 200
COLORS = {"actual": "#3b4252", "model": "#2a6fb0", "hold": "#9a9a9a", "holdout": "#f1e7cf",
          "positive": "#b5523b", "negative": "#2a6fb0"}


class ReportError(RuntimeError):
    """The artifact and processed data disagree, or a required field is missing."""


# ------------------------------------------------------------------ numbers


def resolve(document: Any, pointer: str) -> Any:
    """Follow a JSON Pointer (RFC 6901) such as /model/parameters/inflation."""
    node = document
    for part in pointer.lstrip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def _display(value: Any, kind: str) -> str:
    if kind == "factor":
        return FEATURE_LABELS.get(value, value).lower()
    if isinstance(value, str):
        return "undefined" if value.lower() in {"+infinity", "infinity", "inf", "nan"} else value
    if isinstance(value, bool):
        return "yes" if value else "no"
    if kind == "int":
        return f"{int(value)}"
    if kind == "score":
        return f"{value:+.3f}"
    if kind == "prob":
        return f"{value * 100:.1f}%"
    if kind == "p":
        return f"{value:.1e}" if 0 < value < 0.001 else f"{value:.3f}"
    if kind == "coef":
        return f"{value:.4f}"
    if kind in {"ratio", "stat"}:
        return f"{value:.3f}"
    if kind == "tol":
        return f"{value:g}"
    raise ValueError(f"Unknown display kind: {kind}")


class NumberBook:
    """Every number quoted in the note, with its value, display text and source."""

    def __init__(self, artifact: dict) -> None:
        self.artifact = artifact
        self.items: dict[str, dict[str, Any]] = {}

    def _add(self, key: str, value: Any, kind: str, source: Any, note: str | None) -> Any:
        if key in self.items:
            raise ReportError(f"Duplicate number key: {key}")
        if isinstance(value, float) and not math.isfinite(value):
            value = "+Infinity" if value > 0 else "NaN"
        entry = {"value": value, "display": _display(value, kind), "kind": kind, "source": source}
        if note:
            entry["note"] = note
        self.items[key] = entry
        return value

    def take(self, key: str, pointer: str, kind: str, note: str | None = None) -> Any:
        try:
            value = resolve(self.artifact, pointer)
        except (KeyError, IndexError, ValueError) as error:
            raise ReportError(f"Artifact field missing: {pointer}") from error
        return self._add(key, value, kind, f"model/artifact.json#{pointer}", note)

    def derive(self, key: str, value: Any, kind: str, inputs: list[str], method: str) -> Any:
        return self._add(key, value, kind, {"derived_from": inputs, "method": method}, None)

    def display(self, key: str) -> str:
        return self.items[key]["display"]


def _find_index(rows: list[dict], **match: Any) -> int:
    for index, row in enumerate(rows):
        if all(row.get(name) == value for name, value in match.items()):
            return index
    raise ReportError(f"No artifact row matches {match}")


def _expected_scores(artifact: dict, frame: pd.DataFrame) -> np.ndarray:
    return np.asarray([
        policy_pressure_score(ordered_probabilities(artifact, {name: float(row[name]) for name in FEATURES}))
        for _, row in frame.iterrows()
    ])


def collect_numbers(artifact: dict, holdout: pd.DataFrame, tolerance: float) -> NumberBook:
    book = NumberBook(artifact)
    take, derive = book.take, book.derive

    # Headline indicator.
    take("latest_decision_date", "/latest_prediction/date", "text")
    headline = take("headline_score", "/latest_prediction/expected_score", "score")
    latest = {name: float(artifact["latest_feature_vector"][name]) for name in FEATURES}
    score, low, high = score_and_delta_band(artifact, latest)
    if abs(score - headline) > tolerance:
        raise ReportError("Stored expected score disagrees with the stored parameters")
    band_inputs = ["model/artifact.json#/model/parameters", "model/artifact.json#/model/covariance_hc0",
                   "model/artifact.json#/latest_feature_vector"]
    method = "95% delta-method band using HC0 covariance (src.app.score_and_delta_band), clipped to [-1, 1]"
    derive("headline_score_band_low", max(-1.0, low), "score", band_inputs, method)
    derive("headline_score_band_high", min(1.0, high), "score", band_inputs, method)
    for label in ("Increase", "Hold", "Decrease"):
        take(f"next_round_probability_{label.lower()}", f"/latest_prediction/class_probabilities/{label}", "prob",
             "both upcoming rounds use the latest factor values, so their probabilities are identical")

    # Latest change and the drivers behind it.
    contributions = artifact["per_factor_contribution_to_latest_score_change"]
    previous = {row["feature"]: float(row["previous_usable_decision_value"]) for row in contributions}
    derive("latest_score_change", headline - policy_pressure_score(ordered_probabilities(artifact, previous)), "score",
           ["model/artifact.json#/latest_prediction/expected_score",
            "model/artifact.json#/per_factor_contribution_to_latest_score_change/*/previous_usable_decision_value"],
           "latest expected score minus the expected score at the previous usable decision's factor values")
    ranked = sorted(range(len(contributions)),
                    key=lambda i: abs(contributions[i]["expected_score_contribution_to_latest_change"]), reverse=True)
    for rank, index in enumerate(ranked[:TOP_DRIVERS], start=1):
        take(f"driver_{rank}_factor", f"/per_factor_contribution_to_latest_score_change/{index}/feature", "factor")
        take(f"driver_{rank}_contribution",
             f"/per_factor_contribution_to_latest_score_change/{index}/expected_score_contribution_to_latest_change",
             "score")

    # Sample.
    for key in ("usable_n", "dropped_n", "estimation_n", "holdout_n"):
        take(f"n_{key.removesuffix('_n')}", f"/sample/{key}", "int")
    for key in ("usable_start", "usable_end", "estimation_start", "estimation_end", "holdout_start", "holdout_end"):
        take(f"sample_{key}", f"/sample/{key}", "text")
    take("holdout_fraction", "/specification/holdout_fraction", "ratio")
    for value, label in (("-1", "decrease"), ("0", "hold"), ("1", "increase")):
        take(f"holdout_actual_{label}_count", f"/benchmark_comparison/actual_score_distribution/{value}", "int")

    # Coefficients.
    for name in FEATURES:
        take(f"coef_{name}", f"/model/coefficient_table/{name}/coefficient_or_cutpoint", "coef")
        take(f"se_{name}", f"/model/coefficient_table/{name}/hc0_standard_error", "coef")
        take(f"p_raw_{name}", f"/model/coefficient_table/{name}/p_value", "p")
        take(f"p_holm_{name}", f"/model/coefficient_table/{name}/p_value_holm", "p")
    for index, name in enumerate(CUTPOINTS, start=1):
        take(f"cutpoint_{index}", f"/model/coefficient_table/{name}/coefficient_or_cutpoint", "coef")
        take(f"cutpoint_{index}_se", f"/model/coefficient_table/{name}/hc0_standard_error", "coef")
        take(f"cutpoint_{index}_p_raw", f"/model/coefficient_table/{name}/p_value", "p")
    take("pseudo_r2_mcfadden", "/model/pseudo_r2_mcfadden", "ratio")

    # Out-of-sample comparison.
    for prefix, pointer in (("model", "model"), ("hold", "benchmark_always_hold")):
        take(f"oos_{prefix}_rmse", f"/benchmark_comparison/{pointer}/rmse", "ratio")
        take(f"oos_{prefix}_mae", f"/benchmark_comparison/{pointer}/mae", "ratio")
        take(f"oos_{prefix}_log_score", f"/benchmark_comparison/{pointer}/log_score", "ratio")
    take("oos_frequency_log_score", "/benchmark_comparison/class_frequency_comparator_secondary/log_score", "ratio")
    take("oos_frequency_label", "/benchmark_comparison/class_frequency_comparator_secondary/label", "text")
    take("rmse_ratio", "/benchmark_comparison/rmse_ratio_model_to_hold", "ratio")
    take("oos_winner", "/benchmark_comparison/winner", "text")

    recomputed = _expected_scores(artifact, holdout)
    rmse = float(np.sqrt(np.mean((recomputed - holdout["y"].to_numpy(dtype=float)) ** 2)))
    if abs(rmse - artifact["benchmark_comparison"]["model"]["rmse"]) > tolerance:
        raise ReportError("Holdout predictions recomputed from data/processed do not reproduce the stored RMSE")

    # Diagnostics and falsification.
    diagnostics = artifact["diagnostics"]
    take("joint_lr_statistic", "/diagnostics/joint_slope_lr/statistic", "stat")
    take("joint_lr_p", "/diagnostics/joint_slope_lr/p_value", "p")
    take("stability_lr_statistic", "/diagnostics/parameter_stability/statistic", "stat")
    take("stability_lr_p", "/diagnostics/parameter_stability/p_value", "p")
    take("stability_lr_flag", "/diagnostics/parameter_stability/pass_fail", "text")
    take("stability_split_n_early", "/diagnostics/parameter_stability/groups_n/2015-2019", "int")
    take("stability_split_n_late", "/diagnostics/parameter_stability/groups_n/2020+", "int")
    take("proportional_odds_p", "/diagnostics/proportional_odds/p_value", "p")
    take("serial_correlation_p", "/diagnostics/serial_correlation/p_value", "p")
    unit_roots = diagnostics["unit_root_tests"]
    for feature in FEATURES:
        for test in ("ADF", "KPSS"):
            index = _find_index(unit_roots, feature=feature, form="transformed_model_input", test=test)
            take(f"unit_root_{feature}_{test.lower()}_p", f"/diagnostics/unit_root_tests/{index}/p_value", "p")
            take(f"unit_root_{feature}_{test.lower()}_flag", f"/diagnostics/unit_root_tests/{index}/pass_fail", "text")
    for index in range(len(artifact["falsification_verdicts"])):
        take(f"falsification_{index + 1}_rule", f"/falsification_verdicts/{index}/rule", "text")
        take(f"falsification_{index + 1}_verdict", f"/falsification_verdicts/{index}/verdict", "text")

    # Robustness RB01-RB09.
    checks = artifact["robustness_checks"]["checks"]
    for index, check in enumerate(checks):
        spec = check["specification_id"]
        take(f"robustness_{spec}_name", f"/robustness_checks/checks/{index}/name", "text")
        take(f"robustness_{spec}_survives", f"/robustness_checks/checks/{index}/survives", "text")
        take(f"robustness_{spec}_rmse_ratio", f"/robustness_checks/checks/{index}/rmse_ratio_model_to_hold", "ratio")
        take(f"robustness_{spec}_n_usable", f"/robustness_checks/checks/{index}/n_usable", "int")
        take(f"robustness_{spec}_converged", f"/robustness_checks/checks/{index}/estimator_converged", "text")
        take(f"robustness_{spec}_benchmark_conclusion",
             f"/robustness_checks/checks/{index}/benchmark_conclusion", "text")
        take(f"robustness_{spec}_same_signs", f"/robustness_checks/checks/{index}/same_signs_as_primary", "text")
    survivors = [check["specification_id"] for check in checks if str(check.get("survives")).lower() == "yes"]
    survives_source = ["model/artifact.json#/robustness_checks/checks/*/survives"]
    derive("robustness_survivor_count", len(survivors), "int", survives_source, "count of checks with survives == Yes")
    derive("robustness_survivors", ", ".join(survivors) or "none", "text", survives_source,
           "specification ids with survives == Yes")
    primary_conclusion = artifact["benchmark_comparison"]["winner"]
    flipped = [check["specification_id"] for check in checks
               if check.get("benchmark_conclusion") not in {primary_conclusion, "UNDETERMINED"}]
    flipped_source = ["model/artifact.json#/robustness_checks/checks/*/benchmark_conclusion",
                      "model/artifact.json#/benchmark_comparison/winner"]
    derive("robustness_flipped_benchmark_count", len(flipped), "int", flipped_source,
           "count of checks whose benchmark conclusion differs from the main model's winner")
    derive("robustness_flipped_benchmark_ids", ", ".join(flipped) or "none", "text", flipped_source,
           "specification ids whose benchmark conclusion differs from the main model's winner")
    for family in ("slope_coefficients", "joint_slope_lr", "diagnostics", "robustness_specifications", "cutpoints"):
        take(f"family_{family}", f"/diagnostics/p_value_families/{family}", "text")
    take("robustness_check_count", "/robustness_checks/robustness_specification_count", "int")
    take("total_specifications", "/robustness_checks/total_specifications_including_primary", "int")

    # Reproducibility.
    take("seed", "/seed", "int")
    take("tolerance_coefficients", "/replication_tolerance/coefficients_absolute", "tol")
    take("tolerance_headline", "/replication_tolerance/headline_score_absolute", "tol")
    take("tolerance_headline_name", "/replication_tolerance/headline_score_name", "text")
    take("data_sha256", "/data_sha256_normalized_crlf_to_lf", "text")
    return book


def collect_economic_size(book: NumberBook, artifact: dict, usable: pd.DataFrame, tolerance: float) -> None:
    """Policy-pressure-score change for a +1 SD move per factor, other factors at estimation means."""
    estimation_dates = pd.to_datetime(artifact["sample"]["estimation_rows"])
    train = usable.loc[usable["decision_date"].isin(estimation_dates)]
    if len(train) != artifact["sample"]["estimation_n"]:
        raise ReportError("Estimation rows in the artifact are not all present in data/processed/model_panel.csv")
    covariance = np.asarray(artifact["model"]["covariance_hc0"], dtype=float)
    critical = NormalDist().inv_cdf(0.975)
    baseline = {name: float(train[name].mean()) for name in FEATURES}
    base_score, base_gradient = score_gradient(artifact, baseline)

    scores = _expected_scores(artifact, train)
    estimation_source = ["model/artifact.json#/sample/estimation_rows", "model/artifact.json#/model/parameters",
                         "data/processed/model_panel.csv"]
    typical = book.derive("econ_typical_score_move", float(np.median(np.abs(np.diff(scores)))), "stat",
                          estimation_source,
                          "median absolute change of the model score between consecutive estimation-sample decisions")
    for index, row in enumerate(artifact["economic_size_plus_one_sd"]):
        feature = row["feature"]
        sd = book.take(f"econ_{feature}_sd", f"/economic_size_plus_one_sd/{index}/sd", "coef")
        if abs(sd - float(train[feature].std(ddof=1))) > tolerance:
            raise ReportError(f"Stored SD for {feature} does not match data/processed estimation rows")
        shifted = dict(baseline)
        shifted[feature] += sd
        score, gradient = score_gradient(artifact, shifted)
        change = score - base_score
        stored = row["probability_change"]
        if abs(change - (stored["Increase"]["change"] - stored["Decrease"]["change"])) > tolerance:
            raise ReportError(f"Economic size for {feature} does not reproduce the stored probability changes")
        difference = gradient - base_gradient
        se = float(np.sqrt(max(float(difference @ covariance @ difference), 0.0)))
        inputs = [f"model/artifact.json#/economic_size_plus_one_sd/{index}", "model/artifact.json#/model/covariance_hc0",
                  *estimation_source]
        method = "score at estimation means + 1 SD minus score at means; 95% delta-method band"
        book.derive(f"econ_{feature}_score_change", change, "score", inputs, method)
        low = book.derive(f"econ_{feature}_band_low", change - critical * se, "score", inputs, method)
        high = book.derive(f"econ_{feature}_band_high", change + critical * se, "score", inputs, method)
        meaningful = (low > 0 or high < 0) and abs(change) >= typical
        book.derive(f"econ_{feature}_meaningful", "yes" if meaningful else "no", "text",
                    [*inputs, "econ_typical_score_move"],
                    "yes if the 95% band excludes zero and |change| >= the typical decision-to-decision move")
    meaningful_labels = [FEATURE_LABELS[row["feature"]].lower() for row in artifact["economic_size_plus_one_sd"]
                         if book.items[f"econ_{row['feature']}_meaningful"]["value"] == "yes"]
    book.derive("econ_meaningful_factors", ", ".join(meaningful_labels) or "none", "text",
                ["econ_*_meaningful"], "factors whose one-SD move is economically meaningful by the stated rule")
    book.derive("econ_meaningful_count", len(meaningful_labels), "int", ["econ_*_meaningful"],
                "number of factors whose one-SD move is economically meaningful by the stated rule")


def collect_rb09_household(book: NumberBook, artifact: dict) -> None:
    """Household lending in RB09 (differenced non-stationary factors), from the stored robustness check."""
    checks = artifact["robustness_checks"]["checks"]
    index = _find_index(checks, specification_id="RB09")
    position = _find_index(checks[index]["coefficients"], name="household_lending")
    base = f"/robustness_checks/checks/{index}/coefficients/{position}"
    book.take("robustness_RB09_household_lending_coef", f"{base}/estimate", "coef")
    book.take("robustness_RB09_household_lending_p_raw", f"{base}/p_value", "p")
    holm = book.take("robustness_RB09_household_lending_p_holm", f"{base}/p_value_adjusted", "p")
    main_holm = book.items["p_holm_household_lending"]["value"]
    lost = main_holm < POWER_ALPHA and holm >= POWER_ALPHA
    book.derive("robustness_RB09_household_lending_loses_significance", "yes" if lost else "no", "text",
                [f"model/artifact.json#{base}/p_value_adjusted",
                 "model/artifact.json#/model/coefficient_table/household_lending/p_value_holm"],
                "yes if Holm p < 0.05 in the main model and >= 0.05 in RB09")


def collect_power(book: NumberBook, artifact: dict) -> None:
    """Minimum detectable effect per slope: MDE = (z_0.975 + z_0.80) x SE, using the stated 2.8 approximation."""
    book.derive("power_multiplier", POWER_MULTIPLIER, "stat", ["stated approximation"],
                "z(0.975) + z(0.80) = 1.96 + 0.84, rounded to 2.8 (5% two-sided test, 80% power)")
    for name in FEATURES:
        estimate = book.items[f"coef_{name}"]["value"]
        se = book.items[f"se_{name}"]["value"]
        mde = POWER_MULTIPLIER * se
        inputs = [f"model/artifact.json#/model/coefficient_table/{name}/coefficient_or_cutpoint",
                  f"model/artifact.json#/model/coefficient_table/{name}/hc0_standard_error"]
        book.derive(f"power_{name}_mde", mde, "coef", inputs, "power_multiplier x HC0 standard error")
        book.derive(f"power_{name}_ratio", estimate / mde, "ratio", inputs, "estimate / minimum detectable effect")


def power_note(book: NumberBook) -> str:
    d = book.display
    rows = [[FEATURE_LABELS[name], d(f"coef_{name}"), d(f"se_{name}"), d(f"power_{name}_mde")] for name in FEATURES]
    lines = [
        "# Power: minimum detectable effects",
        "",
        f"For each slope, the minimum detectable effect (MDE) at a 5% two-sided test with 80% power is "
        f"MDE = (z₀.₉₇₅ + z₀.₈₀) × SE ≈ {d('power_multiplier')} × SE, using the robust (HC0) standard error from the "
        f"estimation sample (N = {d('n_estimation')} decisions).",
        "",
        *_markdown_table(["Factor", "Estimate", "Robust SE (HC0)", "MDE (5%, 80% power)"], rows),
        "",
        f"At this sample size (N = {d('n_estimation')}), failure to reject a zero slope is not evidence that the "
        f"factor has no effect.",
        "",
        "Generated by `python -m src.report` from model/artifact.json.",
        "",
    ]
    return "\n".join(lines)


def collect_robustness_short(book: NumberBook, artifact: dict) -> None:
    checks = {check["specification_id"]: index for index, check in enumerate(artifact["robustness_checks"]["checks"])}
    for category, ids in ROBUSTNESS_CATEGORIES.items():
        slug = category.lower().replace(" ", "_")
        converged = [spec for spec in ids if artifact["robustness_checks"]["checks"][checks[spec]].get("estimator_converged")]
        chosen = converged[0] if converged else "none"
        book.derive(f"robustness_short_{slug}", chosen, "text",
                    [f"model/artifact.json#/robustness_checks/checks/{checks[spec]}/estimator_converged" for spec in ids],
                    ROBUSTNESS_SELECTION_RULE)


# ------------------------------------------------------------------- tables


def _markdown_table(header: list[str], rows: list[list[str]]) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|",
            *["| " + " | ".join(row) + " |" for row in rows]]


def results_table(book: NumberBook) -> str:
    d = book.display
    rows = [[FEATURE_LABELS[name], d(f"coef_{name}"), d(f"se_{name}"), d(f"p_raw_{name}"), d(f"p_holm_{name}")]
            for name in FEATURES]
    rows += [["Cutpoint " + name.removeprefix("cutpoint[").removesuffix("]").replace("|", " / "),
              d(f"cutpoint_{index}"), d(f"cutpoint_{index}_se"),
              d(f"cutpoint_{index}_p_raw"), "not adjusted¹"]
             for index, name in enumerate(CUTPOINTS, start=1)]
    lines = [
        "# Ordered-logit estimates",
        "",
        *_markdown_table(["Parameter", "Estimate", "Robust SE (HC0)", "p (raw)", "p (Holm, six slopes)"], rows),
        "",
        f"N estimation: {d('n_estimation')} · N holdout: {d('n_holdout')} · "
        f"estimation sample {d('sample_estimation_start')} to {d('sample_estimation_end')}.",
        "",
        "Robust standard errors are HC0 score-based sandwich estimates. Holm adjustment is applied across "
        "the six slope p-values only.",
        "",
        "¹ Cutpoints are outside the six-slope inferential family and are reported unadjusted.",
        "",
        "Generated by `python -m src.report` from model/artifact.json.",
        "",
    ]
    return "\n".join(lines)


def verdict_sentence(book: NumberBook) -> str:
    winner, ratio = book.items["oos_winner"]["value"], book.items["rmse_ratio"]["value"]
    if winner == "Always Hold" or (isinstance(ratio, (int, float)) and ratio >= 1):
        return f"Ordered logit does not beat Always Hold on the holdout (RMSE ratio {book.display('rmse_ratio')})."
    return f"Ordered logit beats Always Hold on the holdout (RMSE ratio {book.display('rmse_ratio')})."


def oos_comparison(book: NumberBook) -> str:
    d = book.display
    rows = [
        ["Ordered logit", d("oos_model_rmse"), d("oos_model_mae"), d("oos_model_log_score")],
        ["Always Hold (pre-specified benchmark)", d("oos_hold_rmse"), d("oos_hold_mae"), d("oos_hold_log_score") + "¹"],
        [f"Class-frequency comparator ({d('oos_frequency_label')})", "not reported", "not reported",
         d("oos_frequency_log_score")],
    ]
    lines = [
        "# Holdout comparison",
        "",
        f"Holdout: {d('n_holdout')} decisions, {d('sample_holdout_start')} to {d('sample_holdout_end')} "
        f"({d('holdout_actual_decrease_count')} decreases, {d('holdout_actual_hold_count')} holds, "
        f"{d('holdout_actual_increase_count')} increases). Lower is better for every column.",
        "",
        *_markdown_table(["Model", "RMSE", "MAE", "Log score"], rows),
        "",
        f"RMSE ratio (ordered logit / Always Hold): {d('rmse_ratio')}. Winner: {d('oos_winner')}.",
        "",
        f"**Verdict:** {verdict_sentence(book)}",
        "",
        "RMSE and MAE are computed on the expected ordinal score (Decrease = −1, Hold = 0, Increase = +1). "
        "The log score is the mean negative log probability of the observed class.",
        "",
        "¹ Always Hold assigns probability zero to Increase and Decrease, so its log score is infinite "
        "whenever the holdout contains either; it is shown as undefined.",
        "",
        "Generated by `python -m src.report` from model/artifact.json.",
        "",
    ]
    return "\n".join(lines)


def economic_size(book: NumberBook, artifact: dict) -> str:
    d = book.display
    rows, sentences = [], []
    for name in FEATURES:
        unit = artifact.get("units", {}).get(name, "UNKNOWN")
        rows.append([FEATURE_LABELS[name], d(f"econ_{name}_sd"), unit, d(f"econ_{name}_score_change"),
                     f"{d(f'econ_{name}_band_low')} to {d(f'econ_{name}_band_high')}", d(f"econ_{name}_meaningful")])
        excludes = book.items[f"econ_{name}_band_low"]["value"] > 0 or book.items[f"econ_{name}_band_high"]["value"] < 0
        large = abs(book.items[f"econ_{name}_score_change"]["value"]) >= book.items["econ_typical_score_move"]["value"]
        size = ("at least a typical decision-to-decision move" if large
                else "smaller than a typical decision-to-decision move")
        band = "its 95% band excludes zero" if excludes else "its 95% band includes zero"
        if excludes and large:
            reason = f"it is {size} and {band}, so it is economically meaningful"
        elif excludes or large:
            reason = f"it is {size}, but {band}, so it is not economically meaningful"
        else:
            reason = f"it is {size} and {band}, so it is not economically meaningful"
        sentences.append(f"- **{FEATURE_LABELS[name]}:** a one-SD rise moves the score by "
                         f"{d(f'econ_{name}_score_change')}; {reason}.")
    lines = [
        "# Economic size: one-standard-deviation moves",
        "",
        "Change in the policy pressure score (P(Increase) − P(Decrease), score points from −1 to +1) when one factor "
        "rises by one estimation-sample standard deviation and the other five stay at their estimation-sample means. "
        "Bands are 95% delta-method intervals from the stored HC0 covariance.",
        "",
        *_markdown_table(["Factor", "One SD", "Factor unit", "Score change", "95% band", "Economically meaningful"], rows),
        "",
        f"**Rule.** A move is economically meaningful if its 95% band excludes zero and its size is at least the typical "
        f"decision-to-decision move of the model score in the estimation sample (median absolute change: "
        f"{d('econ_typical_score_move')} score points).",
        "",
        *sentences,
        "",
        "Generated by `python -m src.report` from model/artifact.json and data/processed/model_panel.csv.",
        "",
    ]
    return "\n".join(lines)


def _robustness_effect(check: dict, primary_winner: str) -> str:
    if check.get("estimator_converged") is False:
        prefix = "Estimator did not converge; "
    else:
        prefix = ""
    if str(check.get("survives")).lower() == "yes":
        return prefix + "confirms the main result: same slope signs and Always Hold still wins."
    flipped = check.get("benchmark_conclusion") not in {primary_winner, "UNDETERMINED"}
    signs = check.get("same_signs_as_primary")
    if flipped:
        return prefix + ("overturns the negative result: the model beats Always Hold on this check's holdout"
                         + ("." if signs else ", and at least one slope changes sign."))
    return prefix + "same benchmark conclusion, but at least one slope changes sign."


def robustness_short(book: NumberBook, artifact: dict) -> str:
    d = book.display
    checks = {check["specification_id"]: check for check in artifact["robustness_checks"]["checks"]}
    winner = artifact["benchmark_comparison"]["winner"]
    category_of = {spec: category for category, ids in ROBUSTNESS_CATEGORIES.items() for spec in ids}

    def row(spec: str, category: str) -> list[str]:
        return [category, f"{spec}: {d(f'robustness_{spec}_name')}", d(f"robustness_{spec}_n_usable"),
                d(f"robustness_{spec}_rmse_ratio"), d(f"robustness_{spec}_benchmark_conclusion"),
                d(f"robustness_{spec}_same_signs"), d(f"robustness_{spec}_survives"),
                _robustness_effect(checks[spec], winner)]

    header = ["Kind", "Check", "Usable n", "RMSE ratio vs Always Hold", "Benchmark winner", "Same signs",
              "Survives (strict rule)", "Effect on the main result"]
    chosen = [row(d(f"robustness_short_{category.lower().replace(' ', '_')}"), category)
              for category in ROBUSTNESS_CATEGORIES
              if d(f"robustness_short_{category.lower().replace(' ', '_')}") != "none"]
    lines = [
        "# Robustness: the three required checks",
        "",
        f"Main model: RMSE ratio {d('rmse_ratio')}, winner {d('oos_winner')}. **Selection rule:** "
        f"{ROBUSTNESS_SELECTION_RULE}",
        "",
        *_markdown_table(header, chosen),
        "",
        f"**Across all {d('robustness_check_count')} checks:** the model beats Always Hold on the check's own holdout in "
        f"{d('robustness_flipped_benchmark_count')} of {d('robustness_check_count')} "
        f"({d('robustness_flipped_benchmark_ids')}), while only {d('robustness_survivors')} survives the strict rule "
        f"(all six slope signs match the main model and the benchmark winner is the same). The negative main result "
        f"is therefore fragile. Each check uses its own chronological holdout, so the ratios are not directly "
        f"comparable with each other.",
        "",
        "## All checks",
        "",
        *_markdown_table(header, [row(spec, category_of[spec]) for spec in checks]),
        "",
        "Generated by `python -m src.report` from model/artifact.json.",
        "",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------------ figures


def _save(figure: plt.Figure, path: Path) -> None:
    figure.tight_layout()
    # No software/date metadata, so the same inputs give byte-identical files.
    figure.savefig(path, dpi=FIGURE_DPI, metadata={"Software": None})
    plt.close(figure)


def fig_history(path: Path, decisions: pd.DataFrame, usable: pd.DataFrame, scores: np.ndarray,
                holdout_start: pd.Timestamp) -> None:
    figure, axis = plt.subplots(figsize=(FIGURE_WIDTH_INCHES, FIGURE_WIDTH_INCHES * 0.42))
    axis.axvspan(holdout_start, decisions["decision_date"].max(), color=COLORS["holdout"], lw=0,
                 label="Holdout period")
    axis.step(decisions["decision_date"], decisions["score"], where="post", color=COLORS["actual"], lw=1.0,
              label="NBK decision")
    axis.plot(usable["decision_date"], scores, color=COLORS["model"], lw=1.4, marker="o", ms=2.5,
              label="Policy pressure score (model)")
    axis.axhline(0, color=COLORS["hold"], lw=0.6)
    axis.set_ylim(-1.1, 1.1)
    axis.set_yticks([-1, 0, 1])
    axis.set_xlabel("NBK decision date")
    axis.set_ylabel(SCORE_AXIS_LABEL)
    axis.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, frameon=False)
    _save(figure, path)


def fig_oos(path: Path, holdout: pd.DataFrame, scores: np.ndarray) -> None:
    figure, axis = plt.subplots(figsize=(FIGURE_WIDTH_INCHES, FIGURE_WIDTH_INCHES * 0.42))
    dates = holdout["decision_date"]
    axis.plot(dates, np.zeros(len(dates)), color=COLORS["hold"], lw=1.2, ls="--", label="Always Hold (0)")
    axis.plot(dates, scores, color=COLORS["model"], lw=1.4, marker="o", ms=3.5, label="Ordered logit expected score")
    axis.scatter(dates, holdout["y"], color=COLORS["actual"], marker="s", s=18, zorder=3, label="Actual decision")
    axis.set_ylim(-1.15, 1.15)
    axis.set_yticks([-1, 0, 1])
    axis.set_xlabel("NBK decision date (holdout)")
    axis.set_ylabel(SCORE_AXIS_LABEL)
    axis.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, frameon=False)
    _save(figure, path)


def fig_contributions(path: Path, book: NumberBook) -> None:
    labels, values = [], []
    for rank in range(1, TOP_DRIVERS + 1):
        labels.append(FEATURE_LABELS[book.items[f"driver_{rank}_factor"]["value"]])
        values.append(float(book.items[f"driver_{rank}_contribution"]["value"]))
    figure, axis = plt.subplots(figsize=(FIGURE_WIDTH_INCHES, FIGURE_WIDTH_INCHES * 0.3))
    positions = np.arange(len(values))[::-1]
    bars = axis.barh(positions, values, color=[COLORS["positive"] if v > 0 else COLORS["negative"] for v in values])
    axis.bar_label(bars, labels=[_display(v, "score") for v in values], padding=3, fontsize=8)
    axis.set_yticks(positions, labels)
    axis.axvline(0, color=COLORS["actual"], lw=0.6)
    span = max(abs(v) for v in values)
    axis.set_xlim(min(0.0, min(values)) - span * 0.25, max(0.0, max(values)) + span * 0.25)
    axis.set_xlabel("Contribution to the latest change in the policy pressure score (score points)")
    _save(figure, path)


# --------------------------------------------------------------------- run


def load_inputs(artifact_path: Path, decisions_path: Path, model_panel_path: Path):
    artifact = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    decisions = pd.read_csv(decisions_path, parse_dates=["decision_date"]).sort_values("decision_date")
    decisions["score"] = decisions["decision"].astype(str).str.strip().str.title().map(SCORE_MAP)
    panel = pd.read_csv(model_panel_path, parse_dates=["decision_date"])
    usable = panel.dropna(subset=FEATURES + ["y"]).sort_values("decision_date").reset_index(drop=True)
    holdout_dates = pd.to_datetime(artifact["sample"]["holdout_rows"])
    holdout = usable.loc[usable["decision_date"].isin(holdout_dates)].reset_index(drop=True)
    if len(holdout) != artifact["sample"]["holdout_n"]:
        raise ReportError("Holdout rows in the artifact are not all present in data/processed/model_panel.csv")
    return artifact, decisions, usable, holdout


def run(output_dir: Path | str = OUTPUTS, artifact_path: Path | str = ARTIFACT_PATH,
        decisions_path: Path | str = DECISIONS_PATH, model_panel_path: Path | str = MODEL_PANEL_PATH) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact, decisions, usable, holdout = load_inputs(artifact_path, decisions_path, model_panel_path)
    np.random.seed(int(artifact["seed"]))  # nothing here is random; fixed anyway per project rule 5
    tolerance = float(artifact["replication_tolerance"]["coefficients_absolute"])
    book = collect_numbers(artifact, holdout, tolerance)
    collect_economic_size(book, artifact, usable, tolerance)
    collect_robustness_short(book, artifact)
    collect_rb09_household(book, artifact)
    collect_power(book, artifact)
    width_inputs = ["headline_score_band_low", "headline_score_band_high"]
    book.derive("headline_score_band_width", book.items["headline_score_band_high"]["value"]
                - book.items["headline_score_band_low"]["value"], "stat", width_inputs, "band high minus band low")

    (output_dir / "results_table.md").write_text(results_table(book), encoding="utf-8", newline="\n")
    (output_dir / "oos_comparison.md").write_text(oos_comparison(book), encoding="utf-8", newline="\n")
    (output_dir / "economic_size.md").write_text(economic_size(book, artifact), encoding="utf-8", newline="\n")
    (output_dir / "robustness_table_short.md").write_text(robustness_short(book, artifact), encoding="utf-8",
                                                          newline="\n")
    (output_dir / "power_note.md").write_text(power_note(book), encoding="utf-8", newline="\n")
    with plt.rc_context(FIGURE_STYLE):
        fig_history(output_dir / "fig_history.png", decisions, usable, _expected_scores(artifact, usable),
                    pd.Timestamp(artifact["sample"]["holdout_start"]))
        fig_oos(output_dir / "fig_oos.png", holdout, _expected_scores(artifact, holdout))
        fig_contributions(output_dir / "fig_contributions.png", book)
    payload = {
        "description": "Every number quoted in the 4-page note. 'source' is a JSON Pointer into "
                       "model/artifact.json, or the inputs and method of a derived value. "
                       "'display' is the text the note and README use.",
        "generated_by": "python -m src.report",
        "inputs": ["model/artifact.json", "data/processed/nbk_decisions_clean.csv",
                   "data/processed/model_panel.csv"],
        "verdict_sentence": verdict_sentence(book),
        "numbers": book.items,
    }
    (output_dir / "numbers_for_note.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the note's tables, figures and numbers.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUTS)
    args = parser.parse_args(argv)
    payload = run(args.output_dir)
    for name in OUTPUT_FILES:
        print(f"Wrote {args.output_dir / name}")
    print(f"Numbers recorded: {len(payload['numbers'])}")
    print(payload["verdict_sentence"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
