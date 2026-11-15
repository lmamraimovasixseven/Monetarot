"""Блок `dashboard` в model/artifact.json: всё, что показывает Render-приложение (src/app.py), для статичного сайта.

`python run.py dashboard`. Ничего не оценивает: вызывает функции src/app.py, которые читают сохранённые коэффициенты,
пороги и ковариацию (ordered_probabilities, probability_delta_intervals, score_and_delta_band, score_history_frame) и
формируют те же фразы, что видит пользователь Render. Поэтому тексты и числа сайта совпадают с приложением.
Таблицы хранятся с исходными числами и форматом колонки; сайт форматирует их так же, как app.py, и каждое число
получает строку в журнале доказательств (ledger/evidence_ledger.csv, id `dashboard:<путь>`).

Даты раундов зависят от сегодняшнего дня; чтобы блок был воспроизводимым, здесь раунды выбираются после последнего
решения в данных, а страница в браузере пересчитывает их по текущей дате (как Render).
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from statistics import NormalDist
from typing import Any

import pandas as pd

import streamlit.logger  # noqa: E402

# Вне Streamlit кеш app.py пишет «No runtime found»; это не ошибка, сообщение скрыто.
streamlit.logger.get_logger("streamlit.runtime.caching.cache_data_api").setLevel(logging.ERROR)
from src import app  # noqa: E402  (только чистые функции чтения и форматирования)

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = ROOT / "model" / "artifact.json"
ROBUST_PATH = ROOT / "model" / "robust_eval.json"
LOSSES_PATH = ROOT / "config" / "decision_losses.json"
FEATURES = app.FEATURES


def _clean(value: Any) -> Any:
    """JSON без NaN/inf: нечисловые значения pandas → None, numpy-скаляры → Python."""
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def table(columns: list[str], formats: list[str], rows: list[list[Any]]) -> dict[str, Any]:
    """Таблица для сайта: исходные значения ячеек и формат колонки (см. src/site_build.py::fmt_cell)."""
    assert len(columns) == len(formats) and all(len(r) == len(columns) for r in rows), columns
    return {"columns": columns, "formats": formats, "rows": _clean(rows)}


def raw_table(records: list[dict[str, Any]], number_format: str = "g4") -> dict[str, Any]:
    """Таблица из списка словарей артефакта как есть (раскрывающийся блок «Full results stored in artifact»)."""
    columns: list[str] = []
    for record in records:
        columns += [k for k in record if k not in columns]
    rows = [[record.get(c) for c in columns] for record in records]
    formats = ["text" if all(not isinstance(r[i], (int, float)) or isinstance(r[i], bool) for r in rows)
               else number_format for i in range(len(columns))]
    rows = [[v if not isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False) for v in r] for r in rows]
    return table(columns, formats, rows)


def _num_or_text(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value
    text = str(value)
    return "undefined" if text.lower() in {"+infinity", "infinity", "inf", "nan"} else text


# ----------------------------------------------------------------------------- таблицы как в src/app.py

def holdout_table(artifact: dict, robust: dict) -> dict[str, Any]:
    comparison = artifact.get("benchmark_comparison", {})
    specs = [("Ordered logit", comparison.get("model", {}), "M0"),
             ("Always Hold (pre-specified benchmark)", comparison.get("benchmark_always_hold", {}), "B0"),
             ("Class-frequency comparator (secondary, added after the specification freeze)",
              comparison.get("class_frequency_comparator_secondary", {}), "B1")]
    rows = []
    for label, values, spec in specs:
        log_score = "undefined" if label.startswith("Always Hold") else _num_or_text(values.get("log_score"))
        rps = (app._robust_row(robust, "holdout_fixed_origin", spec) or {}).get("rps") if robust else None
        rows.append([label, _num_or_text(values.get("rmse")), _num_or_text(values.get("mae")), log_score, rps])
    return table(["Model", "RMSE", "MAE", "Log score", "RPS (supplementary)"], ["text", "f3", "f3", "f3", "f3"], rows)


def falsification_table(artifact: dict) -> dict[str, Any]:
    rows = []
    for item in artifact.get("falsification_verdicts", []):
        statistic = item.get("statistic")
        if isinstance(statistic, dict):
            statistic = "; ".join(f"{name}: p={app._metric_text(value)}" for name, value in statistic.items())
        rows.append([item.get("rule", "UNKNOWN"), _num_or_text(statistic), item.get("threshold", "UNKNOWN"),
                     "Falsified" if str(item.get("verdict", "")).lower() == "falsified" else "Not falsified"])
    return table(["Rule", "Statistic", "Threshold", "Verdict"], ["text", "f3", "text", "verdict"], rows)


def diagnostics_tables(artifact: dict) -> tuple[dict[str, Any], dict[str, Any]]:
    diagnostics = artifact.get("diagnostics", {})
    rows = []

    def add(test: str, explanation: str, statistic: Any, raw_p: Any, adjusted_p: Any, family: Any, flag: Any) -> None:
        family_text = str(family or "UNKNOWN")
        adjusted = "not adjusted" if "no adjustment" in family_text.lower() else adjusted_p
        rows.append([test, explanation, _num_or_text(statistic), _num_or_text(raw_p), _num_or_text(adjusted),
                     family_text, app._flag_text(flag)])

    joint = diagnostics.get("joint_slope_lr", {})
    add("Joint slope LR", "Tests whether the six slope coefficients are jointly zero.", joint.get("statistic"),
        joint.get("p_value"), joint.get("p_value_adjusted"), joint.get("p_value_family"), joint.get("pass_fail"))
    for key, explanation in (
        ("parameter_stability", "Tests whether slope coefficients are equal across the stored time regimes."),
        ("proportional_odds", "Tests whether cumulative-logit slopes satisfy the proportional-odds assumption."),
        ("serial_correlation", "Tests for serial correlation in standardized Pearson score residuals."),
    ):
        item = diagnostics.get(key, {})
        add(item.get("name", key.replace("_", " ").title()), explanation, item.get("statistic"), item.get("p_value"),
            item.get("p_value_adjusted"), item.get("p_value_family"), item.get("pass_fail"))
    vif = diagnostics.get("vif", [])
    if vif:
        top = max(vif, key=lambda item: float(item.get("statistic", float("-inf"))))
        add(f"Maximum VIF ({top.get('feature', 'UNKNOWN')})", "Reports the largest variance inflation factor across the six predictors.",
            top.get("statistic"), "not applicable", "not applicable", "Descriptive VIF; no p-value family", top.get("pass_fail"))
    for item in (i for i in diagnostics.get("unit_root_tests", []) if i.get("form") == "transformed_model_input"):
        test = str(item.get("test", "UNKNOWN")).upper()
        note = ("Tests the unit-root null; rejection supports stationarity." if test == "ADF"
                else "Tests the stationarity null; non-rejection supports stationarity.")
        add(f"Unit root — {item.get('feature', 'UNKNOWN')} ({test})", note, item.get("statistic"), item.get("p_value"),
            item.get("p_value_adjusted"), item.get("p_value_family"), item.get("pass_fail"))
    main = table(["Test", "What it checks", "Statistic", "p-value (raw)", "p-value (Holm-adjusted where defined)", "Family", "Flag"],
                 ["text", "text", "f3", "f3", "f3", "text", "flag"], rows)
    na = table(["Test", "Reason"], ["text", "text"],
               [[i.get("name", "UNKNOWN"), i.get("reason", "Reason not recorded in the artifact.")]
                for i in diagnostics.get("not_applicable_tests", [])])
    return main, na


def robustness_table(artifact: dict) -> dict[str, Any]:
    rows = []
    for item in artifact.get("robustness_checks", {}).get("checks", []):
        converged, signs = item.get("estimator_converged"), item.get("same_signs_as_primary")
        rows.append([f"{item.get('specification_id', 'UNKNOWN')} — {item.get('name', 'UNKNOWN')}", item.get("n_usable", "UNKNOWN"),
                     _num_or_text(item.get("rmse_ratio_model_to_hold")),
                     "Yes" if signs is True else "No" if signs is False else "UNKNOWN", str(item.get("survives", "UNKNOWN")),
                     "Yes" if converged is True else "No — NOT CONVERGED" if converged is False else "UNKNOWN",
                     "Yes" if app.robustness_check_is_comparable(item) else "No (binary target)"])
    return table(["Check", "Usable n", "RMSE ratio vs Always Hold", "Factor signs match the main model", "Survives",
                  "Converged", "Comparable with main score"], ["text", "int", "f3", "text", "text", "text", "text"], rows)


def robust_design_table(design: dict) -> dict[str, Any]:
    rows = []
    for row in design.get("specifications", []):
        boot = row.get("bootstrap_rmse_ratio_vs_hold") or {}
        hold = row.get("id") == "B0"
        rows.append([row.get("id"), row.get("name"), row.get("rps"), "—" if hold else row.get("rps_skill_vs_hold"),
                     "—" if hold else (row.get("dm_rps_vs_hold") or {}).get("p_value"), row.get("rmse_ratio_to_hold"),
                     "—" if hold else [boot.get("ci_low"), boot.get("ci_high")], row.get("hit_rate")])
    return table(["Id", "Specification", "RPS (lower is better)", "RPS skill vs Hold", "DM p-value (RPS)", "RMSE ratio vs Hold",
                  "95% bootstrap CI of ratio", "Hit rate"], ["text", "text", "f3na", "f3na", "f3na", "f3na", "f3na", "f3na"], rows)


# ----------------------------------------------------------------------------- блок целиком

def _rounds() -> dict[str, Any]:
    if not app.ROUNDS_PATH.is_file():
        return {"source": "UNKNOWN", "verified": False, "dates": []}
    schedule = json.loads(app.ROUNDS_PATH.read_text(encoding="utf-8"))
    dates = sorted({str(item["date"]) for item in schedule.get("rounds", []) if item.get("date")})
    return {"source": str(schedule.get("source") or "UNKNOWN"), "verified": schedule.get("verified") is True, "dates": dates}


def build(artifact_path: Path = ARTIFACT_PATH, robust_path: Path = ROBUST_PATH) -> dict[str, Any]:
    artifact = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    robust = json.loads(Path(robust_path).read_text(encoding="utf-8")) if Path(robust_path).is_file() else {}
    history = app._read_data.__wrapped__(str(app.DATA_PATH), 0)
    panel = app._read_model_panel.__wrapped__(str(app.MODEL_PANEL_PATH), 0)
    provenance = app.load_provenance(str(app.PROVENANCE_PATH))
    screen, scores, version = app.load_data_screen(), app.load_forecast_scores(), app.load_version_comparison()

    latest, previous = app._latest_and_previous_features(artifact)
    latest_date = pd.Timestamp(artifact["latest_prediction"]["date"])
    probabilities = app.ordered_probabilities(artifact, latest)
    intervals = app.probability_delta_intervals(artifact, latest)
    score, band_low, band_high = app.score_and_delta_band(artifact, latest)
    band_low, band_high = max(-1.0, band_low), min(1.0, band_high)
    change = score - app._score_for_vector(artifact, previous)
    previous_date = app.previous_usable_decision_date(panel, latest_date)
    most_likely = max(app.DISPLAY_CLASSES, key=lambda label: probabilities[label])
    lag = provenance.get("assumed_release_lag_months")
    if isinstance(lag, int) and not isinstance(lag, bool) and lag >= 0:
        data_month, lag_label = (latest_date.to_period("M") - lag).strftime("%Y-%m"), f"assumed month t−{lag}"
    else:
        data_month, lag_label = "UNKNOWN", "assumed release lag UNKNOWN"
    rounds = _rounds()
    default_dates, _, schedule_message = app.load_next_decisions(today=latest_date.date())
    comparison = artifact.get("benchmark_comparison", {})
    ratio = comparison.get("rmse_ratio_model_to_hold")
    checks = artifact.get("robustness_checks", {}).get("checks", [])
    rule = provenance.get("decision_rule")
    losses = json.loads(LOSSES_PATH.read_text(encoding="utf-8")) if LOSSES_PATH.is_file() else {}

    params = artifact["model"]["parameters"]
    model = {"features": FEATURES, "labels": [app.FEATURE_LABELS[f] for f in FEATURES],
             "slopes": [float(params[f]) for f in FEATURES],
             "cutpoints": [float(params["cutpoint[Decrease|Hold]"]), float(params["cutpoint[Hold|Increase]"])],
             "covariance_names": list(artifact["model"]["covariance_names"]),
             "covariance": artifact["model"]["covariance_hc0"],
             "latest": [latest[f] for f in FEATURES], "previous": [previous[f] for f in FEATURES],
             "z_975": NormalDist().inv_cdf(0.975)}  # тот же множитель, что в app.score_and_delta_band
    slider = []
    for feature in FEATURES:
        series = pd.to_numeric(panel[feature], errors="coerce").dropna()
        low, high = float(series.min()), float(series.max())
        slider.append({"feature": feature, "min": low, "max": high, "step": (high - low) / 100.0,
                       "baseline": min(max(float(latest[feature]), low), high)})

    contribution_rows = [r for r in artifact.get("per_factor_contribution_to_latest_score_change", [])
                         if r.get("feature") in FEATURES and r.get("expected_score_contribution_to_latest_change") is not None]
    contributions = table(["Factor", "Contribution to score change", "Sign"], ["text", "s4", "text"], [
        [app.FEATURE_LABELS[r["feature"]], float(r["expected_score_contribution_to_latest_change"]),
         "Positive" if r["expected_score_contribution_to_latest_change"] > 0 else
         "Negative" if r["expected_score_contribution_to_latest_change"] < 0 else "Zero"] for r in contribution_rows])
    top = sorted(contributions["rows"], key=lambda r: abs(r[1]), reverse=True)[:3]

    track = app.score_history_frame(artifact, panel)
    designs = robust.get("designs") or {}
    flags = (robust.get("anomaly_screen") or {}).get("flags") or []
    affecting = {(f["feature"], f["month"]) for f in (robust.get("anomaly_screen") or {}).get("affecting_latest_score") or []}
    forecasts = (robust.get("next_decision_forecasts") or {}).get("forecasts") or []
    power = app.power_table(provenance)
    sample = artifact["sample"]
    project = provenance.get("project", {})
    units = artifact.get("units", {})
    coefficient_rows = artifact["model"].get("coefficient_table", {})
    rates = history[["decision_date", "base_rate_after", "decision"]].dropna() if "base_rate_after" in history else history.iloc[0:0]

    block = {
        "label": "Render dashboard (src/app.py) values for the static site; computed from the stored model, nothing estimated",
        "title": "NBK Base-Rate Decision Forecast",
        "intro": ("How hard are six macro factors pushing the National Bank of Kazakhstan towards a rate hike or a cut? "
                  "Read-only view of a fitted ordered-logit model; nothing is re-estimated here."),
        "latest_decision": latest_date.date().isoformat(),
        "previous_decision": previous_date,
        "data_month": data_month, "lag_label": lag_label,
        "unit": app.SCORE_UNIT,
        "score": score, "band": [band_low, band_high], "score_change": change,
        "direction_flag": app.direction_flag_state(band_low, band_high, provenance),
        "probabilities": {k: probabilities[k] for k in app.DISPLAY_CLASSES},
        "intervals": {k: list(intervals[k]) for k in app.DISPLAY_CLASSES},
        "most_likely": most_likely,
        "rounds": rounds | {"default": [d.isoformat() if d else None for d in default_dates],
                            "default_message": schedule_message},
        "rounds_caption": ("Both rounds use the latest available factor values; future values are unknown, so the "
                           "probabilities are identical and only the date differs."),
        "card_foot": (f"Latest factor data as of {latest_date.date().isoformat()}. Conditional model estimates; "
                      "calibration is unverified."),
        "why": app.why_probabilities(artifact, history, data_month, latest, band_low, band_high),
        "verdict_box": (f"{app.verdict_rule_sentence(float(ratio), comparison.get('winner'))} "
                        f"{app.verdict_inference_sentence(robust)} {app.version_change_sentence(version)}"
                        if isinstance(ratio, (int, float)) else "Holdout benchmark result: UNKNOWN."),
        "decision_rule": None if not rule else {
            "head": f"Decision rule (option {rule['option']}: {rule['title']}), a monitoring rule, not a forecast.",
            "text": f"Named user: {app._fact(rule.get('named_user'))}. {rule['rule']} Today: {rule['today']}"},
        "forecast_log_sentence": app.forecast_log_sentence(scores),
        "anomaly_warning": app.anomaly_warning(robust, screen),
        "look_ahead_sentence": (provenance.get("release_lag_limitation") or {}).get("look_ahead_sentence"),
        "release_lag_limitation": (provenance.get("release_lag_limitation") or {}).get("text"),
        "losses_confirmed": not str(losses.get("status", "UNKNOWN")).upper().startswith(("ДОПУЩЕНИЕ", "UNKNOWN")),
        "model": model, "slider": slider, "slider_default": app.SCENARIO_DEFAULT_FACTOR,
        "contributions": contributions, "top_drivers": top,
        "track_record": {"holdout_start": sample["holdout_start"], "dates": [d.date().isoformat() for d in track["Decision date"]],
                         "score": track["Policy pressure score"].tolist(), "actual": track["Actual decision"].tolist()},
        "history": {"dates": [d.date().isoformat() for d in history["decision_date"]], "score": history["ordinal_score"].tolist(),
                    "rate_dates": [d.date().isoformat() for d in rates["decision_date"]],
                    "base_rate": rates["base_rate_after"].astype(float).tolist() if len(rates) else [],
                    "source": (f"Source: NBK base-rate decisions in data/processed/nbk_decisions_clean.csv, built from "
                               f"data/raw/{app.TARGET_SERIES_FILE}. Original publisher: {app._target_publisher(provenance)}.")},
        "evidence": {
            "summary": f"{app.verdict_rule_sentence(ratio, comparison.get('winner', 'UNKNOWN'))} Robustness results are "
                       f"{'mixed' if len({str(r.get('survives', 'UNKNOWN')).lower() for r in checks}) > 1 else 'consistent'}.",
            "inference": app.verdict_inference_sentence(robust),
            "version_change": app.version_change_sentence(version),
            "ratio": ratio, "winner": comparison.get("winner", "UNKNOWN"),
            "verdict_rule": app.verdict_rule_sentence(ratio, comparison.get("winner", "UNKNOWN")),
            "rps_sentence": app.rps_supplementary_sentence(robust),
            "holdout": holdout_table(artifact, robust),
            "falsification": falsification_table(artifact),
            "robustness": robustness_table(artifact),
            "diagnostics": diagnostics_tables(artifact)[0],
            "diagnostics_na": diagnostics_tables(artifact)[1],
            "robustness_total": artifact.get("robustness_checks", {}).get("total_specifications_including_primary", "UNKNOWN"),
            "noncomparable_reason": app.NONCOMPARABLE_REASON,
            "power": None if power is None else table(list(power.columns), ["text", "text", "text", "text"], power.values.tolist()),
            "power_n": (provenance.get("power") or {}).get("n_estimation", "UNKNOWN"),
            "limitations": [s for s in (
                (provenance.get("release_lag_limitation") or {}).get("text"), app.rb09_household_note(artifact),
                app.falsification_three_note(artifact), app.specification_timing_note(provenance),
                app.holdout_update_sentence(artifact, project.get("spec_date_allowed")),
                app.next_forecast_basis_sentence(artifact, lag, default_dates[0] if default_dates else None)) if s],
        },
        "full_results": {
            "coefficient_detail": raw_table([{"Specification": c.get("specification_id", "UNKNOWN"), **coef}
                                             for c in checks for coef in c.get("coefficients", [])]),
            "coefficients": raw_table([{"Parameter": name, **row} for name, row in coefficient_rows.items()]),
            "covariance": table(["", *model["covariance_names"]], ["text", *["g4"] * len(model["covariance_names"])],
                                [[name, *row] for name, row in zip(model["covariance_names"], model["covariance"])]),
            "expanding": raw_table(artifact.get("diagnostics", {}).get("expanding_window_coefficients", [])),
            "unit_roots": raw_table(artifact.get("diagnostics", {}).get("unit_root_tests", [])),
            "structural_breaks": raw_table(artifact.get("diagnostics", {}).get("structural_break_checks", [])),
            "economic_size": raw_table(_clean(pd.json_normalize(artifact.get("economic_size_plus_one_sd", []), sep=".")
                                              .astype(object).where(lambda f: f.notna(), None).to_dict("records"))),
        },
        "stress": {
            "label": robust.get("label", "Exploratory results."),
            "sentences": app.robust_summary_sentences(robust) if robust else [],
            "designs": [{"key": key, "label": app.ROBUST_DESIGN_LABELS[key],
                         "caption": f"{designs[key].get('description', '')} Decisions {designs[key].get('first_date')} to "
                                    f"{designs[key].get('last_date')} (n = {designs[key].get('n')}).",
                         "table": robust_design_table(designs[key])} for key in app.ROBUST_DESIGN_LABELS if key in designs],
            "forecasts": table(["Id", "Specification", "Decrease", "Hold", "Increase", "Score"],
                               ["text", "text", "pct1", "pct1", "pct1", "s3"],
                               [[f["id"], f["name"], f["probabilities"]["Decrease"], f["probabilities"]["Hold"],
                                 f["probabilities"]["Increase"], f["expected_score"]] for f in forecasts]),
            "anomalies": table(["Series", "Month", "Value", "Previous month", "Modified z", "Enters latest score"],
                               ["text", "text", "c2", "c2", "s1", "text"],
                               [[f["series_file"], f["month"], f["value"], f["previous_value"], f["modified_z"],
                                 "yes" if (f["feature"], f["month"]) in affecting else "no"] for f in flags]),
            "z_threshold": (robust.get("settings") or {}).get("modified_z_threshold", "UNKNOWN"),
        },
        "provenance": {
            "series": table([label for _, label in app.PROVENANCE_COLUMNS], ["text"] * len(app.PROVENANCE_COLUMNS),
                            app.provenance_table(provenance).values.tolist()),
            "values": table(["Field", "Value"], ["text", "text"], [[f, str(v)] for f, v in (
                ("Assumed release lag (months before the decision month)", app._fact(provenance.get("assumed_release_lag_months"))),
                ("Named user", app._fact(project.get("named_user"))), ("Decision calendar source", rounds["source"]),
                ("Sample window", f"{sample.get('usable_start', 'UNKNOWN')} to {sample.get('usable_end', 'UNKNOWN')}"),
                ("Estimation timestamp (UTC)", artifact.get("estimation_timestamp_utc", "UNKNOWN")),
                ("Input data SHA-256 (normalized line endings)", artifact.get("data_sha256_normalized_crlf_to_lf", "UNKNOWN")),
                ("Random seed", artifact.get("seed", "UNKNOWN")))]),
            "latest": table(["Factor", "Latest value", "Model input unit"], ["text", "g4", "text"],
                            [[app.FEATURE_LABELS[f], latest[f], units.get(f, "UNKNOWN")] for f in FEATURES]),
        },
    }
    return _clean(block)


def main() -> int:
    from src.artifact_extensions import merge

    block = build()
    merge("dashboard", block)
    print(f"dashboard: score {block['score']:+.3f}, {len(block['evidence']['robustness']['rows'])} robustness checks, "
          f"{len(block['stress']['anomalies']['rows'])} anomaly flags; written to model/artifact.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
