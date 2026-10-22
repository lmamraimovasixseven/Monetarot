"""Propagate the student's fact forms: `python run.py facts` (or `python -m src.facts`).

Reads docs/facts_to_fill.csv (one row per raw series) and docs/facts_to_fill.md
(project facts), validates them, and regenerates every file that depends on them:

* data/raw/SOURCES.md              provenance fields (hashes recomputed; the raw CSVs are only read)
* data/processed/provenance.json   what the dashboard's provenance panel shows
* outputs/release_lag_check.md     assumed lag (config/release_lag.json) vs the real lags in the form
* docs/indicator_card.md, docs/decision_rule.md, docs/validity_facts.md
                                   rendered from docs/templates/ with outputs/numbers_for_note.json

Anything not filled in stays UNKNOWN. The estimation is never changed here.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd

from src.hashing import normalized_sha256
from src.ingest import FEATURE_RULES, LOG_GROWTH_FEATURES, assumed_release_lag_months


ROOT = Path(__file__).resolve().parents[1]
UNKNOWN = "UNKNOWN"
SERIES_COLUMNS = [
    "series_file", "publisher", "source_title", "table_or_series_identifier", "url_or_api_query", "navigation_path",
    "publication_date", "retrieval_date", "release_lag_days", "revised_after_release", "unit", "notes",
]
# Student statement about how every CSV in data/raw was produced (2026-10-18).
EXTRACTION_STATEMENT = ("CSV in data/raw extracted manually by the student from the downloaded Excel file: years and "
                        "months and the needed indicator only; sheet, rows and columns used: UNKNOWN")
SERIES_LABELS = {
    "publisher": "Publisher",
    "source_title": "Source title",
    "table_or_series_identifier": "Table or series identifier",
    "url_or_api_query": "URL or API query",
    "navigation_path": "Navigation path",
    "publication_date": "Publication date",
    "retrieval_date": "Retrieval date",
    "release_lag_days": "Release lag (days after the reference month ends)",
    "revised_after_release": "Revised after release",
    "unit": "Unit (form)",
    "notes": "Notes",
}
PROJECT_FIELDS = {
    "week2_indicator_name": "text",
    "indicator_suggested_by": "text",
    "indicator_suggested_on": "date",
    "indicator_suggested_where": "text",
    "indicator_written_proof": "text",
    "week2_approval_status": "text",
    "week2_indicator_equals_nbk_base_rate_decision": ("yes", "no", UNKNOWN),
    "sampling_approval_who": "text",
    "sampling_approval_when": "date",
    "sampling_approval_proof_location": "text",
    "spec_date_allowed_by": "text",
    "spec_date_allowed": "date",
    "spec_date_proof": "text",
    "spec_commit": "text",
    "named_user": "text",
    "decision_rule_option": ("1", "2", "3", UNKNOWN),
    "new_element": "text",
    "model_refit_scope": ("estimation_sample", "all_data", UNKNOWN),
}
TARGET_SERIES = "base_rate_history.csv"
FACTOR_LABELS = {
    "inflation": "Inflation", "exports": "Exports", "imports": "Imports",
    "corporate_lending": "Corporate lending", "household_lending": "Household lending", "consumption": "Consumption",
}
DATE_LIKE = re.compile(r"\b\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\b|\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_.:\-]+)\s*\}\}")
TEMPLATE_COMMENT = re.compile(r"\A<!--.*?-->\n", re.S)
GENERATED_DOCS = ["indicator_card.md", "decision_rule.md", "validity_facts.md", "data_audit.md"]
AUDITED_SERIES = "consumption_history_updated.csv"
AUDITED_FEATURE = "consumption"
# Every file build_all() produces, relative to the project root.
GENERATED_PATHS = ["data/raw/SOURCES.md", "data/processed/provenance.json", "outputs/release_lag_check.md",
                   *[f"docs/{name}" for name in GENERATED_DOCS], "docs/demo_script.md"]
# docs/demo_script.md is hand-written except for these blocks, which `python run.py facts` fills from the form,
# the release-lag data and outputs/numbers_for_note.json.
DEMO_BLOCK_NAMES = ["decision-rule", "lag-answer", "robustness-answer", "new-element", "q7-answer",
                    "rounds-answer", "hold-answer"]


def demo_block_pattern(name: str) -> re.Pattern[str]:
    return re.compile(rf"<!-- generated:{name}:start -->.*?<!-- generated:{name}:end -->", re.S)


DEMO_RULE_BLOCK = demo_block_pattern("decision-rule")
OPTION_COUNT = 3
UNNAMED_USER = "STUDENT_TO_NAME"


class FactsError(ValueError):
    """A form cell is missing, malformed, or not allowed."""


# --------------------------------------------------------------- validation


def _check_dates(text: str, where: str, today: date, errors: list[str]) -> None:
    for token in DATE_LIKE.findall(text):
        if not ISO_DATE.match(token):
            errors.append(f"{where}: '{token}' looks like a date; write dates as YYYY-MM-DD")
            continue
        try:
            parsed = date.fromisoformat(token)
        except ValueError:
            errors.append(f"{where}: '{token}' is not a valid calendar date")
            continue
        if parsed > today:
            errors.append(f"{where}: '{token}' is after today ({today.isoformat()})")


def _check_cell(value: str, kind, where: str, today: date, errors: list[str]) -> None:
    if value == "":
        errors.append(f"{where}: empty; write UNKNOWN if the fact is not known")
        return
    if "|" in value:
        errors.append(f"{where}: the '|' character is not allowed")
    if value == UNKNOWN:
        return
    if isinstance(kind, tuple):
        if value not in kind:
            errors.append(f"{where}: '{value}' is not one of {', '.join(kind)}")
    elif kind == "date":
        if not ISO_DATE.match(value):
            errors.append(f"{where}: '{value}' must be a date YYYY-MM-DD or UNKNOWN")
        else:
            _check_dates(value, where, today, errors)
    elif kind == "lag":
        if not re.fullmatch(r"\d+", value):
            errors.append(f"{where}: '{value}' must be a non-negative whole number of days or UNKNOWN")
    else:
        _check_dates(value, where, today, errors)


def load_series_facts(path: Path, raw_files: list[str], today: date) -> dict[str, dict[str, str]]:
    errors: list[str] = []
    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != SERIES_COLUMNS:
            raise FactsError(f"{Path(path).name}: columns must be {', '.join(SERIES_COLUMNS)}")
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    seen: dict[str, dict[str, str]] = {}
    kinds = {"retrieval_date": "date", "publication_date": "date", "release_lag_days": "lag",
             "revised_after_release": ("yes", "no", UNKNOWN)}
    for number, row in enumerate(rows, start=2):
        name = row["series_file"]
        if name not in raw_files:
            errors.append(f"{Path(path).name} row {number}: '{name}' is not a file in data/raw")
            continue
        if name in seen:
            errors.append(f"{Path(path).name} row {number}: '{name}' appears twice")
            continue
        for column in SERIES_COLUMNS[1:]:
            _check_cell(row[column], kinds.get(column, "text"), f"{Path(path).name} row {number} ({name}), column {column}",
                        today, errors)
        seen[name] = row
    missing = sorted(set(raw_files) - set(seen))
    if missing:
        errors.append(f"{Path(path).name}: no row for {', '.join(missing)}")
    if errors:
        raise FactsError("\n".join(errors))
    return {name: seen[name] for name in raw_files}


def load_project_facts(path: Path, today: date) -> dict[str, str]:
    errors: list[str] = []
    values: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\|\s*`([a-z0-9_]+)`\s*\|(.*)\|(.*)\|\s*$", line)
        if match and match.group(1) in PROJECT_FIELDS:
            values[match.group(1)] = match.group(2).strip()
    for field, kind in PROJECT_FIELDS.items():
        if field not in values:
            errors.append(f"{Path(path).name}: row for `{field}` is missing")
            continue
        _check_cell(values[field], kind, f"{Path(path).name}, field {field}", today, errors)
    if errors:
        raise FactsError("\n".join(errors))
    return {field: values[field] for field in PROJECT_FIELDS}


# ------------------------------------------------------------- release lags


def release_lag_rows(series: dict[str, dict[str, str]], decision_dates: pd.Series, assumed: int) -> list[dict]:
    """Compare the assumed month offset with each series' real lag, decision by decision."""
    dates = pd.to_datetime(decision_dates).reset_index(drop=True)
    reference_end = (dates.dt.to_period("M") - assumed).dt.end_time.dt.normalize()
    # Data count as available only if published strictly before the decision date.
    tolerated = int((dates - reference_end).dt.days.min()) - 1
    rows = []
    for feature, (filename, _) in FEATURE_RULES.items():
        lag = series[filename]["release_lag_days"]
        row = {"feature": feature, "series_file": filename, "assumed_months": assumed,
               "longest_lag_tolerated_days": tolerated, "real_lag_days": lag, "decisions": len(dates)}
        if lag == UNKNOWN:
            row.update(late=None, verdict="UNKNOWN: real lag not filled in")
        else:
            published = reference_end + pd.to_timedelta(int(lag), unit="D")
            late = int((published >= dates).sum())
            row.update(late=late, verdict=("holds for every decision" if late == 0
                                           else f"fails for {late} of {len(dates)} decisions"))
        rows.append(row)
    return rows


