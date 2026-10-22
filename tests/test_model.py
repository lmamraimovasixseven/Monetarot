import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import model
from src.hashing import normalized_sha256
from src.ingest import build_model_panel


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def fitted_artifact(tmp_path_factory):
    root = tmp_path_factory.mktemp("ordered_model")
    artifact_path = root / "model" / "artifact.json"
    model_panel_path = root / "data" / "processed" / "model_panel.csv"
    model.run_pipeline(
        output_dir=root / "outputs",
        artifact_path=artifact_path,
        model_panel_path=model_panel_path,
    )
    return {
        "artifact": json.loads(artifact_path.read_text(encoding="utf-8")),
        "output_dir": root / "outputs",
    }


def test_artifact_schema_contains_model_and_reproducibility_fields(fitted_artifact):
    artifact = fitted_artifact["artifact"]
    assert artifact["schema_version"] == 1
    assert artifact["model"]["name"] == "Ordered Logit"
    assert artifact["model"]["feature_names"] == model.FEATURES
    assert artifact["model"]["class_order"] == ["Decrease", "Hold", "Increase"]
    assert set(artifact["model"]["parameters"]) == set(model.FEATURES) | {
        "cutpoint[Decrease|Hold]",
        "cutpoint[Hold|Increase]",
    }
    for key in (
        "coefficient_table",
        "covariance_names",
        "covariance_hc0",
        "log_likelihood",
        "pseudo_r2_mcfadden",
    ):
        assert key in artifact["model"]
    for key in (
        "sample",
        "estimation_timestamp_utc",
        "seed",
        "diagnostics",
        "benchmark_comparison",
        "economic_size_plus_one_sd",
        "per_factor_contribution_to_latest_score_change",
        "units",
        "latest_feature_vector",
        "package_versions",
        "data_sha256_normalized_crlf_to_lf",
        "replication_tolerance",
    ):
        assert key in artifact
    assert artifact["data_sha256_normalized_crlf_to_lf"] == normalized_sha256(
        ROOT / "data" / "processed" / "nbk_decisions_clean.csv"
    )


def test_p_value_families_match_the_documented_multiplicity_rules(fitted_artifact):
    artifact = fitted_artifact["artifact"]
    families = artifact["diagnostics"]["p_value_families"]
    assert families["slope_coefficients"].startswith("Holm adjustment across the six")
    assert families["joint_slope_lr"].startswith("single pre-specified primary test")
    assert families["diagnostics"].startswith("raw p-values, no adjustment")
    assert families["robustness_specification_count"] == 9
    assert families["total_specifications_including_primary"] == 10

    parameters = artifact["diagnostics"]["parameters"]
    slopes = [row for row in parameters if row["name"] in model.FEATURES]
    assert len(slopes) == 6
    raw = np.asarray([row["p_value"] for row in slopes])
    expected = __import__("statsmodels.stats.multitest", fromlist=["multipletests"]).multipletests(raw, method="holm")[1]
    np.testing.assert_allclose([row["p_value_adjusted"] for row in slopes], expected)
    assert all("six slope-coefficient" in row["p_value_family"] for row in slopes)
    for diagnostic in (artifact["diagnostics"]["parameter_stability"],
                       artifact["diagnostics"]["proportional_odds"],
                       artifact["diagnostics"]["serial_correlation"]):
        if isinstance(diagnostic.get("p_value"), (int, float)):
            assert diagnostic["p_value_adjusted"] == diagnostic["p_value"]
            assert diagnostic["p_value_family"].startswith("diagnostics")
    joint = artifact["diagnostics"]["joint_slope_lr"]
    assert joint["p_value_adjusted"] == joint["p_value"]
    assert "single primary test" in joint["p_value_family"]


def test_falsification_rules_and_finite_class_frequency_comparator(fitted_artifact):
    artifact = fitted_artifact["artifact"]
    rules = artifact["falsification_verdicts"]
    assert len(rules) == 3
    joint = artifact["diagnostics"]["joint_slope_lr"]
    assert rules[0]["verdict"] == ("falsified" if joint["p_value"] >= 0.10 else "not falsified")
    assert rules[0]["adjusted_transparency_verdict"] in {"falsified", "not falsified"}
    ratio = artifact["benchmark_comparison"]["rmse_ratio_model_to_hold"]
    assert rules[2]["verdict"] == ("falsified" if ratio >= 1 else "not falsified")
    comparator = artifact["benchmark_comparison"]["class_frequency_comparator_secondary"]
    assert comparator["label"] == "added after the specification freeze, secondary"
    assert np.isclose(sum(comparator["probabilities"].values()), 1.0)
    assert np.isfinite(comparator["log_score"])
    assert artifact["benchmark_comparison"]["winner"] == "Always Hold"
    report = (fitted_artifact["output_dir"] / "falsification_verdicts.md").read_text(encoding="utf-8")
    assert "p-value family" in report
    assert "transparency" in report
    annex = (fitted_artifact["output_dir"] / "annex_diagnostics.md").read_text(encoding="utf-8")
    assert "## Limitations of the unit-root tests" in annex
    assert "irregularly spaced" in annex
    assert "88 usable observations" in annex
    assert "all regressors are I(0)" in annex
    assert "not supported for household lending" in annex
    assert "ambiguous for inflation and corporate lending" in annex


