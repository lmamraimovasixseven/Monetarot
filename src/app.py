"""Read-only Streamlit dashboard for the stored NBK ordered-logit artifact."""

from __future__ import annotations

import json
import threading
import time
from datetime import date
from pathlib import Path
from statistics import NormalDist
from urllib.error import URLError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import streamlit as st


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_DIR / "data" / "processed" / "nbk_decisions_clean.csv"
MODEL_PANEL_PATH = PROJECT_DIR / "data" / "processed" / "model_panel.csv"
PROVENANCE_PATH = PROJECT_DIR / "data" / "processed" / "provenance.json"
PROVENANCE_COLUMNS = [
    ("series_file", "Series file"),
    ("publisher", "Publisher"),
    ("source_title", "Source title"),
    ("table_or_series_identifier", "Table or series identifier"),
    ("url_or_api_query", "URL or API query"),
    ("navigation_path", "Navigation path"),
    ("publication_date", "Publication date"),
    ("retrieval_date", "Retrieval date"),
    ("release_lag_days", "Release lag (days)"),
    ("revised_after_release", "Revised after release"),
    ("unit", "Unit"),
    ("notes", "Notes"),
]
TARGET_SERIES_FILE = "base_rate_history.csv"
SCENARIO_DEFAULT_FACTOR = "household_lending"
SIGNIFICANCE_LEVEL = 0.05  # the 5% level used for the Holm-adjusted slope tests
JOINT_TEST_LEVEL = 0.10  # falsification criterion 1 uses the joint LR test at 10%
# Static dedication requested by the team; not a result and not stored in any artifact or output.
DEDICATION = "ДИАС КУМАРБЕКОВ ЛУЧШИЙ ПРОФЕССОР"
ARTIFACT_PATH = PROJECT_DIR / "model" / "artifact.json"
ROUNDS_PATH = PROJECT_DIR / "config" / "forecast_rounds.json"
FEATURES = [
    "inflation",
    "exports",
    "imports",
    "corporate_lending",
    "household_lending",
    "consumption",
]
FEATURE_LABELS = {
    "inflation": "Inflation",
    "exports": "Exports",
    "imports": "Imports",
    "corporate_lending": "Corporate lending",
    "household_lending": "Household lending",
    "consumption": "Consumption",
}
CLASS_ORDER = ["Decrease", "Hold", "Increase"]
DISPLAY_CLASSES = ["Increase", "Hold", "Decrease"]
REFRESH_TIMEOUT_SECONDS = 2.0
REFRESH_STATE_KEY = "calendar_refresh"
SCORE_UNIT = "probability difference P(Increase) - P(Decrease), from −1 (cut certain) to +1 (hike certain)"


class DashboardDataError(ValueError):
    """A user-readable missing or invalid input message for the dashboard."""


def _file_version(path: Path) -> int:
    """Cache key part that changes when a file is replaced, so stale copies are never served."""
    return path.stat().st_mtime_ns


def load_artifact(path_string: str = str(ARTIFACT_PATH)) -> dict:
    """Load the fitted model artifact without importing or fitting an estimator."""
    path = Path(path_string)
    # Checked outside the cache so a renamed or deleted artifact is reported immediately.
    if not path.is_file():
        raise DashboardDataError(
            "Model artifact is missing. Expected model/artifact.json. "
            "Rebuild it with `python run.py model`, then reload this page."
        )
    return _read_artifact(path_string, _file_version(path))


@st.cache_data(show_spinner=False)
def _read_artifact(path_string: str, version: int) -> dict:
    path = Path(path_string)
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise DashboardDataError("Model artifact could not be read as valid JSON.") from None
    required = {"model", "sample", "benchmark_comparison", "latest_feature_vector", "latest_prediction"}
    if not required.issubset(result):
        raise DashboardDataError("Model artifact is incomplete; required model fields are missing.")
    return result


def load_data(path_string: str = str(DATA_PATH)) -> pd.DataFrame:
    """Load the processed historical decision panel for the history chart."""
    path = Path(path_string)
    if not path.is_file():
        raise DashboardDataError("Processed decision data is missing. Expected data/processed/nbk_decisions_clean.csv.")
    return _read_data(path_string, _file_version(path))


@st.cache_data(show_spinner=False)
def _read_data(path_string: str, version: int) -> pd.DataFrame:
    path = Path(path_string)
    try:
        frame = pd.read_csv(path)
    except (OSError, pd.errors.ParserError, UnicodeError):
        raise DashboardDataError("Processed decision data could not be read.") from None
    required = {"decision_date", "decision"}
    if not required.issubset(frame.columns):
        raise DashboardDataError("Processed decision data is missing date or decision columns.")
    frame["decision_date"] = pd.to_datetime(frame["decision_date"], errors="coerce")
    frame["decision"] = frame["decision"].astype("string").str.strip().str.title()
    frame = frame.dropna(subset=["decision_date", "decision"])
    frame = frame.sort_values("decision_date").drop_duplicates("decision_date", keep="last")
    frame = frame.loc[frame.decision.isin(CLASS_ORDER)].reset_index(drop=True)
    if frame.empty:
        raise DashboardDataError("No valid decision observations are available.")
    frame["ordinal_score"] = frame["decision"].map({"Decrease": -1, "Hold": 0, "Increase": 1})
    return frame


def load_model_panel(path_string: str = str(MODEL_PANEL_PATH)) -> pd.DataFrame:
    """Load processed factor rows used by the stored model for scenario bounds."""
    path = Path(path_string)
    if not path.is_file():
        raise DashboardDataError("Processed model data is missing. Expected data/processed/model_panel.csv.")
    return _read_model_panel(path_string, _file_version(path))


@st.cache_data(show_spinner=False)
def _read_model_panel(path_string: str, version: int) -> pd.DataFrame:
    path = Path(path_string)
    try:
        frame = pd.read_csv(path)
    except (OSError, pd.errors.ParserError, UnicodeError):
        raise DashboardDataError("Processed model data could not be read.") from None
    absent = [name for name in FEATURES if name not in frame.columns]
    if absent or "decision_date" not in frame.columns:
        raise DashboardDataError("Processed model data is missing required factor observations.")
    frame["decision_date"] = pd.to_datetime(frame["decision_date"], errors="coerce")
    return frame


def _parameter_vector(artifact: dict) -> tuple[list[str], np.ndarray, np.ndarray]:
    """Return named model parameters and their stored covariance matrix."""
    model = artifact["model"]
    names = list(model.get("covariance_names", []))
    parameters = model.get("parameters", {})
    if not names or any(name not in parameters for name in names):
        raise DashboardDataError("Model artifact has no complete parameter vector.")
    coefficients = np.asarray([parameters[name] for name in names], dtype=float)
    covariance = np.asarray(model.get("covariance_hc0", []), dtype=float)
    if covariance.shape != (len(names), len(names)):
        raise DashboardDataError("Model artifact covariance matrix is missing or has the wrong shape.")
    if not np.isfinite(coefficients).all() or not np.isfinite(covariance).all():
        raise DashboardDataError("Model artifact contains non-finite model parameters.")
    return names, coefficients, covariance


