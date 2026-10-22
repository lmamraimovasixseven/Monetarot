from pathlib import Path

import numpy as np

from src import app
from src.advanced_diagnostics import (
    alternative_specifications,
    decision_growth,
    structural_break_diagnostics,
)


def test_decision_growth_uses_current_and_previous_only_and_keeps_first_missing():
    data = app.load_data()
    growth = decision_growth(data, "corporate_lending")
    ordered = data.sort_values("decision_date")
    assert np.isnan(growth.iloc[0])
    expected = (ordered.corporate_lending.iloc[1] / ordered.corporate_lending.iloc[0] - 1) * 100
    assert np.isclose(growth.iloc[1], expected)
    assert len(growth) == len(data)


def test_unknown_break_scan_is_reproducible_and_labels_exploratory_inference():
    data = app.load_data()
    first_candidates, first = structural_break_diagnostics(data, bootstrap_replicates=9)
    second_candidates, second = structural_break_diagnostics(data, bootstrap_replicates=9)
    assert first == second
    assert first_candidates.equals(second_candidates)
    assert len(first["tests"]) == 12
    assert all(item["status"].startswith("EXPLORATORY") for item in first["tests"])
    assert all("unknown break" in item["null_hypothesis"].lower() for item in first["tests"])
    expected_sources = ("loans_legal_entities_history.csv", "loans_individuals_history.csv")
    raw_dir = Path(__file__).resolve().parents[1] / "data" / "raw"
    assert first["raw_monthly_sources_present"] == {
        name: (raw_dir / name).is_file() for name in expected_sources
    }
    assert "raw monthly lending files are present" in first["sample"]


def test_alternative_specs_keep_fixed_chronological_periods_and_report_all_models():
    data = app.load_data()
    metrics, predictions = alternative_specifications(data)
    evaluated = metrics.loc[metrics.status == "EVALUATED"]
    assert set(evaluated.period_months) == {24, 36, 48}
    assert set(evaluated.specification) == {
        "Current six levels",
        "Log lending levels (diagnostic)",
        "Decision-interval lending growth (diagnostic)",
    }
    assert set(evaluated.model) == {"Hold benchmark", "Logistic Regression", "Random Forest"}
    assert not evaluated.train_test_overlap.any()
    for _, row in evaluated.iterrows():
        assert sum(row.confusion_matrix_actual_rows_predicted_columns[0]) >= 0
        assert sum(row.predicted_class_counts.values()) == row.test_n
        assert sum(row.actual_class_counts.values()) == row.test_n
    assert predictions