def release_lag_markdown(rows: list[dict], assumed: int, limitation: dict | None = None) -> str:
    table = ["| Factor | Series file | Assumed offset (months) | Longest real lag the offset tolerates (days) | "
             "Real lag from the form (days) | Decisions where data would not yet be published | Verdict |",
             "|---|---|---|---|---|---|---|"]
    for row in rows:
        table.append(f"| {FACTOR_LABELS[row['feature']]} | `{row['series_file']}` | {row['assumed_months']} | "
                     f"{row['longest_lag_tolerated_days']} | {row['real_lag_days']} | "
                     f"{UNKNOWN if row['late'] is None else row['late']} | {row['verdict']} |")
    known = [row for row in rows if row["late"] is not None]
    failing = [row for row in known if row["late"]]
    summary = (f"Real lags are filled in for {len(known)} of {len(rows)} factor series. "
               + ("The assumption cannot be checked for the others." if len(known) < len(rows) else "")
               + (f" It fails for: {', '.join(FACTOR_LABELS[r['feature']] for r in failing)}." if failing
                  else (" It holds for every series with a known lag." if known else "")))
    return "\n".join([
        "# Release-lag check: assumed vs real",
        "",
        f"The model aligns every factor to the calendar month {assumed} months before the decision month "
        "(`assumed_release_lag_months` in `config/release_lag.json`). Real lags come from `release_lag_days` in "
        "`docs/facts_to_fill.csv`: calendar days from the last day of the reference month to publication. "
        "A value counts as available only if it was published strictly before the decision date. Decisions are "
        "the usable rows of `data/processed/model_panel.csv`.",
        "",
        *table,
        "",
        summary.strip(),
        "",
        *(["## Upper bounds from file update dates", "",
           "The publication dates in the form are the last-update dates of the downloaded files, not first-release "
           "dates, so the lags below are only upper bounds (true release lag ≤ bound). They do not replace the "
           "real-lag check above.", "", _upper_bound_table(limitation), "", limitation["text"], ""]
          if limitation else []),
        "This check reports only. The estimation still uses the assumed offset; changing it requires an explicit "
        "decision and `python run.py model`.",
        "",
        "Generated by `python run.py facts`.",
        "",
    ])


