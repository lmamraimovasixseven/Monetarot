"""Состояние данных «на дату t»: что было известно в момент t.

Старых винтажей (публикаций с датами) у проекта нет, поэтому доступность месяца M задаётся правилом
публикации: месяц M считается известным с первого дня месяца M + lag, где lag берётся из
config/release_lag.json (то же допущение, что и у модели: решение в месяце M использует данные за M − 2).
Значения — текущие (пересмотренные), поэтому любой бэктест на них помечается «revised-data backtest».
Функции только фильтруют; изменение данных после t не может изменить результат на t (тест в
tests/test_vintages.py).
"""

from __future__ import annotations

import pandas as pd

from src.ingest import ASSUMED_LAG_MONTHS

LABEL = "revised-data backtest (текущие значения; доступность по допущению о публикации, не по реальным винтажам)"


def known_at(month: pd.Period, lag_months: int = ASSUMED_LAG_MONTHS) -> pd.Timestamp:
    """Дата, с которой значение за месяц `month` считается известным."""
    return (month + lag_months).start_time


def as_of(series: pd.Series, t: pd.Timestamp | str, lag_months: int = ASSUMED_LAG_MONTHS) -> pd.Series:
    """Часть месячного ряда (индекс PeriodIndex), известная на дату t."""
    t = pd.Timestamp(t)
    index = pd.PeriodIndex(series.index, freq="M")
    mask = [known_at(month, lag_months) <= t for month in index]
    return series[mask]


def last_known_month(t: pd.Timestamp | str, lag_months: int = ASSUMED_LAG_MONTHS) -> pd.Period:
    t = pd.Timestamp(t)
    return t.to_period("M") - lag_months
