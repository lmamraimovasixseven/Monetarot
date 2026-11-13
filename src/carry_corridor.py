"""Коридор базовой ставки с точки зрения carry trade (блок E): `python run.py corridor`.

Сценарный инструмент, не прогноз курса. Определения: реальная ставка = номинальная − инфляция y/y;
дифференциалы КЗ − РФ и КЗ − КНР (реальные).
* Нижняя граница (капитал не уходит в carry trade в Россию и Китай): номинальная ставка, при которой реальный
  дифференциал к каждому партнёру не ниже премии за риск: L = π_KZ + max_j (r_j + premium).
* Верхняя граница (нет избыточного притока, переукрепления и вреда кредиту): наименьшая из
  (а) π_KZ + max_j r_j + cap — потолок реального дифференциала (параметр притока/переукрепления);
  (б) π_KZ + r_credit0 — реальная ставка, при которой рост корпоративного кредита через 6 месяцев по
      историческому соотношению проекта равен нулю (описательная МНК без подгонки параметров; если наклон
      не отрицательный, ограничение не идентифицировано и не используется).
* Коридор ломается, если L > U.
Функция corridor() — эталон для браузерного движка site/assets/corridor.js (тест сверки до 1e-6).
Эмпирическая проверка (регрессия изменения USD/KZT на реальный дифференциал) выполняется, когда в
data/raw/external/ есть данные; до того — UNKNOWN.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src import external_data
from src.ingest import read_monthly_series

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CREDIT_LEAD_MONTHS = 6
DEFAULTS = {"premium": 2.0, "cap": 6.0}  # пункты; параметры ползунков, допущение пользователя (TODO_HUMAN.md)


def corridor(nbk_rate: float, kz_inflation: float, partner_real_rates: dict[str, float | None],
             premium: float, cap: float, credit_zero_real_rate: float | None) -> dict[str, Any]:
    """Положение ставки в коридоре; та же формула в site/assets/corridor.js."""
    partners = {k: v for k, v in partner_real_rates.items() if v is not None}
    kz_real = nbk_rate - kz_inflation
    differentials = {k: kz_real - v for k, v in partners.items()}
    if not partners:
        return {"kz_real_rate": kz_real, "differentials": {}, "lower": None, "upper": None, "status": "UNKNOWN: нет реальных ставок партнёров"}
    lower = kz_inflation + max(partners.values()) + premium
    candidates = {"inflow_cap": kz_inflation + max(partners.values()) + cap}
    if credit_zero_real_rate is not None:
        candidates["credit"] = kz_inflation + credit_zero_real_rate
    binding = min(candidates, key=candidates.get)
    upper = candidates[binding]
    if lower > upper:
        position = "коридор сломан: нижняя граница выше верхней"
    elif nbk_rate < lower:
        position = "ниже коридора: риск оттока в carry trade"
    elif nbk_rate > upper:
        position = "выше коридора: риск избыточного притока и вреда кредиту"
    else:
        position = "внутри коридора"
    return {"kz_real_rate": kz_real, "differentials": differentials, "lower": lower, "upper": upper,
            "binding_upper": binding, "position": position, "status": "ok"}


def monthly_inputs(raw: Path = RAW) -> pd.DataFrame:
    rate = read_monthly_series(raw / "base_rate_history.csv", "rate")
    inflation = read_monthly_series(raw / "inflation_history.csv", "inflation")
    corporate = read_monthly_series(raw / "loans_legal_entities_history.csv", "loans_legal_entities_mln_kzt")
    frame = pd.concat({"rate": rate, "inflation": inflation, "corporate": corporate}, axis=1).sort_index()
    # Полный месячный календарь: shift() сдвигает строки, поэтому индекс обязан быть упорядочен и без пропусков.
    frame = frame.reindex(pd.period_range(frame.index.min(), frame.index.max(), freq="M"))
    frame["real_rate"] = frame["rate"] - frame["inflation"]
    frame["credit_growth_12m"] = 100 * (np.log(frame["corporate"]) - np.log(frame["corporate"].shift(12)))
    frame["credit_growth_lead"] = frame["credit_growth_12m"].shift(-CREDIT_LEAD_MONTHS)
    return frame


def credit_constraint(frame: pd.DataFrame) -> dict[str, Any]:
    """МНК роста кредита через 6 мес. на реальную ставку; ноль роста → реальная ставка-ограничение."""
    data = frame.dropna(subset=["real_rate", "credit_growth_lead"])
    x, y = data["real_rate"].to_numpy(), data["credit_growth_lead"].to_numpy()
    slope, intercept = np.polyfit(x, y, 1)
    identified = slope < 0
    return {"n": int(len(data)), "first": str(data.index.min()), "last": str(data.index.max()),
            "slope": float(slope), "intercept": float(intercept),
            "credit_zero_real_rate": float(-intercept / slope) if identified else None,
            "identified": bool(identified),
            "note": ("описательное соотношение, не причинная оценка; ограничение используется" if identified else
                     "наклон не отрицательный: ограничение по кредиту не идентифицировано и не используется")}


def fx_regression(fx: pd.Series, differential: pd.Series) -> dict[str, Any]:
    """Изменение 100*log USD/KZT на лаг реального дифференциала: HC1, чувствительность спецификаций, VIF."""
    import statsmodels.api as sm
    from statsmodels.stats.outliers_influence import variance_inflation_factor

    data = pd.concat({"dfx": fx.diff(), "diff": differential.shift(1), "diff2": differential.shift(2)}, axis=1).dropna()
    if len(data) < 24:
        return {"status": f"UNKNOWN: мало наблюдений ({len(data)})"}
    specs = {"дифференциал t-1": ["diff"], "дифференциал t-1 и t-2": ["diff", "diff2"]}
    table = {}
    for label, columns in specs.items():
        design = sm.add_constant(data[columns])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = sm.OLS(data["dfx"], design).fit(cov_type="HC1")
        table[label] = {"n": int(fit.nobs), "coef": float(fit.params["diff"]), "se": float(fit.bse["diff"]),
                        "p": float(fit.pvalues["diff"]), "r2": float(fit.rsquared)}
    design = sm.add_constant(data[["diff", "diff2"]])
    vif = {c: float(variance_inflation_factor(design.to_numpy(), i)) for i, c in enumerate(design.columns) if c != "const"}
    rw_mae = float(np.mean(np.abs(data["dfx"])))  # случайное блуждание: прогноз изменения = 0
    main = table["дифференциал t-1"]
    return {"status": "ok", "specifications": table, "vif": vif, "random_walk_mae_of_change": rw_mae,
            "verdict": ("связь значима на 5% (HC1)" if main["p"] < 0.05 else "связи не видно (p ≥ 0.05, HC1)"),
            "ovb_compass": OVB_COMPASS}


OVB_COMPASS = [
    {"omitted": "цена нефти", "corr_with_differential": "+ (доходы → ставка выше)", "effect_on_kzt": "укрепление (USD/KZT ↓)",
     "bias": "коэффициент смещён вниз (к более отрицательному)"},
    {"omitted": "глобальный аппетит к риску", "corr_with_differential": "− (в стрессе премии и инфляция растут)",
     "effect_on_kzt": "в стрессе ослабление (USD/KZT ↑)", "bias": "знак смещения неоднозначен"},
    {"omitted": "курс рубля", "corr_with_differential": "неоднозначно", "effect_on_kzt": "ослабление рубля тянет тенге",
     "bias": "неоднозначно; проверяется добавлением USD/RUB, когда есть данные"},
]


def partner_real_rates(directory: Path = external_data.EXTERNAL_DIR) -> tuple[dict[str, float | None], dict[str, str]]:
    """Последние реальные ставки РФ и КНР из data/raw/external (средневзвешенная ставка − ИПЦ y/y)."""
    out, notes = {}, {}
    pairs = {"Россия": ("ru_key_rate", "ru_cpi_yoy", False), "Китай": ("cn_policy_rate", "cn_cpi_yoy", True)}
    for label, (rate_name, cpi_name, china) in pairs.items():
        rates, cpi = external_data.read_raw(rate_name, directory), external_data.read_raw(cpi_name, directory)
        if rates.empty or cpi.empty:
            out[label], notes[label] = None, "UNKNOWN: данных нет (шаблон)"
            continue
        monthly = external_data.monthly_step_rate(rates)
        yoy = external_data.cpi_yoy(cpi, cpi.columns[1], china=china)["yoy"]
        joined = pd.concat([monthly, yoy], axis=1, join="inner").dropna()
        if joined.empty:
            out[label], notes[label] = None, "UNKNOWN: ряды ставки и инфляции не пересекаются"
            continue
        out[label] = float(joined.iloc[-1, 0] - joined.iloc[-1, 1])
        notes[label] = f"месяц {joined.index[-1]}"
    return out, notes


def build() -> dict[str, Any]:
    frame = monthly_inputs()
    last = frame.dropna(subset=["rate", "inflation"]).iloc[-1]
    month = str(frame.dropna(subset=["rate", "inflation"]).index[-1])
    credit = credit_constraint(frame)
    partners, notes = partner_real_rates()
    current = corridor(float(last["rate"]), float(last["inflation"]), partners, DEFAULTS["premium"], DEFAULTS["cap"],
                       credit["credit_zero_real_rate"])
    sensitivity = [{"premium": p, **{k: current_k for k, current_k in corridor(
        float(last["rate"]), float(last["inflation"]), partners, p, DEFAULTS["cap"], credit["credit_zero_real_rate"]).items()
        if k in ("lower", "upper", "position")}} for p in (0.0, 1.0, 2.0, 3.0, 4.0)]
    fx_status = "UNKNOWN: нет данных USD/KZT и реальных ставок партнёров (TODO_HUMAN.md)"
    return {"month": month, "nbk_rate": float(last["rate"]), "kz_inflation": float(last["inflation"]),
            "kz_real_rate": float(last["rate"] - last["inflation"]), "partner_real_rates": partners,
            "partner_notes": notes, "defaults": DEFAULTS, "defaults_status": "допущение пользователя (параметры ползунков)",
            "credit_constraint": credit, "current": current, "premium_sensitivity": sensitivity,
            "fx_regression": {"status": fx_status} if None in partners.values() else {"status": "pending"},
            "panel_note": "Панель по трём странам с фиксированными эффектами — только иллюстрация: три единицы не дают "
                          "надёжных стандартных ошибок; строится, когда есть данные.",
            "benchmark": "курс как случайное блуждание (прогноз изменения = 0)"}


def main() -> int:
    block = build()
    from src.artifact_extensions import merge

    merge("carry_corridor", block)
    print(f"Corridor ({block['month']}): KZ real rate {block['kz_real_rate']:.2f}; partners {block['partner_notes']}; "
          f"credit constraint identified: {block['credit_constraint']['identified']}; status {block['current']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