# ---------------------------------------------------------------- rendering


def render(template: str, values: dict[str, str]) -> str:
    body = TEMPLATE_COMMENT.sub("", template)
    missing = sorted({key for key in PLACEHOLDER.findall(body) if key not in values})
    if missing:
        raise KeyError(f"Template uses unknown keys: {missing}")
    return PLACEHOLDER.sub(lambda match: values[match.group(1)], body)


def _code(value: str) -> str:
    return f"`{UNKNOWN}`" if value == UNKNOWN else value


def _provenance_block(row: dict[str, str]) -> str:
    lines = [f"- {label}: {_code(row[column]).rstrip('.')}." for column, label in SERIES_LABELS.items()]
    return "\n".join([*lines, f"- {EXTRACTION_STATEMENT}."])


def _coverage(raw_dir: Path, name: str) -> tuple[str, str]:
    months = pd.read_csv(raw_dir / name, usecols=["year_month"])["year_month"].astype(str)
    return months.min(), months.max()


CARD_SOURCE_COLUMNS = ["publisher", "source_title", "table_or_series_identifier", "url_or_api_query", "navigation_path",
                       "publication_date", "retrieval_date", "release_lag_days", "revised_after_release", "unit"]
CARD_SOURCE_HEADER = ["Series file", "Publisher", "Source title", "Identifier", "URL or API query", "Navigation path",
                      "Publication date", "Retrieval date", "Release lag (days)", "Revised after release", "Unit"]
FILL_CALLS = re.compile(r"\.(ffill|bfill|fillna|interpolate|pad|backfill)\(|method=[\"'](ffill|bfill|pad)")


def _sources_table(series: dict[str, dict[str, str]]) -> str:
    lines = ["| " + " | ".join(CARD_SOURCE_HEADER) + " |", "|" + "---|" * len(CARD_SOURCE_HEADER)]
    for name, row in series.items():
        lines.append(f"| `{name}` | " + " | ".join(row[column] for column in CARD_SOURCE_COLUMNS) + " |")
    notes = [f"- `{name}`: {row['notes']}" for name, row in series.items() if row["notes"] != UNKNOWN]
    return "\n".join(lines + (["", "Notes from the form:", "", *notes] if notes else []))


def parse_card_sources(text: str) -> dict[str, dict[str, str]]:
    """Read the sources table back out of docs/indicator_card.md."""
    rows = {}
    for line in text.splitlines():
        match = re.match(r"^\| `([^`]+\.csv)` \|(.*)\|$", line)
        if match:
            cells = [cell.strip() for cell in match.group(2).split("|")]
            if len(cells) == len(CARD_SOURCE_COLUMNS):
                rows[match.group(1)] = dict(zip(CARD_SOURCE_COLUMNS, cells))
    return rows


def parse_sources_md(text: str) -> dict[str, dict[str, str]]:
    """Read the per-file provenance fields back out of data/raw/SOURCES.md."""
    labels = {label: column for column, label in SERIES_LABELS.items()}
    rows: dict[str, dict[str, str]] = {}
    for section in re.split(r"(?m)^### ", text)[1:]:
        name = re.match(r"`([^`]+)`", section)
        if not name:
            continue
        fields = {}
        for label, column in labels.items():
            found = re.search(rf"^- {re.escape(label)}: (.*)\.$", section, re.M)
            if found:
                fields[column] = found.group(1).replace(f"`{UNKNOWN}`", UNKNOWN)
        rows[name.group(1)] = fields
    return rows


def series_audit(raw_dir: Path, name: str) -> dict:
    """Frequency facts for one raw file, computed from the file itself."""
    frame = pd.read_csv(raw_dir / name)
    value_column = [column for column in frame.columns if column != "year_month"][0]
    months = pd.PeriodIndex(pd.to_datetime(frame["year_month"], format="%Y-%m"), freq="M")
    full = pd.period_range(months.min(), months.max(), freq="M")
    values = frame[value_column]
    runs = values.groupby((values != values.shift(1)).cumsum()).size()
    unique_consecutive = months.is_unique and len(months) == len(full)
    return {
        "file": name, "column": value_column, "rows": len(frame), "first": str(months.min()), "last": str(months.max()),
        "missing_months": len(set(full) - set(months)), "duplicate_months": int(months.duplicated().sum()),
        "frequency": "monthly, every calendar month present" if unique_consecutive else "monthly labels with gaps",
        "repeats": int((values == values.shift(1)).sum()), "pairs": len(values) - 1, "longest_run": int(runs.max()),
    }


_SCALES = {"thousand": "thousand", "thousands": "thousand", "mln": "million", "million": "million",
           "millions": "million", "bln": "billion", "billion": "billion"}
_CURRENCIES = {"usd": "USD", "dollar": "USD", "dollars": "USD", "kzt": "KZT", "tenge": "KZT"}


def _parse_unit(text: str) -> dict:
    words = re.findall(r"[a-z]+", text.lower().replace("year-on-year", "yoy"))
    return {
        "scale": next((_SCALES[word] for word in words if word in _SCALES), None),
        "currency": next((_CURRENCIES[word] for word in words if word in _CURRENCIES), None),
        "yoy": "yoy" in words,
    }


