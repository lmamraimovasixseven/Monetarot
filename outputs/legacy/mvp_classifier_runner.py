"""Rebuild isolated MVP backtest and validity artifacts from the current CSV."""

import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import confusion_matrix

from src.legacy_classifier import CLASSES, CLASS_ORDER, DATA_PATH, FEATURES, calculate_class_metrics, calculate_metrics, expanding_window_backtest, load_data, make_model
from src.period_backtest import TEST_PERIOD_MONTHS, evaluate_periods
from src.diagnostics_view import probability_diagnostics
from src.stability import expanding_window_stability
from src.advanced_diagnostics import (
    alternative_specifications,
    detailed_error_analysis,
    structural_break_diagnostics,
)
from src.hashing import normalized_sha256


ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / "outputs"
LEGACY_OUTPUTS = OUTPUTS / "legacy"
RESULTS_PATH = LEGACY_OUTPUTS / "mvp_backtest_results.json"
PREDICTIONS_PATH = LEGACY_OUTPUTS / "mvp_backtest_predictions.csv"
VALIDITY_PATH = LEGACY_OUTPUTS / "mvp_validity_report.json"
CANONICAL_RESULTS_PATH = OUTPUTS / "backtest_results.json"
CANONICAL_PREDICTIONS_PATH = OUTPUTS / "sealed_test_predictions.csv"


def _metrics_frame(predictions):
    # calculate_metrics is the app's shared metric implementation; Streamlit
    # caption calls are harmless in CLI mode, but avoid depending on its UI output.
    return calculate_metrics(predictions).to_dict(orient="records")


def output_paths(outputs_dir=None):
    """Return every file location the runner writes, rooted at ``outputs_dir``."""
    outputs = Path(outputs_dir) if outputs_dir is not None else OUTPUTS
    legacy = outputs / "legacy"
    return {
        "outputs": outputs,
        "legacy": legacy,
        "results": legacy / "mvp_backtest_results.json",
        "predictions": legacy / "mvp_backtest_predictions.csv",
        "validity": legacy / "mvp_validity_report.json",
        "canonical_results": outputs / "backtest_results.json",
        "canonical_predictions": outputs / "sealed_test_predictions.csv",
    }


def _display_path(path):
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


