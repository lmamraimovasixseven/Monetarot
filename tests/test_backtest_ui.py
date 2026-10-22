import ast
import json
from pathlib import Path
from urllib.error import URLError

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from src import app


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "src" / "app.py"


def test_app_is_read_only_and_renders_dashboard_sections_without_old_tabs():
    at = AppTest.from_file(str(APP_PATH)).run(timeout=30)
    assert not at.exception
    assert [item.label for item in at.tabs] == ["Overview", "Drivers and scenario", "Evidence", "Data and provenance"]
    assert len(at.title) == 1
    cards = [item.value for item in at.markdown if "forecast-card" in item.value]
    assert len(cards) == 2
    assert "2026" in cards[0] and "2026" in cards[1]
    assert all("probability-interval" in card and "95% CI" in card for card in cards)
    assert all("INCREASE</span>" not in card and "<strong>" not in card for card in cards)
    assert any("Both rounds use the latest available factor values" in item.value for item in at.caption)
    assert any("Model does not beat the Always Hold benchmark" in item.value for item in at.warning)
    assert any("Most likely at the next decision:" in item.value for item in at.caption)
    assert len(at.slider) == 1

    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"fit", "OLS"}
        for node in ast.walk(tree)
    )
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    imported_modules = [
        alias.name for node in imports for alias in node.names
    ] + [node.module or "" for node in imports if isinstance(node, ast.ImportFrom)]
    assert not any(name.startswith(("sklearn", "statsmodels", "src.forecasting")) for name in imported_modules)


def test_headline_score_uses_stored_parameters_and_scenario_slider_changes_score():
    artifact = app.load_artifact()
    latest = artifact["latest_feature_vector"]
    probabilities = app.ordered_probabilities(artifact, latest)
    expected_score = probabilities["Increase"] - probabilities["Decrease"]
    assert app.policy_pressure_score(probabilities) == pytest.approx(expected_score)
    assert sum(probabilities.values()) == pytest.approx(1.0)

    at = AppTest.from_file(str(APP_PATH)).run(timeout=30)
    first = next(item.value for item in at.metric if item.label == "Scenario policy pressure score")
    control = at.slider[0]
    changed = control.value + control.step
    if changed > control.max:
        changed = control.value - control.step
    at.slider[0].set_value(changed).run(timeout=30)
    second = next(item.value for item in at.metric if item.label == "Scenario policy pressure score")
    assert first != second


def test_cached_render_time_is_under_three_seconds():
    at = AppTest.from_file(str(APP_PATH)).run(timeout=30)
    caption = next(item.value for item in at.caption if item.value.startswith("Cached dashboard render time:"))
    seconds = float(caption.split(":", 1)[1].split()[0])
    assert seconds < 3.0


def test_probability_intervals_are_bounded_and_use_full_covariance():
    artifact = app.load_artifact()
    intervals = app.probability_delta_intervals(artifact, artifact["latest_feature_vector"])
    assert set(intervals) == {"Increase", "Hold", "Decrease"}
    assert all(0 <= low <= high <= 1 for low, high in intervals.values())
    assert app._probability_display(0.00001) == "0.0%"
    assert app._probability_display(0.99999) == "100.0%"


def test_refresh_status_reports_only_real_request_outcomes(monkeypatch):
    assert app._refresh_source("UNKNOWN") == (False, "No refresh source is configured.")

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            return b"calendar"

    monkeypatch.setattr(app, "urlopen", lambda *args, **kwargs: _Response())
    success, success_message = app._refresh_source("https://example.invalid/calendar")
    assert success is True
    assert "source responded" in success_message

    def failed_request(*args, **kwargs):
        raise URLError("offline")

    monkeypatch.setattr(app, "urlopen", failed_request)
    failed, failure_message = app._refresh_source("https://example.invalid/calendar")
    assert failed is False
    assert "request failed" in failure_message


def test_missing_artifact_has_plain_user_facing_error(tmp_path):
    with pytest.raises(app.DashboardDataError, match="Model artifact is missing"):
        app.load_artifact(str(tmp_path / "missing.json"))


def test_headline_has_no_embedded_model_result_literals():
    source = APP_PATH.read_text(encoding="utf-8")
    with (ROOT / "model" / "artifact.json").open(encoding="utf-8") as file:
        artifact = json.load(file)
    assert f"{artifact['sample']['usable_n']} observations" not in source
    assert str(artifact["benchmark_comparison"]["rmse_ratio_model_to_hold"]) not in source
    assert artifact["latest_prediction"]["date"] not in source