def unit_check(raw_dir: Path, name: str, form_unit: str) -> dict:
    """Compare the unit in the form with the hint in the CSV column name. Neither side is changed."""
    column = [c for c in pd.read_csv(raw_dir / name, nrows=0).columns if c != "year_month"][0]
    hint = _parse_unit(column)
    hint_text = (" ".join(part for part in (hint["scale"], hint["currency"]) if part)
                 or ("year-on-year" if hint["yoy"] else ""))
    result = {"column": column, "form": form_unit, "header_hint": hint_text or "none"}
    if form_unit == UNKNOWN:
        result["verdict"] = "not checked: unit UNKNOWN in the form"
        return result
    form = _parse_unit(form_unit)
    if not hint_text:
        result["verdict"] = "no unit hint in the column name to compare"
    elif hint["yoy"] and not (hint["scale"] or hint["currency"]):
        result["verdict"] = "agrees (year-on-year)" if form["yoy"] else "CONFLICT: header says year-on-year"
    elif hint["currency"] and form["currency"] and hint["currency"] != form["currency"]:
        result["verdict"] = f"CONFLICT: currency (form {form['currency']}, header {hint['currency']})"
    elif hint["scale"] and form["scale"] and hint["scale"] != form["scale"]:
        result["verdict"] = f"CONFLICT: scale (form {form['scale']}, header {hint['scale']})"
    elif hint["scale"] and not form["scale"]:
        result["verdict"] = f"currency agrees; scale not stated in the form (header says {hint['scale']})"
    else:
        result["verdict"] = "agrees"
    return result


def _unit_line(check: dict) -> str:
    form = f"`{UNKNOWN}`" if check["form"] == UNKNOWN else check["form"]
    return (f"- Unit (form, student statement): {form}; column `{check['column']}` hint: {check['header_hint']}; "
            f"check: {check['verdict']}. Neither the form nor the CSV header is changed.")


def _units_table(checks: dict[str, dict]) -> str:
    lines = ["| Raw file | Unit (form) | Column name | Hint in column name | Check |", "|---|---|---|---|---|"]
    for name, check in checks.items():
        lines.append(f"| `{name}` | {check['form']} | `{check['column']}` | {check['header_hint']} | {check['verdict']} |")
    return "\n".join(lines)


def release_lag_limitation(series: dict[str, dict[str, str]], raw_dir: Path, decision_dates: pd.Series,
                           assumed: int, tolerated: int, numbers: dict) -> dict:
    """Upper bounds from file update dates vs the M-minus-assumed availability window, and the limitation text.

    A file's update date is not the first release of its last month, so the computed lag is only an upper
    bound on the true release lag. Nothing here changes the estimation.
    """
    dates = pd.to_datetime(decision_dates).reset_index(drop=True)
    windows = (dates - (dates.dt.to_period("M") - assumed).dt.end_time.dt.normalize()).dt.days
    total = len(windows)
    median = float(windows.median())
    rows = []
    for feature, (filename, _) in FEATURE_RULES.items():
        published = series[filename]["publication_date"]
        last = pd.read_csv(raw_dir / filename, usecols=["year_month"])["year_month"].astype(str).max()
        bound = None if published == UNKNOWN else (date.fromisoformat(published) - pd.Period(last, "M").end_time.date()).days
        exceeded = None if bound is None else int((windows < bound).sum())
        rows.append({"feature": feature, "series_file": filename, "last_month": last, "file_update_date": published,
                     "upper_bound_days": bound, "decisions_where_bound_exceeds_window": exceeded})

    def label(feature: str) -> str:
        return FACTOR_LABELS[feature].lower()

    def joined(names: list[str]) -> str:
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]

    bounds_text = "; ".join(
        f"{label(r['feature'])} {r['upper_bound_days']} day{'s' if r['upper_bound_days'] != 1 else ''}"
        if r["upper_bound_days"] is not None else f"{label(r['feature'])} UNKNOWN" for r in rows)
    groups: dict[int, list[str]] = {}
    for r in rows:
        if r["decisions_where_bound_exceeds_window"]:
            groups.setdefault(r["decisions_where_bound_exceeds_window"], []).append(label(r["feature"]))
    phrases = [f"{joined(names)} at every decision ({count} of {total})" if count == total
               else f"{joined(names)} at decisions early in the month ({count} of {total})"
               for count, names in sorted(groups.items(), reverse=True)]
    unknown = [label(r["feature"]) for r in rows if r["upper_bound_days"] is None]
    look_ahead = ("Possible look-ahead cannot be ruled out for " + "; ".join(phrases) + "."
                  if phrases else "No upper bound exceeds the shortest window.")
    if unknown:
        look_ahead += f" No upper bound is available for {joined(unknown)}."
    n = numbers["numbers"]
    text = (
        f"Real release lags are UNKNOWN. The model assumes data for month M−{assumed} are available at a decision "
        f"in month M, which leaves about {int(round(median / 5) * 5)} days (median {median:g}; {windows.min()} to "
        f"{windows.max()} across decisions); `outputs/release_lag_check.md` uses the stricter shortest window minus "
        f"one day ({tolerated} days). File update dates give only upper bounds on the release lag (true lag ≤ "
        f"bound): {bounds_text}. {look_ahead} The nearest existing check is RB07 "
        f"(\"{n['robustness_RB07_name']['display']}\", which shifts all factors): benchmark winner "
        f"{n['robustness_RB07_benchmark_conclusion']['display']}, survives {n['robustness_RB07_survives']['display']}; "
        f"a check that shifts only the trade series was not run. Revision status of all series is UNKNOWN.")
    return {"text": text, "assumed_release_lag_months": assumed, "decisions": total,
            "window_days": {"min": int(windows.min()), "median": median, "max": int(windows.max())},
            "strict_tolerance_days": tolerated, "series": rows}


