"""Правило решения из функции потерь: `python run.py decision`.

Решение (ждёт подтверждения человека): казначей или портфельный менеджер с тенговыми госбумагами до
заседания НБ РК решает, удлинять или сокращать дюрацию. Потери — допущение пользователя
(`config/decision_losses.json`), не оценка модели.

* Бинарный вариант: «удлинить» против «не удлинять». Удлинять стоит, если
  P(снижение) * L_miss > (1 - P(снижение)) * L_false, откуда порог p* = L_false / (L_false + L_miss).
* Трёхисходный вариант: действие с минимальными ожидаемыми потерями sum_k p_k * L[a, k].
* Чувствительность: p* при разных соотношениях r = L_miss / L_false (p* = 1 / (1 + r), убывает по r).
* Оценка прогноза потерями: средние реализованные потери правила на holdout для модели, Always Hold и
  частот классов (используется в блоке D).

Пишет docs/decision_memo.md и outputs/decision_rule.json. Ничего не оценивает.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
LOSSES_PATH = ROOT / "config" / "decision_losses.json"
ARTIFACT_PATH = ROOT / "model" / "artifact.json"
HOLDOUT_PREDICTIONS = ROOT / "outputs" / "annex_predictions.csv"
OUTPUT_JSON = ROOT / "outputs" / "decision_rule.json"
MEMO_PATH = ROOT / "docs" / "decision_memo.md"
OUTCOMES = ["Decrease", "Hold", "Increase"]
ACTION_LABELS = {"lengthen": "удлинить дюрацию", "keep": "оставить дюрацию", "shorten": "сократить дюрацию"}


def load_losses(path: Path = LOSSES_PATH) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    matrix = config["loss_matrix"]
    if set(matrix) != set(config["actions"]) or any(len(row) != len(OUTCOMES) for row in matrix.values()):
        raise ValueError("loss_matrix must have one row per action and one column per outcome")
    if any(value < 0 for row in matrix.values() for value in row):
        raise ValueError("losses must be non-negative")
    return config


def binary_threshold(lengthen_but_no_cut: float, not_lengthen_but_cut: float) -> float:
    """p*: удлинять, если P(снижение) > p*. p* = L_false / (L_false + L_miss)."""
    if lengthen_but_no_cut < 0 or not_lengthen_but_cut < 0 or lengthen_but_no_cut + not_lengthen_but_cut == 0:
        raise ValueError("losses must be non-negative and not both zero")
    return lengthen_but_no_cut / (lengthen_but_no_cut + not_lengthen_but_cut)


def expected_losses(probabilities: dict[str, float] | np.ndarray, matrix: dict[str, list[float]]) -> dict[str, float]:
    p = np.array([probabilities[k] for k in OUTCOMES]) if isinstance(probabilities, dict) else np.asarray(probabilities)
    return {action: float(np.dot(row, p)) for action, row in matrix.items()}


def best_action(probabilities, matrix: dict[str, list[float]]) -> str:
    losses = expected_losses(probabilities, matrix)
    return min(losses, key=lambda action: (losses[action], list(matrix).index(action)))


def sensitivity(ratios: list[float], base_false: float = 1.0) -> list[dict[str, float]]:
    """p* для соотношений r = L_miss / L_false."""
    return [{"ratio_miss_to_false": float(r), "threshold": binary_threshold(base_false, base_false * r)} for r in ratios]


def realized_losses(probability_rows: np.ndarray, actual: list[str], matrix: dict[str, list[float]]) -> float:
    """Средние реализованные потери, если на каждом решении выбирать действие с минимальными ожидаемыми потерями."""
    total = 0.0
    for p, outcome in zip(probability_rows, actual):
        action = best_action(p, matrix)
        total += matrix[action][OUTCOMES.index(outcome)]
    return total / len(actual)


def holdout_loss_evaluation(artifact: dict, matrix: dict[str, list[float]],
                            predictions_path: Path = HOLDOUT_PREDICTIONS) -> dict[str, Any]:
    frame = pd.read_csv(predictions_path)
    actual = frame["actual_decision"].tolist()
    model = frame[["P_Decrease", "P_Hold", "P_Increase"]].to_numpy()
    hold = np.tile([0.0, 1.0, 0.0], (len(frame), 1))
    freq = artifact["benchmark_comparison"]["class_frequency_comparator_secondary"]["probabilities"]
    frequency = np.tile([freq[k] for k in OUTCOMES], (len(frame), 1))
    return {"n": len(frame), "first": str(frame["decision_date"].iloc[0]), "last": str(frame["decision_date"].iloc[-1]),
            "model": realized_losses(model, actual, matrix), "always_hold": realized_losses(hold, actual, matrix),
            "class_frequency": realized_losses(frequency, actual, matrix)}


def build(artifact_path: Path = ARTIFACT_PATH, losses_path: Path = LOSSES_PATH,
          predictions_path: Path = HOLDOUT_PREDICTIONS) -> dict[str, Any]:
    artifact = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    config = load_losses(losses_path)
    probabilities = artifact["latest_prediction"]["class_probabilities"]
    binary = config["binary_losses"]
    threshold = binary_threshold(binary["lengthen_but_no_cut"], binary["not_lengthen_but_cut"])
    p_cut = float(probabilities["Decrease"])
    losses = expected_losses(probabilities, config["loss_matrix"])
    return {
        "decision": config["decision"], "decision_status": config["decision_status"],
        "loss_status": config["status"], "loss_matrix": config["loss_matrix"], "binary_losses": binary,
        "probabilities": probabilities, "probability_date": artifact["latest_prediction"]["date"],
        "binary_threshold_p_cut": threshold, "p_cut": p_cut,
        # соотношение потерь r = L_miss / L_false, при котором бинарный ответ меняется: p_cut = 1 / (1 + r*)
        "switch_ratio_miss_to_false": (1 - p_cut) / p_cut if p_cut > 0 else None,
        "binary_action": "lengthen" if p_cut > threshold else "not_lengthen",
        "expected_losses": losses, "best_action": best_action(probabilities, config["loss_matrix"]),
        "sensitivity": sensitivity(config["sensitivity_ratios"], binary["lengthen_but_no_cut"]),
        "holdout_loss_evaluation": holdout_loss_evaluation(artifact, config["loss_matrix"], predictions_path),
    }


def memo(block: dict[str, Any]) -> str:
    ev = block["holdout_loss_evaluation"]
    sens = "\n".join(f"| {row['ratio_miss_to_false']:g} | {row['threshold']:.3f} |" for row in block["sensitivity"])
    losses = "\n".join(f"| {ACTION_LABELS[a]} | {v:.3f} |" for a, v in block["expected_losses"].items())
    verdict = ("меньше, чем у Always Hold" if ev["model"] < ev["always_hold"] else
               "не меньше, чем у Always Hold")
    return f"""<!-- Сгенерировано `python run.py decision` (src/decision_rule.py); не править руками. -->