def test_evidence_tables_use_artifact_metrics_and_defined_log_score_display():
    artifact = app.load_artifact()
    table = app._holdout_comparison_frame(artifact)
    comparison = artifact["benchmark_comparison"]

    assert list(table.columns) == ["Model", "RMSE", "MAE", "Log score"]
    assert table["Model"].tolist() == [
        "Ordered logit",
        "Always Hold (pre-specified benchmark)",
        "Class-frequency comparator (secondary, added after the specification freeze)",
    ]
    assert table.iloc[0]["RMSE"] == f"{comparison['model']['rmse']:.3f}"
    assert table.iloc[0]["MAE"] == f"{comparison['model']['mae']:.3f}"
    assert table.iloc[0]["Log score"] == f"{comparison['model']['log_score']:.3f}"
    assert table.iloc[1]["Log score"] == "undefined"
    secondary = comparison["class_frequency_comparator_secondary"]
    assert table.iloc[2]["Log score"] == f"{secondary['log_score']:.3f}"

    at = AppTest.from_file(str(APP_PATH)).run(timeout=30)
    assert not at.exception
    assert any("Always Hold assigns probability zero" in item.value for item in at.caption)
    assert any("robustness results are mixed" in item.value for item in at.info)
    assert any(
        "Model does not beat the Always Hold benchmark on the holdout" in item.value
        for item in at.caption
    )
    assert any(
        "first-differences household and corporate 12-month log growth and inflation" in item.value
        and "Total specifications run: 10" in item.value
        for item in at.caption
    )


def test_evidence_diagnostics_falsification_and_robustness_are_readable_tables():
    artifact = app.load_artifact()
    diagnostics, not_applicable = app._diagnostic_frames(artifact)
    assert list(diagnostics.columns) == [
        "Test", "What it checks", "Statistic", "p-value (raw)",
        "p-value (Holm-adjusted where defined)", "Family", "Flag",
    ]
    assert "Joint slope LR" in diagnostics["Test"].tolist()
    assert any("Maximum VIF" in name for name in diagnostics["Test"])
    assert any("inflation (ADF)" in name for name in diagnostics["Test"])
    assert not_applicable["Test"].tolist() == [
        item["name"] for item in artifact["diagnostics"]["not_applicable_tests"]
    ]
    assert "not adjusted" in diagnostics.loc[diagnostics["Test"] == "Joint slope LR", "p-value (Holm-adjusted where defined)"].iloc[0]

    falsification = app._falsification_frame(artifact)
    assert falsification["Rule"].tolist() == [item["rule"] for item in artifact["falsification_verdicts"]]
    assert falsification["Verdict"].tolist() == [
        "Falsified" if item["verdict"] == "falsified" else "Not falsified"
        for item in artifact["falsification_verdicts"]
    ]

    robustness = app._robustness_frame(artifact)
    assert len(robustness) == len(artifact["robustness_checks"]["checks"])
    nonconverged = next(row for row in artifact["robustness_checks"]["checks"] if row["estimator_converged"] is False)
    displayed = robustness.loc[robustness["Check"].str.startswith(nonconverged["specification_id"]), "Converged"].iloc[0]
    assert displayed == "No — NOT CONVERGED"


def test_evidence_contains_no_raw_json_renderers_or_dict_writes():
    source = APP_PATH.read_text(encoding="utf-8")
    assert "st.json(" not in source
    assert not any(line.strip().startswith("st.write(") and "dict" in line for line in source.splitlines())


# ------------------------------------------------------- scenario control


def _scenario_values(at):
    score = next(m.value for m in at.metric if m.label == "Scenario policy pressure score")
    band = next(c.value for c in at.caption if c.value.startswith("95% delta-method band"))
    return score, band


def test_scenario_factor_selector_defaults_to_household_lending_and_uses_data_ranges():
    import pandas as pd

    panel = pd.read_csv(ROOT / "data" / "processed" / "model_panel.csv")
    at = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    assert not at.exception
    selector = next(box for box in at.selectbox if box.label == "Factor to change")
    assert selector.value == "household_lending" and list(selector.options) == [app.FEATURE_LABELS[f] for f in app.FEATURES]
    slider = at.slider[0]
    series = pd.to_numeric(panel["household_lending"], errors="coerce").dropna()
    assert slider.label == app.FEATURE_LABELS["household_lending"]
    assert (slider.min, slider.max) == pytest.approx((series.min(), series.max()))
    assert slider.step == pytest.approx((series.max() - series.min()) / 100)

    selector.set_value("inflation").run()
    assert not at.exception
    slider = at.slider[0]
    series = pd.to_numeric(panel["inflation"], errors="coerce").dropna()
    assert slider.label == app.FEATURE_LABELS["inflation"]
    assert (slider.min, slider.max) == pytest.approx((series.min(), series.max()))


def test_scenario_score_and_band_follow_the_stored_covariance():
    artifact = app.load_artifact()
    at = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    next(box for box in at.selectbox if box.label == "Factor to change").set_value("exports").run()
    slider = at.slider[0]
    slider.set_value(slider.max).run()
    features = dict(artifact["latest_feature_vector"])
    features["exports"] = slider.max
    score, low, high = app.score_and_delta_band(artifact, features)
    shown_score, shown_band = _scenario_values(at)
    assert shown_score == f"{score:+.3f}"
    assert shown_band == f"95% delta-method band: [{max(-1.0, low):+.3f}, {min(1.0, high):+.3f}]"

def test_limitations_show_the_rb09_household_note_from_the_artifact():
    artifact = app.load_artifact()
    note = app.rb09_household_note(artifact)
    assert "loses significance when its non-stationarity is removed" in note
    at = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    evidence = next(tab for tab in at.tabs if tab.label == "Evidence")
    assert note in [item.value for item in evidence.markdown]
    assert app.rb09_household_note({}).endswith("UNKNOWN (not in the model artifact).")