def _upper_bound_table(limitation: dict) -> str:
    lines = ["| Factor | Last month in CSV | File update date | Upper bound on release lag (days) | "
             "Decisions where the bound exceeds the window |", "|---|---|---|---|---|"]
    for r in limitation["series"]:
        count = r["decisions_where_bound_exceeds_window"]
        lines.append(f"| {FACTOR_LABELS[r['feature']]} | {r['last_month']} | {r['file_update_date']} | "
                     f"{UNKNOWN if r['upper_bound_days'] is None else r['upper_bound_days']} | "
                     f"{UNKNOWN if count is None else f'{count} of {limitation['decisions']}'} |")
    return "\n".join(lines)


def power_block(numbers: dict) -> dict:
    """The power table as shown in outputs/power_note.md, copied from numbers_for_note.json for the dashboard."""
    n = numbers["numbers"]
    if "power_multiplier" not in n:
        return {}
    return {
        "source": "outputs/power_note.md (values from outputs/numbers_for_note.json)",
        "n_estimation": n["n_estimation"]["display"],
        "rows": [{"feature": feature, "estimate": n[f"coef_{feature}"]["display"],
                  "se": n[f"se_{feature}"]["display"], "mde": n[f"power_{feature}_mde"]["display"]}
                 for feature in FEATURE_RULES],
    }


def chosen_decision_rule(rule_doc: str, option: str, named_user: str) -> dict | None:
    """The chosen option's title, rule and today's status, read from the generated docs/decision_rule.md."""
    if option == UNKNOWN:
        return None
    section = rule_doc.split(f"## Option {option}:", 1)[1].split("\n## ", 1)[0]
    title = section.splitlines()[0].strip()
    found = {key: re.search(rf"^- \*\*{key}:\*\* (.*)$", section, re.M) for key in ("Rule", "Today")}
    return {"option": option, "title": title, "named_user": named_user,
            "rule": found["Rule"].group(1) if found["Rule"] else UNKNOWN,
            "today": found["Today"].group(1) if found["Today"] else UNKNOWN,
            "source": "docs/decision_rule.md"}


def _count_summary(values) -> str:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (item[0] == UNKNOWN, -item[1], item[0]))
    return "; ".join(f"{value} ({count} file{'s' if count != 1 else ''})" for value, count in ordered)


def _frequency_table(audits: list[dict]) -> str:
    lines = ["| Raw file | Column | Rows | First month | Last month | Missing months | Frequency |",
             "|---|---|---|---|---|---|---|"]
    for item in audits:
        lines.append(f"| `{item['file']}` | `{item['column']}` | {item['rows']} | {item['first']} | {item['last']} | "
                     f"{item['missing_months']} | {item['frequency']} |")
    return "\n".join(lines)


def provenance_consistency(root: Path = ROOT) -> list[tuple[str, bool, str]]:
    """Compare form, SOURCES.md, the indicator card and the dashboard panel field by field."""
    from src.app import PROVENANCE_COLUMNS, provenance_table

    raw_files = sorted(path.name for path in (root / "data" / "raw").glob("*.csv"))
    form = load_series_facts(root / "docs" / "facts_to_fill.csv", raw_files, date.today())
    sources = parse_sources_md((root / "data" / "raw" / "SOURCES.md").read_text(encoding="utf-8"))
    card = parse_card_sources((root / "docs" / "indicator_card.md").read_text(encoding="utf-8"))
    provenance = json.loads((root / "data" / "processed" / "provenance.json").read_text(encoding="utf-8"))
    panel_frame = provenance_table(provenance)
    label_to_column = {label: column for column, label in PROVENANCE_COLUMNS}
    panel = {row["Series file"]: {label_to_column[k]: v for k, v in row.items() if k in label_to_column}
             for row in panel_frame.to_dict(orient="records")}
    results = []
    for name in raw_files:
        problems = []
        for column in CARD_SOURCE_COLUMNS:
            expected = form[name][column]
            for where, table in (("SOURCES.md", sources), ("indicator card", card), ("app panel", panel)):
                shown = table.get(name, {}).get(column)
                if shown != expected:
                    problems.append(f"{where} {column}={shown!r} vs form {expected!r}")
        results.append((name, not problems, "; ".join(problems) or "form, SOURCES.md, card and app panel agree"))
    return results


def _transformations_table() -> str:
    lines = ["| Factor | Raw file | Transformation (function in `src/ingest.py`) |", "|---|---|---|"]
    for feature, (filename, column) in FEATURE_RULES.items():
        steps = ("`read_monthly_series` → `complete_month_calendar` → `log_level` → `log_growth_12m` "
                 "(100 × 12-month log change) → `apply_release_lag`" if feature in LOG_GROWTH_FEATURES
                 else "`read_monthly_series` → level, no transformation → `apply_release_lag`")
        lines.append(f"| {FACTOR_LABELS[feature]} | `{filename}` (`{column}`) | {steps} |")
    lines.append("| Decision (target) | `base_rate_history.csv` (`rate`) | `build_base_rate_targets` (rate after vs "
                 "before → Increase / Hold / Decrease) → score −1 / 0 / +1 in `build_model_panel` |")
    return "\n".join(lines)


def _coverage_table(raw_dir: Path, names: list[str]) -> str:
    lines = ["| Raw file | First month | Last month |", "|---|---|---|"]
    for name in names:
        first, last = _coverage(raw_dir, name)
        lines.append(f"| `{name}` | {first} | {last} |")
    return "\n".join(lines)


def _rule_values(numbers: dict) -> dict[str, str]:
    """Whether each decision-rule option would trigger on the latest artifact values."""
    value = lambda key: numbers[key]["value"]  # noqa: E731
    band_clear = value("headline_score_band_low") > 0 or value("headline_score_band_high") < 0
    moved = abs(value("latest_score_change")) > value("econ_typical_score_move")
    probabilities = {label: value(f"next_round_probability_{label}") for label in ("increase", "hold", "decrease")}
    top = max(probabilities, key=probabilities.get)
    return {
        "r.option1_triggered": "yes" if band_clear else "no",
        "r.option2_triggered": "yes" if moved else "no",
        "r.option3_triggered": "yes" if top != "hold" else "no",
        "r.option3_top_class": top.title(),
    }