def ordered_probabilities(artifact: dict, features: dict[str, float]) -> dict[str, float]:
    """Calculate ordered-logit probabilities from stored slopes and cutpoints."""
    names, _, _ = _parameter_vector(artifact)
    params = artifact["model"]["parameters"]
    missing = [name for name in FEATURES if name not in features or pd.isna(features[name])]
    if missing:
        raise DashboardDataError("A required latest factor observation is missing.")
    eta = sum(float(params[name]) * float(features[name]) for name in FEATURES)
    cut_decrease_hold = float(params["cutpoint[Decrease|Hold]"])
    cut_hold_increase = float(params["cutpoint[Hold|Increase]"])

    def logistic(value: float) -> float:
        if value >= 0:
            return 1.0 / (1.0 + np.exp(-value))
        exp_value = np.exp(value)
        return exp_value / (1.0 + exp_value)

    p_decrease = logistic(cut_decrease_hold - eta)
    p_at_most_hold = logistic(cut_hold_increase - eta)
    probabilities = {
        "Decrease": float(p_decrease),
        "Hold": float(p_at_most_hold - p_decrease),
        "Increase": float(1.0 - p_at_most_hold),
    }
    if min(probabilities.values()) < -1e-10 or not np.isclose(sum(probabilities.values()), 1.0, atol=1e-10):
        raise DashboardDataError("Model artifact produced invalid class probabilities.")
    return probabilities


def policy_pressure_score(probabilities: dict[str, float]) -> float:
    """Return the expected ordinal pressure score, P(Increase) minus P(Decrease)."""
    return float(probabilities["Increase"] - probabilities["Decrease"])


def score_gradient(artifact: dict, features: dict[str, float]) -> tuple[float, np.ndarray]:
    """Return the score and its gradient with respect to the stored parameters (covariance order)."""
    names, _, _ = _parameter_vector(artifact)
    params = artifact["model"]["parameters"]
    score = policy_pressure_score(ordered_probabilities(artifact, features))
    eta = sum(float(params[name]) * float(features[name]) for name in FEATURES)
    c0 = float(params["cutpoint[Decrease|Hold]"])
    c1 = float(params["cutpoint[Hold|Increase]"])

    def logistic_density(value: float) -> float:
        probability = 1.0 / (1.0 + np.exp(-np.clip(value, -700, 700)))
        return float(probability * (1.0 - probability))

    f0 = logistic_density(c0 - eta)
    f1 = logistic_density(c1 - eta)
    derivative_eta = f0 + f1
    gradient_by_name = {name: derivative_eta * float(features[name]) for name in FEATURES}
    gradient_by_name["cutpoint[Decrease|Hold]"] = -f0
    gradient_by_name["cutpoint[Hold|Increase]"] = -f1
    return score, np.asarray([gradient_by_name[name] for name in names], dtype=float)


def score_and_delta_band(artifact: dict, features: dict[str, float]) -> tuple[float, float, float]:
    """Compute score and a 95% delta-method band from stored robust covariance."""
    _, _, covariance = _parameter_vector(artifact)
    score, gradient = score_gradient(artifact, features)
    variance = float(gradient @ covariance @ gradient.T)
    if not np.isfinite(variance) or variance < -1e-10:
        raise DashboardDataError("Stored covariance did not produce a valid scenario uncertainty band.")
    standard_error = float(np.sqrt(max(variance, 0.0)))
    critical = NormalDist().inv_cdf(0.975)
    return score, score - critical * standard_error, score + critical * standard_error


def probability_delta_intervals(artifact: dict, features: dict[str, float]) -> dict[str, tuple[float, float]]:
    """Calculate 95% delta-method intervals for each stored ordered-logit probability."""
    names, _, covariance = _parameter_vector(artifact)
    params = artifact["model"]["parameters"]
    probabilities = ordered_probabilities(artifact, features)
    eta = sum(float(params[name]) * float(features[name]) for name in FEATURES)
    c0 = float(params["cutpoint[Decrease|Hold]"])
    c1 = float(params["cutpoint[Hold|Increase]"])

    def density(value: float) -> float:
        probability = 1.0 / (1.0 + np.exp(-np.clip(value, -700, 700)))
        return float(probability * (1.0 - probability))

    f0, f1 = density(c0 - eta), density(c1 - eta)
    derivatives = {
        "Decrease": (-f0, f0, 0.0),
        "Hold": (f0 - f1, -f0, f1),
        "Increase": (f1, 0.0, -f1),
    }
    critical = NormalDist().inv_cdf(0.975)
    intervals = {}
    for label, (d_eta, d_c0, d_c1) in derivatives.items():
        gradient_by_name = {feature: d_eta * float(features[feature]) for feature in FEATURES}
        gradient_by_name["cutpoint[Decrease|Hold]"] = d_c0
        gradient_by_name["cutpoint[Hold|Increase]"] = d_c1
        gradient = np.asarray([gradient_by_name[name] for name in names], dtype=float)
        variance = float(gradient @ covariance @ gradient.T)
        if not np.isfinite(variance) or variance < -1e-10:
            raise DashboardDataError("Stored covariance did not produce valid probability intervals.")
        standard_error = float(np.sqrt(max(variance, 0.0)))
        value = probabilities[label]
        intervals[label] = (
            max(0.0, value - critical * standard_error),
            min(1.0, value + critical * standard_error),
        )
    return intervals


def load_next_decisions(path: Path = ROUNDS_PATH, today: date | None = None) -> tuple[list[date | None], str, str]:
    """Read up to two confirmed future meetings from the maintained calendar."""
    if not path.is_file():
        return [None, None], "UNKNOWN", "Decision calendar is not configured."
    try:
        schedule = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [None, None], "UNKNOWN", "Decision calendar could not be read."
    source = str(schedule.get("source") or "UNKNOWN")
    if schedule.get("verified") is not True:
        return [None, None], source, "Decision dates are not marked as verified in the calendar."
    today = today or date.today()
    candidates = []
    for item in schedule.get("rounds", []):
        try:
            round_date = date.fromisoformat(str(item["date"]))
        except (KeyError, TypeError, ValueError):
            continue
        if round_date > today:
            candidates.append(round_date)
    candidates = sorted(set(candidates))[:2]
    message = "" if len(candidates) == 2 else "Fewer than two confirmed future decision dates are available."
    return candidates + [None] * (2 - len(candidates)), source, message


def _score_for_vector(artifact: dict, values: dict[str, float]) -> float:
    return policy_pressure_score(ordered_probabilities(artifact, values))


def _latest_and_previous_features(artifact: dict) -> tuple[dict[str, float], dict[str, float]]:
    latest = artifact.get("latest_feature_vector", {})
    contribution_rows = artifact.get("contributions") or artifact.get("per_factor_contribution_to_latest_score_change")
    if not isinstance(contribution_rows, list):
        raise DashboardDataError("Model artifact has no factor contribution rows.")
    previous = {row.get("feature"): row.get("previous_usable_decision_value") for row in contribution_rows}
    if any(feature not in latest or feature not in previous for feature in FEATURES):
        raise DashboardDataError("A latest or previous factor observation is missing from the model artifact.")
    return (
        {feature: float(latest[feature]) for feature in FEATURES},
        {feature: float(previous[feature]) for feature in FEATURES},
    )


