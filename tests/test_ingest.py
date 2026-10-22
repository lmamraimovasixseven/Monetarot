from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import ingest
from src.hashing import normalized_sha256


ROOT = Path(__file__).resolve().parents[1]


def test_read_monthly_series_parses_values_and_rejects_non_numeric(tmp_path):
    source = tmp_path / "series.csv"
    source.write_text("year_month,value\n2020-01,2\n2020-02,4\n", encoding="utf-8")
    result = ingest.read_monthly_series(source, "value")
    assert result.index.tolist() == [pd.Period("2020-01", freq="M"), pd.Period("2020-02", freq="M")]
    assert result.tolist() == [2.0, 4.0]
    source.write_text("year_month,value\n2020-01,not-a-number\n", encoding="utf-8")
    with pytest.raises(ValueError, match="non-numeric"):
        ingest.read_monthly_series(source, "value")


def test_complete_month_calendar_keeps_gaps_missing():
    series = pd.Series([10.0, 30.0], index=pd.PeriodIndex(["2020-01", "2020-03"], freq="M"), name="value")
    result = ingest.complete_month_calendar(series)
    assert result.index.astype(str).tolist() == ["2020-01", "2020-02", "2020-03"]
    assert pd.isna(result.loc[pd.Period("2020-02", freq="M")])


def test_growth_rate_is_month_over_month_and_does_not_bridge_gaps():
    series = pd.Series([10.0, 15.0, 30.0], index=pd.PeriodIndex(["2020-01", "2020-02", "2020-04"], freq="M"))
    result = ingest.growth_rate(series)
    assert pd.isna(result.loc[pd.Period("2020-01", freq="M")])
    assert result.loc[pd.Period("2020-02", freq="M")] == pytest.approx(50.0)
    assert pd.isna(result.loc[pd.Period("2020-03", freq="M")])
    assert pd.isna(result.loc[pd.Period("2020-04", freq="M")])


def test_log_level_only_logs_positive_values():
    source = pd.Series([1.0, np.e, 0.0, -1.0, np.nan], name="level")
    result = ingest.log_level(source)
    assert result.iloc[:2].tolist() == pytest.approx([0.0, 1.0])
    assert result.iloc[2:].isna().all()


def test_first_difference_uses_adjacent_calendar_months():
    source = pd.Series([2.0, 5.0, 11.0], index=pd.PeriodIndex(["2020-01", "2020-02", "2020-04"], freq="M"))
    result = ingest.first_difference(source)
    assert pd.isna(result.loc[pd.Period("2020-01", freq="M")])
    assert result.loc[pd.Period("2020-02", freq="M")] == pytest.approx(3.0)
    assert pd.isna(result.loc[pd.Period("2020-03", freq="M")])
    assert pd.isna(result.loc[pd.Period("2020-04", freq="M")])


def test_log_growth_12m_uses_calendar_year_and_does_not_fill_gaps():
    index = pd.period_range("2020-01", periods=18, freq="M")
    source = pd.Series(np.arange(1.0, 19.0), index=index, name="value")
    source.loc[pd.Period("2020-06", freq="M")] = np.nan
    result = ingest.log_growth_12m(source)
    assert result.loc[pd.Period("2021-01", freq="M")] == pytest.approx(100 * np.log(13 / 1))
    assert pd.isna(result.loc[pd.Period("2021-06", freq="M")])
    assert result.loc[pd.Period("2021-02", freq="M")] == pytest.approx(100 * np.log(14 / 2))


def test_apply_release_lag_uses_explicit_calendar_month_offset():
    source = pd.Series(
        [1.0, 2.0, 3.0],
        index=pd.PeriodIndex(["2020-01", "2020-02", "2020-03"], freq="M"),
        name="value",
    )
    dates = pd.Series(pd.to_datetime(["2020-03-15", "2020-04-15"]))
    assert ingest.apply_release_lag(source, dates, lag_months=2).tolist() == [1.0, 2.0]


def test_build_model_panel_uses_specified_transforms_and_excludes_rate_columns(tmp_path):
    output = tmp_path / "model_panel.csv"
    panel = ingest.build_model_panel(output_path=output)
    assert output.is_file()
    assert panel.columns.tolist() == [
        "decision_date", "decision", "y", "inflation", "exports", "imports",
        "corporate_lending", "household_lending", "consumption",
    ]
    assert len(panel) == 90
    assert set(panel["y"]) == {-1, 0, 1}
    assert not {"base_rate_before", "base_rate_after"}.intersection(panel.columns)
    rows = panel.dropna(subset=ingest.FEATURE_RULES.keys())
    assert len(rows) == 88
    first = rows.iloc[0]
    assert first["decision_date"] == "2016-03-15"
    raw = ingest.read_monthly_series(ROOT / "data/raw/export_history.csv", "exports_thousand_usd")
    expected = ingest.apply_release_lag(ingest.log_growth_12m(raw), pd.Series(pd.to_datetime([first["decision_date"]])))
    assert first["exports"] == pytest.approx(expected.iloc[0])


