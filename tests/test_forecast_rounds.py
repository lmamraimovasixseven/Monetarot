import json
from datetime import date

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src import app
from src.forecasting import (
    ROUND_NAMES,
    chronological_training_rows,
    fit_conditional_forecast_model,
    latest_observation_scenarios,
    load_future_round_schedule,
)


TODAY = date(2026, 10, 15)


def test_two_scenarios_use_latest_historical_feature_row_and_preserve_missing_values():
    data = app.load_data().sort_values("decision_date").copy()
    data.loc[data.index[-1], "household_lending"] = np.nan
    data["base_rate_before"] = 999
    data["base_rate_after"] = 999
    as_of, scenarios = latest_observation_scenarios(data, app.FEATURES)
    assert as_of == data.decision_date.max()
    assert scenarios.index.tolist() == list(ROUND_NAMES)
    assert scenarios.loc[ROUND_NAMES[0]].equals(scenarios.loc[ROUND_NAMES[1]])
    assert pd.isna(scenarios.loc[ROUND_NAMES[0], "household_lending"])
    assert "decision" not in scenarios.columns
    assert "base_rate_before" not in scenarios.columns
    assert "base_rate_after" not in scenarios.columns


def test_missing_schedule_and_unverified_dates_never_show_meeting_dates(tmp_path):
    as_of = pd.Timestamp("2026-09-07")
    absent = load_future_round_schedule(tmp_path / "absent.json", as_of, today=TODAY)
    assert len(absent) == 2
    assert all(item["date"] is None for item in absent)

    schedule_path = tmp_path / "unverified.json"
    schedule_path.write_text(json.dumps({
        "source": "unverified note",
        "verified": False,
        "rounds": [{"date": "2026-11-01"}, {"date": "2026-12-01"}],
    }), encoding="utf-8")
    unverified = load_future_round_schedule(schedule_path, as_of, today=TODAY)
    assert all(item["date"] is None for item in unverified)
    assert all("verified source" in item["status"] for item in unverified)


def test_only_confirmed_chronological_future_dates_are_displayable(tmp_path):
    schedule_path = tmp_path / "verified.json"
    schedule_path.write_text(json.dumps({
        "source": "NBK official calendar (maintainer-confirmed)",
        "verified": True,
        "rounds": [{"date": "2026-11-01"}, {"date": "2026-12-01"}],
    }), encoding="utf-8")
    rounds = load_future_round_schedule(schedule_path, "2026-09-07", today=TODAY)
    assert [row["date"] for row in rounds] == [date(2026, 11, 1), date(2026, 12, 1)]

    schedule_path.write_text(json.dumps({
        "source": "maintainer-confirmed source",
        "verified": True,
        "rounds": [{"date": "2026-12-01"}, {"date": "2026-11-01"}],
    }), encoding="utf-8")
    rounds = load_future_round_schedule(schedule_path, "2026-09-07", today=TODAY)
    assert rounds[0]["date"] == date(2026, 12, 1)
    assert rounds[1]["date"] is None
    assert "order is invalid" in rounds[1]["status"]


def test_serving_app_reads_the_next_schedule_date_and_has_no_estimator_path():
    app_test = AppTest.from_file(str(app.PROJECT_DIR / "src" / "app.py")).run(timeout=30)
    assert not app_test.exception
    assert len(app_test.slider) == 1
    assert [tab.label for tab in app_test.tabs] == ["Overview", "Drivers and scenario", "Evidence", "Data and provenance"]
    rounds, _, _ = app.load_next_decisions(today=TODAY)
    assert rounds == [date(2026, 10, 23), date(2026, 12, 4)]
    source = (app.PROJECT_DIR / "src" / "app.py").read_text(encoding="utf-8")
    assert "src.forecasting" not in source
    assert "sklearn" not in source
    assert ".fit(" not in source


def test_unknown_or_missing_calendar_never_invents_a_decision_date(tmp_path):
    absent, _, status = app.load_next_decisions(tmp_path / "absent.json", today=TODAY)
    assert absent == [None, None]
    assert "not configured" in status
    path = tmp_path / "unverified.json"
    path.write_text(json.dumps({"source": "UNKNOWN", "verified": False, "rounds": [{"date": "2026-10-23"}]}))
    value, _, status = app.load_next_decisions(path, today=TODAY)
    assert value == [None, None]
    assert "not marked as verified" in status


def test_artifact_score_matches_latest_stored_probability_order():
    artifact = app.load_artifact()
    probabilities = app.ordered_probabilities(artifact, artifact["latest_feature_vector"])
    assert app.policy_pressure_score(probabilities) == pytest.approx(
        artifact["latest_prediction"]["expected_score"], abs=1e-10
    )
