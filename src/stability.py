"""Pre-test expanding-window stability checks for the fixed MVP model."""

import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score

from src.legacy_classifier import CLASSES, FEATURES, make_model


# Fixed before examining final-holdout outcomes. Each validation block has six
# decisions; the expanding training windows end before the next block starts.
INITIAL_TRAIN_SIZE = 56
FOLD_SIZE = 6
FOLD_COUNT = 3


def expanding_window_stability(df, final_test_start):
    """Evaluate fixed Logistic Regression against Hold on pre-holdout folds."""
    pretest = df.loc[df["decision_date"] < final_test_start].sort_values("decision_date").reset_index(drop=True)
    rows = []
    fold_predictions = []
    for fold_index in range(FOLD_COUNT):
        train_end = INITIAL_TRAIN_SIZE + fold_index * FOLD_SIZE
        test_end = train_end + FOLD_SIZE
        if test_end > len(pretest):
            raise ValueError("Insufficient pre-holdout rows for the fixed stability folds")
        training = pretest.iloc[:train_end]
        test = pretest.iloc[train_end:test_end]
        model = make_model("Logistic Regression")
        model.fit(training[FEATURES], training["decision"])
        predicted = model.predict(test[FEATURES])
        actual = test["decision"]
        for name, values in (("Logistic Regression", predicted), ("Hold benchmark", ["Hold"] * len(test))):
            rows.append({
                "fold": fold_index + 1,
                "model": name,
                "train_n": len(training),
                "train_end": training["decision_date"].max().strftime("%Y-%m-%d"),
                "test_n": len(test),
                "test_start": test["decision_date"].min().strftime("%Y-%m-%d"),
                "test_end": test["decision_date"].max().strftime("%Y-%m-%d"),
                "accuracy": float(accuracy_score(actual, values)),
                "balanced_accuracy": float(balanced_accuracy_score(actual, values)),
                "macro_f1": float(f1_score(actual, values, labels=CLASSES, average="macro", zero_division=0)),
            })
        frame = test[["decision_date", "decision"]].rename(columns={"decision": "actual"}).copy()
        frame["fold"] = fold_index + 1
        frame["Logistic Regression"] = predicted
        frame["Hold benchmark"] = "Hold"
        fold_predictions.append(frame)
    return pd.DataFrame(rows), pd.concat(fold_predictions, ignore_index=True)
