"""Преререгистрация и Reality Check.

`python run.py prereg`        — при первом запуске пишет prereg/freeze.json (SHA-256 prereg.md и candidates.json,
                                дата заморозки); затем считает Reality Check на заседание 2026-12-04 и пишет блоки
                                `prereg` и `reality_check` в model/artifact.json. Существующую заморозку не перезаписывает.
`python run.py prereg-check`  — падает (код 1), если замороженный файл изменён после заморозки.
Оценка после решения (`score_reality_check`) вызывается из `python run.py forecast-score`.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.hashing import normalized_sha256

ROOT = Path(__file__).resolve().parents[1]
PREREG_DIR = ROOT / "prereg"
FROZEN_FILES = ["prereg.md", "candidates.json"]
FREEZE_PATH = PREREG_DIR / "freeze.json"
ARTIFACT_PATH = ROOT / "model" / "artifact.json"
DECISIONS_PATH = ROOT / "data" / "processed" / "nbk_decisions_clean.csv"
RATE_PATH = ROOT / "data" / "raw" / "base_rate_history.csv"
LOG_PATH = ROOT / "docs" / "forecast_log.csv"
TARGET_DATE = "2026-12-04"
OUTCOMES = ["Decrease", "Hold", "Increase"]
QUANTILES = [0.1, 0.5, 0.9]


def hashes(directory: Path = PREREG_DIR) -> dict[str, str]:
    return {name: normalized_sha256(Path(directory) / name) for name in FROZEN_FILES}


def freeze(directory: Path = PREREG_DIR, today: date | None = None) -> dict[str, Any]:
    path = Path(directory) / "freeze.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    record = {"frozen_on": (today or date.today()).isoformat(), "sha256": hashes(directory),
              "rule": "these files must not change after freezing; python run.py prereg-check fails otherwise"}
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return record


def check(directory: Path = PREREG_DIR) -> list[str]:
    path = Path(directory) / "freeze.json"
    if not path.is_file():
        return ["prereg/freeze.json is missing (run `python run.py prereg` once to freeze)"]
    frozen = json.loads(path.read_text(encoding="utf-8"))["sha256"]
    current = hashes(directory)
    return [f"{name} changed after freezing (frozen {frozen[name][:12]}, now {current[name][:12]})"
            for name in FROZEN_FILES if frozen.get(name) != current[name]]


def step_distribution(decisions_path: Path = DECISIONS_PATH) -> dict[str, dict[float, float]]:
    """Эмпирическое распределение размеров шага (п.п.) внутри снижений и повышений."""
    panel = pd.read_csv(decisions_path).dropna(subset=["base_rate_before", "base_rate_after", "decision"])
    steps = (panel["base_rate_after"] - panel["base_rate_before"]).round(4)
    result = {}
    for outcome in ("Decrease", "Increase"):
        values = steps[panel["decision"] == outcome]
        counts = values.value_counts(normalize=True).sort_index()
        result[outcome] = {float(k): float(v) for k, v in counts.items()}
    result["Hold"] = {0.0: 1.0}
    return result


def rate_distribution(current_rate: float, probabilities: dict[str, float],
                      steps: dict[str, dict[float, float]]) -> list[tuple[float, float]]:
    mass: dict[float, float] = {}
    for outcome in OUTCOMES:
        for step, share in steps[outcome].items():
            rate = round(current_rate + step, 4)
            mass[rate] = mass.get(rate, 0.0) + probabilities[outcome] * share
    return sorted(mass.items())


def quantile(distribution: list[tuple[float, float]], q: float) -> float:
    cumulative = 0.0
    for rate, p in distribution:
        cumulative += p
        if cumulative >= q - 1e-12:
            return rate
    return distribution[-1][0]


def reality_check(artifact_path: Path = ARTIFACT_PATH, rate_path: Path = RATE_PATH,
                  decisions_path: Path = DECISIONS_PATH) -> dict[str, Any]:
    artifact = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    probabilities = {k: float(v) for k, v in artifact["latest_prediction"]["class_probabilities"].items()}
    rates = pd.read_csv(rate_path)
    current = float(rates["rate"].iloc[-1])
    steps = step_distribution(decisions_path)
    distribution = rate_distribution(current, probabilities, steps)
    expected = float(sum(rate * p for rate, p in distribution))
    log = pd.read_csv(LOG_PATH) if LOG_PATH.is_file() else pd.DataFrame()
    logged = log[log["target_decision_date"] == TARGET_DATE].to_dict("records") if len(log) else []
    return {
        "target": f"итог заседания НБ РК {TARGET_DATE} (ставка после решения)",
        "current_rate": current, "current_rate_month": str(rates["year_month"].iloc[-1]),
        "probabilities": probabilities, "probability_date": artifact["latest_prediction"]["date"],
        "step_distribution": {k: {str(s): p for s, p in v.items()} for k, v in steps.items()},
        "expected_rate": expected,
        "interval_80": [quantile(distribution, 0.1), quantile(distribution, 0.9)],
        "median_rate": quantile(distribution, 0.5),
        "benchmark_always_hold": current,
        "linked_forecast_log_row": logged[0] if logged else None,
        "fallback_target": "инфляция y/y за ноябрь 2026 (БНС); m/m в данных нет; дата публикации UNKNOWN",
    }


def pinball(y: float, q_value: float, q: float) -> float:
    return float(max(q * (y - q_value), (q - 1) * (y - q_value)))


def score_reality_check(check_block: dict[str, Any], actual_rate: float, actual_class: str) -> dict[str, Any]:
    probs = np.array([check_block["probabilities"][k] for k in OUTCOMES])
    observed = np.array([1.0 if k == actual_class else 0.0 for k in OUTCOMES])
    rps = float(((np.cumsum(probs) - np.cumsum(observed))[:2] ** 2).sum() / 2)
    hold_rps = float(((np.cumsum([0, 1, 0]) - np.cumsum(observed))[:2] ** 2).sum() / 2)
    low, high = check_block["interval_80"]
    quantiles = {0.1: low, 0.5: check_block["median_rate"], 0.9: high}
    return {"actual_rate": actual_rate, "actual_class": actual_class, "rps_model": rps, "rps_always_hold": hold_rps,
            "pinball": {str(q): pinball(actual_rate, v, q) for q, v in quantiles.items()},
            "pinball_always_hold": {str(q): pinball(actual_rate, check_block["benchmark_always_hold"], q) for q in QUANTILES},
            "inside_80": bool(low <= actual_rate <= high),
            "error_analysis": "[FILL IN: разбор ошибки пишет человек]"}


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if args and args[0] == "check":
        problems = check()
        for problem in problems:
            print(f"FAIL  {problem}")
        print("prereg-check: " + ("FAIL" if problems else "PASS (frozen files unchanged)"))
        return 1 if problems else 0
    record = freeze()
    problems = check()
    block = reality_check()
    from src.artifact_extensions import merge

    merge("prereg", {"frozen_on": record["frozen_on"], "sha256": record["sha256"], "unchanged": not problems})
    merge("reality_check", block)
    print(f"Frozen on {record['frozen_on']}; unchanged: {not problems}. Expected rate {block['expected_rate']:.3f}, "
          f"80% [{block['interval_80'][0]}, {block['interval_80'][1]}], Always Hold {block['benchmark_always_hold']}.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
