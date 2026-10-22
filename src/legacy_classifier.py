"""Legacy classifier calculations used only by archived diagnostic runners."""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    precision_recall_fscore_support,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_DIR / "data" / "processed" / "nbk_decisions_clean.csv"
FEATURES = ["inflation", "exports", "imports", "corporate_lending", "household_lending", "consumption"]
CLASS_ORDER = ["Decrease", "Hold", "Increase"]
CLASSES = ["Increase", "Hold", "Decrease"]


def make_model(model_name):
    """Build the historical MVP classifier pipeline with its original settings."""
    if model_name == "Logistic Regression":
        estimator = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42)
    elif model_name == "Random Forest":
        estimator = RandomForestClassifier(
            n_estimators=300, max_depth=4, min_samples_leaf=3,
            class_weight="balanced", random_state=42,
        )
    else:
        raise ValueError(f"Unknown model: {model_name}")
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("model", estimator),
    ])


def get_class_probabilities(model, features):
    """Return the first row's fitted probabilities keyed by their class labels."""
    method = getattr(model, "predict_proba", None)
    if not callable(method):
        return None
    values = np.asarray(method(features), dtype=float)
    fitted_classes = list(getattr(model, "classes_", []))
    if values.ndim != 2 or values.shape[0] != 1 or values.shape[1] != len(fitted_classes):
        raise ValueError("Classifier probabilities do not match fitted classes")
    mapped = dict(zip(fitted_classes, values[0]))
    if set(mapped) != set(CLASS_ORDER):
        raise ValueError("Classifier must provide all decision classes")
    return [{"Direction": label, "Probability": float(mapped[label])} for label in ["Increase", "Hold", "Decrease"]]


def load_data():
    """Load and order the processed data for archived classifier evaluation."""
    frame = pd.read_csv(DATA_PATH)
    frame["decision_date"] = pd.to_datetime(frame["decision_date"], errors="coerce")
    frame["decision"] = frame["decision"].astype("string").str.strip().str.title()
    for name in FEATURES:
        frame[name] = pd.to_numeric(frame[name], errors="coerce")
    return frame.dropna(subset=["decision_date", "decision"]).loc[lambda x: x.decision.isin(CLASS_ORDER)].sort_values("decision_date").reset_index(drop=True)


def expanding_window_backtest(df):
    """Run archived 24-month chronological comparison using the old classifiers."""
    cutoff = df["decision_date"].max() - pd.DateOffset(months=24)
    training = df.loc[df.decision_date < cutoff].copy()
    test = df.loc[df.decision_date >= cutoff].copy()
    if len(training) < 10 or training.decision.nunique() < 2:
        return pd.DataFrame(), training, test
    logistic = make_model("Logistic Regression").fit(training[FEATURES], training.decision)
    forest = make_model("Random Forest").fit(training[FEATURES], training.decision)
    predictions = test[["decision_date", "decision"]].rename(columns={"decision": "actual"}).copy()
    predictions["benchmark_hold"] = "Hold"
    predictions["Logistic Regression"] = logistic.predict(test[FEATURES])
    predictions["Random Forest"] = forest.predict(test[FEATURES])
    predictions["decision_date"] = predictions.decision_date.dt.strftime("%Y-%m-%d")
    return predictions.reset_index(drop=True), training, test


def calculate_metrics(predictions):
    """Calculate archived baseline and classifier summary metrics."""
    rows = []
    for column, name in [
        ("benchmark_hold", "Hold benchmark"),
        ("Logistic Regression", "Logistic Regression"),
        ("Random Forest", "Random Forest (additional comparison)"),
    ]:
        actual, predicted = predictions.actual, predictions[column]
        rows.append({
            "Model": name,
            "Test observations": len(predictions),
            "Accuracy": accuracy_score(actual, predicted),
            "Balanced accuracy": balanced_accuracy_score(actual, predicted),
            "Macro F1": f1_score(actual, predicted, labels=CLASSES, average="macro", zero_division=0),
        })
    return pd.DataFrame(rows)


def calculate_class_metrics(predictions, prediction_column):
    """Calculate per-class archived precision, recall, F1 and counts."""
    precision, recall, f1, support = precision_recall_fscore_support(
        predictions.actual, predictions[prediction_column], labels=CLASS_ORDER, zero_division=0,
    )
    return pd.DataFrame({
        "Class": CLASS_ORDER, "Precision": precision, "Recall": recall, "F1-score": f1,
        "Actual observations": support,
        "Predicted observations": [int((predictions[prediction_column] == label).sum()) for label in CLASS_ORDER],
    })
