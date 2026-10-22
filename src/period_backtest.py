"""Fixed-parameter chronological backtests across predeclared holdout widths."""

import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score

from src.legacy_classifier import CLASS_ORDER, FEATURES, get_class_probabilities, make_model


TEST_PERIOD_MONTHS = (24, 36, 48)
MIN_TRAIN_ROWS = 10


def _counts(values, total):
    counts = values.value_counts().reindex(CLASS_ORDER, fill_value=0)
    return {
        label: {"count": int(counts[label]), "share": float(counts[label] / total)}
        for label in CLASS_ORDER
    }


def evaluate_periods(data):
    """Evaluate Hold, Logistic Regression, and Random Forest on each tail window."""
    ordered = data.sort_values("decision_date").reset_index(drop=True)
    latest_date = ordered["decision_date"].max()
    period_reports = []
    prediction_frames = []

    for months in TEST_PERIOD_MONTHS:
        cutoff = latest_date - pd.DateOffset(months=months)
        training = ordered.loc[ordered["decision_date"] < cutoff].copy()
        test = ordered.loc[ordered["decision_date"] >= cutoff].copy()
        train_counts = _counts(training["decision"], len(training)) if len(training) else {}
        actual_counts = _counts(test["decision"], len(test)) if len(test) else {}
        report = {
            "test_period_months": months,
            "cutoff": cutoff.strftime("%Y-%m-%d"),
            "train_n": int(len(training)),
            "train_start": training["decision_date"].min().strftime("%Y-%m-%d") if len(training) else None,
            "train_end": training["decision_date"].max().strftime("%Y-%m-%d") if len(training) else None,
            "test_n": int(len(test)),
            "test_start": test["decision_date"].min().strftime("%Y-%m-%d") if len(test) else None,
            "test_end": test["decision_date"].max().strftime("%Y-%m-%d") if len(test) else None,
            "train_class_distribution": train_counts,
            "actual_class_distribution": actual_counts,
            "train_test_overlap": bool(set(training.index).intersection(test.index)),
            "status": "EVALUATED",
            "models": [],
        }
        if len(training) < MIN_TRAIN_ROWS or len(test) == 0 or training["decision"].nunique() < 2:
            report["status"] = "NOT EVALUABLE: insufficient training/test rows or training classes"
            period_reports.append(report)
            continue
        if report["train_test_overlap"] or not training["decision_date"].max() < test["decision_date"].min():
            raise AssertionError(f"Chronological split overlaps for {months}-month period")

        base = test[["decision_date", "decision"]].rename(columns={"decision": "actual"}).copy()
        base.insert(0, "test_period_months", months)
        base["predicted_Hold benchmark"] = "Hold"
        predictions = {"Hold benchmark": base["predicted_Hold benchmark"].to_numpy()}
        for model_name in ("Logistic Regression", "Random Forest"):
            model = make_model(model_name)
            model.fit(training[FEATURES], training["decision"])
            values = model.predict(test[FEATURES])
            predictions[model_name] = values
            base[f"predicted_{model_name}"] = values
            probability_rows = get_class_probabilities(model, test[FEATURES].iloc[[0]])
            all_probabilities = []
            if probability_rows is not None:
                # Probabilities for each test row are obtained from the same fitted model.
                matrix = model.predict_proba(test[FEATURES])
                fitted_classes = list(model.classes_)
                mapping = {label: matrix[:, fitted_classes.index(label)] for label in CLASS_ORDER}
                for label in CLASS_ORDER:
                    base[f"probability_{model_name}_{label}"] = mapping[label]
                all_probabilities = matrix
                if not ((abs(all_probabilities.sum(axis=1) - 1.0)) <= 1e-8).all():
                    raise AssertionError(f"Probability rows do not sum to 1 for {model_name}, {months} months")

        for model_name, values in predictions.items():
            actual = test["decision"]
            report["models"].append({
                "model": model_name,
                "n": int(len(test)),
                "accuracy": float(accuracy_score(actual, values)),
                "balanced_accuracy": float(balanced_accuracy_score(actual, values)),
                "macro_f1": float(f1_score(actual, values, labels=CLASS_ORDER, average="macro", zero_division=0)),
                "confusion_matrix_labels": CLASS_ORDER,
                "confusion_matrix_actual_rows_predicted_columns": confusion_matrix(actual, values, labels=CLASS_ORDER).tolist(),
                "predicted_class_distribution": _counts(pd.Series(values), len(test)),
                "actual_class_distribution": actual_counts,
            })
        prediction_frames.append(base)
        period_reports.append(report)

    all_predictions = pd.concat(prediction_frames, ignore_index=True) if prediction_frames else pd.DataFrame()
    return period_reports, all_predictions