def main(outputs_dir=None):
    paths = output_paths(outputs_dir)
    OUTPUTS, LEGACY_OUTPUTS = paths["outputs"], paths["legacy"]
    RESULTS_PATH, PREDICTIONS_PATH, VALIDITY_PATH = paths["results"], paths["predictions"], paths["validity"]
    CANONICAL_RESULTS_PATH, CANONICAL_PREDICTIONS_PATH = paths["canonical_results"], paths["canonical_predictions"]
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    LEGACY_OUTPUTS.mkdir(parents=True, exist_ok=True)
    source_hash_before = normalized_sha256(DATA_PATH)
    raw = pd.read_csv(DATA_PATH)
    required = {"decision_date", "decision", "base_rate_before", "base_rate_after", *FEATURES}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise ValueError(f"Required CSV columns are missing: {missing}")
    if len(FEATURES) != 6 or len(set(FEATURES)) != 6:
        raise AssertionError("The allowed factor list must contain exactly six unique factors")
    allowed = set(CLASSES)
    if not set(raw["decision"].astype(str).str.strip().str.title()).issubset(allowed):
        raise ValueError("Dataset contains an unsupported decision class")
    before = pd.to_numeric(raw["base_rate_before"], errors="coerce")
    after = pd.to_numeric(raw["base_rate_after"], errors="coerce")
    expected = pd.Series("Hold", index=raw.index)
    expected.loc[after > before] = "Increase"
    expected.loc[after < before] = "Decrease"
    normalized = raw["decision"].astype(str).str.strip().str.title()
    label_mismatches = int((expected != normalized).sum())
    if label_mismatches:
        raise ValueError(f"Decision labels disagree with base-rate changes in {label_mismatches} rows")

    data = load_data()
    predictions, training, test = expanding_window_backtest(data)
    if predictions.empty:
        raise RuntimeError("Chronological backtest did not produce predictions")
    cutoff = data["decision_date"].max() - pd.DateOffset(months=24)
    if not training["decision_date"].max() < cutoff or not (test["decision_date"] >= cutoff).all():
        raise AssertionError("Train/test chronology does not match the app's final 24-month split")
    if set(training.index).intersection(test.index):
        raise AssertionError("Train and test rows overlap")

    metric_rows = _metrics_frame(predictions)
    period_results, period_predictions = evaluate_periods(data)
    break_candidates, break_report = structural_break_diagnostics(data)
    alternative_rows, alternative_predictions = alternative_specifications(data)
    detailed_errors = detailed_error_analysis(data, period_predictions, months=24)
    probability_analysis = {}
    for period_months in TEST_PERIOD_MONTHS:
        period_rows = period_predictions.loc[period_predictions["test_period_months"] == period_months]
        probability_analysis[str(period_months)] = {}
        for model_name in ("Logistic Regression", "Random Forest"):
            summary = probability_diagnostics(period_rows, model_name, CLASS_ORDER)
            if summary is None:
                probability_analysis[str(period_months)][model_name] = {"status": "unavailable or invalid"}
                continue
            threshold_records = summary["thresholds"].to_dict(orient="records")
            for row in threshold_records:
                if pd.isna(row["Accuracy"]):
                    row["Accuracy"] = None
            probability_analysis[str(period_months)][model_name] = {
                "n": summary["n"],
                "mean_probabilities": summary["mean_probabilities"].to_dict(orient="records"),
                "maximum_probability": summary["max_probability"],
                "thresholds": threshold_records,
                "multiclass_brier": summary["multiclass_brier"],
                "calibration_note": "Descriptive only; sample sizes are small and no calibration fit or claim is made.",
            }
    class_reports = {}
    matrices = {}
    for column, name in (("benchmark_hold", "Hold benchmark"), ("Logistic Regression", "Logistic Regression"), ("Random Forest", "Random Forest")):
        class_reports[name] = calculate_class_metrics(predictions, column).to_dict(orient="records")
        matrices[name] = confusion_matrix(predictions["actual"], predictions[column], labels=CLASS_ORDER).tolist()

    model = make_model("Logistic Regression")
    model_parameters = model.named_steps["model"].get_params(deep=False)
    random_forest_parameters = make_model("Random Forest").named_steps["model"].get_params(deep=False)
    result = {
        "input": {"path": str(DATA_PATH.relative_to(ROOT)), "sha256": source_hash_before},
        "features": FEATURES,
        "classes": CLASSES,
        "split": {
            "train_n": int(len(training)), "train_start": training["decision_date"].min().strftime("%Y-%m-%d"),
            "train_end": training["decision_date"].max().strftime("%Y-%m-%d"),
            "cutoff": cutoff.strftime("%Y-%m-%d"), "test_n": int(len(test)),
            "test_start": test["decision_date"].min().strftime("%Y-%m-%d"),
            "test_end": test["decision_date"].max().strftime("%Y-%m-%d"),
        },
        "model_parameters": {
            "Logistic Regression": model_parameters,
            "Random Forest (additional comparison)": random_forest_parameters,
            "pipeline": ["median imputer", "standard scaler", "classifier"],
            "Hold benchmark": {"rule": "predict Hold for every test observation"},
        },
        "metrics": metric_rows,
        "period_comparison": period_results,
        "out_of_sample_probability_analysis": probability_analysis,
        "primary_period_months": 24,
        "primary_period_justification": "Retain the existing final 24-month sealed test as the primary estimate; 36- and 48-month windows are sensitivity analyses, not selected by performance.",
        "class_metrics": class_reports,
        "confusion_matrices": matrices,
        "test_class_counts": {str(k): int(v) for k, v in test["decision"].value_counts().items()},
        "limitations": [
            "Only 16 observations are in the final test; reported metrics are descriptive.",
            "Predictor availability uses the existing month t-2 approximation; exact release dates are unverified.",
            "No hyperparameter search or model selection uses final-test observations.",
            "Random Forest remains an additional comparison in the existing backtest, not a claimed improvement.",
        ],
    }
    fold_metrics, fold_predictions = expanding_window_stability(data, cutoff)
    # Stability details are included in validity; folds stop before the final cutoff.
    model_row = next(item for item in metric_rows if item["Model"] == "Logistic Regression")
    hold_row = next(item for item in metric_rows if item["Model"] == "Hold benchmark")
    predictive_status = "BELOW BENCHMARK" if model_row["Accuracy"] < hold_row["Accuracy"] else "AT OR ABOVE BENCHMARK"
    validity = {
        "Data": {"raw_rows": int(len(raw)), "missing_columns": missing, "invalid_label_count": int((~normalized.isin(allowed)).sum()), "decision_rate_mismatches": label_mismatches, "factor_count": len(FEATURES), "factor_missing_after_load": {key: int(value) for key, value in data[FEATURES].isna().sum().items()}, "duplicate_decision_dates_after_load": int(data["decision_date"].duplicated().sum()), "source_sha256": source_hash_before},
        "Statistical": {"status": "DESCRIPTIVE ONLY", "note": "Small multiclass sample; this MVP does not claim inferential statistical validity."},
        "Predictive": {"status": predictive_status, "metrics": metric_rows, "class_metrics": class_reports, "period_comparison": period_results, "out_of_sample_probability_analysis": probability_analysis},
        "Stability": {"fold_design": {"initial_train_size": 56, "fold_size": 6, "fold_count": 3, "training_window": "expanding", "selection_or_tuning": "none"}, "fold_metrics": fold_metrics.to_dict(orient="records"), "fold_predictions": fold_predictions.to_dict(orient="records"), "final_test_excluded": bool((fold_predictions["decision_date"] < cutoff).all())},
        "Structural_break_diagnostics": break_report,
        "Alternative_specifications": {
            "status": "DIAGNOSTIC ONLY; no specification selected",
            "comparisons": alternative_rows.to_dict(orient="records"),
            "out_of_sample_prediction_rows": alternative_predictions,
        },
        "Data_source_validation": {
            "status": "PARTIAL: processed values and supplied raw CSVs available; original downloads, workbooks, and provenance are unavailable",
            "processed_csv_sha256": source_hash_before,
            "raw_source_inventory": "Supplied CSVs are inventoried in data/raw/SOURCES.md; publishers, source URLs, retrieval dates, release lags, and confirmed units remain UNKNOWN.",
            "raw_monthly_credit_files_present": break_report["raw_monthly_sources_present"],
            "excel_workbooks_present": break_report["excel_workbooks_present"],
            "unit_validation": "Source numeric columns are available, but actual units cannot be confirmed without authenticated series metadata.",
            "date_matching_validation": "Monthly CSV labels can be aligned mechanically; the two-month reference offset is a reconstruction convention, not a verified release date or vintage match.",
        },
    }
    primary_rows = period_predictions.loc[period_predictions["test_period_months"] == 24].copy()
    if len(primary_rows) != len(predictions):
        raise AssertionError("24-month comparison predictions differ from the existing sealed-test size")
    # Keep the familiar 24-month artifact while adding class-name keyed probabilities.
    output_predictions = predictions.copy()
    for model_name in ("Logistic Regression", "Random Forest"):
        for label in CLASS_ORDER:
            output_predictions[f"probability_{model_name}_{label}"] = primary_rows[f"probability_{model_name}_{label}"].to_numpy()
    output_predictions.to_csv(PREDICTIONS_PATH, index=False)
    period_predictions.to_csv(LEGACY_OUTPUTS / "mvp_period_predictions.csv", index=False)
    break_candidates.to_csv(LEGACY_OUTPUTS / "mvp_structural_break_candidates.csv", index=False)
    (LEGACY_OUTPUTS / "mvp_structural_break_summary.json").write_text(json.dumps(break_report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    (LEGACY_OUTPUTS / "mvp_alternative_specifications.json").write_text(
        json.dumps({"status": "DIAGNOSTIC ONLY; no specification selected", "results": alternative_rows.to_dict(orient="records"), "out_of_sample_predictions": alternative_predictions}, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    detailed_errors.to_csv(LEGACY_OUTPUTS / "mvp_detailed_error_analysis.csv", index=False)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    VALIDITY_PATH.write_text(json.dumps(validity, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    # Keep the existing public artifact schemas and enrich only the related
    # backtest files with the requested period comparison and probabilities.
    if CANONICAL_RESULTS_PATH.exists():
        canonical_result = json.loads(CANONICAL_RESULTS_PATH.read_text(encoding="utf-8"))
        canonical_result["period_comparison"] = period_results
        canonical_result["out_of_sample_probability_analysis"] = probability_analysis
        canonical_result["primary_period_months"] = 24
        canonical_result["primary_period_justification"] = result["primary_period_justification"]
        canonical_result["class_metrics"] = class_reports
        canonical_result["confusion_matrices"] = matrices
        canonical_result["input_sha256"] = source_hash_before
        CANONICAL_RESULTS_PATH.write_text(json.dumps(canonical_result, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    if CANONICAL_PREDICTIONS_PATH.exists():
        canonical_predictions = pd.read_csv(CANONICAL_PREDICTIONS_PATH)
        expected_dates = pd.to_datetime(predictions["decision_date"])
        if len(canonical_predictions) != len(expected_dates) or not pd.to_datetime(canonical_predictions["decision_date"]).equals(expected_dates.reset_index(drop=True)):
            raise AssertionError("Existing sealed prediction artifact does not match the fixed 24-month test")
        canonical_predictions = canonical_predictions.copy()
        for model_name in ("Logistic Regression", "Random Forest"):
            for label in CLASS_ORDER:
                canonical_predictions[f"probability_{model_name}_{label}"] = primary_rows[f"probability_{model_name}_{label}"].to_numpy()
        canonical_predictions.to_csv(CANONICAL_PREDICTIONS_PATH, index=False)
    source_hash_after = normalized_sha256(DATA_PATH)
    if source_hash_before != source_hash_after:
        raise AssertionError("Input CSV changed during pipeline execution")
    print(f"Created {_display_path(RESULTS_PATH)}")
    print(f"Created {_display_path(PREDICTIONS_PATH)}")
    print(f"Updated {_display_path(CANONICAL_RESULTS_PATH)} and {_display_path(CANONICAL_PREDICTIONS_PATH)} with related period/probability results")
    print(f"Created {_display_path(VALIDITY_PATH)}")
    print("Created outputs/legacy/mvp_structural_break_candidates.csv and outputs/legacy/mvp_structural_break_summary.json")
    print("Created outputs/legacy/mvp_alternative_specifications.json and outputs/legacy/mvp_detailed_error_analysis.csv")
    print(f"Structural-break scope: {break_report['sample']}")
    print(f"Raw lending source files present: {break_report['raw_monthly_sources_present']}")
    for record in break_report["tests"]:
        if record.get("status", "").startswith("EXPLORATORY"):
            print(f"Break scan {record['feature']} {record['form']} {record['test']} at {record['selected_date']}: sup-F={record['sup_f_statistic']:.3f}, moving-block bootstrap p={record['moving_block_bootstrap_pvalue']:.3f}")
    print("Alternative specification metrics:")
    for record in alternative_rows.to_dict(orient="records"):
        if record.get("status") == "EVALUATED":
            print(f"  {record['period_months']}m | {record['specification']} | {record['model']}: accuracy={record['accuracy']:.3f}, balanced_accuracy={record['balanced_accuracy']:.3f}, macro_f1={record['macro_f1']:.3f}")
    print(f"Train={len(training)}, test={len(test)}, input SHA-256={source_hash_after}")
    for item in metric_rows:
        print(f"{item['Model']}: accuracy={item['Accuracy']:.6f}, balanced_accuracy={item['Balanced accuracy']:.6f}, macro_f1={item['Macro F1']:.6f}")
    return paths


if __name__ == "__main__":
    main()
