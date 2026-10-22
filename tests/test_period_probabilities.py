from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src import app
from src.diagnostics_view import error_table, feature_range_summary, load_diagnostic_artifacts, probability_diagnostics
from src.period_backtest import TEST_PERIOD_MONTHS, evaluate_periods


ROOT = Path(__file__).resolve().parents[1]


def test_artifact_probabilities_are_named_and_sum_to_one():
    artifact = app.load_artifact()
    probabilities = app.ordered_probabilities(artifact, artifact["latest_feature_vector"])
    assert list(probabilities) == ["Decrease", "Hold", "Increase"]
    assert np.isclose(sum(probabilities.values()), 1.0, atol=1e-10)


def test_probability_score_and_delta_band_use_artifact_covariance():
    artifact = app.load_artifact()
    vector = dict(artifact["latest_feature_vector"])
    baseline = app.score_and_delta_band(artifact, vector)
    vector["inflation"] += 1.0
    changed = app.score_and_delta_band(artifact, vector)
    assert baseline[0] != changed[0]
    assert baseline[1] <= baseline[0] <= baseline[2]
    assert changed[1] <= changed[0] <= changed[2]


def test_dashboard_shows_stored_model_outputs_and_honesty_text():
    at = AppTest.from_file(str(ROOT / "src" / "app.py")).run(timeout=30)
    assert not at.exception
    source = (ROOT / "src" / "app.py").read_text(encoding="utf-8")
    assert "NBK Base-Rate Decision Forecast" in [element.value for element in at.title]
    assert any(element.label == "Policy pressure score" for element in at.metric)
    assert any("does not beat Always Hold" in element.value for element in at.info)
    assert "P(Increase) - P(Decrease)" in source
    assert [tab.label for tab in at.tabs] == ["Overview", "Drivers and scenario", "Evidence", "Data and provenance"]
    assert len(at.slider) == 1


def test_all_periods_are_chronological_and_metrics_use_each_period_test_set():
    data = app.load_data()
    reports, predictions = evaluate_periods(data)
    assert tuple(report["test_period_months"] for report in reports) == TEST_PERIOD_MONTHS
    assert len(reports) == 3
    assert set(predictions["test_period_months"]) == set(TEST_PERIOD_MONTHS)
    for report in reports:
        cutoff = pd.Timestamp(report["cutoff"])
        assert report["status"] == "EVALUATED"
        assert report["train_test_overlap"] is False
        assert pd.Timestamp(report["train_end"]) < cutoff <= pd.Timestamp(report["test_start"])
        assert report["test_n"] == sum(item["count"] for item in report["actual_class_distribution"].values())
        assert {item["model"] for item in report["models"]} == {
            "Hold benchmark", "Logistic Regression", "Random Forest"
        }
        for model in report["models"]:
            assert model["n"] == report["test_n"]
            assert sum(item["count"] for item in model["predicted_class_distribution"].values()) == report["test_n"]
            assert sum(map(sum, model["confusion_matrix_actual_rows_predicted_columns"])) == report["test_n"]
    primary = reports[0]
    assert primary["test_n"] == 16
    assert [(m["model"], m["accuracy"]) for m in primary["models"]] == [
        ("Hold benchmark", 0.625), ("Logistic Regression", 0.1875), ("Random Forest", 0.1875)
    ]


def test_probability_diagnostics_use_saved_out_of_sample_rows():
    frame = pd.read_csv(ROOT / "outputs" / "legacy" / "mvp_period_predictions.csv")
    frame = frame.loc[frame.test_period_months == 24]
    report = probability_diagnostics(frame, "Random Forest", app.CLASS_ORDER)
    assert report is not None and report["n"] == 16
    assert report["max_probability"]["n"] == 16
    assert all(row["n"] == 16 for row in report["mean_probabilities"].to_dict("records"))
    assert report["multiclass_brier"] >= 0
    incomplete = frame.drop(columns=["probability_Random Forest_Hold"])
    assert probability_diagnostics(incomplete, "Random Forest", app.CLASS_ORDER) is None


def test_feature_range_and_error_table_cover_real_test_rows():
    data = app.load_data()
    ranges = feature_range_summary(data, app.FEATURES, 24)
    assert len(ranges) == 6
    household = ranges.set_index("Feature").loc["household_lending"]
    corporate = ranges.set_index("Feature").loc["corporate_lending"]
    assert household["Test outside train range"] == 16
    assert corporate["Test outside train range"] == 16
    period_predictions = pd.read_csv(ROOT / "outputs" / "legacy" / "mvp_period_predictions.csv")
    test_rows = period_predictions.loc[period_predictions.test_period_months == 24]
    joined = error_table(test_rows, data, app.FEATURES)
    assert len(joined) == 16
    assert {"Logistic Regression correct", "Random Forest correct", *app.FEATURES}.issubset(joined.columns)


def test_missing_or_incomplete_diagnostic_artifacts_are_reported(tmp_path):
    loaded, issues = load_diagnostic_artifacts(tmp_path)
    assert loaded == {}
    assert len(issues) == 3
    output_dir = tmp_path / "outputs" / "legacy"
    output_dir.mkdir(parents=True)
    (output_dir / "mvp_backtest_results.json").write_text("{}", encoding="utf-8")
    (output_dir / "mvp_period_predictions.csv").write_text("actual\nHold\n", encoding="utf-8")
    (output_dir / "mvp_validity_report.json").write_text("{}", encoding="utf-8")
    loaded, issues = load_diagnostic_artifacts(tmp_path)
    assert loaded["results"]["period_comparison"] == []
    assert any("period_comparison" in issue for issue in issues)
    assert any("required columns" in issue for issue in issues)


def test_app_does_not_import_estimation_or_legacy_forecast_modules():
    source = (ROOT / "src" / "app.py").read_text(encoding="utf-8")
    assert "sklearn" not in source
    assert "statsmodels" not in source
    assert "src.forecasting" not in source
    assert ".fit(" not in source
