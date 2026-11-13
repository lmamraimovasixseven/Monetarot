"""Модуль прогноза рядов (блок D): `python run.py forecast --series S --cutoff YYYY-MM [--h H --method M]`
и `python run.py desk` (полный бэктест по prereg/candidates.json).

forecast(series, cutoff, h, method) использует только наблюдения до месяца cutoff включительно, даёт точку и
80% интервал на любом горизонте. Кандидаты, ряды, горизонты и дизайн бэктеста заморожены в
prereg/candidates.json до написания этого модуля; модуль их только читает.

Каждая оценка через statsmodels имеет запасной путь (D35): ARIMA — statespace, затем больше итераций, затем
innovations MLE; ETS — при ошибке оптимизации naive с пометкой. Таблицы имеют фиксированный набор строк
(статус в строке), поэтому число строк отчёта не зависит от сходимости.
Результаты пишутся в outputs/desk/ (не в корень outputs/: их не сравнивает `python run.py check`).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from scipy.stats import norm

from src.hashing import normalized_sha256

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES_PATH = ROOT / "prereg" / "candidates.json"
CALENDAR_PATH = ROOT / "config" / "intervention_calendar.csv"
OUT_DIR = ROOT / "outputs" / "desk"
FORECAST_LEDGER = ROOT / "ledger" / "forecast_ledger.csv"
NOMINAL = 0.80
Z = float(norm.ppf(0.5 + NOMINAL / 2))
MIN_PAST_ERRORS = 20
SEASON = 12
LABEL = "revised-data backtest"
LEDGER_COLUMNS = ["run_utc", "series", "cutoff", "h", "target_month", "method", "point", "lower_80", "upper_80",
                  "interval_method", "candidates_sha256", "status"]


# ----------------------------------------------------------------------------- данные

def load_series(name: str, root: Path = ROOT) -> pd.Series:
    """Месячный ряд с PeriodIndex; пустой ряд, если данных нет (USD/KZT до загрузки)."""
    from src.ingest import read_monthly_series

    raw = root / "data" / "raw"
    if name == "inflation_yoy":
        return read_monthly_series(raw / "inflation_history.csv", "inflation").rename(name)
    if name == "real_rate":
        rate = read_monthly_series(raw / "base_rate_history.csv", "rate")
        inflation = read_monthly_series(raw / "inflation_history.csv", "inflation")
        joined = pd.concat([rate, inflation], axis=1, join="inner").dropna()
        return (joined.iloc[:, 0] - joined.iloc[:, 1]).rename(name)
    if name == "imports_log":
        return (100 * np.log(read_monthly_series(raw / "import_history.csv", "imports_thousand_usd"))).rename(name)
    if name == "usd_kzt":
        from src import external_data

        daily = external_data.read_raw("usd_kzt")
        monthly = external_data.monthly_average(daily)
        return (100 * np.log(monthly["value"])).rename(name) if len(monthly) else pd.Series(dtype=float, name=name)
    raise KeyError(name)


# ----------------------------------------------------------------------------- методы

def _sd(values: np.ndarray) -> float:
    values = values[np.isfinite(values)]
    return float(np.std(values, ddof=1)) if len(values) > 1 else float("nan")


def m_naive(y: np.ndarray, h: int) -> tuple[np.ndarray, np.ndarray, str]:
    sigma = _sd(np.diff(y))
    return np.repeat(y[-1], h), sigma * np.sqrt(np.arange(1, h + 1)), "ok"


def m_seasonal_naive(y: np.ndarray, h: int) -> tuple[np.ndarray, np.ndarray, str]:
    if len(y) < 2 * SEASON:
        raise ValueError("fewer than two seasons")
    point = np.array([y[len(y) - SEASON + ((i - 1) % SEASON)] for i in range(1, h + 1)])
    sigma = _sd(y[SEASON:] - y[:-SEASON])
    k = np.floor((np.arange(1, h + 1) - 1) / SEASON) + 1
    return point, sigma * np.sqrt(k), "ok"


def m_mean12(y: np.ndarray, h: int) -> tuple[np.ndarray, np.ndarray, str]:
    window = y[-12:]
    return np.repeat(window.mean(), h), np.repeat(_sd(window) * math.sqrt(1 + 1 / len(window)), h), "ok"


def m_ar1(y: np.ndarray, h: int) -> tuple[np.ndarray, np.ndarray, str]:
    """OLS y_t = c + phi*y_{t-1}; дисперсия ошибки прогноза sigma^2 * sum phi^(2i)."""
    x, target = y[:-1], y[1:]
    design = np.column_stack([np.ones_like(x), x])
    (c, phi), *_ = np.linalg.lstsq(design, target, rcond=None)
    sigma = _sd(target - design @ np.array([c, phi]))
    point, last = [], y[-1]
    for _ in range(h):
        last = c + phi * last
        point.append(last)
    variance = np.cumsum([phi ** (2 * i) for i in range(h)]) * sigma ** 2
    return np.array(point), np.sqrt(variance), "ok"


def ar1_parameters(y: np.ndarray) -> dict[str, float | str]:
    x, target = y[:-1], y[1:]
    (c, phi), *_ = np.linalg.lstsq(np.column_stack([np.ones_like(x), x]), target, rcond=None)
    mean = c / (1 - phi) if phi != 1 else float("nan")
    half_life = math.log(0.5) / math.log(phi) if 0 < phi < 1 else float("nan")
    return {"n": int(len(y)), "c": float(c), "phi": float(phi), "mean": float(mean), "half_life_months": float(half_life)}


def _ets(y: np.ndarray, h: int, kind: str) -> tuple[np.ndarray, np.ndarray, str]:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    options = {"ses": {}, "holt_damped": {"trend": "add", "damped_trend": True},
               "holt_winters": {"trend": None, "seasonal": "add", "seasonal_periods": SEASON}}[kind]
    if kind == "holt_winters" and len(y) < 2 * SEASON:
        raise ValueError("fewer than two seasons")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = ExponentialSmoothing(y, initialization_method="estimated", **options).fit(optimized=True)
        point = np.asarray(fit.forecast(h), dtype=float)
        if not np.isfinite(point).all():
            raise ValueError("non-finite forecast")
    except Exception as exc:  # запасной путь: naive с пометкой (число строк не меняется)
        point, sd, _ = m_naive(y, h)
        return point, sd, f"fallback naive ({type(exc).__name__})"
    sigma = _sd(y - np.asarray(fit.fittedvalues, dtype=float))
    alpha = float(fit.params.get("smoothing_level", 0.5) or 0.5)
    factor = np.sqrt(1 + np.arange(h) * alpha ** 2) if kind == "ses" else np.sqrt(np.arange(1, h + 1))
    return point, sigma * factor, "ok"


ARIMA_ORDERS = {"arima_011": (0, 1, 1), "arima_110": (1, 1, 0), "arima_111": (1, 1, 1), "arima_200": (2, 0, 0)}


def fit_arima(y: np.ndarray, order: tuple[int, int, int]):
    """ARIMA с запасным путём: statespace → statespace с maxiter 1000 → innovations MLE."""
    from statsmodels.tsa.arima.model import ARIMA

    trend = "c" if order[1] == 0 else "n"
    attempts = [("statespace", {}), ("statespace", {"method_kwargs": {"maxiter": 1000}}), ("innovations_mle", {})]
    last = None
    for method, extra in attempts:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                result = ARIMA(y, order=order, trend=trend).fit(method=method, **extra)
            converged = bool(result.mle_retvals.get("converged", True)) if result.mle_retvals else True
            last = (result, f"ok ({method})" if converged else f"nonconverged ({method})")
            if converged:
                return last
        except Exception as exc:
            last = (None, f"failed ({method}: {type(exc).__name__})")
    return last


def _arima(y: np.ndarray, h: int, name: str) -> tuple[np.ndarray, np.ndarray, str]:
    result, status = fit_arima(y, ARIMA_ORDERS[name])
    if result is None:
        point, sd, _ = m_naive(y, h)
        return point, sd, f"fallback naive ({status})"
    forecast = result.get_forecast(h)
    return np.asarray(forecast.predicted_mean, dtype=float), np.sqrt(np.asarray(forecast.var_pred_mean, dtype=float)), status


METHODS: dict[str, Callable[[np.ndarray, int], tuple[np.ndarray, np.ndarray, str]]] = {
    "naive": m_naive, "seasonal_naive": m_seasonal_naive, "mean12": m_mean12, "ar1": m_ar1,
    "ses": lambda y, h: _ets(y, h, "ses"), "holt_damped": lambda y, h: _ets(y, h, "holt_damped"),
    "holt_winters": lambda y, h: _ets(y, h, "holt_winters"),
    **{name: (lambda y, h, n=name: _arima(y, h, n)) for name in ARIMA_ORDERS},
}


def forecast(series: pd.Series, cutoff: str | pd.Period, h: int, method: str) -> dict[str, Any]:
    """Точка и 80% интервал (формула модели) на горизонты 1..h, только по данным до cutoff включительно."""
    cutoff = pd.Period(cutoff, freq="M")
    history = series[pd.PeriodIndex(series.index, freq="M") <= cutoff].dropna()
    if len(history) < 3:
        raise ValueError(f"too few observations up to {cutoff}: {len(history)}")
    point, sd, status = METHODS[method](history.to_numpy(dtype=float), h)
    months = [str(cutoff + i) for i in range(1, h + 1)]
    return {"series": series.name, "cutoff": str(cutoff), "method": method, "n_used": int(len(history)),
            "target_months": months, "point": point.tolist(), "lower_80": (point - Z * sd).tolist(),
            "upper_80": (point + Z * sd).tolist(), "status": status}


# ----------------------------------------------------------------------------- бэктест

def backtest(series: pd.Series, methods: list[str], horizons: list[int], first_origin: int,
             origins: list[int] | None = None) -> pd.DataFrame:
    """Расширяющееся окно: на каждом начале все параметры переоцениваются по данным до него."""
    values = series.dropna()
    index = pd.PeriodIndex(values.index, freq="M")
    h_max = max(horizons)
    positions = origins if origins is not None else list(range(first_origin, len(values) - min(horizons) + 1))
    rows = []
    for position in positions:
        history = values.iloc[:position]
        for method in methods:
            try:
                point, sd, status = METHODS[method](history.to_numpy(dtype=float), h_max)
            except ValueError as exc:
                point, sd, status = np.full(h_max, np.nan), np.full(h_max, np.nan), f"not applicable ({exc})"
            for h in horizons:
                target = position + h - 1
                if target >= len(values):
                    continue
                rows.append({"origin": str(index[position - 1]), "n_used": position, "method": method, "h": h,
                             "target_month": str(index[target]), "actual": float(values.iloc[target]),
                             "point": float(point[h - 1]), "sd": float(sd[h - 1]), "status": status})
    frame = pd.DataFrame(rows)
    frame["error"] = frame["actual"] - frame["point"]
    frame["lower_formula"] = frame["point"] - Z * frame["sd"]
    frame["upper_formula"] = frame["point"] + Z * frame["sd"]
    return add_empirical_intervals(frame)


def add_empirical_intervals(frame: pd.DataFrame) -> pd.DataFrame:
    """Интервал из квантилей прошлых ошибок вне выборки (тот же метод и горизонт, только известные к началу)."""
    lower, upper = np.full(len(frame), np.nan), np.full(len(frame), np.nan)
    for (_, _), group in frame.groupby(["method", "h"]):
        group = group.sort_values("origin")
        for i, (row_index, row) in enumerate(group.iterrows()):
            known = group[group["target_month"] <= row["origin"]]["error"].dropna()
            if len(known) >= MIN_PAST_ERRORS:
                q_low, q_high = np.quantile(known, [(1 - NOMINAL) / 2, (1 + NOMINAL) / 2])
                lower[frame.index.get_loc(row_index)] = row["point"] + q_low
                upper[frame.index.get_loc(row_index)] = row["point"] + q_high
    frame["lower_empirical"], frame["upper_empirical"] = lower, upper
    return frame


def pinball(y: np.ndarray, q_value: np.ndarray, q: float) -> np.ndarray:
    diff = y - q_value
    return np.maximum(q * diff, (q - 1) * diff)


def metrics(frame: pd.DataFrame) -> dict[str, float | int | None]:
    ok = frame.dropna(subset=["point"])
    if ok.empty:
        return {"n": 0, "MAE": None, "RMSE": None, "pinball_q10": None, "pinball_q90": None,
                "coverage_formula": None, "coverage_empirical": None, "n_empirical": 0}
    y = ok["actual"].to_numpy()
    emp = ok.dropna(subset=["lower_empirical"])
    return {"n": int(len(ok)), "MAE": float(np.mean(np.abs(ok["error"]))), "RMSE": float(np.sqrt(np.mean(ok["error"] ** 2))),
            "pinball_q10": float(np.mean(pinball(y, ok["lower_formula"].to_numpy(), 0.1))),
            "pinball_q90": float(np.mean(pinball(y, ok["upper_formula"].to_numpy(), 0.9))),
            "coverage_formula": float(np.mean((y >= ok["lower_formula"]) & (y <= ok["upper_formula"]))),
            "coverage_empirical": float(np.mean((emp["actual"] >= emp["lower_empirical"]) & (emp["actual"] <= emp["upper_empirical"])))
            if len(emp) else None, "n_empirical": int(len(emp))}


def subperiods(calendar_path: Path = CALENDAR_PATH) -> list[tuple[str, str | None, str | None]]:
    """Подпериоды по календарю вмешательств: границы — даты событий типа level_shift и temporary_episode."""
    calendar = pd.read_csv(calendar_path)
    cuts = sorted({str(pd.Period(d, "M")) for d, t in zip(calendar["date"], calendar["type"])
                   if t in ("level_shift", "temporary_episode")})
    bounds = [None, *cuts, None]
    return [(f"{a or 'начало'} – {b or 'конец'}", a, b) for a, b in zip(bounds, bounds[1:])]


def _in(frame: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    mask = np.ones(len(frame), dtype=bool)
    if start:
        mask &= frame["target_month"] >= start
    if end:
        mask &= frame["target_month"] < end
    return frame[mask]


def event_windows(series_name: str, calendar_path: Path = CALENDAR_PATH, file_name: str | None = None) -> list[tuple[str, str]]:
    calendar = pd.read_csv(calendar_path)
    windows = []
    for row in calendar.itertuples():
        if file_name and row.series_affected != file_name:
            continue
        start = str(pd.Period(row.date, "M"))
        end = str(pd.Period(row.end_date, "M")) if isinstance(row.end_date, str) and row.end_date else str(pd.Period(row.date, "M") + 2)
        windows.append((start, end))
    return windows


def evaluate_series(name: str, spec: dict, candidates: dict, frame: pd.DataFrame | None = None) -> dict[str, Any]:
    from src.robust_eval import dm_test

    series = load_series(name)
    if series.dropna().empty:
        return {"status": "UNKNOWN: данных нет (шаблон; TODO_HUMAN.md)", "n_observations": 0}
    first = int(candidates["backtest"]["first_origin_observations"])
    benchmark = candidates["benchmark"]["seasonal" if spec.get("seasonal") else "non_seasonal"]
    frame = frame if frame is not None else backtest(series, candidates["candidates"], candidates["horizons"], first)
    files = {"inflation_yoy": "inflation_history.csv", "imports_log": "import_history.csv", "real_rate": "inflation_history.csv"}
    windows = event_windows(name, file_name=files.get(name))
    result: dict[str, Any] = {"status": "ok", "label": LABEL, "n_observations": int(series.dropna().size),
                              "first_month": str(series.dropna().index.min()), "last_month": str(series.dropna().index.max()),
                              "first_origin_observations": first, "benchmark": benchmark,
                              "n_origins": int(frame["origin"].nunique()), "n_models": len(candidates["candidates"]),
                              "horizons": {}}
    for h in candidates["horizons"]:
        by_h = frame[frame["h"] == h]
        bench = by_h[by_h["method"] == benchmark].set_index("target_month")
        table = {}
        for method in candidates["candidates"]:
            rows = by_h[by_h["method"] == method]
            entry = metrics(rows)
            entry["statuses"] = sorted(set(rows["status"]))[:3]
            joined = rows.set_index("target_month").join(bench[["error"]], rsuffix="_bench", how="inner").dropna(subset=["error", "error_bench"])
            if method != benchmark and len(joined) >= 3:
                entry["dm_vs_benchmark_p"] = dm_test(np.abs(joined["error"]), np.abs(joined["error_bench"]), horizon=h)["p_value"]
            else:
                entry["dm_vs_benchmark_p"] = None
            outside = rows
            for start, end in windows:
                outside = outside[~((outside["target_month"] >= start) & (outside["target_month"] <= end))]
            entry["MAE_without_event_windows"] = metrics(outside)["MAE"]
            entry["coverage_by_subperiod"] = {label: metrics(_in(rows, a, b))["coverage_formula"] for label, a, b in subperiods()}
            table[method] = entry
        valid = {m: e for m, e in table.items() if e["MAE"] is not None}
        winner = min(valid, key=lambda m: (valid[m]["MAE"], candidates["candidates"].index(m)))
        p = table[winner]["dm_vs_benchmark_p"]
        beats = winner != benchmark and p is not None and p < 0.05
        cov_f, cov_e = table[winner]["coverage_formula"], table[winner]["coverage_empirical"]
        if cov_f is not None and cov_e is not None:
            closer = "квантили прошлых ошибок" if abs(cov_e - NOMINAL) < abs(cov_f - NOMINAL) else "формула модели"
            interval_choice = (f"покрытие 80% интервала у {winner}: формула {cov_f:.3f}, квантили прошлых ошибок {cov_e:.3f}; "
                               f"ближе к номиналу: {closer}")
        else:
            interval_choice = f"покрытие 80% интервала у {winner}: формула {cov_f}; квантили ошибок недоступны"
        result["horizons"][str(h)] = {"table": table, "lowest_mae": winner, "interval_choice": interval_choice,
                                      "verdict": (f"{winner}: MAE ниже бенчмарка {benchmark}, DM p = {p:.3f} < 0.05" if beats else
                                                  f"нет выигрыша у {benchmark}: наименьший MAE у {winner}"
                                                  + (f", но DM p = {p:.3f}" if p is not None else ""))}
    return result


def differencing_report(series: pd.Series) -> dict[str, Any]:
    """ADF и KPSS для уровня и первой разности; AICc только внутри одинакового d; Ljung–Box остатков."""
    from statsmodels.stats.diagnostic import acorr_ljungbox
    from statsmodels.tsa.stattools import adfuller, kpss

    y = series.dropna().to_numpy(dtype=float)
    tests = {}
    for label, values in (("level", y), ("first_difference", np.diff(y))):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            adf_p = float(adfuller(values, autolag="AIC")[1])
            kpss_p = float(kpss(values, regression="c", nlags="auto")[1])
        tests[label] = {"adf_p": adf_p, "kpss_p": kpss_p}
    models = {}
    for name, order in {"ar1": (1, 0, 0), **ARIMA_ORDERS}.items():
        result, status = fit_arima(y, order)
        if result is None:
            models[name] = {"d": order[1], "aicc": None, "ljung_box_p_lag12": None, "status": status}
            continue
        resid = np.asarray(result.resid, dtype=float)[order[1]:]
        lb = float(acorr_ljungbox(resid, lags=[12], return_df=True)["lb_pvalue"].iloc[0])
        models[name] = {"d": order[1], "aicc": float(result.aicc), "ljung_box_p_lag12": lb, "status": status,
                        "n_params": int(len(result.params))}
    for d in {m["d"] for m in models.values()}:
        group = {k: v for k, v in models.items() if v["d"] == d and v["aicc"] is not None}
        best = min(v["aicc"] for v in group.values()) if group else None
        for k, v in group.items():
            v["delta_aicc"] = v["aicc"] - best
        ties = [k for k, v in group.items() if v["delta_aicc"] <= 2]
        chosen = min(ties, key=lambda k: (group[k]["n_params"], group[k]["aicc"])) if ties else None
        for k in group:
            group[k]["chosen_within_d"] = k == chosen
    return {"tests": tests, "models": models}


def ar1_by_subperiod(series: pd.Series) -> list[dict[str, Any]]:
    rows = []
    for label, start, end in [("весь ряд", None, None), *subperiods()]:
        part = series.dropna()
        index = pd.PeriodIndex(part.index, freq="M").astype(str)
        mask = np.ones(len(part), dtype=bool)
        if start:
            mask &= index >= start
        if end:
            mask &= index < end
        part = part[mask]
        rows.append({"period": label, **(ar1_parameters(part.to_numpy(dtype=float)) if len(part) >= 24 else
                                         {"n": int(len(part)), "status": "слишком короткий (< 24 наблюдений)"})})
    return rows


def half_life_words(params: dict[str, Any]) -> str:
    phi, hl = params.get("phi"), params.get("half_life_months")
    if phi is None or not isinstance(hl, float) or math.isnan(hl):
        return "период полураспада не определён (phi вне (0, 1))"
    return (f"отклонение от среднего {params['mean']:.2f} уменьшается вдвое примерно за {hl:.1f} мес. "
            f"(phi = {phi:.3f})")


# ----------------------------------------------------------------------------- y/y из m/m

def yoy_from_mom(mom_percent: list[float]) -> float:
    """y/y из двенадцати последних m/m: (prod(1 + m/100) - 1) * 100."""
    if len(mom_percent) != 12:
        raise ValueError("need exactly 12 monthly changes")
    return (float(np.prod([1 + m / 100 for m in mom_percent])) - 1) * 100


def required_mom_for_year_end(known_mom_this_year: list[float], target_yoy_december: float) -> float:
    """Средний m/m в оставшиеся месяцы, чтобы декабрь к декабрю закончился на target (эффект базы учтён)."""
    remaining = 12 - len(known_mom_this_year)
    if remaining <= 0:
        raise ValueError("no months remain")
    done = float(np.prod([1 + m / 100 for m in known_mom_this_year]))
    return (((1 + target_yoy_december / 100) / done) ** (1 / remaining) - 1) * 100


# ----------------------------------------------------------------------------- запуск

def append_forecast_ledger(rows: list[dict[str, Any]], path: Path = FORECAST_LEDGER) -> int:
    """Только добавление: строка с тем же (series, cutoff, h, method, candidates_sha256) не дублируется."""
    existing = set()
    if Path(path).is_file():
        with Path(path).open(encoding="utf-8", newline="") as handle:
            existing = {(r["series"], r["cutoff"], r["h"], r["method"], r["candidates_sha256"]) for r in csv.DictReader(handle)}
    new = [r for r in rows if (r["series"], r["cutoff"], str(r["h"]), r["method"], r["candidates_sha256"]) not in existing]
    write_header = not Path(path).is_file()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_COLUMNS, lineterminator="\n")
        if write_header:
            writer.writeheader()
        writer.writerows(new)
    return len(new)


def run_desk(out_dir: Path = OUT_DIR, write_ledger: bool = True) -> dict[str, Any]:
    started = time.perf_counter()
    candidates = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    sha = normalized_sha256(CANDIDATES_PATH)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {"label": LABEL, "candidates_sha256": sha, "nominal_coverage": NOMINAL, "series": {}}
    ledger_rows = []
    run_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    for name, spec in candidates["series"].items():
        series = load_series(name)
        if series.dropna().empty:
            summary["series"][name] = {"status": "UNKNOWN: данных нет (шаблон; TODO_HUMAN.md)", "n_observations": 0}
            continue
        frame = backtest(series, candidates["candidates"], candidates["horizons"],
                         int(candidates["backtest"]["first_origin_observations"]))
        frame.to_csv(out_dir / f"backtest_{name}.csv", index=False, float_format="%.6f", lineterminator="\n")
        result = evaluate_series(name, spec, candidates, frame)
        result["differencing"] = differencing_report(series)
        result["ar1"] = ar1_by_subperiod(series)
        result["ar1_words"] = half_life_words(result["ar1"][0])
        cutoff = str(series.dropna().index.max())
        current = {}
        for method in {result["horizons"]["1"]["lowest_mae"], result["benchmark"]}:
            fc = forecast(series, cutoff, max(candidates["horizons"]), method)
            current[method] = fc
            for i, month in enumerate(fc["target_months"]):
                ledger_rows.append({"run_utc": run_utc, "series": name, "cutoff": cutoff, "h": i + 1, "target_month": month,
                                    "method": method, "point": f"{fc['point'][i]:.6f}", "lower_80": f"{fc['lower_80'][i]:.6f}",
                                    "upper_80": f"{fc['upper_80'][i]:.6f}", "interval_method": "model formula",
                                    "candidates_sha256": sha, "status": fc["status"]})
        result["current_forecasts"] = current
        summary["series"][name] = result
    summary["models_tried"] = len(candidates["candidates"])
    summary["windows_tried"] = int(sum(s.get("n_origins", 0) for s in summary["series"].values()))
    summary["yoy_table"] = "UNKNOWN: месячной инфляции m/m в данных нет; таблица «что нужно для X% в декабре» строится, когда появится ряд m/m (TODO_HUMAN.md)"
    summary["runtime_seconds"] = round(time.perf_counter() - started, 1)
    (out_dir / "forecast_desk.md").write_text(render_markdown(summary), encoding="utf-8", newline="\n")
    if write_ledger:
        summary["forecast_ledger_rows_added"] = append_forecast_ledger(ledger_rows)
    return summary


def render_markdown(summary: dict[str, Any]) -> str:
    lines = ["<!-- Сгенерировано `python run.py desk` (src/forecast_desk.py). -->", "# Модуль прогноза рядов", "",
             f"Метка: **{summary['label']}** (старых винтажей нет). Кандидаты заморожены: `prereg/candidates.json`, SHA-256 "
             f"`{summary['candidates_sha256'][:16]}…`. Испытано моделей: {summary['models_tried']}; начал окна (всего по рядам): "
             f"{summary['windows_tried']}. Номинальное покрытие интервалов {summary['nominal_coverage']:.0%}.", ""]
    for name, result in summary["series"].items():
        lines += [f"## {name}", ""]
        if result.get("status") != "ok":
            lines += [f"Статус: {result['status']}", ""]
            continue
        lines += [f"Наблюдений {result['n_observations']} ({result['first_month']} – {result['last_month']}); первое начало после "
                  f"{result['first_origin_observations']} наблюдений; начал {result['n_origins']}; бенчмарк `{result['benchmark']}`.", ""]
        for h, block in result["horizons"].items():
            lines += [f"### h = {h}: {block['verdict']}", "",
                      "| Метод | n | MAE | RMSE | pinball q10 | pinball q90 | покрытие (формула) | покрытие (квантили ошибок) | DM p против бенчмарка | MAE без окон событий | статус |",
                      "|---|---|---|---|---|---|---|---|---|---|---|"]
            for method, e in block["table"].items():
                f = lambda v: "—" if v is None else f"{v:.3f}"  # noqa: E731
                lines.append(f"| {method} | {e['n']} | {f(e['MAE'])} | {f(e['RMSE'])} | {f(e['pinball_q10'])} | {f(e['pinball_q90'])} | "
                             f"{f(e['coverage_formula'])} | {f(e['coverage_empirical'])} | {f(e['dm_vs_benchmark_p'])} | "
                             f"{f(e['MAE_without_event_windows'])} | {'; '.join(e['statuses'])} |")
            lines += ["", f"Интервалы: {block['interval_choice']}.", ""]
        diff = result["differencing"]
        lines += ["### Дифференцирование и AICc (сравнение только при одинаковом d)", "",
                  f"ADF p (уровень) {diff['tests']['level']['adf_p']:.3f}, KPSS p (уровень) {diff['tests']['level']['kpss_p']:.3f}; "
                  f"ADF p (разность) {diff['tests']['first_difference']['adf_p']:.3f}, KPSS p (разность) {diff['tests']['first_difference']['kpss_p']:.3f}.", "",
                  "| Модель | d | AICc | ΔAICc внутри d | Ljung–Box p (12) | выбрана внутри d | статус |", "|---|---|---|---|---|---|---|"]
        for model_name, m in diff["models"].items():
            f = lambda v: "—" if v is None else f"{v:.2f}"  # noqa: E731
            lines.append(f"| {model_name} | {m['d']} | {f(m['aicc'])} | {f(m.get('delta_aicc'))} | {f(m['ljung_box_p_lag12'])} | "
                         f"{'да' if m.get('chosen_within_d') else 'нет'} | {m['status']} |")
        lines += ["", f"**AR(1):** {result['ar1_words']}.", "", "| Период | n | phi | среднее | полураспад, мес. |", "|---|---|---|---|---|"]
        for row in result["ar1"]:
            if "phi" in row:
                lines.append(f"| {row['period']} | {row['n']} | {row['phi']:.3f} | {row['mean']:.2f} | {row['half_life_months']:.1f} |")
            else:
                lines.append(f"| {row['period']} | {row['n']} | — | — | {row['status']} |")
        lines.append("")
    lines += [f"Таблица y/y из m/m: {summary['yoy_table']}", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["desk", "forecast"])
    parser.add_argument("--series", default="inflation_yoy")
    parser.add_argument("--cutoff", default=None)
    parser.add_argument("--h", type=int, default=3)
    parser.add_argument("--method", default="naive")
    args = parser.parse_args(argv)
    if args.action == "forecast":
        series = load_series(args.series)
        if series.dropna().empty:
            print(f"{args.series}: UNKNOWN (нет данных)")
            return 1
        print(json.dumps(forecast(series, args.cutoff or str(series.dropna().index.max()), args.h, args.method),
                         ensure_ascii=False, indent=2))
        return 0
    summary = run_desk()
    from src.artifact_extensions import merge

    compact = json.loads(json.dumps(summary, default=float))
    merge("forecast_desk", compact)
    print(f"Desk: {summary['models_tried']} models, {summary['windows_tried']} origins, {summary['runtime_seconds']} s; "
          f"forecast ledger rows added: {summary.get('forecast_ledger_rows_added')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
