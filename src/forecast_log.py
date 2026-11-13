"""Forecast log: record the next-decision forecast BEFORE the decision, score it AFTER.

`python run.py forecast-log`   appends the current next-decision probabilities and score of the
                               frozen pre-specified model to docs/forecast_log.csv, with the UTC
                               timestamp, the git commit of HEAD (and whether the working tree had
                               uncommitted changes), the SHA-256 of model/artifact.json and a hash of
                               the input data. Commit and push the log immediately: the commit on
                               GitHub is the external timestamp (docs/development_plan.md).
`python run.py forecast-score` scores every logged forecast whose decision is now in the data
                               (RPS, squared error of the expected score, hit), next to Always Hold,
                               and writes data/processed/forecast_scores.json (read by the dashboard)
                               and outputs/forecast_scores.md.

Rules enforced here: a forecast cannot be logged for a date on or before today, or for a decision
that is already in the data; existing log rows are never rewritten (the log is append-only and
guarded by tests/test_forecast_log.py). Nothing here estimates anything.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.hashing import normalized_sha256
from src.ingest import ASSUMED_LAG_MONTHS


ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "docs" / "forecast_log.csv"
ARTIFACT_PATH = ROOT / "model" / "artifact.json"
ROUNDS_PATH = ROOT / "config" / "forecast_rounds.json"
CALENDAR_PATH = ROOT / "config" / "nbk_decision_dates.csv"
DECISIONS_PATH = ROOT / "data" / "processed" / "nbk_decisions_clean.csv"
RAW_DIR = ROOT / "data" / "raw"
SCORES_JSON = ROOT / "data" / "processed" / "forecast_scores.json"
SCORES_MD = ROOT / "outputs" / "forecast_scores.md"
MODEL_LABEL = "M0: pre-specified ordered logit (frozen; model/artifact.json)"
CLASS_ORDER = ["Decrease", "Hold", "Increase"]
SCORE = {"Decrease": -1, "Hold": 0, "Increase": 1}
# config/forecast_rounds.json lists announcement dates (a Friday); the decision calendar uses effective
# dates (usually the following Monday or Tuesday). A logged target is matched with the first decision in the
# data whose effective date falls on the target date or within this many days after it.
MATCH_WINDOW_DAYS = 10
COLUMNS = ["logged_at_utc", "target_decision_date", "based_on_decision", "factor_month", "model",
           "p_decrease", "p_hold", "p_increase", "expected_score", "git_commit", "git_worktree",
           "artifact_sha256", "data_sha256"]


class ForecastLogError(ValueError):
    """A forecast that must not be logged (too late, duplicate, or no target date)."""


def data_sha256(raw_dir: Path = RAW_DIR, calendar_path: Path = CALENDAR_PATH) -> str:
    """One hash over the raw monthly files and the decision calendar (CRLF normalized to LF)."""
    digest = hashlib.sha256()
    for path in sorted(Path(raw_dir).glob("*.csv")) + [Path(calendar_path)]:
        digest.update(f"{path.name}:{normalized_sha256(path)}\n".encode("utf-8"))
    return digest.hexdigest()


def git_state(root: Path = ROOT) -> tuple[str, str]:
    if not (root / ".git").exists() or shutil.which("git") is None:
        return "UNKNOWN", "UNKNOWN"
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
    status = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True)
    commit = head.stdout.strip() if head.returncode == 0 else "UNKNOWN"
    worktree = "UNKNOWN" if status.returncode else ("uncommitted changes" if status.stdout.strip() else "clean")
    return commit, worktree


def next_target_date(today: date, rounds_path: Path = ROUNDS_PATH, calendar_path: Path = CALENDAR_PATH) -> date:
    """The first verified round after today that is not yet a decision in the calendar."""
    rounds = json.loads(Path(rounds_path).read_text(encoding="utf-8"))
    if not rounds.get("verified"):
        raise ForecastLogError(f"{Path(rounds_path).name} is not marked verified; no target date can be logged")
    calendar = set(pd.to_datetime(pd.read_csv(calendar_path)["decision_date"]).dt.date)
    future = sorted(d for d in (date.fromisoformat(r["date"]) for r in rounds.get("rounds", []) if r.get("date"))
                    if d > today and d not in calendar)
    if not future:
        raise ForecastLogError("no upcoming decision date after today in config/forecast_rounds.json")
    return future[0]


def read_log(path: Path = LOG_PATH) -> list[dict[str, str]]:
    if not Path(path).is_file():
        return []
    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != COLUMNS:
            raise ForecastLogError(f"{Path(path).name}: columns must be {', '.join(COLUMNS)}")
        return list(reader)


def make_entry(now: datetime, target: date, artifact_path: Path = ARTIFACT_PATH, raw_dir: Path = RAW_DIR,
               calendar_path: Path = CALENDAR_PATH, root: Path = ROOT) -> dict[str, str]:
    artifact = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    latest = artifact["latest_prediction"]
    probabilities = latest["class_probabilities"]
    commit, worktree = git_state(root)
    based_on = latest["date"]
    return {
        "logged_at_utc": now.astimezone(timezone.utc).replace(microsecond=0).isoformat(),
        "target_decision_date": target.isoformat(),
        "based_on_decision": based_on,
        "factor_month": str(pd.Period(based_on, freq="M") - ASSUMED_LAG_MONTHS),
        "model": MODEL_LABEL,
        **{f"p_{name.lower()}": f"{float(probabilities[name]):.6f}" for name in CLASS_ORDER},
        "expected_score": f"{float(latest['expected_score']):.6f}",
        "git_commit": commit,
        "git_worktree": worktree,
        "artifact_sha256": normalized_sha256(artifact_path),
        "data_sha256": data_sha256(raw_dir, calendar_path),
    }


def append_forecast(now: datetime | None = None, log_path: Path = LOG_PATH, artifact_path: Path = ARTIFACT_PATH,
                    rounds_path: Path = ROUNDS_PATH, calendar_path: Path = CALENDAR_PATH, raw_dir: Path = RAW_DIR,
                    root: Path = ROOT, target: date | None = None) -> dict[str, str]:
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(timezone.utc).date()
    target = target or next_target_date(today, rounds_path, calendar_path)
    if target <= today:
        raise ForecastLogError(f"too late: the decision of {target} is not after today ({today})")
    calendar = set(pd.to_datetime(pd.read_csv(calendar_path)["decision_date"]).dt.date)
    if any(target <= day <= target + timedelta(days=MATCH_WINDOW_DAYS) for day in calendar):
        raise ForecastLogError(f"the decision for {target} is already in the decision calendar")
    entry = make_entry(now, target, artifact_path, raw_dir, calendar_path, root)
    existing = read_log(log_path)
    if any(row["target_decision_date"] == entry["target_decision_date"]
           and row["artifact_sha256"] == entry["artifact_sha256"] for row in existing):
        raise ForecastLogError(f"a forecast for {target} from this artifact is already logged")
    write_header = not Path(log_path).is_file()
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    with Path(log_path).open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        if write_header:
            writer.writeheader()
        writer.writerow(entry)
    return entry


# ------------------------------------------------------------------ scoring


def rps(probabilities: list[float], actual: str) -> float:
    observed = np.array([1.0 if name == actual else 0.0 for name in CLASS_ORDER])
    gap = np.cumsum(probabilities)[:2] - np.cumsum(observed)[:2]
    return float((gap ** 2).sum() / 2.0)


def score_log(log_path: Path = LOG_PATH, decisions_path: Path = DECISIONS_PATH) -> dict[str, Any]:
    rows = read_log(log_path)
    decisions = pd.read_csv(decisions_path, parse_dates=["decision_date"])
    decisions = decisions.dropna(subset=["decision"])
    scored = []
    for row in rows:
        target = pd.Timestamp(row["target_decision_date"])
        match = decisions[(decisions["decision_date"] >= target)
                          & (decisions["decision_date"] <= target + pd.Timedelta(days=MATCH_WINDOW_DAYS))]
        if match.empty:
            continue
        actual = str(match["decision"].iloc[0])
        probs = [float(row[f"p_{name.lower()}"]) for name in CLASS_ORDER]
        expected = float(row["expected_score"])
        hold = [0.0, 1.0, 0.0]
        scored.append({
            "target_decision_date": row["target_decision_date"], "logged_at_utc": row["logged_at_utc"],
            "effective_date": match["decision_date"].iloc[0].date().isoformat(), "actual": actual,
            "predicted_class": CLASS_ORDER[int(np.argmax(probs))], "hit": CLASS_ORDER[int(np.argmax(probs))] == actual,
            "rps_model": rps(probs, actual), "rps_always_hold": rps(hold, actual),
            "squared_error_model": (expected - SCORE[actual]) ** 2, "squared_error_always_hold": float(SCORE[actual] ** 2),
            "artifact_sha256": row["artifact_sha256"],
        })
    summary: dict[str, Any] = {"generated_by": "python run.py forecast-score", "n_logged": len(rows),
                               "n_scored": len(scored), "scored": scored,
                               "latest_logged": rows[-1] if rows else None}
    if scored:
        summary["rmse_model"] = float(np.sqrt(np.mean([s["squared_error_model"] for s in scored])))
        summary["rmse_always_hold"] = float(np.sqrt(np.mean([s["squared_error_always_hold"] for s in scored])))
        summary["mean_rps_model"] = float(np.mean([s["rps_model"] for s in scored]))
        summary["mean_rps_always_hold"] = float(np.mean([s["rps_always_hold"] for s in scored]))
        summary["hit_rate"] = float(np.mean([s["hit"] for s in scored]))
    return summary


def render_markdown(summary: dict[str, Any]) -> str:
    lines = ["# Logged forecasts and their scores", "",
             f"Forecasts logged before the decision (`docs/forecast_log.csv`): {summary['n_logged']}; scored "
             f"(decision now in the data): {summary['n_scored']}. Lower RPS and squared error are better. A forecast "
             "is matched with the first decision whose effective date falls on the logged (announcement) date or "
             f"within {MATCH_WINDOW_DAYS} days after it.", ""]
    if summary["n_scored"]:
        lines += ["| Target date | Effective date | Actual | Predicted class | Hit | RPS model | RPS Always Hold | "
                  "Sq. error model | Sq. error Always Hold |", "|---|---|---|---|---|---|---|---|---|"]
        for s in summary["scored"]:
            lines.append(f"| {s['target_decision_date']} | {s['effective_date']} | {s['actual']} | {s['predicted_class']} | "
                         f"{'yes' if s['hit'] else 'no'} | {s['rps_model']:.3f} | {s['rps_always_hold']:.3f} | "
                         f"{s['squared_error_model']:.3f} | {s['squared_error_always_hold']:.3f} |")
        lines += ["", f"Over {summary['n_scored']} scored forecasts: RMSE {summary['rmse_model']:.3f} (Always Hold "
                      f"{summary['rmse_always_hold']:.3f}); mean RPS {summary['mean_rps_model']:.3f} (Always Hold "
                      f"{summary['mean_rps_always_hold']:.3f}); hit rate {summary['hit_rate']:.3f}. The promotion rule "
                      "in `docs/development_plan.md` decides what, if anything, these numbers allow."]
    else:
        lines.append("No logged forecast has been scored yet.")
    lines += ["", "Generated by `python run.py forecast-score` (src/forecast_log.py).", ""]
    return "\n".join(lines)


def reality_check_score(summary: dict[str, Any], decisions_path: Path = DECISIONS_PATH,
                        artifact_path: Path = ARTIFACT_PATH) -> dict[str, Any] | None:
    """Блок F: pinball, покрытие 80% и RPS для преререгистрированной цели, когда решение есть в данных."""
    from src import prereg

    artifact = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    block = artifact.get("reality_check")
    scored = [s for s in summary["scored"] if s["target_decision_date"] == prereg.TARGET_DATE]
    if not block or not scored:
        return None
    decisions = pd.read_csv(decisions_path)
    rate = decisions.loc[decisions["decision_date"] == scored[0]["effective_date"], "base_rate_after"]
    return prereg.score_reality_check(block, float(rate.iloc[0]), scored[0]["actual"]) if len(rate) else None


def write_scores(log_path: Path = LOG_PATH, decisions_path: Path = DECISIONS_PATH, json_path: Path = SCORES_JSON,
                 md_path: Path = SCORES_MD) -> dict[str, Any]:
    summary = score_log(log_path, decisions_path)
    summary["reality_check_score"] = reality_check_score(summary, decisions_path)
    Path(json_path).parent.mkdir(parents=True, exist_ok=True)
    Path(json_path).write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    Path(md_path).parent.mkdir(parents=True, exist_ok=True)
    Path(md_path).write_text(render_markdown(summary), encoding="utf-8", newline="\n")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["log", "score"])
    args = parser.parse_args(argv)
    if args.action == "log":
        try:
            entry = append_forecast()
        except ForecastLogError as error:
            print(f"NOT LOGGED: {error}")
            return 1
        print(f"Logged forecast for {entry['target_decision_date']} at {entry['logged_at_utc']}: "
              f"P(Decrease) {entry['p_decrease']}, P(Hold) {entry['p_hold']}, P(Increase) {entry['p_increase']}, "
              f"expected score {entry['expected_score']}; artifact {entry['artifact_sha256'][:12]}, data "
              f"{entry['data_sha256'][:12]}, HEAD {entry['git_commit'][:12]} ({entry['git_worktree']}).")
        print("Commit and push docs/forecast_log.csv now: the GitHub commit is the external timestamp.")
    summary = write_scores()
    print(f"Forecast log: {summary['n_logged']} logged, {summary['n_scored']} scored "
          f"({SCORES_MD.relative_to(ROOT)}, {SCORES_JSON.relative_to(ROOT)}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