def test_robustness_checks_are_chronological_and_corrected_within_spec(fitted_artifact):
    artifact = fitted_artifact["artifact"]
    robustness = artifact["robustness_checks"]
    checks = robustness["checks"]
    assert robustness["total_specifications_including_primary"] == 10
    assert robustness["robustness_specification_count"] == 9
    assert robustness["selection_prohibited"] is True
    assert [row["specification_id"] for row in checks] == [f"RB{i:02d}" for i in range(1, 10)]
    for check in checks:
        if check["status"] != "COMPLETED":
            continue
        assert check["estimation_end"] < check["holdout_start"]
        assert check["holdout_n"] > 0
        assert check["rmse_ratio_model_to_hold"] is not None
        coefficients = check["coefficients"]
        assert len([row for row in coefficients if row["name"] in model.FEATURES]) == 6
        raw = np.asarray([row["p_value"] for row in coefficients if row["name"] in model.FEATURES])
        expected = __import__("statsmodels.stats.multitest", fromlist=["multipletests"]).multipletests(raw, method="holm")[1]
        actual = [row["p_value_adjusted"] for row in coefficients if row["name"] in model.FEATURES]
        np.testing.assert_allclose(actual, expected)
        assert all(row["p_value_family"].startswith(f"robustness specification {check['specification_id']}")
                   for row in coefficients if row["name"] in model.FEATURES)
    differenced = checks[-1]
    assert differenced["name"] == "Differenced non-stationary factors"
    assert differenced["feature_transformations"] == {
        "household_lending": "first difference of 12-month log growth",
        "corporate_lending": "first difference of 12-month log growth",
        "inflation": "first difference of inflation",
        "other factors": "main-model transformations unchanged",
    }
    assert len(differenced["coefficients"]) == len(model.FEATURES)
    assert all(coefficient["p_value"] is not None
               and coefficient["p_value_adjusted"] is not None
               and coefficient["p_value_family"].startswith("robustness specification RB09")
               for coefficient in differenced["coefficients"])
    assert all(
        coefficient["sign"] == (
            "positive" if coefficient["estimate"] > 0
            else "negative" if coefficient["estimate"] < 0
            else "zero"
        )
        for coefficient in differenced["coefficients"]
    )
    report = (fitted_artifact["output_dir"] / "robustness_table.md").read_text(encoding="utf-8")
    assert "Total specifications: 10" in report
    assert "Differenced non-stationary factors" in report
    assert "first difference of 12-month log growth" in report
    assert "not used to select a final model" in report


def test_differenced_factor_specification_differences_monthly_inputs_before_release_alignment():
    main_panel = pd.read_csv(ROOT / "data" / "processed" / "model_panel.csv")
    decision_panel = main_panel[["decision_date", "decision", "y"]]
    differenced = model._robustness_panel(
        decision_panel,
        model.RAW_DIR,
        first_difference_features=("household_lending", "corporate_lending", "inflation"),
    )
    unchanged = model._robustness_panel(decision_panel, model.RAW_DIR)

    for feature in ("household_lending", "corporate_lending"):
        filename, source_column = model.FEATURE_RULES[feature]
        monthly = model.log_growth_12m(
            model.read_monthly_series(model.RAW_DIR / filename, source_column)
        ).diff()
        expected = model.apply_release_lag(monthly, pd.to_datetime(decision_panel.decision_date))
        np.testing.assert_allclose(
            differenced[feature].to_numpy(),
            expected.to_numpy(),
            equal_nan=True,
        )

    filename, source_column = model.FEATURE_RULES["inflation"]
    monthly_inflation = model.complete_month_calendar(
        model.read_monthly_series(model.RAW_DIR / filename, source_column)
    ).diff()
    expected_inflation = model.apply_release_lag(
        monthly_inflation,
        pd.to_datetime(decision_panel.decision_date),
    )
    np.testing.assert_allclose(
        differenced["inflation"].to_numpy(),
        expected_inflation.to_numpy(),
        equal_nan=True,
    )
    for feature in ("exports", "imports", "consumption"):
        np.testing.assert_allclose(
            differenced[feature].to_numpy(),
            unchanged[feature].to_numpy(),
            equal_nan=True,
        )


def test_covariance_is_symmetric_and_positive_semidefinite(fitted_artifact):
    covariance = np.asarray(fitted_artifact["artifact"]["model"]["covariance_hc0"], dtype=float)
    assert covariance.shape == (8, 8)
    np.testing.assert_allclose(covariance, covariance.T, rtol=0, atol=1e-10)
    assert np.linalg.eigvalsh(covariance).min() >= -1e-8


def test_seed_reproduces_ordered_logit_coefficients(tmp_path):
    panel = build_model_panel(output_path=tmp_path / "model_panel.csv")
    usable = panel.dropna(subset=model.FEATURES + ["y"]).reset_index(drop=True)
    holdout_n = int(np.ceil(0.20 * len(usable)))
    training = usable.iloc[:-holdout_n].copy()
    _, fit_a, _ = model._fit_ordered(training, seed=42)
    _, fit_b, _ = model._fit_ordered(training, seed=42)
    np.testing.assert_allclose(np.asarray(fit_a.params), np.asarray(fit_b.params), rtol=0, atol=1e-10)


def test_estimation_rows_are_chronologically_disjoint_from_holdout(fitted_artifact):
    sample = fitted_artifact["artifact"]["sample"]
    estimation = set(sample["estimation_rows"])
    holdout = set(sample["holdout_rows"])
    assert sample["usable_n"] == 88
    assert sample["holdout_n"] == 18
    assert sample["estimation_n"] == 70
    assert estimation.isdisjoint(holdout)
    assert max(estimation) < min(holdout)
    assert sample["estimation_end"] < sample["holdout_start"]
    assert len(sample["estimation_rows"]) == sample["estimation_n"]
    assert len(sample["holdout_rows"]) == sample["holdout_n"]


def test_pipeline_does_not_import_legacy_classifier_runner():
    source = (ROOT / "src" / "model.py").read_text(encoding="utf-8")
    assert "outputs.legacy" not in source
    assert "src.app" not in source
