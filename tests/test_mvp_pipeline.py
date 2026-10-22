import json
import shutil
from pathlib import Path

import pandas as pd
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

import run_all
from src import app
from src import legacy_classifier as legacy
from src.hashing import normalized_sha256
from src.stability import expanding_window_stability


ROOT = Path(__file__).resolve().parents[1]


def _csv_hash():
    return normalized_sha256(legacy.DATA_PATH)


def test_allowed_features_classes_and_target_direction():
    assert legacy.FEATURES == app.FEATURES
    assert len(legacy.FEATURES) == len(set(legacy.FEATURES)) == 6
    raw = pd.read_csv(legacy.DATA_PATH)
    assert set(raw["decision"].str.title()) <= {"Increase", "Hold", "Decrease"}
    expected = raw.apply(
        lambda row: "Increase" if row.base_rate_after > row.base_rate_before
        else "Decrease" if row.base_rate_after < row.base_rate_before else "Hold", axis=1
    )
    assert expected.tolist() == raw["decision"].str.title().tolist()


def test_legacy_classifier_backtest_is_chronological_and_isolated_from_app():
    data = app.load_data()
    predictions, train, test = legacy.expanding_window_backtest(data)
    cutoff = data.decision_date.max() - pd.DateOffset(months=24)
    assert set(train.index).isdisjoint(test.index)
    assert train.decision_date.max() < cutoff <= test.decision_date.min()
    assert len(predictions) == len(test)
    app_source = (ROOT / "src" / "app.py").read_text(encoding="utf-8")
    assert "sklearn" not in app_source and ".fit(" not in app_source
    assert "src.forecasting" not in app_source


def test_legacy_pipeline_fits_only_training_rows(monkeypatch):
    original = legacy.make_model
    fitted = []

    def recording_factory(name):
        pipeline = original(name)
        original_fit = pipeline.fit

        def recording_fit(X, y, *args, **kwargs):
            fitted.append((X.index.copy(), y.index.copy()))
            return original_fit(X, y, *args, **kwargs)

        pipeline.fit = recording_fit
        return pipeline

    monkeypatch.setattr(legacy, "make_model", recording_factory)
    _, train, test = legacy.expanding_window_backtest(app.load_data())
    assert len(fitted) == 2
    for x_index, y_index in fitted:
        assert x_index.equals(y_index)
        assert set(x_index) == set(train.index)
        assert set(x_index).isdisjoint(test.index)


def test_benchmark_metrics_and_class_statistics_use_same_test_rows():
    predictions, _, _ = legacy.expanding_window_backtest(app.load_data())
    assert predictions["benchmark_hold"].index.equals(predictions["actual"].index)
    assert (predictions["benchmark_hold"] == "Hold").all()
    for column in ("benchmark_hold", "Logistic Regression"):
        reported = legacy.calculate_class_metrics(predictions, column)
        p, r, f, support = precision_recall_fscore_support(
            predictions.actual, predictions[column], labels=legacy.CLASS_ORDER, zero_division=0
        )
        assert reported["Precision"].tolist() == p.tolist()
        assert reported["Recall"].tolist() == r.tolist()
        assert reported["F1-score"].tolist() == f.tolist()
        assert reported["Actual observations"].tolist() == support.tolist()
        cm = confusion_matrix(predictions.actual, predictions[column], labels=legacy.CLASS_ORDER)
        assert int(cm.sum()) == len(predictions)
        assert reported["Predicted observations"].tolist() == cm.sum(axis=0).tolist()


def test_stability_folds_are_chronological_and_exclude_final_holdout():
    data = app.load_data()
    cutoff = data.decision_date.max() - pd.DateOffset(months=24)
    metrics, predictions = expanding_window_stability(data, cutoff)
    assert metrics["fold"].nunique() == 3
    assert set(metrics["model"]) == {"Logistic Regression", "Hold benchmark"}
    assert (pd.to_datetime(predictions["decision_date"]) < cutoff).all()
    for _, fold in metrics.groupby("fold"):
        assert fold["train_end"].nunique() == 1
        assert fold["test_start"].nunique() == fold["test_end"].nunique() == 1
        assert fold["train_end"].iloc[0] < fold["test_start"].iloc[0]
        assert fold["test_n"].nunique() == 1


def test_legacy_pipeline_creates_isolated_artifacts_and_preserves_input_csv(tmp_path):
    before = _csv_hash()
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    # Seed the canonical files the runner enriches so that branch runs on copies.
    for name in ("backtest_results.json", "sealed_test_predictions.csv"):
        shutil.copy2(ROOT / "outputs" / name, outputs / name)
    paths = run_all.main(outputs_dir=outputs)
    assert _csv_hash() == before
    assert all(path.is_relative_to(tmp_path) for path in paths.values())
    for key in ("results", "predictions", "validity", "canonical_results", "canonical_predictions"):
        assert paths[key].is_file()
    assert (paths["legacy"] / "mvp_period_predictions.csv").is_file()
    results = json.loads(paths["results"].read_text(encoding="utf-8"))
    validity = json.loads(paths["validity"].read_text(encoding="utf-8"))
    predictions = pd.read_csv(paths["predictions"])
    assert results["input"]["sha256"] == before
    assert len(predictions) == results["split"]["test_n"] == 16
    assert results["metrics"][0]["Accuracy"] == 0.625
    assert results["metrics"][1]["Accuracy"] == 0.1875
    assert [row["test_period_months"] for row in results["period_comparison"]] == [24, 36, 48]
    assert validity["Stability"]["final_test_excluded"] is True
    enriched = pd.read_csv(paths["predictions"])
    for label in legacy.CLASS_ORDER:
        assert f"probability_Random Forest_{label}" in enriched.columns
    probability_columns = [f"probability_Random Forest_{label}" for label in legacy.CLASS_ORDER]
    assert ((enriched[probability_columns].sum(axis=1) - 1.0).abs() <= 1e-8).all()