def previous_usable_decision_date(model_panel: pd.DataFrame, latest_date: pd.Timestamp) -> str:
    """Date of the last decision before ``latest_date`` with all six factors observed."""
    usable = model_panel.dropna(subset=FEATURES)
    earlier = usable.loc[usable["decision_date"] < latest_date, "decision_date"]
    return earlier.max().date().isoformat() if not earlier.empty else "UNKNOWN"


def _probability_display(value: float) -> str:
    """Always show probabilities with one decimal place, including boundary values."""
    return f"{value * 100:.1f}%"


def forecast_card_html(round_number: int, round_date: date | None, probabilities: dict[str, float],
                       intervals: dict[str, tuple[float, float]], as_of_date: str,
                       most_likely: str) -> str:
    """Render one rounded financial-terminal forecast card from artifact outputs."""
    palette = {"Increase": "increase", "Hold": "hold", "Decrease": "decrease"}
    date_display = (
        f"{round_date.strftime('%A').upper()}, {round_date.day} {round_date.strftime('%B %Y').upper()}"
        if round_date is not None else "DATE NOT CONFIRMED"
    )
    rows = []
    for label in DISPLAY_CLASSES:
        value = float(probabilities[label])
        low, high = intervals[label]
        rows.append(
            "<div class='probability-row {highlight}'>"
            "<span class='probability-label'>{label}</span>"
            "<span class='probability-track'><span class='probability-fill {tone}' style='width:{width:.1f}%'></span></span>"
            "<span class='probability-value'>{value}</span>"
            "<span class='probability-interval'>95% CI {low}–{high}</span></div>".format(
                highlight="is-top" if label == most_likely else "",
                label=label,
                tone=palette[label],
                width=max(0.0, min(100.0, value * 100.0)),
                value=_probability_display(value),
                low=_probability_display(low),
                high=_probability_display(high),
            )
        )
    return f"""
    <style>
    .forecast-card {{ background:#fff; border:1px solid #d9e0e8; border-radius:14px;
      padding:24px 26px; min-height:360px; box-shadow:0 3px 12px rgba(31,47,70,.045); }}
    .forecast-card-head {{ color:#667386; font-size:.76rem; font-weight:700; letter-spacing:.11em; }}
    .forecast-date {{ margin:18px 0 23px; color:#172b4d; font-size:1.38rem; line-height:1.3;
      font-weight:750; letter-spacing:.035em; }}
    .probability-row {{ display:grid; grid-template-columns:88px minmax(70px,1fr) 54px; gap:10px;
      align-items:center; padding:7px 8px; border-radius:7px; margin:2px 0; }}
    .probability-row.is-top {{ background:#f0f5fa; }}
    .probability-label {{ color:#35445a; font-size:.88rem; font-weight:600; }}
    .probability-track {{ display:block; height:8px; overflow:hidden; background:#e9edf2; border-radius:99px; }}
    .probability-fill {{ display:block; height:100%; border-radius:99px; }}
    .probability-fill.increase {{ background:#16855f; }} .probability-fill.hold {{ background:#3979ae; }}
    .probability-fill.decrease {{ background:#c65a50; }}
    .probability-value {{ text-align:right; color:#24364c; font-size:.86rem; font-variant-numeric:tabular-nums; font-weight:700; }}
    .probability-interval {{ grid-column:2 / 4; color:#6c7888; text-align:right; font-size:.72rem; font-variant-numeric:tabular-nums; }}
    .forecast-card-foot {{ border-top:1px solid #edf0f3; margin-top:21px; padding-top:12px; color:#6c7888; font-size:.76rem; }}
    </style>
    <section class="forecast-card">
      <div class="forecast-card-head">ROUND {round_number} &nbsp;·&nbsp; {'NEXT DECISION' if round_number == 1 else 'SECOND NEXT DECISION'}</div>
      <h3 class="forecast-date">{date_display}</h3>
      {''.join(rows)}
      <div class="forecast-card-foot">Latest factor data as of {as_of_date}. Conditional model estimates; calibration is unverified.</div>
    </section>
    """


def load_provenance(path_string: str = str(PROVENANCE_PATH)) -> dict:
    """Read the generated provenance facts; a missing or unreadable file means every fact is UNKNOWN."""
    path = Path(path_string)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _target_publisher(provenance: dict) -> str:
    row = next((item for item in provenance.get("series", []) if item.get("series_file") == TARGET_SERIES_FILE), {})
    return _fact(row.get("publisher"))


def _render_history(frame: pd.DataFrame, provenance: dict) -> None:
    st.subheader("History")
    chart = frame[["decision_date", "ordinal_score"]].rename(columns={
        "decision_date": "Decision date",
        "ordinal_score": "Ordinal decision score",
    })
    st.vega_lite_chart(
        chart,
        {
            "mark": {"type": "line", "interpolate": "step-after", "point": False},
            "encoding": {
                "x": {"field": "Decision date", "type": "temporal", "title": "NBK decision date"},
                "y": {
                    "field": "Ordinal decision score",
                    "type": "quantitative",
                    "title": "Decision direction score",
                    "scale": {"domain": [-1, 1]},
                    "axis": {"values": [-1, 0, 1], "labelExpr": "datum.value === -1 ? 'Decrease (-1)' : datum.value === 0 ? 'Hold (0)' : 'Increase (+1)'"},
                },
                "tooltip": [
                    {"field": "Decision date", "type": "temporal"},
                    {"field": "Ordinal decision score", "type": "quantitative"},
                ],
            },
            "height": 250,
        },
        width="stretch",
    )
    st.caption(f"Source: NBK base-rate decisions in data/processed/nbk_decisions_clean.csv, built from "
               f"data/raw/{TARGET_SERIES_FILE}. Original publisher: {_target_publisher(provenance)}.")


def _render_drivers(artifact: dict) -> None:
    st.subheader("Latest score-change contributions")
    rows = artifact.get("contributions") or artifact.get("per_factor_contribution_to_latest_score_change")
    if not isinstance(rows, list):
        st.info("Factor contribution results are not present in the model artifact.")
        return
    panel = pd.DataFrame([
        {
            "Factor": FEATURE_LABELS.get(item.get("feature"), item.get("feature", "UNKNOWN")),
            "Contribution to score change": float(item["expected_score_contribution_to_latest_change"]),
            "Sign": "Positive" if float(item["expected_score_contribution_to_latest_change"]) > 0 else (
                "Negative" if float(item["expected_score_contribution_to_latest_change"]) < 0 else "Zero"
            ),
        }
        for item in rows
        if item.get("feature") in FEATURES and item.get("expected_score_contribution_to_latest_change") is not None
    ])
    if panel.empty:
        st.info("Factor contribution results are not present in the model artifact.")
        return
    top = panel.reindex(panel["Contribution to score change"].abs().sort_values(ascending=False).index).head(3)
    st.caption("Top three drivers by absolute contribution")
    for rank, (column, (_, row)) in enumerate(zip(st.columns(3), top.iterrows()), start=1):
        column.metric(f"Driver {rank}: {row['Factor']}", f"{row['Contribution to score change']:+.4f}")
    st.bar_chart(panel.set_index("Factor")[["Contribution to score change"]], horizontal=True)
    st.dataframe(panel.style.format({"Contribution to score change": lambda value: f"{value:+.4f}"}), hide_index=True, width="stretch")
    st.caption("Contributions come from the model artifact; the stored method notes that they are not additive.")


