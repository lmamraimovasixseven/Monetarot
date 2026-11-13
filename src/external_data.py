"""Внешние ряды для коридора carry trade (Россия, Китай, курсы): загрузка и месячная агрегация.

Файлы лежат в data/raw/external/ (описание в config/external_sources.json). Пока владелец не добавил
значения, файл содержит только заголовок, и функции возвращают пустой ряд со статусом UNKNOWN.
Обрабатываемые особенности источников (по одной на каждый тип, см. docs/DATA.md):
* ставка меняется внутри месяца → месячное значение = средневзвешенное по календарным дням, ставка действует
  с даты изменения до следующей (последнее известное значение тянется только внутри покрытого периода);
* курсы публикуются по рабочим дням → среднее по дням, которые есть в файле; пропуски не заполняются;
* ИПЦ публикуется как индекс «тот же месяц прошлого года = 100» → y/y = индекс − 100, если значения > 50;
* в Китае январь и февраль смещаются Новым годом по лунному календарю → эти месяцы помечаются флагом.
Ничего не оценивает.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "external_sources.json"
EXTERNAL_DIR = ROOT / "data" / "raw" / "external"


def sources(path: Path = CONFIG_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))["series"]


def read_raw(name: str, directory: Path = EXTERNAL_DIR, config: dict | None = None) -> pd.DataFrame:
    spec = (config or sources())[name]
    frame = pd.read_csv(Path(directory) / spec["file"])
    if frame.columns.tolist() != spec["columns"]:
        raise ValueError(f"{spec['file']}: columns must be {spec['columns']}, got {frame.columns.tolist()}")
    value = spec["columns"][1]
    numeric = pd.to_numeric(frame[value], errors="coerce")
    if (frame[value].notna() & numeric.isna()).any():
        raise ValueError(f"{spec['file']}: non-numeric values in {value}")
    frame[value] = numeric
    return frame


def monthly_step_rate(changes: pd.DataFrame, date_column: str = "date", value_column: str | None = None,
                      until: pd.Timestamp | None = None) -> pd.Series:
    """Средневзвешенная по дням ставка за месяц из таблицы изменений (дата вступления, новое значение)."""
    if changes.empty:
        return pd.Series(dtype=float, name="rate")
    value_column = value_column or [c for c in changes.columns if c != date_column][0]
    table = changes.assign(**{date_column: pd.to_datetime(changes[date_column])}).sort_values(date_column)
    if table[date_column].duplicated().any():
        raise ValueError("duplicate change dates")
    start = table[date_column].iloc[0]
    end = until or (table[date_column].iloc[-1] + pd.offsets.MonthEnd(0))
    days = pd.date_range(start, end, freq="D")
    daily = table.set_index(date_column)[value_column].reindex(days).ffill()
    monthly = daily.groupby(daily.index.to_period("M")).mean()
    first = start.to_period("M")
    if start.day != 1:  # первый месяц покрыт не полностью: значение не публикуется как месячное
        monthly = monthly.drop(first)
    return monthly.rename("rate")


def monthly_average(daily: pd.DataFrame, date_column: str = "date", value_column: str | None = None) -> pd.DataFrame:
    """Среднее за месяц по опубликованным рабочим дням и число дней наблюдений (пропуски не заполняются)."""
    if daily.empty:
        return pd.DataFrame(columns=["value", "days"])
    value_column = value_column or [c for c in daily.columns if c != date_column][0]
    table = daily.assign(**{date_column: pd.to_datetime(daily[date_column])}).dropna(subset=[value_column])
    grouped = table.groupby(table[date_column].dt.to_period("M"))[value_column]
    return pd.DataFrame({"value": grouped.mean(), "days": grouped.size()})


def cpi_yoy(frame: pd.DataFrame, value_column: str, china: bool = False) -> pd.DataFrame:
    """y/y в процентах; индекс «тот же месяц прошлого года = 100» переводится вычитанием 100."""
    if frame.empty:
        return pd.DataFrame(columns=["yoy", "lunar_new_year_month"])
    months = pd.PeriodIndex(pd.to_datetime(frame["year_month"], format="%Y-%m"), freq="M")
    values = frame[value_column].to_numpy(dtype=float)
    yoy = np.where(values > 50, values - 100.0, values)
    out = pd.DataFrame({"yoy": yoy}, index=months)
    out["lunar_new_year_month"] = china & out.index.month.isin([1, 2])
    return out


def status() -> dict[str, str]:
    """По каждому внешнему ряду: «данные есть (N строк)» или «UNKNOWN: только шаблон»."""
    result = {}
    for name, spec in sources().items():
        frame = read_raw(name)
        result[name] = f"данные есть ({len(frame)} строк)" if len(frame) else "UNKNOWN: только шаблон (TODO_HUMAN.md)"
    return result
