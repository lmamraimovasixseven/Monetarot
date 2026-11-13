"""Блок B: обработка особенностей новых источников (на синтетических данных) и календарь вмешательств."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src import external_data as ed
from src import vintages

ROOT = Path(__file__).resolve().parents[1]


def test_rate_changed_mid_month_is_averaged_over_days():
    changes = pd.DataFrame({"date": ["2025-01-01", "2025-01-21"], "rate": [10.0, 12.0]})
    monthly = ed.monthly_step_rate(changes, until=pd.Timestamp("2025-02-28"))
    assert monthly[pd.Period("2025-01", "M")] == pytest.approx((20 * 10 + 11 * 12) / 31)
    assert monthly[pd.Period("2025-02", "M")] == pytest.approx(12.0)


def test_partially_covered_first_month_is_not_reported():
    changes = pd.DataFrame({"date": ["2025-01-15"], "rate": [10.0]})
    assert pd.Period("2025-01", "M") not in ed.monthly_step_rate(changes, until=pd.Timestamp("2025-02-28")).index


def test_fx_average_uses_published_days_only_and_counts_them():
    daily = pd.DataFrame({"date": ["2025-01-09", "2025-01-10", "2025-01-13"], "usd_kzt": [500.0, 510.0, 520.0]})
    out = ed.monthly_average(daily)
    assert out.loc[pd.Period("2025-01", "M"), "value"] == pytest.approx(510.0)
    assert out.loc[pd.Period("2025-01", "M"), "days"] == 3


def test_cpi_index_is_converted_and_lunar_new_year_months_are_flagged():
    frame = pd.DataFrame({"year_month": ["2025-01", "2025-02", "2025-03"], "cpi_yoy_pct": [100.5, 99.3, 0.1]})
    out = ed.cpi_yoy(frame, "cpi_yoy_pct", china=True)
    assert out["yoy"].round(6).tolist() == [0.5, -0.7, 0.1]
    assert out["lunar_new_year_month"].tolist() == [True, True, False]


def test_template_files_report_unknown_not_zero():
    for name, state in ed.status().items():
        frame = ed.read_raw(name)
        assert (state.startswith("UNKNOWN")) == frame.empty, name


def test_intervention_calendar_has_the_required_entries():
    calendar = pd.read_csv(ROOT / "config" / "intervention_calendar.csv")
    assert len(calendar) >= 3
    assert set(calendar["type"]) <= {"single", "level_shift", "temporary_episode", "seasonal_break"}
    vat = calendar[calendar["event"].str.contains("НДС")]
    assert len(vat) == 1 and vat["date"].iloc[0] == "2026-01-01" and "12%" in vat["event"].iloc[0] and "16%" in vat["event"].iloc[0]
    assert calendar["source"].notna().all()


def test_a_change_after_t_does_not_change_what_is_known_at_t():
    index = pd.period_range("2025-01", "2025-12", freq="M")
    series = pd.Series(range(12), index=index, dtype=float)
    t = pd.Timestamp("2025-09-15")
    before = vintages.as_of(series, t)
    changed = series.copy()
    changed[changed.index > vintages.last_known_month(t)] += 1000.0
    pd.testing.assert_series_equal(before, vintages.as_of(changed, t))
    assert before.index.max() == vintages.last_known_month(t)
