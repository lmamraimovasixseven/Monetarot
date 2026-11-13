"""Проверка ловушек бэктеста: `python run.py traps` (код 1, если найдена хотя бы одна).

1. Полновыборочные параметры: прогнозы детерминированных методов в бэктесте пересчитываются по данным до
   начала окна, а затем с искажёнными будущими данными; результат должен совпасть.
2. Неправильный бенчмарк: сезонный ряд сравнивается с seasonal naive, несезонный с naive (prereg/candidates.json).
3. Слишком мало сезонов: каждое начало окна имеет не меньше заявленного числа наблюдений (и не меньше двух сезонов
   для сезонных методов).
4. Ручное удаление шоков: число наблюдений в бэктесте равно числу строк исходного ряда.
5. Непроверенные интервалы: у каждого метода посчитано покрытие.
6. Победитель постфактум: бэктест сделан по замороженному списку кандидатов (тот же хеш, тот же набор).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src import forecast_desk as fd
from src import prereg

ROOT = Path(__file__).resolve().parents[1]
DETERMINISTIC = ["naive", "mean12", "ar1", "seasonal_naive"]


def run(artifact_path: Path = ROOT / "model" / "artifact.json", out_dir: Path = fd.OUT_DIR, samples: int = 3) -> list[str]:
    problems: list[str] = []
    artifact = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    desk = artifact.get("forecast_desk")
    if not desk:
        return ["forecast_desk block missing from model/artifact.json (run `python run.py desk`)"]
    candidates = json.loads(fd.CANDIDATES_PATH.read_text(encoding="utf-8"))
    frozen = json.loads((ROOT / "prereg" / "freeze.json").read_text(encoding="utf-8"))["sha256"]["candidates.json"]
    if desk["candidates_sha256"] != frozen or prereg.check():
        problems.append("6 post-hoc: backtest candidates hash differs from the frozen prereg/candidates.json")
    rng = np.random.default_rng(42)
    for name, result in desk["series"].items():
        if result.get("status") != "ok":
            continue
        spec = candidates["series"][name]
        expected = candidates["benchmark"]["seasonal" if spec.get("seasonal") else "non_seasonal"]
        if result["benchmark"] != expected:
            problems.append(f"2 benchmark: {name} uses {result['benchmark']}, expected {expected}")
        for h, block in result["horizons"].items():
            if list(block["table"]) != candidates["candidates"]:
                problems.append(f"6 post-hoc: {name} h={h} table is not the frozen candidate list")
            for method, entry in block["table"].items():
                if entry["n"] and entry["coverage_formula"] is None:
                    problems.append(f"5 intervals: {name} h={h} {method} has no coverage")
        series = fd.load_series(name)
        if result["n_observations"] != int(series.dropna().size):
            problems.append(f"4 shocks removed: {name} backtest used {result['n_observations']} of {series.dropna().size} observations")
        frame = pd.read_csv(out_dir / f"backtest_{name}.csv", dtype={"origin": str, "target_month": str})
        if frame["n_used"].min() < candidates["backtest"]["first_origin_observations"]:
            problems.append(f"3 seasons: {name} has an origin with fewer than the declared observations")
        seasonal_rows = frame[frame["method"].isin(["seasonal_naive", "holt_winters"]) & (frame["n_used"] < 2 * fd.SEASON)]
        if seasonal_rows["status"].str.startswith("ok").any():
            problems.append(f"3 seasons: {name} seasonal method estimated with fewer than two seasons")
        rows = frame[frame["method"].isin(DETERMINISTIC) & (frame["h"] == 1)]
        for _, row in rows.iloc[rng.choice(len(rows), size=min(samples, len(rows)), replace=False)].iterrows():
            origin = pd.Period(row["origin"], "M")
            index = pd.PeriodIndex(series.index, freq="M")
            perturbed = series.where(index <= origin, series + 1000.0)
            for data in (series, perturbed):
                value = fd.forecast(data, origin, 1, row["method"])["point"][0]
                if abs(value - row["point"]) > 1e-5:
                    problems.append(f"1 full-sample: {name} {row['method']} at {origin} gives {value:.6f}, backtest {row['point']:.6f}")
                    break
    return problems


def main() -> int:
    problems = run()
    for problem in problems:
        print(f"TRAP  {problem}")
    print("traps: " + ("FAIL" if problems else "PASS (no trap found)"))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