def test_align_to_decision_months_uses_decision_month_minus_two():
    series = pd.Series([3.0, 4.0, 5.0], index=pd.PeriodIndex(["2020-01", "2020-02", "2020-03"], freq="M"), name="value")
    dates = pd.Series(pd.to_datetime(["2020-03-02", "2020-04-20"]))
    assert ingest.align_to_decision_months(series, dates, lag_months=2).tolist() == [3.0, 4.0]


def test_build_base_rate_targets_uses_previous_decision_rate():
    rates = pd.Series([10.0, 11.0, 9.0], index=pd.PeriodIndex(["2020-01", "2020-02", "2020-03"], freq="M"), name="rate")
    dates = pd.Series(pd.to_datetime(["2020-02-02", "2020-03-02", "2020-03-20"]))
    result = ingest.build_base_rate_targets(rates, dates)
    assert result["base_rate_before"].tolist() == [10.0, 11.0, 9.0]
    assert result["base_rate_after"].tolist() == [11.0, 9.0, 9.0]
    assert result["decision"].tolist() == ["Increase", "Decrease", "Hold"]


def test_build_panel_uses_raw_levels_for_all_six_factors_and_writes_file(tmp_path):
    dates = pd.read_csv(ROOT / "config" / "nbk_decision_dates.csv", parse_dates=["decision_date"]).decision_date
    path = tmp_path / "panel.csv"
    panel = ingest.build_panel(decision_dates=dates, output_path=path)
    assert panel.columns.tolist() == ingest.OUTPUT_COLUMNS
    assert panel["decision_date"].iloc[0] == "2015-10-02"
    assert len(panel) == 90
    assert path.is_file()
    for feature, (filename, source_column) in ingest.FEATURE_RULES.items():
        source = ingest.read_monthly_series(ROOT / "data" / "raw" / filename, source_column)
        expected = ingest.align_to_decision_months(source, pd.to_datetime(dates), lag_months=2)
        if feature == "household_lending":
            expected = expected.round(8)
        np.testing.assert_allclose(panel[feature].to_numpy(), expected.to_numpy(), rtol=0, atol=0)


def test_compare_cells_reports_matches_and_differences():
    original = pd.DataFrame({"decision_date": pd.to_datetime(["2020-01-01"]), "x": [1.0], "decision": ["Hold"]})
    rebuilt = pd.DataFrame({"decision_date": pd.to_datetime(["2020-01-01"]), "x": [2.0], "decision": ["Hold"]})
    report, matches, differences = ingest.compare_cells(original, rebuilt)
    assert report.columns.tolist() == ["date", "column", "original", "rebuilt", "difference"]
    assert matches == 1
    assert differences == 1
    assert report.loc[report["column"] == "x", "difference"].iloc[0] == 1.0


def test_main_writes_panel_and_rebuild_report_without_modifying_raw(tmp_path, monkeypatch):
    raw_paths = sorted((ROOT / "data" / "raw").glob("*.csv"))
    raw_hashes = {path.name: normalized_sha256(path) for path in raw_paths}
    reference = tmp_path / "reference.csv"
    reference.write_bytes((ROOT / "data" / "processed" / "nbk_decisions_clean.csv").read_bytes())
    monkeypatch.setattr(ingest, "ROOT", tmp_path)
    monkeypatch.setattr(ingest, "RAW_DIR", ROOT / "data" / "raw")
    monkeypatch.setattr(ingest, "DECISION_DATES_PATH", ROOT / "config" / "nbk_decision_dates.csv")
    monkeypatch.setattr(ingest, "DECISIONS_PATH", tmp_path / "data" / "processed" / "nbk_decisions_clean.csv")
    monkeypatch.setattr(ingest, "CHECK_PATH", tmp_path / "outputs" / "rebuild_check.csv")
    monkeypatch.setenv("NBK_REBUILD_REFERENCE", str(reference))
    matching, differing = ingest.main()
    assert matching + differing == 90 * (len(ingest.OUTPUT_COLUMNS) - 1)
    assert ingest.DECISIONS_PATH.is_file()
    assert ingest.CHECK_PATH.is_file()
    assert not (tmp_path / "data" / "processed" / "rebuilt_candidate.csv").exists()
    assert pd.read_csv(ingest.CHECK_PATH).columns.tolist() == ["date", "column", "original", "rebuilt", "difference"]
    assert raw_hashes == {path.name: normalized_sha256(path) for path in raw_paths}