def build_all(root: Path = ROOT, numbers_path: Path | None = None, today: date | None = None) -> dict[str, str]:
    """Return {relative output path: content} for every file generated from the forms."""
    root = Path(root)
    today = today or date.today()
    raw_dir = root / "data" / "raw"
    raw_files = sorted(path.name for path in raw_dir.glob("*.csv"))
    series = load_series_facts(root / "docs" / "facts_to_fill.csv", raw_files, today)
    project = load_project_facts(root / "docs" / "facts_to_fill.md", today)
    assumed = assumed_release_lag_months(root / "config" / "release_lag.json")
    numbers = json.loads(Path(numbers_path or root / "outputs" / "numbers_for_note.json").read_text(encoding="utf-8"))
    panel = pd.read_csv(root / "data" / "processed" / "model_panel.csv", parse_dates=["decision_date"])
    usable = panel.dropna(subset=list(FEATURE_RULES) + ["y"])
    lag_rows = release_lag_rows(series, usable["decision_date"], assumed)
    limitation = release_lag_limitation(series, raw_dir, usable["decision_date"], assumed,
                                        lag_rows[0]["longest_lag_tolerated_days"], numbers)

    unit_checks = {name: unit_check(raw_dir, name, series[name]["unit"]) for name in raw_files}
    filled = sum(row[column] != UNKNOWN for row in series.values() for column in SERIES_COLUMNS[1:])
    total = len(series) * (len(SERIES_COLUMNS) - 1)
    values: dict[str, str] = {
        "provenance_summary": (
            f"Provenance fields below are generated from `docs/facts_to_fill.csv` by `python run.py facts`; "
            f"{filled} of {total} cells are filled in and the rest are `UNKNOWN`. Shared-publisher status is not "
            f"part of the form. Units in the form are compared with the column-name hints in each file section."),
    }
    for name in raw_files:
        values[f"provenance:{name}"] = _provenance_block(series[name])
        values[f"sha256:{name}"] = normalized_sha256(raw_dir / name)
        values[f"unit:{name}"] = _unit_line(unit_checks[name])
    sources = render((root / "docs" / "templates" / "SOURCES.template.md").read_text(encoding="utf-8"), values)

    provenance = {
        "generated_by": "python run.py facts",
        "forms": ["docs/facts_to_fill.csv", "docs/facts_to_fill.md"],
        "assumed_release_lag_months": assumed,
        "release_lag_definition": "calendar days from the last day of the reference month to publication",
        "series": [series[name] for name in raw_files],
        "project": project,
        "release_lag_check": [{key: row[key] for key in ("feature", "series_file", "real_lag_days", "verdict")}
                              for row in lag_rows],
        "release_lag_limitation": limitation,
        "power": power_block(numbers),
    }

    doc_values = {f"n.{key}": entry["display"] for key, entry in numbers["numbers"].items()}
    doc_values["n.verdict_sentence"] = numbers["verdict_sentence"]
    doc_values |= {f"f.{key}": value for key, value in project.items()}
    known_lags = [row for row in lag_rows if row["late"] is not None]
    doc_values |= {
        "r.assumed_lag_months": str(assumed),
        "r.longest_lag_tolerated_days": str(lag_rows[0]["longest_lag_tolerated_days"]),
        "r.real_lags_known": str(len(known_lags)),
        "r.factor_series_count": str(len(lag_rows)),
        "r.release_lag_failures": ", ".join(FACTOR_LABELS[r["feature"]] for r in known_lags if r["late"]) or "none",
        "r.sources_table": _sources_table(series),
        "r.transformations_table": _transformations_table(),
        "r.coverage_table": _coverage_table(raw_dir, raw_files),
        "r.series_filled_cells": str(filled),
        "r.series_total_cells": str(total),
        "r.target_publisher": series[TARGET_SERIES]["publisher"],
        "r.revised_known": str(sum(row["revised_after_release"] != UNKNOWN for row in series.values())),
        "r.raw_file_count": str(len(raw_files)),
        "r.lag_limitation": limitation["text"],
        "r.upper_bound_table": _upper_bound_table(limitation),
    }
    doc_values |= _rule_values(numbers["numbers"])
    for number in range(1, OPTION_COUNT + 1):
        chosen = project["decision_rule_option"] == str(number)
        doc_values[f"r.option{number}_user"] = project["named_user"] if chosen else UNNAMED_USER

    # Data audit: frequency facts from the raw files, alignment facts from data/processed and src/ingest.py.
    audits = [series_audit(raw_dir, name) for name in raw_files]
    audited = next(item for item in audits if item["file"] == AUDITED_SERIES)
    raw_series = pd.read_csv(raw_dir / AUDITED_SERIES)
    lookup = dict(zip(raw_series["year_month"].astype(str), raw_series[audited["column"]]))
    reference = (usable["decision_date"].dt.to_period("M") - assumed).astype(str)
    mismatches = sum(lookup.get(ref) != value for ref, value in zip(reference, usable[AUDITED_FEATURE]))
    shared = reference.value_counts()
    ingest_source = (ROOT / "src" / "ingest.py").read_text(encoding="utf-8")  # audits the code, not the data
    fill_calls = sorted({match.group(0) for match in FILL_CALLS.finditer(ingest_source)})
    doc_values |= {
        "r.frequency_table": _frequency_table(audits),
        "r.audit_file": AUDITED_SERIES,
        "r.audit_column": audited["column"],
        "r.audit_rows": str(audited["rows"]),
        "r.audit_first": audited["first"],
        "r.audit_last": audited["last"],
        "r.audit_missing_months": str(audited["missing_months"]),
        "r.audit_duplicate_months": str(audited["duplicate_months"]),
        "r.audit_frequency": audited["frequency"],
        "r.audit_repeats": str(audited["repeats"]),
        "r.audit_pairs": str(audited["pairs"]),
        "r.audit_longest_run": str(audited["longest_run"]),
        "r.audit_decisions": str(len(usable)),
        "r.audit_mismatches": str(mismatches),
        "r.audit_shared_months": str(int((shared > 1).sum())),
        "r.audit_shared_decisions": str(int(shared[shared > 1].sum())),
        "r.fill_calls_in_ingest": ", ".join(f"`{call}`" for call in fill_calls) or "none",
        "r.audit_form_notes": series[AUDITED_SERIES]["notes"],
        "r.audit_form_publisher": series[AUDITED_SERIES]["publisher"],
        "r.audit_form_url": series[AUDITED_SERIES]["url_or_api_query"],
        "r.audit_form_retrieval": series[AUDITED_SERIES]["retrieval_date"],
        "r.audit_form_lag": series[AUDITED_SERIES]["release_lag_days"],
        "r.units_table": _units_table(unit_checks),
        "r.units_summary": "; ".join(f"`{name}`: {check['form']}" for name, check in unit_checks.items()),
        "r.units_recorded": str(sum(check["form"] != UNKNOWN for check in unit_checks.values())),
        "r.unit_conflicts": ", ".join(f"`{name}` ({check['verdict']})" for name, check in unit_checks.items()
                                      if check["verdict"].startswith("CONFLICT")) or "none",
        "r.unit_scale_unstated": ", ".join(f"`{name}`" for name, check in unit_checks.items()
                                           if check["verdict"].startswith("currency agrees")) or "none",
        "r.fill_verdict": ("**No interpolation and no forward or backward fill** is applied in the ingest path."
                           if not fill_calls else "**Fill or interpolation calls exist** in the ingest path (listed above)."),
        "r.fill_short": "no interpolation or fill" if not fill_calls else "fill or interpolation present (see data audit)",
        "r.monthly_complete_files": str(sum(item["frequency"].startswith("monthly, every") for item in audits)),
        "r.publisher_summary": _count_summary(row["publisher"] for row in series.values()),
        "r.retrieval_summary": _count_summary(row["retrieval_date"] for row in series.values()),
    }

    outputs = {
        "data/raw/SOURCES.md": sources,
        "data/processed/provenance.json": "",
        "outputs/release_lag_check.md": release_lag_markdown(lag_rows, assumed, limitation),
    }
    for name in GENERATED_DOCS:
        template = (root / "docs" / "templates" / f"{name.removesuffix('.md')}.template.md").read_text(encoding="utf-8")
        header = f"<!-- Generated by `python run.py facts` from docs/templates/{name.removesuffix('.md')}.template.md; do not edit by hand. -->\n"
        outputs[f"docs/{name}"] = header + render(template, doc_values)
    # The dashboard shows the chosen rule exactly as the generated decision-rule document states it.
    provenance["decision_rule"] = chosen_decision_rule(outputs["docs/decision_rule.md"],
                                                       project["decision_rule_option"], project["named_user"])
    outputs["data/processed/provenance.json"] = json.dumps(provenance, indent=2, ensure_ascii=False) + "\n"
    outputs["docs/demo_script.md"] = demo_script_blocks(
        (root / "docs" / "demo_script.md").read_text(encoding="utf-8"), {
            "decision-rule": demo_rule_sentence(provenance["decision_rule"]),
            "lag-answer": demo_lag_answer(limitation, numbers),
            "robustness-answer": demo_robustness_answer(numbers),
            "new-element": demo_new_element(project),
            "q7-answer": demo_factor_answer(numbers),
            "rounds-answer": demo_rounds_answer(numbers, assumed),
            "hold-answer": demo_hold_answer(root / "data" / "processed" / "nbk_decisions_clean.csv"),
        })
    return outputs


