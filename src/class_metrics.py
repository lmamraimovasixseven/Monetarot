"""Per-class holdout metrics in the spirit of Merton's measure (exploratory, supplementary): `python run.py class-metrics`.

Writes model/extensions/class_metrics.json and outputs/class_metrics.md; model/artifact.json is not changed. Nothing is
estimated: the frozen model's holdout probabilities are read from outputs/annex_predictions.csv (written by
src/model.py), the class-frequency probabilities from the artifact (estimation sample only), and Always Hold puts
probability one on Hold.

For each class k (Decrease, Hold, Increase) on the holdout:
* n_k: number of realised decisions of class k;
* mean probability assigned to the realised class, over the decisions of class k;
* recall: share of the decisions of class k whose argmax forecast is k (ties go to the first class in the order
  Decrease, Hold, Increase).
Summaries over the classes that occur in the holdout (n_k > 0), J of them:
* mean class recall = average of the recalls;
* Merton's measure CP = (sum of the recalls - 1) / (J - 1), as defined in Kim, Mizen and Thanaset (2006, section 3.2);
  a "stopped-clock" forecast that always predicts one class scores 0, a perfect forecast 1. Always Hold therefore
  has recall 0 for Decrease and Increase and CP = 0 by construction.

Exploratory and supplementary: added after the holdout had been seen; the pre-specified verdict (RMSE ratio) does not
change.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PREDICTIONS_PATH = ROOT / "outputs" / "annex_predictions.csv"
ARTIFACT_PATH = ROOT / "model" / "artifact.json"
OUTPUT_PATH = ROOT / "model" / "extensions" / "class_metrics.json"
REPORT_PATH = ROOT / "outputs" / "class_metrics.md"
CLASSES = ["Decrease", "Hold", "Increase"]
FORECASTERS = {"frozen_model": "Frozen model", "class_frequencies": "Class frequencies", "always_hold": "Always Hold"}
LABEL = ("Exploratory and supplementary: added on 2026-11-17 after the holdout had been seen. The pre-specified "
         "verdict (holdout RMSE ratio) does not change.")


def probabilities(predictions: pd.DataFrame, artifact: dict) -> dict[str, pd.DataFrame]:
    n = len(predictions)
    frequencies = artifact["benchmark_comparison"]["class_frequency_comparator_secondary"]["probabilities"]
    return {
        "frozen_model": predictions[[f"P_{c}" for c in CLASSES]].set_axis(CLASSES, axis=1).astype(float).reset_index(drop=True),
        "class_frequencies": pd.DataFrame([[float(frequencies[c]) for c in CLASSES]] * n, columns=CLASSES),
        "always_hold": pd.DataFrame([[0.0, 1.0, 0.0]] * n, columns=CLASSES),
    }


def class_table(probs: pd.DataFrame, actual: pd.Series) -> dict[str, Any]:
    predicted = probs.idxmax(axis=1)  # first maximum in the order Decrease, Hold, Increase
    per_class, present = {}, []
    for c in CLASSES:
        mask = actual.eq(c).to_numpy()
        n_k = int(mask.sum())
        entry = {"n": n_k}
        if n_k:
            entry["mean_probability_of_realised_class"] = float(probs.loc[mask, c].mean())
            entry["recall"] = float(predicted[mask].eq(c).mean())
            entry["correct"] = int(predicted[mask].eq(c).sum())
            present.append(c)
        per_class[c] = entry
    recalls = [per_class[c]["recall"] for c in present]
    j = len(present)
    return {"classes": per_class, "classes_present": j,
            "mean_class_recall": sum(recalls) / j,
            "merton_cp": (sum(recalls) - 1) / (j - 1) if j > 1 else None,
            "mean_probability_of_realised_class": float(probs.to_numpy()[range(len(actual)), [CLASSES.index(a) for a in actual]].mean())}


def run(predictions_path: Path = PREDICTIONS_PATH, artifact_path: Path = ARTIFACT_PATH) -> dict[str, Any]:
    predictions = pd.read_csv(predictions_path)
    artifact = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    actual = predictions["actual_decision"].astype(str).reset_index(drop=True)
    if len(predictions) != int(artifact["sample"]["holdout_n"]):
        raise ValueError("annex_predictions.csv does not hold the artifact's holdout decisions")
    tables = {key: class_table(p, actual) for key, p in probabilities(predictions, artifact).items()}
    frozen, hold = tables["frozen_model"], tables["always_hold"]
    non_hold = [c for c in CLASSES if c != "Hold" and frozen["classes"][c]["n"]]
    return {
        "label": LABEL,
        "holdout": {"n": len(predictions), "start": str(predictions.decision_date.iloc[0]), "end": str(predictions.decision_date.iloc[-1])},
        "class_order": CLASSES, "forecasters": tables,
        "summary": {"frozen_minus_always_hold_cp": None if frozen["merton_cp"] is None else frozen["merton_cp"] - (hold["merton_cp"] or 0.0),
                    "frozen_correct_non_hold": sum(frozen["classes"][c]["correct"] for c in non_hold),
                    "non_hold_decisions": sum(frozen["classes"][c]["n"] for c in non_hold)},
        "definitions": {
            "recall": "share of the decisions of class k whose argmax forecast is k",
            "mean_class_recall": "average recall over the classes with n_k > 0",
            "merton_cp": "(sum of recalls over the J classes with n_k > 0 - 1) / (J - 1); 0 for a stopped clock, 1 for a perfect forecast (Kim, Mizen and Thanaset 2006)",
        },
    }


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def report(result: dict[str, Any]) -> str:
    f = lambda v: "n/a" if v is None else f"{v:.3f}"  # noqa: E731
    h = result["holdout"]
    lines = ["# Per-class holdout metrics (exploratory, supplementary)", "", result["label"], "",
             f"Holdout: {h['n']} decisions, {h['start']} to {h['end']}.", "",
             "| Forecaster | " + " | ".join(f"{c}: n, mean P(realised), recall" for c in CLASSES) + " | Mean class recall | Merton CP |",
             "|---|" + "---|" * (len(CLASSES) + 2)]
    for key, name in FORECASTERS.items():
        t = result["forecasters"][key]
        cells = [(f"{t['classes'][c]['n']}, {f(t['classes'][c].get('mean_probability_of_realised_class'))}, {f(t['classes'][c].get('recall'))}"
                  if t["classes"][c]["n"] else "0, n/a, n/a") for c in CLASSES]
        lines.append(f"| {name} | " + " | ".join(cells) + f" | {f(t['mean_class_recall'])} | {f(t['merton_cp'])} |")
    lines += ["", "Definitions: " + "; ".join(f"{k}: {v}" for k, v in result["definitions"].items()) + ".", "",
              "Generated by `python run.py class-metrics` into model/extensions/class_metrics.json; model/artifact.json is not changed.", ""]
    return "\n".join(lines)


def main() -> int:
    result = _clean(run())
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    REPORT_PATH.write_text(report(result), encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)} and {REPORT_PATH.relative_to(ROOT)}: " + json.dumps(result["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