def _fact(value: object) -> str:
    """Show a provenance fact as recorded, or the word UNKNOWN."""
    text = "" if value is None else str(value).strip()
    return text if text else "UNKNOWN"


def provenance_table(provenance: dict) -> pd.DataFrame:
    """One row per raw series with every provenance field, or UNKNOWN where the form has no fact."""
    series = provenance.get("series") or [{}]
    return pd.DataFrame([{label: _fact(row.get(column)) for column, label in PROVENANCE_COLUMNS} for row in series],
                        columns=[label for _, label in PROVENANCE_COLUMNS])


def _render_provenance(artifact: dict, schedule_source: str, provenance: dict) -> None:
    st.subheader("Data and provenance")
    if not provenance:
        st.info("Provenance facts are missing (data/processed/provenance.json). Run `python run.py facts`; "
                "until then every source field is UNKNOWN.")
    st.dataframe(provenance_table(provenance), hide_index=True, width="stretch")
    st.caption("Source fields come from docs/facts_to_fill.csv via `python run.py facts`. "
               "Release lag = days from the end of the reference month to publication.")
    sample = artifact["sample"]
    project = provenance.get("project", {})
    values = [
        ("Assumed release lag (months before the decision month)", _fact(provenance.get("assumed_release_lag_months"))),
        ("Named user", _fact(project.get("named_user"))),
        ("Decision calendar source", schedule_source),
        ("Sample window", f"{sample.get('usable_start', 'UNKNOWN')} to {sample.get('usable_end', 'UNKNOWN')}"),
        ("Estimation timestamp (UTC)", artifact.get("estimation_timestamp_utc", "UNKNOWN")),
        ("Input data SHA-256 (normalized line endings)", artifact.get("data_sha256_normalized_crlf_to_lf", "UNKNOWN")),
        ("Random seed", artifact.get("seed", "UNKNOWN")),
    ]
    st.dataframe(pd.DataFrame([
        {"Field": str(field), "Value": str(value)} for field, value in values
    ]), hide_index=True, width="stretch")
    units = artifact.get("units", {})
    features = artifact.get("latest_feature_vector", {})
    st.dataframe(pd.DataFrame([
        {"Factor": FEATURE_LABELS.get(feature, feature), "Latest value": features.get(feature), "Model input unit": units.get(feature, "UNKNOWN")}
        for feature in FEATURES
    ]), hide_index=True, width="stretch")


def _refresh_source(source: str, timeout: float = REFRESH_TIMEOUT_SECONDS) -> tuple[bool, str]:
    """Make a real, bounded GET request to the configured calendar source."""
    if not source.startswith(("https://", "http://")):
        return False, "No refresh source is configured."
    try:
        request = Request(source, headers={"User-Agent": "NBK forecast dashboard"})
        with urlopen(request, timeout=timeout) as response:
            response.read(512)
        return True, "Calendar source responded; the serving app still uses its local processed data and fitted artifact."
    except (URLError, TimeoutError, OSError):
        return False, "The configured calendar refresh request failed."


def start_refresh(source: str) -> dict:
    """Run the calendar check on a daemon thread so it never blocks rendering."""
    state = {"source": source, "started": time.monotonic(), "result": None, "elapsed": None}

    def worker() -> None:
        started = time.monotonic()
        result = _refresh_source(source)
        state["elapsed"] = time.monotonic() - started
        state["result"] = result

    threading.Thread(target=worker, name="calendar-refresh", daemon=True).start()
    return state


def refresh_status(state: dict, now: float | None = None) -> tuple[str, str]:
    """Return ("ok" | "failed" | "pending", message); anything over the time limit has failed."""
    now = time.monotonic() if now is None else now
    timed_out = f"The calendar refresh request did not finish within {REFRESH_TIMEOUT_SECONDS:g} seconds."
    result = state.get("result")
    if result is not None:
        if state.get("elapsed") is not None and state["elapsed"] > REFRESH_TIMEOUT_SECONDS:
            return "failed", timed_out
        return ("ok" if result[0] else "failed"), result[1]
    if now - state["started"] >= REFRESH_TIMEOUT_SECONDS:
        return "failed", timed_out
    return "pending", "Calendar refresh check is in progress."


def _render_refresh_status(source: str, cached_as_of: str) -> None:
    """Show the CACHED label unless this session's calendar check has succeeded."""
    state = st.session_state.get(REFRESH_STATE_KEY)
    if state is None or state.get("source") != source:
        state = start_refresh(source)
        st.session_state[REFRESH_STATE_KEY] = state
    initial_status, _ = refresh_status(state)

    # While the check is pending the block polls itself, then reruns the page once
    # it settles so the polling stops.
    @st.fragment(run_every=0.5 if initial_status == "pending" else None)
    def status_block() -> None:
        status, message = refresh_status(state)
        if initial_status == "pending" and status != "pending":
            st.rerun()
        if status == "ok":
            st.caption(f"Local factor data and model artifact as of {cached_as_of}. {message}")
        else:
            st.warning(f"CACHED DATA, as of {cached_as_of}. {message}")

    status_block()


def _metric_text(value: object) -> str:
    """Format a stored metric without exposing non-finite JSON sentinels."""
    if value is None:
        return "not reported"
    if isinstance(value, str):
        if value.lower() in {"+infinity", "infinity", "inf", "nan"}:
            return "undefined"
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "not reported"
    return f"{number:.3f}" if np.isfinite(number) else "undefined"


def _holdout_comparison_frame(artifact: dict) -> pd.DataFrame:
    """Build the requested holdout comparison using artifact values only."""
    comparison = artifact.get("benchmark_comparison", {})
    rows = [
        ("Ordered logit", comparison.get("model", {})),
        ("Always Hold (pre-specified benchmark)", comparison.get("benchmark_always_hold", {})),
        ("Class-frequency comparator (secondary, added after the specification freeze)",
         comparison.get("class_frequency_comparator_secondary", {})),
    ]
    return pd.DataFrame([
        {
            "Model": label,
            "RMSE": _metric_text(values.get("rmse")),
            "MAE": _metric_text(values.get("mae")),
            "Log score": "undefined" if label.startswith("Always Hold") else _metric_text(values.get("log_score")),
        }
        for label, values in rows
    ])