def demo_lag_answer(limitation: dict, numbers: dict) -> str:
    """Q3 of the demo: built from the computed upper bounds and RB07's existing entries, never typed."""
    total = limitation["decisions"]
    window = limitation["window_days"]
    groups: dict[tuple[int, int], list[str]] = {}
    for row in limitation["series"]:
        count = row["decisions_where_bound_exceeds_window"]
        if count:
            groups.setdefault((count, row["upper_bound_days"]), []).append(FACTOR_LABELS[row["feature"]].lower())
    parts = []
    for (count, bound), names in sorted(groups.items(), reverse=True):
        who = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        where = (f"at every decision ({count} of {total})" if count == total
                 else f"at decisions early in the month ({count} of {total})")
        verb = "exceed" if len(names) > 1 else "exceeds"
        parts.append(f"{who} ({bound} days) {verb} the assumed availability {where}")
    exceed = ("; ".join(parts) + ", so look-ahead cannot be ruled out there") if parts else (
        "no upper bound exceeds the assumed availability")
    rb07 = numbers["numbers"]["robustness_RB07_name"]["display"]
    return (f"It cannot be ruled out. Real release lags are UNKNOWN, and file update dates give only upper bounds "
            f"(true lag ≤ bound). The model assumes data for month M−{limitation['assumed_release_lag_months']} are "
            f"available at a decision in month M, about {int(round(window['median'] / 5) * 5)} days later "
            f"(median {window['median']:g}; {window['min']} to {window['max']}); {exceed}. The nearest existing "
            f"check is RB07 (\"{rb07}\"), which shifts all factors; a check that shifts only the trade series was not "
            f"run (`outputs/release_lag_check.md`, `outputs/robustness_table_short.md`).")