# Decision memo (Gate 0)

**Решение (ждёт подтверждения человека):** {block['decision']}

**Статус потерь:** {block['loss_status']}

## Usefulness Test

- **Without you (без нас):** пользователь смотрит на текущую ставку и заявления НБ РК и по умолчанию считает, что ставка не изменится (Always Hold). Это и есть наш бенчмарк.
- **Change (что меняется):** модель даёт вероятности снижения, сохранения и повышения ставки и переводит их в действие с дюрацией через явную функцию потерь.
- **Cost of error (цена ошибки):** удлинить дюрацию, а снижения нет (потеря {block['binary_losses']['lengthen_but_no_cut']:g} усл. ед.); не удлинить, а снижение есть (упущенная выгода {block['binary_losses']['not_lengthen_but_cut']:g} усл. ед.). Значения — допущение пользователя.
- **Who benefits (кому выгодно):** держатели тенговых госбумаг (казначейства банков, портфельные управляющие); они видят не только вероятность, но и порог, при котором стоит действовать.

## Порог из функции потерь

Удлинять, если P(снижение) > p* = L_false / (L_false + L_miss) = **{block['binary_threshold_p_cut']:.3f}**.
Сейчас (вероятности на решение {block['probability_date']}) P(снижение) = **{block['p_cut']:.3f}**, поэтому бинарное правило: **{'удлинить' if block['binary_action'] == 'lengthen' else 'не удлинять'}**.

Трёхисходное правило (ожидаемые потери, усл. ед.):

| Действие | Ожидаемые потери |
|---|---|
{losses}

Минимум ожидаемых потерь: **{ACTION_LABELS[block['best_action']]}**.

## Чувствительность порога к соотношению потерь

| r = L_miss / L_false | p* |
|---|---|
{sens}

Чем дороже упущенное снижение по сравнению с ложным удлинением, тем ниже порог.

## Оценка прогноза потерями (holdout {ev['first']} – {ev['last']}, {ev['n']} решений)

Средние реализованные потери трёхисходного правила: модель {ev['model']:.3f}, Always Hold {ev['always_hold']:.3f}, частоты классов {ev['class_frequency']:.3f}. У модели потери {verdict}. Это одна выборка из {ev['n']} решений без интервала; вывода «модель лучше» отсюда не следует.
"""


def main() -> int:
    block = build()
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(block, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    MEMO_PATH.write_text(memo(block), encoding="utf-8", newline="\n")
    from src.artifact_extensions import merge

    merge("decision", block)
    print(f"Порог p* = {block['binary_threshold_p_cut']:.3f}; P(снижение) = {block['p_cut']:.3f}; "
          f"действие с минимальными потерями: {block['best_action']}. Wrote {MEMO_PATH.name}, {OUTPUT_JSON.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