def _falsification_frame(artifact: dict) -> pd.DataFrame:
    """Convert stored falsification rules and verdicts to a readable table."""
    rows = []
    for item in artifact.get("falsification_verdicts", []):
        statistic = item.get("statistic")
        if isinstance(statistic, dict):
            statistic = "; ".join(f"{name}: p={_metric_text(value)}" for name, value in statistic.items())
        rows.append({
            "Rule": item.get("rule", "UNKNOWN"),
            "Statistic": _metric_text(statistic),
            "Threshold": item.get("threshold", "UNKNOWN"),
            "Verdict": "Falsified" if str(item.get("verdict", "")).lower() == "falsified" else "Not falsified",
        })
    return pd.DataFrame(rows, columns=["Rule", "Statistic", "Threshold", "Verdict"])


def _diagnostic_frames(artifact: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build compact diagnostic and not-applicable tables from the artifact."""
    diagnostics = artifact.get("diagnostics", {})
    rows = []

    def add_row(test: str, explanation: str, statistic: object, raw_p: object,
                adjusted_p: object, family: object, flag: object) -> None:
        family_text = str(family or "UNKNOWN")
        adjusted_display = "not adjusted" if "no adjustment" in family_text or "no adjustment" in family_text.lower() else adjusted_p
        rows.append({
            "Test": test,
            "What it checks": explanation,
            "Statistic": _metric_text(statistic),
            "p-value (raw)": _metric_text(raw_p),
            "p-value (Holm-adjusted where defined)": _metric_text(adjusted_display),
            "Family": family_text,
            "Flag": _flag_text(flag),
        })

    joint = diagnostics.get("joint_slope_lr", {})
    add_row("Joint slope LR", "Tests whether the six slope coefficients are jointly zero.",
            joint.get("statistic"), joint.get("p_value"), joint.get("p_value_adjusted"),
            joint.get("p_value_family"), joint.get("pass_fail"))

    for key, explanation in (
        ("parameter_stability", "Tests whether slope coefficients are equal across the stored time regimes."),
        ("proportional_odds", "Tests whether cumulative-logit slopes satisfy the proportional-odds assumption."),
        ("serial_correlation", "Tests for serial correlation in standardized Pearson score residuals."),
    ):
        item = diagnostics.get(key, {})
        add_row(item.get("name", key.replace("_", " ").title()), explanation,
                item.get("statistic"), item.get("p_value"), item.get("p_value_adjusted"),
                item.get("p_value_family"), item.get("pass_fail"))

    vif = diagnostics.get("vif", [])
    if vif:
        maximum = max(vif, key=lambda item: float(item.get("statistic", float("-inf"))))
        add_row(f"Maximum VIF ({maximum.get('feature', 'UNKNOWN')})",
                "Reports the largest variance inflation factor across the six predictors.",
                maximum.get("statistic"), "not applicable", "not applicable",
                "Descriptive VIF; no p-value family", maximum.get("pass_fail"))

    unit_tests = [item for item in diagnostics.get("unit_root_tests", [])
                  if item.get("form") == "transformed_model_input"]
    for item in unit_tests:
        test = str(item.get("test", "UNKNOWN")).upper()
        null_note = "Tests the unit-root null; rejection supports stationarity." if test == "ADF" else (
            "Tests the stationarity null; non-rejection supports stationarity."
        )
        add_row(f"Unit root — {item.get('feature', 'UNKNOWN')} ({test})", null_note,
                item.get("statistic"), item.get("p_value"), item.get("p_value_adjusted"),
                item.get("p_value_family"), item.get("pass_fail"))

    diagnostic_table = pd.DataFrame(rows, columns=[
        "Test", "What it checks", "Statistic", "p-value (raw)",
        "p-value (Holm-adjusted where defined)", "Family", "Flag",
    ])
    na_rows = [{
        "Test": item.get("name", "UNKNOWN"),
        "Reason": item.get("reason", "Reason not recorded in the artifact."),
    } for item in diagnostics.get("not_applicable_tests", [])]
    return diagnostic_table, pd.DataFrame(na_rows, columns=["Test", "Reason"])


def _flag_text(value: object) -> str:
    """Normalize stored diagnostic flags for display."""
    normalized = str(value or "UNKNOWN").strip().upper()
    return {"PASS": "Pass", "FAIL": "Fail", "NOT APPLICABLE": "Not applicable"}.get(normalized, str(value or "UNKNOWN"))


def _robustness_frame(artifact: dict) -> pd.DataFrame:
    """Build the robustness table without recalculating any estimates."""
    checks = artifact.get("robustness_checks", {}).get("checks", [])
    rows = []
    for item in checks:
        converged = item.get("estimator_converged")
        rows.append({
            "Check": f"{item.get('specification_id', 'UNKNOWN')} — {item.get('name', 'UNKNOWN')}",
            "Usable n": item.get("n_usable", "UNKNOWN"),
            "RMSE ratio vs Always Hold": _metric_text(item.get("rmse_ratio_model_to_hold")),
            "Factor signs match the main model": "Yes" if item.get("same_signs_as_primary") is True else "No" if item.get("same_signs_as_primary") is False else "UNKNOWN",
            "Survives": str(item.get("survives", "UNKNOWN")),
            "Converged": "Yes" if converged is True else "No — NOT CONVERGED" if converged is False else "UNKNOWN",
        })
    return pd.DataFrame(rows, columns=[
        "Check", "Usable n", "RMSE ratio vs Always Hold", "Factor signs match the main model",
        "Survives", "Converged",
    ])


def _render_artifact_tables(artifact: dict) -> None:
    """Render full stored results as tables, never as raw JSON."""
    st.dataframe(_holdout_comparison_frame(artifact), hide_index=True, width="stretch")
    st.dataframe(_falsification_frame(artifact), hide_index=True, width="stretch")
    diagnostic_table, not_applicable = _diagnostic_frames(artifact)
    st.dataframe(diagnostic_table, hide_index=True, width="stretch")
    if not not_applicable.empty:
        st.dataframe(not_applicable, hide_index=True, width="stretch")
    robustness = _robustness_frame(artifact)
    if not robustness.empty:
        st.dataframe(robustness, hide_index=True, width="stretch")
        coefficient_detail = [
            {"Specification": check.get("specification_id", "UNKNOWN"), **coefficient}
            for check in artifact.get("robustness_checks", {}).get("checks", [])
            for coefficient in check.get("coefficients", [])
        ]
        if coefficient_detail:
            st.dataframe(pd.DataFrame(coefficient_detail), hide_index=True, width="stretch")
    model = artifact.get("model", {})
    coefficient_rows = model.get("coefficients", model.get("coefficient_table", []))
    if isinstance(coefficient_rows, list) and coefficient_rows:
        st.dataframe(pd.DataFrame(coefficient_rows), hide_index=True, width="stretch")
    elif isinstance(model.get("parameters"), dict):
        st.dataframe(pd.DataFrame([
            {"Parameter": name, "Estimate": estimate}
            for name, estimate in model["parameters"].items()
        ]), hide_index=True, width="stretch")
    names = model.get("covariance_names", [])
    covariance = model.get("covariance_hc0")
    if names and covariance:
        st.dataframe(pd.DataFrame(covariance, index=names, columns=names), width="stretch")
    expanding = artifact.get("diagnostics", {}).get("expanding_window_coefficients", [])
    if expanding:
        st.dataframe(pd.DataFrame(expanding), hide_index=True, width="stretch")
    for title, key in (
        ("All unit-root checks", "unit_root_tests"),
        ("Structural-break checks", "structural_break_checks"),
        ("Economic-size results", "economic_size_plus_one_sd"),
    ):
        detail = artifact.get("diagnostics", {}).get(key)
        if detail:
            st.subheader(title)
            st.dataframe(pd.DataFrame(detail), hide_index=True, width="stretch")
    economic_size = artifact.get("economic_size_plus_one_sd")
    if economic_size:
        st.subheader("Economic size from artifact")
        st.dataframe(pd.json_normalize(economic_size, sep="."), hide_index=True, width="stretch")


def rb09_household_note(artifact: dict) -> str:
    """Household lending in robustness check RB09, read from the artifact (no value is typed here)."""
    checks = artifact.get("robustness_checks", {}).get("checks", [])
    rb09 = next((check for check in checks if check.get("specification_id") == "RB09"), None)
    main = artifact.get("model", {}).get("coefficient_table", {}).get("household_lending", {})
    coefficient = next((row for row in (rb09 or {}).get("coefficients", []) if row.get("name") == "household_lending"), None)
    if not rb09 or not coefficient or not isinstance(main.get("p_value_holm"), (int, float)):
        return "Household lending in the differenced-factor check (RB09): UNKNOWN (not in the model artifact)."
    lost = main["p_value_holm"] < SIGNIFICANCE_LEVEL <= coefficient["p_value_adjusted"]
    text = (f"In RB09 ({rb09.get('name', 'UNKNOWN')}), household lending has coefficient {coefficient['estimate']:.4f} "
            f"(raw p {coefficient['p_value']:.3f}, Holm p {coefficient['p_value_adjusted']:.3f}), against Holm p "
            f"{main['p_value_holm']:.3f} in the main model")
    return text + ("; the only significant factor loses significance when its non-stationarity is removed."
                   if lost else ".")


def direction_flag_state(band_low: float, band_high: float, provenance: dict) -> str:
    """State of decision-rule option 1 (direction flag) for the latest score's 95% band."""
    rule = provenance.get("decision_rule")
    if not rule:
        return "Direction flag: UNKNOWN (no decision rule recorded in docs/facts_to_fill.md)"
    state = ("triggered hawkish" if band_low > 0 else "triggered dovish" if band_high < 0 else "not triggered")
    suffix = "" if str(rule.get("option")) == "1" else " (not the chosen decision rule)"
    return f"Direction flag: {state}{suffix}"


def falsification_three_note(artifact: dict) -> str:
    """Falsification criterion 3 (holdout RMSE ratio >= 1), from the artifact only."""
    comparison = artifact.get("benchmark_comparison", {})
    ratio, holdout = comparison.get("rmse_ratio_model_to_hold"), comparison.get("holdout_n")
    verdict = next((item for item in artifact.get("falsification_verdicts", [])
                    if "RMSE ratio" in str(item.get("rule", ""))), None)
    if verdict is None or not isinstance(ratio, (int, float)) or not isinstance(holdout, int):
        return "Falsification criterion 3 (holdout RMSE ratio ≥ 1): UNKNOWN (not in the model artifact)."
    if str(verdict.get("verdict")).lower() == "falsified":
        return (f"Falsification criterion 3 (holdout RMSE ratio ≥ 1) is met: on the {holdout} holdout decisions the "
                f"RMSE ratio is {ratio:.3f}, so the model does not forecast better than Always Hold; the difference "
                f"from 1 is too small to say the model is worse; we can only say it is not better.")
    return (f"Falsification criterion 3 (holdout RMSE ratio ≥ 1) is not met: on the {holdout} holdout decisions the "
            f"RMSE ratio is {ratio:.3f}.")


def specification_timing_note(provenance: dict) -> str:
    """Specification timing; the date and commit come from docs/facts_to_fill.md via provenance.json."""
    project = provenance.get("project", {})
    commit = str(project.get("spec_commit") or "").strip()
    try:
        allowed = date.fromisoformat(str(project.get("spec_date_allowed")))
    except ValueError:
        allowed = None
    if allowed is None or not commit or commit == "UNKNOWN":
        return "Specification timing: UNKNOWN (record spec_date_allowed and spec_commit in docs/facts_to_fill.md)."
    return (f"No time-stamped Week-4 pre-registration was submitted. The instructor allowed the model specification "
            f"(docs/model_spec.md) to be accepted with the date of its commit, {allowed.day} {allowed:%B %Y} "
            f"(commit {commit}). Exploratory backtests were run before the specification was committed; see "
            f"docs/deviations.md D15.")


def power_table(provenance: dict) -> pd.DataFrame | None:
    """The power table of outputs/power_note.md, as copied into provenance.json; no estimate/MDE column."""
    rows = (provenance.get("power") or {}).get("rows")
    if not rows:
        return None
    return pd.DataFrame([{"Factor": FEATURE_LABELS.get(row["feature"], row["feature"]), "Estimate": row["estimate"],
                          "SE": row["se"], "Minimum detectable effect": row["mde"]} for row in rows])


def _render_power(provenance: dict) -> None:
    st.subheader("Power: minimum detectable effects")
    table = power_table(provenance)
    if table is None:
        st.info("Power table: UNKNOWN (run `python run.py report` and `python run.py facts`).")
        return
    st.dataframe(table, hide_index=True, width="stretch")
    n = (provenance.get("power") or {}).get("n_estimation", "UNKNOWN")
    st.caption(f"At this sample size (N = {n}), failure to reject a zero slope is not evidence that the factor "
               f"has no effect.")


def why_probabilities(artifact: dict, history: pd.DataFrame, data_month: str, latest_features: dict[str, float],
                      band_low: float, band_high: float) -> list[str]:
    """The four explanations under the round blocks; every value comes from the artifact or processed data."""
    items = [
        f"**Same inputs for both rounds.** Both rounds use the latest available factor values (factor data month "
        f"{data_month or 'UNKNOWN'}), because future factor values are unknown. Both blocks are therefore the same "
        f"conditional estimate: the probabilities are identical and only the date differs. This is not an error and "
        f"not a separate forecast for each date."
    ]
    counts = history["decision"].value_counts() if "decision" in history else pd.Series(dtype=int)
    if counts.empty:
        items.append("**Why Hold is most likely.** UNKNOWN (no processed decision history).")
    else:
        hold, total = int(counts.get("Hold", 0)), int(counts.sum())
        if counts.idxmax() == "Hold":
            items.append(f"**Why Hold is most likely.** Hold was the most common NBK decision in the sample: {hold} of "
                         f"{total} decisions in data/processed/nbk_decisions_clean.csv.")
        else:
            items.append(f"**Decision mix.** Hold was {hold} of {total} decisions; the most common decision in the "
                         f"sample was {counts.idxmax()}.")
    try:
        intervals = probability_delta_intervals(artifact, latest_features)
        increase, decrease = intervals["Increase"], intervals["Decrease"]
        overlap = increase[0] <= decrease[1] and decrease[0] <= increase[1]
        includes_zero = band_low <= 0 <= band_high
        ranges = (f"Increase {_probability_display(increase[0])}–{_probability_display(increase[1])}, Decrease "
                  f"{_probability_display(decrease[0])}–{_probability_display(decrease[1])}")
        band = f"score band {band_low:+.3f} to {band_high:+.3f}"
        if overlap and includes_zero:
            items.append(f"**Hike or cut?** The 95% intervals ({ranges}) are wide and overlap, and the {band} includes "
                         f"zero, so the model does not separate a hike from a cut at this date.")
        else:
            items.append(f"**Hike or cut?** The 95% intervals are {ranges}; the {band}"
                         f"{' includes' if includes_zero else ' does not include'} zero.")
    except (DashboardDataError, KeyError, TypeError, ValueError):
        items.append("**Hike or cut?** UNKNOWN (the model artifact has no usable probabilities or covariance).")
    comparison = artifact.get("benchmark_comparison", {})
    ratio, holdout = comparison.get("rmse_ratio_model_to_hold"), comparison.get("holdout_n")
    joint = artifact.get("diagnostics", {}).get("joint_slope_lr", {}).get("p_value")
    if not all(isinstance(value, (int, float)) for value in (ratio, holdout, joint)):
        items.append("**Why the model does not beat Always Hold.** UNKNOWN (not in the model artifact).")
    elif ratio >= 1:
        link = (f"The factors have a detectable link with the decisions (joint likelihood-ratio test p = {joint:.3f}), "
                f"but the link is too weak to improve on always predicting Hold, the most common outcome."
                if joint < JOINT_TEST_LEVEL else
                f"The joint likelihood-ratio test does not detect a link between the factors and the decisions "
                f"(p = {joint:.3f}).")
        items.append(f"**Why the model does not beat Always Hold.** On the {holdout} holdout decisions the RMSE ratio "
                     f"is {ratio:.3f}, which is not below 1. {link} This is a limitation of the model, not a data error.")
    else:
        items.append(f"**Holdout comparison.** On the {holdout} holdout decisions the RMSE ratio is {ratio:.3f}, below 1.")
    return items


def _render_decision_rule(provenance: dict) -> None:
    """Show the student's chosen monitoring rule exactly as docs/decision_rule.md states it."""
    rule = provenance.get("decision_rule")
    if not rule:
        st.info("Decision rule: UNKNOWN (no option chosen in docs/facts_to_fill.md).")
        return
    st.info(f"**Decision rule (option {rule['option']}: {rule['title']}), a monitoring rule, not a forecast.** "
            f"Named user: {_fact(rule.get('named_user'))}. {rule['rule']} Today: {rule['today']}")


def _render_evidence(artifact: dict, provenance: dict) -> None:
    comparison = artifact.get("benchmark_comparison", {})
    ratio = comparison.get("rmse_ratio_model_to_hold")
    winner = comparison.get("winner", "UNKNOWN")
    checks = artifact.get("robustness_checks", {}).get("checks", [])
    survivals = {str(row.get("survives", "UNKNOWN")).lower() for row in checks}
    robustness_status = "mixed" if len(survivals) > 1 else "consistent"
    if ratio is None:
        result_sentence = "holdout benchmark outcome is UNKNOWN"
    elif winner == "Always Hold" or float(ratio) >= 1.0:
        result_sentence = f"Ordered logit does not beat Always Hold on the holdout (RMSE ratio {_metric_text(ratio)})"
    else:
        result_sentence = f"Ordered logit beats Always Hold on the holdout (RMSE ratio {_metric_text(ratio)})"
    st.info(f"{result_sentence}; robustness results are {robustness_status}.")

    st.subheader("Holdout comparison")
    st.dataframe(_holdout_comparison_frame(artifact), hide_index=True, width="stretch")
    st.caption("Always Hold assigns probability zero to Increase and Decrease, so the log score cannot be computed on a holdout that contains them.")
    st.caption(f"RMSE ratio (model / Always Hold): {_metric_text(ratio)} · Winner: {winner}")
    st.caption(
        "Model does not beat the Always Hold benchmark on the holdout."
        if ratio is not None and (winner == "Always Hold" or float(ratio) >= 1.0)
        else "Model beats the Always Hold benchmark on the holdout."
        if ratio is not None else "Holdout benchmark result: UNKNOWN."
    )

    st.subheader("Falsification")
    falsification = _falsification_frame(artifact)
    def verdict_style(frame: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame([
            ["background-color: #fde8e7; color: #8f211a; font-weight: 700" if value == "Falsified"
             else "background-color: #e7f4ec; color: #17633d; font-weight: 700" if column == "Verdict"
             else "" for column, value in row.items()]
            for _, row in frame.iterrows()
        ], index=frame.index, columns=frame.columns)
    st.dataframe(falsification.style.apply(verdict_style, axis=None), hide_index=True, width="stretch")

    st.subheader("Diagnostics")
    diagnostic_table, not_applicable = _diagnostic_frames(artifact)
    st.dataframe(diagnostic_table, hide_index=True, width="stretch")
    if not not_applicable.empty:
        st.caption("Tests that do not apply to the ordinal model")
        st.dataframe(not_applicable, hide_index=True, width="stretch")

    st.subheader("Robustness specifications")
    robustness = _robustness_frame(artifact)
    if not robustness.empty:
        st.dataframe(robustness, hide_index=True, width="stretch")
        total = artifact.get("robustness_checks", {}).get("total_specifications_including_primary", "UNKNOWN")
        st.caption(
            "Ratios in different rows use different holdouts and are not comparable with each other. "
            "The differenced non-stationary-factor check first-differences household and corporate "
            "12-month log growth and inflation; other factors retain their main-model transformations. "
            f"Total specifications run: {total}."
        )
    else:
        st.info("Robustness checks are not present in the model artifact.")

    with st.expander("Full results stored in artifact"):
        st.subheader("Holdout comparison")
        _render_artifact_tables(artifact)

    _render_power(provenance)

    st.subheader("Limitations")
    limitation = provenance.get("release_lag_limitation", {}).get("text")
    st.markdown(limitation if limitation else
                "Release-lag limitation: UNKNOWN (data/processed/provenance.json is missing; run `python run.py facts`).")
    st.markdown(rb09_household_note(artifact))
    st.markdown(falsification_three_note(artifact))
    st.markdown(specification_timing_note(provenance))
    st.caption("Generated from config/release_lag.json, docs/facts_to_fill.csv and the raw files by `python run.py facts`.")


def main() -> None:
    """Render the read-only dashboard and report its cached render duration."""
    started = time.perf_counter()
    st.set_page_config(page_title="NBK Policy Pressure Score", layout="wide")
    try:
        artifact = load_artifact(str(ARTIFACT_PATH))
        history = load_data(str(DATA_PATH))
        model_panel = load_model_panel(str(MODEL_PANEL_PATH))
        latest_features, previous_features = _latest_and_previous_features(artifact)
        latest_date = pd.Timestamp(artifact["latest_prediction"]["date"])
        if history.empty or model_panel.empty or pd.isna(latest_date):
            raise DashboardDataError("A required latest observation is missing.")
        if not model_panel["decision_date"].eq(latest_date).any():
            raise DashboardDataError("Latest factor observation is missing from processed model data.")
        missing_model_cols = [name for name in FEATURES if name not in model_panel.columns]
        if missing_model_cols:
            raise DashboardDataError("Processed model data is missing required factor observations.")
        latest_score = _score_for_vector(artifact, latest_features)
        _, band_low, band_high = score_and_delta_band(artifact, latest_features)
        band_low, band_high = max(-1.0, band_low), min(1.0, band_high)
        previous_score = _score_for_vector(artifact, previous_features)
        score_change = latest_score - previous_score
        previous_date = previous_usable_decision_date(model_panel, latest_date)
        decision_dates, schedule_source, schedule_message = load_next_decisions()
        provenance = load_provenance(str(PROVENANCE_PATH))
        assumed_lag = provenance.get("assumed_release_lag_months")
        if isinstance(assumed_lag, int) and not isinstance(assumed_lag, bool) and assumed_lag >= 0:
            next_data_month = (latest_date.to_period("M") - assumed_lag).strftime("%Y-%m")
            lag_label = f"assumed month t−{assumed_lag}"
        else:
            next_data_month, lag_label = "UNKNOWN", "assumed release lag UNKNOWN"
    except DashboardDataError as error:
        st.error(str(error))
        st.stop()
    except (KeyError, TypeError, ValueError, IndexError):
        st.error("Dashboard data is incomplete or invalid. Check the processed files and model artifact.")
        st.stop()

    st.markdown("<style>\n"
                ".stApp {background:#f6f8fb;}\n"
                "h1 {color:#172b4d; font-weight:700; letter-spacing:-.025em;}\n"
                ".stTabs [data-baseweb='tab-list'] {gap:1.15rem; border-bottom:1px solid #d9e0e8;}\n"
                ".stTabs [data-baseweb='tab'] {color:#667386; font-weight:650; padding:0.75rem 0.15rem;}\n"
                ".stTabs [aria-selected='true'] {color:#174a7e;}\n"
                "</style>", unsafe_allow_html=True)
    st.title("NBK Base-Rate Decision Forecast")
    st.markdown(DEDICATION)
    headline_cols = st.columns([1.25, 1.0, 1.4])
    headline_cols[0].metric("Policy pressure score", f"{latest_score:+.3f}")
    headline_cols[0].caption(f"95% band: {band_low:+.3f} to {band_high:+.3f}")
    headline_cols[0].caption(direction_flag_state(band_low, band_high, provenance))
    headline_cols[1].metric("Change versus previous decision", f"{score_change:+.3f}")
    probabilities = ordered_probabilities(artifact, latest_features)
    most_likely = max(DISPLAY_CLASSES, key=lambda label: probabilities[label])
    top_percent = _probability_display(probabilities[most_likely])
    next_date_text = decision_dates[0].strftime("%d %B %Y") if decision_dates[0] else "date not confirmed"
    headline_cols[2].caption(f"Most likely at the next decision: {most_likely} ({top_percent})")
    headline_cols[2].caption(f"Next scheduled decision: {next_date_text}")
    st.caption(f"Unit: {SCORE_UNIT}")
    st.caption(
        f"Period: NBK decision of {latest_date.date().isoformat()}, "
        f"factor data month {next_data_month} ({lag_label})"
    )
    st.caption(f"Latest change: {score_change:+.3f} versus the decision of {previous_date}")
    cached_as_of = latest_date.date().isoformat()
    _render_refresh_status(schedule_source, cached_as_of)
    if schedule_message:
        st.caption(schedule_message)

    overview_tab, drivers_tab, evidence_tab, provenance_tab = st.tabs(
        ["Overview", "Drivers and scenario", "Evidence", "Data and provenance"]
    )
    with overview_tab:
        st.subheader("Next scheduled NBK decisions")
        card_intervals = probability_delta_intervals(artifact, latest_features)
        card_columns = st.columns(2, gap="large")
        for index, (column, round_date) in enumerate(zip(card_columns, decision_dates), start=1):
            with column:
                st.markdown(
                    forecast_card_html(index, round_date, probabilities, card_intervals,
                                       latest_date.date().isoformat(), most_likely),
                    unsafe_allow_html=True,
                )
        st.caption("Both rounds use the latest available factor values; future values are unknown, so the probabilities are identical and only the date differs.")
        with st.expander("Why these probabilities?"):
            for item in why_probabilities(artifact, history, next_data_month, latest_features, band_low, band_high):
                st.markdown(f"- {item}")
        comparison = artifact.get("benchmark_comparison", {})
        ratio = comparison.get("rmse_ratio_model_to_hold")
        if isinstance(ratio, (int, float)):
            if comparison.get("winner") == "Always Hold" or float(ratio) >= 1.0:
                st.warning(f"Model does not beat the Always Hold benchmark on the holdout (RMSE ratio {float(ratio):.3f})")
            else:
                st.success(f"Model beats the Always Hold benchmark on the holdout (RMSE ratio {float(ratio):.3f})")
        else:
            st.warning("Holdout benchmark result: UNKNOWN.")
        _render_decision_rule(provenance)
        _render_history(history, provenance)
    with drivers_tab:
        _render_drivers(artifact)
        st.subheader("Scenario control")
        st.caption("Change one observed factor while holding the other latest inputs fixed. The interval uses the stored covariance and delta method.")
        slider_feature = st.selectbox(
            "Factor to change", FEATURES, index=FEATURES.index(SCENARIO_DEFAULT_FACTOR),
            format_func=lambda name: FEATURE_LABELS[name], key="scenario_factor",
        )
        series = pd.to_numeric(model_panel[slider_feature], errors="coerce").dropna()
        if series.empty or slider_feature not in latest_features:
            st.info("Scenario slider is unavailable because no observed factor range is present.")
        else:
            low, high = float(series.min()), float(series.max())
            if low == high:
                st.info("Scenario slider is unavailable because the observed factor has no range.")
            else:
                baseline = min(max(float(latest_features[slider_feature]), low), high)
                step = (high - low) / 100.0
                # One key per factor, so switching factors starts the slider at that factor's latest value.
                scenario_value = st.slider(FEATURE_LABELS[slider_feature], min_value=low, max_value=high, value=baseline,
                                           step=step, key=f"scenario_value_{slider_feature}")
                scenario_features = dict(latest_features)
                scenario_features[slider_feature] = float(scenario_value)
                scenario_score, ci_low, ci_high = score_and_delta_band(artifact, scenario_features)
                st.metric("Scenario policy pressure score", f"{scenario_score:+.3f}")
                st.caption(f"95% delta-method band: [{max(-1.0, ci_low):+.3f}, {min(1.0, ci_high):+.3f}]")
                st.caption("Only the selected factor moves; the other five stay at their latest values.")
    with evidence_tab:
        _render_evidence(artifact, provenance)
    with provenance_tab:
        _render_provenance(artifact, schedule_source, provenance)
    elapsed = time.perf_counter() - started
    st.caption(f"Cached dashboard render time: {elapsed:.3f} seconds.")


if __name__ == "__main__":
    main()