def demo_robustness_answer(numbers: dict) -> str:
    """Q8 of the demo, from the same numbers as outputs/robustness_table_short.md."""
    n = numbers["numbers"]
    verb = "reproduces" if n["robustness_survivor_count"]["value"] == 1 else "reproduce"
    return (f"No: in {n['robustness_flipped_benchmark_count']['display']} of {n['robustness_check_count']['display']} "
            f"checks the model beats Always Hold on that check's own holdout, and only "
            f"{n['robustness_survivors']['display']} {verb} both the signs and the conclusion "
            f"(`outputs/robustness_table_short.md`).")


def demo_factor_answer(numbers: dict) -> str:
    """Q7 of the demo: the significant factor and what happens to it in RB09, from numbers_for_note.json."""
    n = numbers["numbers"]
    d = lambda key: n[key]["display"]  # noqa: E731
    answer = (f"Only household lending is significant after Holm adjustment (raw p {d('p_raw_household_lending')}, "
              f"Holm p {d('p_holm_household_lending')}; `outputs/results_table.md`), and it is the only one-SD move "
              f"that is economically meaningful by the stated rule (`outputs/economic_size.md`). In RB09 "
              f"(\"{d('robustness_RB09_name')}\") its coefficient is {d('robustness_RB09_household_lending_coef')} "
              f"(raw p {d('robustness_RB09_household_lending_p_raw')}, Holm p "
              f"{d('robustness_RB09_household_lending_p_holm')}; `outputs/robustness_table.md`)")
    if n["robustness_RB09_household_lending_loses_significance"]["value"] == "yes":
        return answer + ", so the only significant factor loses significance when its non-stationarity is removed."
    return answer + "."


def demo_rounds_answer(numbers: dict, assumed: int) -> str:
    """Why both rounds are identical: same latest factor values (data month = latest decision month - lag)."""
    latest = numbers["numbers"]["latest_decision_date"]["value"]
    month = (pd.Period(latest, "M") - assumed).strftime("%Y-%m") if latest != UNKNOWN else UNKNOWN
    return (f"Both rounds use the latest available factor values (factor data month {month}), because future factor "
            f"values are unknown, so both blocks are the same conditional estimate and only the date differs; this is "
            f"not an error and not a separate forecast for each date (the \"Why these probabilities?\" panel on the "
            f"Overview tab).")


def demo_hold_answer(decisions_path: Path) -> str:
    """Why Hold dominates: counts from data/processed/nbk_decisions_clean.csv, as in the dashboard panel."""
    if not Path(decisions_path).is_file():
        return "UNKNOWN (data/processed/nbk_decisions_clean.csv is missing)."
    counts = pd.read_csv(decisions_path)["decision"].astype(str).str.strip().str.title().value_counts()
    hold, total = int(counts.get("Hold", 0)), int(counts.sum())
    if counts.idxmax() != "Hold":
        return f"It does not: Hold was {hold} of {total} decisions, and the most common decision was {counts.idxmax()}."
    return (f"Hold was the most common NBK decision in the sample ({hold} of {total} decisions in "
            f"`data/processed/nbk_decisions_clean.csv`), so Hold gets the highest probability and always predicting Hold "
            f"is hard to beat (`outputs/oos_comparison.md`).")


def demo_new_element(project: dict) -> str:
    """Q17 of the demo: the new-element sentence exactly as recorded in the form."""
    value = project.get("new_element", UNKNOWN)
    if value == UNKNOWN:
        return "Not recorded yet: `new_element` in `docs/facts_to_fill.md` is UNKNOWN."
    return value


def demo_script_blocks(text: str, contents: dict[str, str]) -> str:
    for name in DEMO_BLOCK_NAMES:
        pattern = demo_block_pattern(name)
        if not pattern.search(text):
            raise FactsError(f"docs/demo_script.md has no generated {name} block")
        block = f"<!-- generated:{name}:start -->{contents[name]}<!-- generated:{name}:end -->"
        text = pattern.sub(lambda _: block, text, count=1)
    return text


def demo_rule_sentence(rule: dict | None) -> str:
    """The demo step for the decision rule, built from the chosen option and named user in the form."""
    if not rule:
        return ("No option is chosen yet: record `decision_rule_option` in `docs/facts_to_fill.md`, then state that "
                "rule in the form \"if the indicator moves beyond X, do Y, because Z\" as a monitoring rule, not a forecast.")
    return (f"State the chosen rule: option {rule['option']}, {rule['title']} (`decision_rule_option` in "
            f"`docs/facts_to_fill.md`), for the named user, {rule['named_user']}. Say it in the form \"if the "
            f"indicator moves beyond X, do Y, because Z\" as worded in `docs/decision_rule.md`, read today's status "
            f"from the screen, and say that it is a monitoring rule, not a forecast.")


def demo_script_with_rule(text: str, rule: dict | None) -> str:
    if not DEMO_RULE_BLOCK.search(text):
        raise FactsError("docs/demo_script.md has no generated decision-rule block")
    block = f"<!-- generated:decision-rule:start -->{demo_rule_sentence(rule)}<!-- generated:decision-rule:end -->"
    return DEMO_RULE_BLOCK.sub(lambda _: block, text, count=1)


def write_all(outputs: dict[str, str], root: Path = ROOT) -> None:
    for relative, content in outputs.items():
        path = Path(root) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the fact forms and regenerate the files that use them.")
    parser.parse_args(argv)
    try:
        outputs = build_all()
    except FactsError as error:
        print("The fact forms have errors; nothing was written:\n" + str(error))
        return 1
    write_all(outputs)
    for relative in outputs:
        print(f"Wrote {relative}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
