"""Паттерны рядов (блок C): `python run.py patterns`.

* Тест сезонности: ряд приводится к стационарному виду (m/m: разность логарифма для уровней, первая разность
  для ставок), остаток регрессируется на 11 месячных фиктивных переменных; F сравнивается с 999 перестановками
  меток месяцев (seed 42) на всей выборке и на каждой половине. Решение: «да» (p < 0.05 везде), «нестабильно»
  (p < 0.05 на всей выборке, но не на обеих половинах), «слабо» (0.05 ≤ p < 0.10), «нет».
* Робастный STL на m/m: окно сезонной компоненты выбирается по псевдо-реальным ревизиям последней точки
  (сезонно скорректированное значение в момент t по данным до t против оценки по данным на 12 мес. позже);
  выбор записывается в docs/DECISIONS.md. Последнее скорректированное значение с полосой пересмотра (80% ревизий).
* Типы выбросов (флаги экрана скачков, модифицированный z на MAD): одиночный, сдвиг уровня, временный эпизод,
  сезонный разрыв; подряд идущие флаги — один эпизод. Ничего не удаляется: флаг, тип, причина, known_at.
* as_of_view(t): только то, что было известно на дату t (src/vintages.py).
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src import data_screen, vintages
from src.ingest import FEATURE_RULES, LOG_GROWTH_FEATURES, RAW_DIR, read_monthly_series

ROOT = Path(__file__).resolve().parents[1]
DECISIONS_DOC = ROOT / "docs" / "DECISIONS.md"
PERMUTATIONS = 999
SEED = 42
STL_WINDOWS = [7, 11, 15, 21, 35]
REVISION_ORIGINS = 24
REVISION_LAG = 12
SERIES = {**{f: v for f, v in FEATURE_RULES.items()}}


def stationary(feature: str, raw_dir: Path = RAW_DIR) -> pd.Series:
    filename, column = SERIES[feature]
    series = read_monthly_series(Path(raw_dir) / filename, column)
    change = 100 * np.log(series).diff() if feature in LOG_GROWTH_FEATURES else series.diff()
    return change.dropna().rename(feature)


def dummy_f(values: np.ndarray, months: np.ndarray) -> float:
    """F-статистика регрессии на месячные фиктивные (11 штук + константа) против одной константы."""
    design = np.column_stack([np.ones(len(values))] + [(months == m).astype(float) for m in range(2, 13)])
    beta, *_ = np.linalg.lstsq(design, values, rcond=None)
    rss_full = float(((values - design @ beta) ** 2).sum())
    rss_null = float(((values - values.mean()) ** 2).sum())
    df_full = len(values) - design.shape[1]
    return ((rss_null - rss_full) / 11) / (rss_full / df_full) if rss_full > 0 and df_full > 0 else float("nan")


def permutation_p(values: np.ndarray, months: np.ndarray, rng: np.random.Generator, draws: int = PERMUTATIONS) -> float:
    observed = dummy_f(values, months)
    exceed = sum(dummy_f(values, rng.permutation(months)) >= observed for _ in range(draws))
    return (exceed + 1) / (draws + 1)


def seasonality_test(series: pd.Series, draws: int = PERMUTATIONS, seed: int = SEED) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    values = series.to_numpy(dtype=float)
    months = pd.PeriodIndex(series.index, freq="M").month.to_numpy()
    half = len(values) // 2
    p_full = permutation_p(values, months, rng, draws)
    p_first = permutation_p(values[:half], months[:half], rng, draws)
    p_second = permutation_p(values[half:], months[half:], rng, draws)
    if p_full < 0.05 and p_first < 0.05 and p_second < 0.05:
        verdict = "да"
    elif p_full < 0.05:
        verdict = "нестабильно"
    elif p_full < 0.10:
        verdict = "слабо"
    else:
        verdict = "нет"
    return {"n": int(len(values)), "F": float(dummy_f(values, months)), "p_permutation": p_full,
            "p_first_half": p_first, "p_second_half": p_second, "verdict": verdict, "draws": draws}


def stl_adjusted(series: pd.Series, window: int) -> pd.Series:
    from statsmodels.tsa.seasonal import STL

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = STL(series.to_numpy(dtype=float), period=12, seasonal=window, robust=True).fit()
    return pd.Series(series.to_numpy(dtype=float) - result.seasonal, index=series.index)


def stl_revisions(series: pd.Series, window: int, origins: int = REVISION_ORIGINS, lag: int = REVISION_LAG) -> np.ndarray:
    """Ревизии последней точки: SA(t | данные до t) − SA(t | данные до t + lag)."""
    revisions = []
    n = len(series)
    for end in range(n - lag - origins, n - lag):
        if end < 36:
            continue
        first = stl_adjusted(series.iloc[: end + 1], window).iloc[-1]
        later = stl_adjusted(series.iloc[: end + 1 + lag], window).iloc[end]
        revisions.append(first - later)
    return np.array(revisions)


def choose_stl_window(series: pd.Series) -> dict[str, Any]:
    table = {}
    for window in STL_WINDOWS:
        revisions = stl_revisions(series, window)
        table[str(window)] = {"mean_abs_revision": float(np.mean(np.abs(revisions))), "n": int(len(revisions)),
                              "q10": float(np.quantile(revisions, 0.1)), "q90": float(np.quantile(revisions, 0.9))}
    chosen = min(table, key=lambda w: (table[w]["mean_abs_revision"], int(w)))
    adjusted = stl_adjusted(series, int(chosen))
    last = float(adjusted.iloc[-1])
    return {"windows": table, "chosen_window": int(chosen), "last_month": str(series.index[-1]),
            "last_adjusted": last, "last_raw": float(series.iloc[-1]),
            "revision_band_80": [last - table[chosen]["q90"], last - table[chosen]["q10"]]}


def classify_flags(flags: list[dict[str, Any]], levels: pd.Series, lag_months: int | None = None) -> list[dict[str, Any]]:
    """Тип каждого эпизода; подряд идущие флаги одного ряда объединяются в один эпизод."""
    lag = vintages.ASSUMED_LAG_MONTHS if lag_months is None else lag_months
    by_month = sorted(flags, key=lambda f: f["month"])
    episodes: list[list[dict[str, Any]]] = []
    for flag in by_month:
        month = pd.Period(flag["month"], "M")
        if episodes and month - pd.Period(episodes[-1][-1]["month"], "M") == 1 * month.freq:
            episodes[-1].append(flag)
        else:
            episodes.append([flag])
    calendar_months = pd.Series([pd.Period(f["month"], "M").month for f in by_month])
    repeated = set(calendar_months.value_counts()[lambda c: c >= 3].index)
    index = pd.PeriodIndex(levels.index, freq="M")
    out = []
    for episode in episodes:
        start, end = pd.Period(episode[0]["month"], "M"), pd.Period(episode[-1]["month"], "M")
        before = levels[(index >= start - 6) & (index < start)]
        after = levels[(index > end) & (index <= end + 6)]
        jump = float(levels[index == end].iloc[0] - before.mean()) if len(before) else float("nan")
        if len(episode) == 1 and start.month in repeated:
            kind, reason = "seasonal_break", f"тот же календарный месяц помечен в ≥ 3 годах"
        elif len(after) == 0:
            kind, reason = "single", "после флага нет наблюдений: тип пока не определён (помечен как одиночный)"
        else:
            persistence = float((after.mean() - before.mean()) / jump) if jump not in (0.0,) and np.isfinite(jump) else 0.0
            window = f"в следующих {len(after)} мес." + (" (предварительно: меньше 6 мес.)" if len(after) < 6 else "")
            if len(episode) >= 2 and persistence < 0.5:
                kind, reason = "temporary_episode", f"{len(episode)} мес. подряд, затем возврат: {window} сохраняется {persistence:.0%} скачка"
            elif persistence >= 0.5:
                kind, reason = "level_shift", f"новый уровень держится: {window} сохраняется {persistence:.0%} скачка"
            else:
                kind, reason = "single", f"возврат: {window} сохраняется {persistence:.0%} скачка"
        out.append({"series_file": episode[0]["series_file"], "start": str(start), "end": str(end), "months": len(episode),
                    "type": kind, "calendar_type": calendar_type(episode[0]["series_file"], start, end), "reason": reason, "max_abs_z": float(max(abs(f["modified_z"]) for f in episode)),
                    "known_at": vintages.known_at(end, lag).date().isoformat(), "action": "помечено, не удалено"})
    return out


def calendar_type(series_file: str, start: pd.Period, end: pd.Period) -> str | None:
    """Тип из config/intervention_calendar.csv (решение человека), если событие пересекается с эпизодом."""
    calendar = pd.read_csv(ROOT / "config" / "intervention_calendar.csv")
    for row in calendar[calendar["series_affected"] == series_file].itertuples():
        first = pd.Period(row.date, "M")
        last = pd.Period(row.end_date, "M") if isinstance(row.end_date, str) and row.end_date else first
        if row.type == "seasonal_break" and first.month == start.month:
            return row.type
        if first <= end and start <= last:
            return row.type
    return None


def outlier_episodes(raw_dir: Path = RAW_DIR) -> list[dict[str, Any]]:
    flags = data_screen.anomaly_screen(raw_dir)
    out = []
    for feature, (filename, column) in FEATURE_RULES.items():
        series_flags = [f for f in flags if f["series_file"] == filename]
        if series_flags:
            out += classify_flags(series_flags, read_monthly_series(Path(raw_dir) / filename, column))
    return out


def as_of_view(t: str | pd.Timestamp, episodes: list[dict[str, Any]], raw_dir: Path = RAW_DIR) -> dict[str, Any]:
    """Что было известно на дату t: последний известный месяц и значение каждого ряда, эпизоды с known_at ≤ t."""
    t = pd.Timestamp(t)
    series = {}
    for feature, (filename, column) in FEATURE_RULES.items():
        known = vintages.as_of(read_monthly_series(Path(raw_dir) / filename, column), t)
        series[feature] = {"last_month": str(known.index.max()) if len(known) else None,
                           "last_value": float(known.iloc[-1]) if len(known) else None}
    return {"t": t.date().isoformat(), "series": series,
            "episodes": [e for e in episodes if pd.Timestamp(e["known_at"]) <= t], "label": vintages.LABEL}


def decisions_markdown(stl: dict[str, dict[str, Any]]) -> str:
    lines = ["<!-- Сгенерировано `python run.py patterns` (src/patterns.py); не править руками. -->",
             "# Решения по методам", "",
             "## Окно STL по ревизиям последней точки", "",
             f"Для каждого окна: средняя абсолютная ревизия сезонно скорректированного значения последней точки "
             f"(оценка по данным до t против оценки по данным до t + {REVISION_LAG}), {REVISION_ORIGINS} последних начал. "
             "Выбирается окно с наименьшей ревизией; при равенстве — более короткое.", "",
             "| Ряд | " + " | ".join(f"окно {w}" for w in STL_WINDOWS) + " | выбрано |",
             "|---|" + "---|" * (len(STL_WINDOWS) + 1)]
    for name, block in stl.items():
        cells = " | ".join(f"{block['windows'][str(w)]['mean_abs_revision']:.3f}" for w in STL_WINDOWS)
        lines.append(f"| {name} | {cells} | {block['chosen_window']} |")
    return "\n".join(lines + [""])


def build(draws: int = PERMUTATIONS) -> dict[str, Any]:
    seasonality, stl = {}, {}
    for feature in FEATURE_RULES:
        series = stationary(feature)
        seasonality[feature] = seasonality_test(series, draws)
        if seasonality[feature]["verdict"] in ("да", "нестабильно"):
            stl[feature] = choose_stl_window(series)
    episodes = outlier_episodes()
    decision_dates = pd.read_csv(ROOT / "config" / "nbk_decision_dates.csv")["decision_date"].tolist()
    views = {t: as_of_view(t, episodes) for t in decision_dates[-8:]}
    return {"seasonality": seasonality, "stl": stl, "episodes": episodes, "as_of_views": views,
            "transform": "m/m: 100*diff(log) для уровней, первая разность для ставок"}


def main() -> int:
    block = build()
    DECISIONS_DOC.write_text(decisions_markdown(block["stl"]), encoding="utf-8", newline="\n")
    from src.artifact_extensions import merge

    merge("patterns", json.loads(json.dumps(block)))
    verdicts = {k: v["verdict"] for k, v in block["seasonality"].items()}
    print(f"Seasonality: {verdicts}; STL for {list(block['stl'])}; episodes: {len(block['episodes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
