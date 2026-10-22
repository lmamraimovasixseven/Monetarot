"""Pure helpers for conditional forecasts at upcoming decision rounds."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd


ROUND_NAMES = (
    "Next NBK decision",
    "Second next NBK decision",
)


def chronological_training_rows(data: pd.DataFrame, months: int = 24) -> pd.DataFrame:
    """Match the existing backtest's pre-final-holdout training boundary."""
    cutoff = pd.to_datetime(data["decision_date"]).max() - pd.DateOffset(months=months)
    return data.loc[pd.to_datetime(data["decision_date"]) < cutoff].copy()


def fit_conditional_forecast_model(training_data: pd.DataFrame, features: list[str], model_factory, model_name: str):
    """Fit the existing model factory with allowed factors and historical labels."""
    if "decision" not in training_data:
        raise ValueError("Training rows must include historical decision labels.")
    forbidden = {"decision", "base_rate_before", "base_rate_after"}.intersection(features)
    if forbidden:
        raise ValueError(f"Target information cannot be passed as predictors: {sorted(forbidden)}")
    model = model_factory(model_name)
    model.fit(training_data[features], training_data["decision"])
    return model


def latest_observation_scenarios(data: pd.DataFrame, features: list[str]) -> tuple[pd.Timestamp, pd.DataFrame]:
    """Repeat the last observed feature vector for two frozen-factor scenarios.

    Missing observed values remain missing so the fitted sklearn Pipeline can
    apply its training-only imputer. This function never reads target columns.
    """
    if data.empty:
        raise ValueError("No historical observations are available for forecasting.")
    if not set(features).issubset(data.columns) or "decision_date" not in data.columns:
        raise ValueError("The dataset is missing the date or configured predictors.")
    ordered = data.sort_values("decision_date")
    latest = ordered.iloc[-1]
    as_of = pd.Timestamp(latest["decision_date"])
    latest_features = latest.loc[features]
    scenarios = pd.DataFrame([latest_features.to_dict(), latest_features.to_dict()], columns=features)
    scenarios.index = list(ROUND_NAMES)
    return as_of, scenarios


def load_future_round_schedule(
    config_path: str | Path,
    as_of_date: str | date | pd.Timestamp,
    today: date | None = None,
) -> list[dict]:
    """Return two configured future rounds, showing dates only when attested.

    The app cannot independently validate an external calendar. Dates become
    displayable only after the maintainer records a source and sets `verified`
    true in the project schedule file.
    """
    path = Path(config_path)
    config = {}
    if path.is_file():
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            config = {}
    raw_rounds = config.get("rounds", []) if isinstance(config, dict) else []
    source = config.get("source") if isinstance(config, dict) else None
    verified = config.get("verified") is True if isinstance(config, dict) else False
    reference_date = max(pd.Timestamp(as_of_date).date(), today or date.today())

    output = []
    for index, name in enumerate(ROUND_NAMES):
        entry = raw_rounds[index] if index < len(raw_rounds) and isinstance(raw_rounds[index], dict) else {}
        event_date = None
        status = "Meeting date not provided or verified."
        raw_date = entry.get("date")
        if raw_date and verified and isinstance(source, str) and source.strip():
            try:
                parsed = pd.Timestamp(raw_date).date()
            except (TypeError, ValueError):
                parsed = None
            if parsed is not None and parsed > reference_date:
                event_date = parsed
                status = f"Configured source: {source.strip()}"
            elif parsed is not None:
                status = "Configured date is not in the future relative to current date and data vintage."
            else:
                status = "Configured meeting date is invalid; date hidden."
        elif raw_date:
            status = "A date is present in the schedule but lacks a verified source; date hidden."
        output.append({"round": index + 1, "name": name, "date": event_date, "status": status})

    first, second = output
    if first["date"] is not None and second["date"] is not None and second["date"] <= first["date"]:
        second["date"] = None
        second["status"] = "Schedule order is invalid; second date hidden until corrected."
    return output
