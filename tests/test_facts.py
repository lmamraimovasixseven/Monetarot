"""Tests for the fact forms and everything generated from them (src.facts). Temp copies only."""

from __future__ import annotations

import csv
import json
import re
import shutil
from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import check, facts, ingest
from src.hashing import normalized_sha256


ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 17)
GENERATED = facts.GENERATED_PATHS
# Non-result digits allowed in the doc templates.
TEMPLATE_LITERALS = {"0", "1", "2", "3", "12", "95", "100",  # 1-3 are also option labels
                     "2015", "2022"}  # devaluation years in the validity bullet the student specified


@pytest.fixture
def root(tmp_path):
    """A temporary project tree holding copies of everything src.facts reads."""
    for relative in ("docs/facts_to_fill.csv", "docs/facts_to_fill.md", "config/release_lag.json", "docs/demo_script.md",
                     "data/processed/model_panel.csv", "data/processed/nbk_decisions_clean.csv",
                     "outputs/numbers_for_note.json"):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, tmp_path / relative)
    shutil.copytree(ROOT / "docs" / "templates", tmp_path / "docs" / "templates")
    (tmp_path / "data" / "raw").mkdir(parents=True)
    for path in (ROOT / "data" / "raw").glob("*.csv"):
        shutil.copy2(path, tmp_path / "data" / "raw" / path.name)
    return tmp_path


def _edit_series(root: Path, name: str, **values: str) -> None:
    path = root / "docs" / "facts_to_fill.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if row["series_file"] == name:
            row.update(values)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=facts.SERIES_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _edit_project(root: Path, field: str, value: str) -> None:
    path = root / "docs" / "facts_to_fill.md"
    text = path.read_text(encoding="utf-8")
    text, count = re.subn(rf"(\| `{field}` \|)[^|]*(\|)", rf"\g<1> {value} \g<2>", text)
    assert count == 1
    path.write_text(text, encoding="utf-8")


def test_committed_generated_files_match_the_forms():
    outputs = facts.build_all(ROOT)
    assert sorted(outputs) == sorted(GENERATED)
    for relative, content in outputs.items():
        assert (ROOT / relative).read_text(encoding="utf-8").replace("\r\n", "\n") == content, (
            f"{relative} is stale; run `python run.py facts`")


def test_forms_cover_all_seven_raw_series_and_start_unknown():
    with (ROOT / "docs" / "facts_to_fill.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert sorted(row["series_file"] for row in rows) == sorted(p.name for p in (ROOT / "data" / "raw").glob("*.csv"))
    assert len(rows) == 7
    assert list(rows[0]) == facts.SERIES_COLUMNS
    project = facts.load_project_facts(ROOT / "docs" / "facts_to_fill.md", TODAY)
    assert set(project) == set(facts.PROJECT_FIELDS)


def _blank_series(root: Path) -> None:
    for path in (root / "data" / "raw").glob("*.csv"):
        _edit_series(root, path.name, **{column: "UNKNOWN" for column in facts.SERIES_COLUMNS[1:]})


def test_unknown_forms_keep_every_provenance_field_unknown_and_hashes(root):
    _blank_series(root)
    outputs = facts.build_all(root, today=TODAY)
    sources = outputs["data/raw/SOURCES.md"]
    for path in (root / "data" / "raw").glob("*.csv"):
        assert normalized_sha256(path) in sources
    assert "## Pre-cleaning disclosure" in sources
    assert sources.count("- Publisher: `UNKNOWN`.") == 7
    provenance = json.loads(outputs["data/processed/provenance.json"])
    assert all(value == "UNKNOWN" for row in provenance["series"] for key, value in row.items() if key != "series_file")
    assert provenance["assumed_release_lag_months"] == ingest.assumed_release_lag_months(root / "config/release_lag.json")
    assert "real lag not filled in" in outputs["outputs/release_lag_check.md"]


def test_filled_cells_propagate_to_sources_provenance_card_and_lag_check(root):
    _blank_series(root)
    _edit_series(root, "inflation_history.csv", publisher="Example Publisher (test value)",
                 retrieval_date="2026-01-15", release_lag_days="10", revised_after_release="no")
    _edit_series(root, "export_history.csv", release_lag_days="45")
    _edit_project(root, "named_user", "Example user (test value)")
    outputs = facts.build_all(root, today=TODAY)
    sources = outputs["data/raw/SOURCES.md"]
    inflation_section = sources.split("### `inflation_history.csv`")[1].split("###")[0]
    assert "- Publisher: Example Publisher (test value)." in inflation_section
    assert "- Retrieval date: 2026-01-15." in inflation_section
    provenance = json.loads(outputs["data/processed/provenance.json"])
    row = next(item for item in provenance["series"] if item["series_file"] == "inflation_history.csv")
    assert row["release_lag_days"] == "10"
    assert provenance["project"]["named_user"] == "Example user (test value)"
    card = outputs["docs/indicator_card.md"]
    assert "Example Publisher (test value)" in card and "Example user (test value)" in card
    lag = outputs["outputs/release_lag_check.md"]
    inflation_line = next(line for line in lag.splitlines() if line.startswith("| Inflation"))
    export_line = next(line for line in lag.splitlines() if line.startswith("| Exports"))
    assert "holds for every decision" in inflation_line
    assert re.search(r"fails for \d+ of \d+ decisions", export_line)
    assert "Real lags are filled in for 2 of 6" in lag


def test_release_lag_tolerance_matches_decision_calendar():
    panel = __import__("pandas").read_csv(ROOT / "data/processed/model_panel.csv", parse_dates=["decision_date"])
    usable = panel.dropna(subset=list(ingest.FEATURE_RULES) + ["y"])
    series = {name: {"release_lag_days": "UNKNOWN"} for _, (name, _) in ingest.FEATURE_RULES.items()}
    rows = facts.release_lag_rows(series, usable["decision_date"], ingest.ASSUMED_LAG_MONTHS)
    tolerated = rows[0]["longest_lag_tolerated_days"]
    at_limit = {name: {"release_lag_days": str(tolerated)} for name in series}
    over = {name: {"release_lag_days": str(tolerated + 1)} for name in series}
    assert all(row["late"] == 0 for row in facts.release_lag_rows(at_limit, usable["decision_date"], ingest.ASSUMED_LAG_MONTHS))
    assert all(row["late"] >= 1 for row in facts.release_lag_rows(over, usable["decision_date"], ingest.ASSUMED_LAG_MONTHS))


@pytest.mark.parametrize("column,value,message", [
    ("retrieval_date", "2027-01-01", "after today"),
    ("retrieval_date", "15.01.2026", "YYYY-MM-DD"),
    ("retrieval_date", "2026-02-30", "not a valid calendar date"),
    ("release_lag_days", "-3", "non-negative whole number"),
    ("release_lag_days", "2.5", "non-negative whole number"),
    ("revised_after_release", "maybe", "not one of yes, no, UNKNOWN"),
    ("notes", "published 2030-05-01", "after today"),
    ("publisher", "", "empty; write UNKNOWN"),
])
def test_invalid_series_cells_give_clear_errors(root, column, value, message):
    _edit_series(root, "import_history.csv", **{column: value})
    with pytest.raises(facts.FactsError, match=re.escape(message)) as error:
        facts.build_all(root, today=TODAY)
    assert "import_history.csv" in str(error.value) and column in str(error.value)


@pytest.mark.parametrize("field,value,message", [
    ("sampling_approval_when", "2026-13-01", "not a valid calendar date"),
    ("sampling_approval_when", "next week", "YYYY-MM-DD or UNKNOWN"),
    ("decision_rule_option", "4", "not one of 1, 2, 3, UNKNOWN"),
    ("model_refit_scope", "everything", "not one of estimation_sample, all_data, UNKNOWN"),
    ("week2_indicator_equals_nbk_base_rate_decision", "true", "not one of yes, no, UNKNOWN"),
])
def test_invalid_project_facts_give_clear_errors(root, field, value, message):
    _edit_project(root, field, value)
    with pytest.raises(facts.FactsError, match=re.escape(message)):
        facts.build_all(root, today=TODAY)


def test_missing_series_row_is_an_error(root):
    path = root / "docs" / "facts_to_fill.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(line for line in lines if not line.startswith("import_history.csv")) + "\n",
                    encoding="utf-8")
    with pytest.raises(facts.FactsError, match="no row for import_history.csv"):
        facts.build_all(root, today=TODAY)


def test_write_all_only_writes_generated_files_and_never_raw_csvs(root):
    before = {path.name: normalized_sha256(path) for path in (root / "data" / "raw").glob("*.csv")}
    outputs = facts.build_all(root, today=TODAY)
    facts.write_all(outputs, root)
    after = {path.name: normalized_sha256(path) for path in (root / "data" / "raw").glob("*.csv")}
    assert before == after
    assert sorted(outputs) == sorted(GENERATED)


def test_assumed_lag_is_read_from_config(tmp_path):
    assert ingest.ASSUMED_LAG_MONTHS == json.loads((ROOT / "config/release_lag.json").read_text())["assumed_release_lag_months"]
    path = tmp_path / "release_lag.json"
    path.write_text(json.dumps({"assumed_release_lag_months": 3}), encoding="utf-8")
    assert ingest.assumed_release_lag_months(path) == 3
    for bad in (-1, 1.5, "2", True):
        path.write_text(json.dumps({"assumed_release_lag_months": bad}), encoding="utf-8")
        with pytest.raises(ValueError, match="non-negative integer"):
            ingest.assumed_release_lag_months(path)


def test_check_fails_when_a_generated_file_disagrees_with_the_form(root):
    numbers = root / "outputs" / "numbers_for_note.json"
    facts.write_all(facts.build_all(root, today=TODAY), root)
    result = check.Report()
    check.compare_facts(result, numbers, root=root)
    assert result.failed == 0
    _edit_series(root, "inflation_history.csv", publisher="Changed in the form only (test value)")
    result = check.Report()
    check.compare_facts(result, numbers, root=root)
    assert {item for status, item, _ in result.rows if status == "FAIL"} == {
        "facts: data/raw/SOURCES.md", "facts: data/processed/provenance.json", "facts: docs/indicator_card.md",
        "provenance consistency: inflation_history.csv"}


def test_doc_templates_type_no_result_numbers():
    for name in facts.GENERATED_DOCS:
        template = facts.TEMPLATE_COMMENT.sub(
            "", (ROOT / "docs" / "templates" / f"{name.removesuffix('.md')}.template.md").read_text(encoding="utf-8"))
        body = facts.PLACEHOLDER.sub("", template)
        digits = {token for token in re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])", body)}
        assert digits <= TEMPLATE_LITERALS, (name, sorted(digits - TEMPLATE_LITERALS))


# ------------------------------------------------------- dashboard panel


def _app_copy(root: Path) -> Path:
    (root / "src").mkdir()
    shutil.copy2(ROOT / "src" / "app.py", root / "src" / "app.py")
    shutil.copytree(ROOT / "data" / "processed", root / "data" / "processed")
    (root / "model").mkdir()
    shutil.copy2(ROOT / "model" / "artifact.json", root / "model" / "artifact.json")
    (root / "config").mkdir()
    shutil.copy2(ROOT / "config" / "forecast_rounds.json", root / "config" / "forecast_rounds.json")
    return root / "src" / "app.py"


def _provenance_table(at: AppTest):
    return next(frame.value for frame in at.dataframe if "Publisher" in frame.value.columns)


def test_app_provenance_panel_shows_form_values_or_unknown(tmp_path):
    path = _app_copy(tmp_path)
    provenance_path = tmp_path / "data" / "processed" / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    for row in provenance["series"]:
        for key in row:
            if key != "series_file":
                row[key] = "UNKNOWN"
        if row["series_file"] == "base_rate_history.csv":
            row["publisher"] = "Example Publisher (test value)"
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    at = AppTest.from_file(str(path), default_timeout=30).run()
    assert not at.exception
    table = _provenance_table(at)
    assert len(table) == 7
    assert "Example Publisher (test value)" in table["Publisher"].tolist()
    assert (table.drop(columns=["Series file", "Publisher"]) == "UNKNOWN").all().all()
    assert any("Original publisher: Example Publisher (test value)" in c.value for c in at.caption)

    provenance_path.unlink()
    at = AppTest.from_file(str(path), default_timeout=30).run()
    assert not at.exception
    assert any("Provenance facts are missing" in item.value for item in at.info)
    assert (_provenance_table(at) == "UNKNOWN").all().all()
    assert any("Original publisher: UNKNOWN" in c.value for c in at.caption)
    assert any("assumed release lag UNKNOWN" in c.value for c in at.caption)


# --------------------------------------------- student-stated provenance


U = "UNKNOWN"
_BNS, _NBK = "Bureau of National Statistics", "National Bank of Kazakhstan"
_TRADE_NAV = "Главная > Отрасли > Экономика > Статистика внешней, взаимной торговли и товарных рынков"
_LOANS = ("Кредиты экономике от банков второго уровня (исторические данные)",
          "https://nationalbank.kz/file/download/135680",
          "Главная > Статистика > Денежно-кредитная и банковская статистика > Кредитный рынок > "
          "Кредиты экономике от банков второго уровня (исторические данные)")
RETRIEVED = "2026-10-08"
OLD_BASE_RATE_URL = "https://prg.kz/document/?doc_id=36378707&pos=302;-4"
# Student-stated provenance: publisher, source_title, url, navigation_path, publication_date, retrieval_date.
STATED = {
    "base_rate_history.csv": ("secondary: prg.kz (table); primary: National Bank of Kazakhstan, as cited in the "
                              "table's own notes (NBK press releases)",
                              "Базовая ставка Национального Банка РК (2015-2026)",
                              "https://prg.kz/document/?doc_id=36378707&pos=6;67", U, U, RETRIEVED),
    "inflation_history.csv": (_BNS, "Индекс потребительских цен по 12 основным разделам",
                              "https://stat.gov.kz/api/iblock/element/1549/file/ru/",
                              "Главная > Отрасли > Экономика > Статистика цен", "2026-10-01", RETRIEVED),
    "consumption_history_updated.csv": (_BNS, "Индексы физического объема розничной торговли по месяцам 2015-2026 годы",
                                        "https://stat.gov.kz/api/iblock/element/4084/file/ru/",
                                        "Главная > Отрасли > Экономика > Статистика внутренней торговли > Розничная торговля",
                                        "2026-10-07", RETRIEVED),
    "export_history.csv": (_BNS, "Товарооборот в иностранной валюте (экспорт)",
                           "https://stat.gov.kz/api/iblock/element/446905/file/ru/", _TRADE_NAV, "2026-10-05", RETRIEVED),
    "import_history.csv": (_BNS, "Товарооборот в иностранной валюте (импорт)",
                           "https://stat.gov.kz/api/iblock/element/446906/file/ru/", _TRADE_NAV, "2026-10-05", RETRIEVED),
    "loans_individuals_history.csv": (_NBK, _LOANS[0], _LOANS[1], _LOANS[2], "2026-09-24", RETRIEVED),
    "loans_legal_entities_history.csv": (_NBK, _LOANS[0], _LOANS[1], _LOANS[2], "2026-09-24", RETRIEVED),
}
STATED_COLUMNS = ["publisher", "source_title", "url_or_api_query", "navigation_path", "publication_date", "retrieval_date"]
TEXT_FILES = {".md", ".csv", ".json", ".py", ".txt", ".toml", ".ini", ".cfg"}


def _repo_text_files():
    for path in ROOT.rglob("*"):
        parts = set(path.relative_to(ROOT).parts)
        if path.is_file() and path.suffix in TEXT_FILES and not parts & {".git", ".venv", ".pytest-temp", "__pycache__"}:
            yield path


def test_form_holds_exactly_the_stated_facts():
    raw_files = sorted(p.name for p in (ROOT / "data" / "raw").glob("*.csv"))
    form = facts.load_series_facts(ROOT / "docs" / "facts_to_fill.csv", raw_files, date.today())
    assert set(form) == set(STATED)
    for name, row in form.items():
        assert tuple(row[column] for column in STATED_COLUMNS) == STATED[name], name
        assert row["table_or_series_identifier"] == (
            f"{row['source_title']}; no series code on the source page (student-stated); identified by title")
        for column in ("release_lag_days", "revised_after_release"):
            assert row[column] == U, (name, column)
        for column in ("publication_date", "retrieval_date"):
            if row[column] != U:
                assert date.fromisoformat(row[column]) <= date.today()
        assert "utm_" not in row["url_or_api_query"].lower()
    base_rate = form["base_rate_history.csv"]
    assert "not an NBK publication" in base_rate["notes"]
    for column in ("«Дата установления ставки (с)»", "«Размер ставки, %»", "«Коридор базовой ставки, %»", "«Примечание»"):
        assert column in base_rate["notes"]
    assert "the February 2026 issue was published 2026-03-02" in form["inflation_history.csv"]["notes"]


def test_sources_md_has_the_extraction_statement_for_every_series():
    sources = (ROOT / "data" / "raw" / "SOURCES.md").read_text(encoding="utf-8")
    sections = re.split(r"(?m)^### ", sources)[1:]
    assert len(sections) == 7
    for section in sections:
        assert f"- {facts.EXTRACTION_STATEMENT}." in section, section.splitlines()[0]


def test_old_urls_and_titles_are_gone_everywhere():
    for path in _repo_text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        relative = path.relative_to(ROOT).as_posix()
        if relative == "tests/test_facts.py":
            continue  # this file names them in order to test for them
        assert OLD_BASE_RATE_URL not in text, relative
        assert "element/454290" not in text, relative
        assert "annual household food expenditure" not in text.lower(), relative


def test_sources_card_and_app_panel_agree_with_the_form():
    results = facts.provenance_consistency(ROOT)
    assert len(results) == 7
    assert all(ok for _, ok, _ in results), [detail for _, ok, detail in results if not ok]


def test_consistency_check_catches_a_card_edited_by_hand(root):
    facts.write_all(facts.build_all(root, today=TODAY), root)
    card = root / "docs" / "indicator_card.md"
    card.write_text(card.read_text(encoding="utf-8").replace("https://stat.gov.kz/api/iblock/element/1549/file/ru/",
                                                             "https://example.invalid/edited", 1), encoding="utf-8")
    failed = {name for name, ok, _ in facts.provenance_consistency(root) if not ok}
    assert failed == {"inflation_history.csv"}


def test_data_audit_matches_a_direct_computation():
    import pandas as pd

    raw = pd.read_csv(ROOT / "data" / "raw" / "consumption_history_updated.csv")
    audit = facts.series_audit(ROOT / "data" / "raw", "consumption_history_updated.csv")
    assert audit["rows"] == len(raw) and audit["first"] == raw["year_month"].min() and audit["last"] == raw["year_month"].max()
    assert audit["repeats"] == int((raw["consumption_yoy"] == raw["consumption_yoy"].shift()).sum())
    assert not facts.FILL_CALLS.search((ROOT / "src" / "ingest.py").read_text(encoding="utf-8"))
    assert facts.FILL_CALLS.search("x = frame.ffill()") and facts.FILL_CALLS.search("s.interpolate()")
    text = (ROOT / "docs" / "data_audit.md").read_text(encoding="utf-8")
    assert f"{audit['rows']} rows from {audit['first']} to {audit['last']}" in text
    assert "(mismatches: 0)" in text


def test_indicator_card_has_all_eight_rows_and_stated_sources():
    text = (ROOT / "docs" / "indicator_card.md").read_text(encoding="utf-8")
    for row in ("1. Concept", "2. Formula", "3. Unit and scale", "4. Frequency and lag", "5. Coverage",
                "6. Source and vintage", "7. Transformations", "8. Known weaknesses"):
        assert f"| {row} |" in text and f"## {row}" in text, row
    card = facts.parse_card_sources(text)
    assert len(card) == 7
    for name, values in STATED.items():
        assert tuple(card[name][column] for column in STATED_COLUMNS) == values, name
    assert card["base_rate_history.csv"]["unit"] == STATED_UNITS["base_rate_history.csv"]


# ------------------------------------------------------------------ units


STATED_UNITS = {
    "export_history.csv": "thousand USD", "import_history.csv": "thousand USD",
    "loans_individuals_history.csv": "million KZT", "loans_legal_entities_history.csv": "million KZT",
    "inflation_history.csv": "year-on-year percent change",
    "consumption_history_updated.csv": "year-on-year percent change",
    "base_rate_history.csv": "percent (source column header «Размер ставки, %»)",
}


def test_form_units_are_the_stated_ones():
    raw_files = sorted(p.name for p in (ROOT / "data" / "raw").glob("*.csv"))
    form = facts.load_series_facts(ROOT / "docs" / "facts_to_fill.csv", raw_files, date.today())
    assert {name: row["unit"] for name, row in form.items()} == STATED_UNITS


def test_unit_check_reports_conflicts_without_changing_either_side():
    raw = ROOT / "data" / "raw"
    before = {p.name: normalized_sha256(p) for p in raw.glob("*.csv")}
    checks = {name: facts.unit_check(raw, name, unit) for name, unit in STATED_UNITS.items()}
    for name in ("export_history.csv", "import_history.csv", "loans_individuals_history.csv",
                 "loans_legal_entities_history.csv"):
        assert checks[name]["verdict"] == "agrees", name
    assert checks["consumption_history_updated.csv"]["verdict"] == "agrees (year-on-year)"
    assert checks["inflation_history.csv"]["verdict"] == "no unit hint in the column name to compare"
    assert checks["base_rate_history.csv"]["verdict"] == "no unit hint in the column name to compare"
    assert facts.unit_check(raw, "export_history.csv", "million US dollars")["verdict"] == (
        "CONFLICT: scale (form million, header thousand)")
    assert facts.unit_check(raw, "loans_individuals_history.csv", "tenge (KZT)")["verdict"].startswith(
        "currency agrees; scale not stated")
    assert facts.unit_check(raw, "export_history.csv", "million KZT")["verdict"].startswith("CONFLICT: currency")
    assert facts.unit_check(raw, "base_rate_history.csv", U)["verdict"].startswith("not checked")
    assert before == {p.name: normalized_sha256(p) for p in raw.glob("*.csv")}


def test_units_reach_sources_audit_card_validity_and_app_panel():
    sources = (ROOT / "data" / "raw" / "SOURCES.md").read_text(encoding="utf-8")
    export_section = sources.split("### `export_history.csv`")[1].split("###")[0]
    assert "Unit (form, student statement): thousand USD" in export_section
    assert "check: agrees" in export_section and "`exports_thousand_usd`" in export_section
    audit = (ROOT / "docs" / "data_audit.md").read_text(encoding="utf-8")
    assert "## Units" in audit and "CONFLICT" not in audit and "not confirmed" not in audit
    card = (ROOT / "docs" / "indicator_card.md").read_text(encoding="utf-8")
    unit_row = next(line for line in card.splitlines() if line.startswith("| 3. Unit and scale |"))
    transform_row = next(line for line in card.splitlines() if line.startswith("| 7. Transformations |"))
    assert "thousand USD" in unit_row and "million KZT" in unit_row and "not confirmed" not in card
    assert "Conflicts with CSV column names: none" in unit_row
    assert "removes the unit scale but not the currency effect" in transform_row
    validity = (ROOT / "docs" / "validity_facts.md").read_text(encoding="utf-8")
    construct = validity.split("## Construct validity")[1].split("## Internal validity")[0]
    assert ("mixes volume, price and exchange-rate effects, notably around the 2015 and 2022 devaluations; "
            "the model does not separate them. [assumption]") in construct
    from src.app import provenance_table
    panel = provenance_table(json.loads((ROOT / "data/processed/provenance.json").read_text(encoding="utf-8")))
    assert dict(zip(panel["Series file"], panel["Unit"])) == STATED_UNITS


def test_no_annual_source_wording_remains():
    for relative in ("docs/facts_to_fill.csv", "docs/data_audit.md", "docs/indicator_card.md", "data/raw/SOURCES.md",
                     "docs/validity_facts.md", "README.md", "TODO_HUMAN.md", "data/processed/provenance.json",
                     *[f"docs/templates/{p.name}" for p in (ROOT / "docs" / "templates").glob("*.md")]):
        assert "annual" not in (ROOT / relative).read_text(encoding="utf-8").lower(), relative


def test_todo_human_lists_only_open_items():
    text = (ROOT / "TODO_HUMAN.md").read_text(encoding="utf-8")
    for resolved in ("Official table or series identifier", "Scale of both lending files", "primary publisher",
                     "Resolved:"):
        assert resolved not in text, resolved
    for still_open in ("publication date and navigation path", "Release lag in days", "revised after release",
                       "sheet, rows and columns", "Claim-level check", "docs/ai_use.md", "Written approval of decision-date sampling"):
        assert still_open in text, still_open


# ------------------------------------------------------- indicator origin


def test_indicator_origin_is_recorded_as_student_stated_and_never_as_approved():
    project = facts.load_project_facts(ROOT / "docs" / "facts_to_fill.md", date.today())
    assert project["week2_indicator_name"] == "NBK base-rate decisions (increase / hold / decrease)"
    assert project["indicator_suggested_by"] == "the course instructor"
    assert date.fromisoformat(project["indicator_suggested_on"]) == date(2026, 10, 7) <= date.today()
    assert project["indicator_suggested_where"] == "during a discussion at a lecture"
    assert project["indicator_written_proof"] == "oral, no written proof"
    assert project["week2_approval_status"] == (
        "instructor-suggested on 2026-10-07 at a lecture; formal approval record UNKNOWN")
    assert project["week2_indicator_equals_nbk_base_rate_decision"] == "UNKNOWN"
    claims = re.compile(r"formally approved|was approved|approved in week 2|approved indicator|\bregistered\b", re.I)
    for relative in ("docs/indicator_card.md", "docs/validity_facts.md", "README.md", "TODO_HUMAN.md",
                     "docs/facts_to_fill.md", "docs/deviations.md", "docs/templates/indicator_card.template.md",
                     "docs/templates/validity_facts.template.md"):
        assert not claims.search((ROOT / relative).read_text(encoding="utf-8")), relative
    card = (ROOT / "docs" / "indicator_card.md").read_text(encoding="utf-8")
    assert "formal approval record UNKNOWN" in card and "Suggested by the course instructor on 2026-10-07" in card

# ------------------------------------------------- release-lag upper bounds


def test_form_upper_bound_notes_match_the_computed_bounds():
    provenance = json.loads((ROOT / "data/processed/provenance.json").read_text(encoding="utf-8"))
    limitation = provenance["release_lag_limitation"]
    raw_files = sorted(p.name for p in (ROOT / "data" / "raw").glob("*.csv"))
    form = facts.load_series_facts(ROOT / "docs" / "facts_to_fill.csv", raw_files, date.today())
    for row in limitation["series"]:
        bound = row["upper_bound_days"]
        note = form[row["series_file"]]["notes"]
        assert f"Upper bound from file update date: {bound} day{'s' if bound != 1 else ''}; true release lag UNKNOWN." in note
        assert form[row["series_file"]]["release_lag_days"] == "UNKNOWN"
    assert "Upper bound from file update date: UNKNOWN; not applicable to the target." in form["base_rate_history.csv"]["notes"]
    consumption = form["consumption_history_updated.csv"]["notes"]
    assert "the retail-trade February 2025 issue was published 2025-03-12 (12 days" in consumption
    assert "the February 2026 issue was published 2026-03-02" in form["inflation_history.csv"]["notes"]
    for row in form.values():
        assert row["revised_after_release"] == "UNKNOWN"


def test_limitation_text_is_consistent_with_the_strict_check_and_rb07():
    provenance = json.loads((ROOT / "data/processed/provenance.json").read_text(encoding="utf-8"))
    limitation = provenance["release_lag_limitation"]
    text = limitation["text"]
    total = limitation["decisions"]
    by_feature = {row["feature"]: row for row in limitation["series"]}
    for feature in ("exports", "imports"):
        assert by_feature[feature]["decisions_where_bound_exceeds_window"] == total
    assert f"exports and imports at every decision ({total} of {total})" in text
    consumption = by_feature["consumption"]["decisions_where_bound_exceeds_window"]
    assert 0 < consumption < total and f"consumption at decisions early in the month ({consumption} of {total})" in text
    for feature in ("inflation", "corporate_lending", "household_lending"):
        assert by_feature[feature]["decisions_where_bound_exceeds_window"] == 0
    window = limitation["window_days"]
    assert f"median {window['median']:g}; {window['min']} to {window['max']} across decisions" in text
    check = (ROOT / "outputs" / "release_lag_check.md").read_text(encoding="utf-8")
    assert f"shortest window minus one day ({limitation['strict_tolerance_days']} days)" in text
    assert f"| {limitation['strict_tolerance_days']} | UNKNOWN |" in check, "strict 30-day tolerance column unchanged"
    assert "## Upper bounds from file update dates" in check
    numbers = json.loads((ROOT / "outputs" / "numbers_for_note.json").read_text(encoding="utf-8"))["numbers"]
    assert numbers["robustness_RB07_name"]["display"] in text
    assert "a check that shifts only the trade series was not run" in text
    assert text in (ROOT / "docs" / "validity_facts.md").read_text(encoding="utf-8")


def test_app_shows_the_limitation_and_the_chosen_decision_rule(tmp_path):
    path = _app_copy(tmp_path)
    provenance = json.loads((tmp_path / "data/processed/provenance.json").read_text(encoding="utf-8"))
    at = AppTest.from_file(str(path), default_timeout=30).run()
    assert not at.exception
    evidence = next(tab for tab in at.tabs if tab.label == "Evidence")
    assert "Limitations" in [item.value for item in evidence.subheader]
    assert provenance["release_lag_limitation"]["text"] in [item.value for item in evidence.markdown]
    rule = provenance["decision_rule"]
    overview = next(tab for tab in at.tabs if tab.label == "Overview")
    shown = [item.value for item in overview.info if item.value.startswith("**Decision rule")]
    assert shown and f"option {rule['option']}" in shown[0] and rule["named_user"] in shown[0] and rule["today"] in shown[0]

    (tmp_path / "data/processed/provenance.json").unlink()
    at = AppTest.from_file(str(path), default_timeout=30).run()
    evidence = next(tab for tab in at.tabs if tab.label == "Evidence")
    assert any("Release-lag limitation: UNKNOWN" in item.value for item in evidence.markdown)
    assert any(item.value.startswith("Decision rule: UNKNOWN") for item in at.info)

# ------------------------------------------------------ chosen decision rule


def _demo_rule_cell(text: str) -> str:
    return text.split("<!-- generated:decision-rule:start -->", 1)[1].split("<!-- generated:decision-rule:end -->", 1)[0]


def test_named_user_and_demo_step_come_from_the_form():
    project = facts.load_project_facts(ROOT / "docs" / "facts_to_fill.md", date.today())
    option, user = project["decision_rule_option"], project["named_user"]
    rule_doc = (ROOT / "docs" / "decision_rule.md").read_text(encoding="utf-8")
    for number in (1, 2, 3):
        section = rule_doc.split(f"## Option {number}:", 1)[1].split("\n## ", 1)[0]
        expected = user if str(number) == option else facts.UNNAMED_USER
        assert f"- **Named user:** {expected}." in section, number
    cell = _demo_rule_cell((ROOT / "docs" / "demo_script.md").read_text(encoding="utf-8"))
    title = rule_doc.split(f"## Option {option}:", 1)[1].splitlines()[0].strip()
    assert f"option {option}, {title}" in cell and user in cell
    assert "option STUDENT" not in (ROOT / "docs" / "demo_script.md").read_text(encoding="utf-8")
    assert not re.search(r"\d+\.\d+", cell), "the demo cell quotes no numbers; they are read from the screen"


def test_changing_the_form_updates_the_rule_doc_and_demo_step(root):
    _edit_project(root, "decision_rule_option", "2")
    _edit_project(root, "named_user", "Example user (test value)")
    outputs = facts.build_all(root, today=TODAY)
    rule_doc = outputs["docs/decision_rule.md"]
    assert "- **Named user:** Example user (test value). Suits a user who writes a pre-meeting brief" in rule_doc
    assert rule_doc.count(f"- **Named user:** {facts.UNNAMED_USER}.") == 2
    cell = _demo_rule_cell(outputs["docs/demo_script.md"])
    assert "option 2, momentum flag" in cell and "Example user (test value)" in cell
    rest = outputs["docs/demo_script.md"].replace(cell, "")
    assert rest == (root / "docs" / "demo_script.md").read_text(encoding="utf-8").replace(
        _demo_rule_cell((root / "docs" / "demo_script.md").read_text(encoding="utf-8")), ""), "only the block changes"

    _edit_project(root, "decision_rule_option", "UNKNOWN")
    outputs = facts.build_all(root, today=TODAY)
    assert outputs["docs/decision_rule.md"].count(f"- **Named user:** {facts.UNNAMED_USER}.") == 3
    assert _demo_rule_cell(outputs["docs/demo_script.md"]).startswith("No option is chosen yet")

# ------------------------------------------------- first screen and evidence


def test_first_screen_shows_band_and_direction_flag_from_the_artifact(tmp_path):
    from src import app as dashboard

    artifact = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))
    _, low, high = dashboard.score_and_delta_band(artifact, artifact["latest_feature_vector"])
    low, high = max(-1.0, low), min(1.0, high)
    expected_state = "triggered hawkish" if low > 0 else "triggered dovish" if high < 0 else "not triggered"
    path = _app_copy(tmp_path)
    at = AppTest.from_file(str(path), default_timeout=30).run()
    in_tabs = {caption.value for tab in at.tabs for caption in tab.caption}
    header = [caption.value for caption in at.caption if caption.value not in in_tabs]
    assert f"95% band: {low:+.3f} to {high:+.3f}" in header
    assert f"Direction flag: {expected_state}" in header
    assert any(text.startswith("Unit:") for text in header) and any(text.startswith("Period:") for text in header)
    assert any(item.value.startswith("CACHED DATA") for item in at.warning) or any(
        text.startswith("Local factor data") for text in header)

    (tmp_path / "data/processed/provenance.json").unlink()
    at = AppTest.from_file(str(path), default_timeout=30).run()
    assert any(caption.value.startswith("Direction flag: UNKNOWN") for caption in at.caption)
    assert any(caption.value == f"95% band: {low:+.3f} to {high:+.3f}" for caption in at.caption)


def test_limitations_add_falsification_and_specification_timing_or_unknown(tmp_path):
    from src import app as dashboard

    artifact = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))
    provenance = json.loads((ROOT / "data/processed/provenance.json").read_text(encoding="utf-8"))
    note = dashboard.falsification_three_note(artifact)
    comparison = artifact["benchmark_comparison"]
    assert f"on the {comparison['holdout_n']} holdout decisions the RMSE ratio is {comparison['rmse_ratio_model_to_hold']:.3f}" in note
    assert "the difference from 1 is too small to say the model is worse; we can only say it is not better" in note
    assert dashboard.falsification_three_note({}).endswith("UNKNOWN (not in the model artifact).")
    timing = dashboard.specification_timing_note(provenance)
    project = provenance["project"]
    allowed = date.fromisoformat(project["spec_date_allowed"])
    assert f"{allowed.day} {allowed:%B %Y} (commit {project['spec_commit']})" in timing
    assert timing.startswith("No time-stamped Week-4 pre-registration was submitted.") and "D15" in timing
    assert dashboard.specification_timing_note({}).startswith("Specification timing: UNKNOWN")
    path = _app_copy(tmp_path)
    at = AppTest.from_file(str(path), default_timeout=30).run()
    evidence = next(tab for tab in at.tabs if tab.label == "Evidence")
    shown = [item.value for item in evidence.markdown]
    assert note in shown and timing in shown


def test_evidence_power_table_has_no_ratio_column_and_matches_the_numbers(tmp_path):
    from src import app as dashboard

    numbers = json.loads((ROOT / "outputs" / "numbers_for_note.json").read_text(encoding="utf-8"))["numbers"]
    provenance = json.loads((ROOT / "data/processed/provenance.json").read_text(encoding="utf-8"))
    table = dashboard.power_table(provenance)
    assert list(table.columns) == ["Factor", "Estimate", "SE", "Minimum detectable effect"]
    for feature, row in zip(FACTOR_ORDER, table.to_dict(orient="records")):
        assert (row["Estimate"], row["SE"], row["Minimum detectable effect"]) == (
            numbers[f"coef_{feature}"]["display"], numbers[f"se_{feature}"]["display"],
            numbers[f"power_{feature}_mde"]["display"])
    assert dashboard.power_table({}) is None
    note = (ROOT / "outputs" / "power_note.md").read_text(encoding="utf-8")
    assert "÷ MDE" not in note and "| Factor | Estimate | Robust SE (HC0) | MDE (5%, 80% power) |" in note
    path = _app_copy(tmp_path)
    at = AppTest.from_file(str(path), default_timeout=30).run()
    evidence = next(tab for tab in at.tabs if tab.label == "Evidence")
    assert f"At this sample size (N = {numbers['n_estimation']['display']}), failure to reject a zero slope is not evidence that the factor has no effect." in [
        caption.value for caption in evidence.caption]
    (tmp_path / "data/processed/provenance.json").unlink()
    at = AppTest.from_file(str(path), default_timeout=30).run()
    evidence = next(tab for tab in at.tabs if tab.label == "Evidence")
    assert any(item.value.startswith("Power table: UNKNOWN") for item in evidence.info)


def test_drivers_helper_line_is_under_the_slider(tmp_path):
    path = _app_copy(tmp_path)
    at = AppTest.from_file(str(path), default_timeout=30).run()
    drivers = next(tab for tab in at.tabs if tab.label == "Drivers and scenario")
    captions = [caption.value for caption in drivers.caption]
    band = next(i for i, text in enumerate(captions) if text.startswith("95% delta-method band"))
    assert captions[band + 1] == "Only the selected factor moves; the other five stay at their latest values."


FACTOR_ORDER = list(ingest.FEATURE_RULES)

# ------------------------------------------- "Why these probabilities?" and dedication


def _walk(node):
    yield node
    for child in getattr(node, "children", {}).values():
        yield from _walk(child)


def test_why_panel_explains_with_generated_numbers_and_unknown_fallbacks(tmp_path):
    import pandas as pd
    from src import app as dashboard

    artifact = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))
    history = dashboard.load_data()
    latest = {name: float(value) for name, value in artifact["latest_feature_vector"].items()}
    _, low, high = dashboard.score_and_delta_band(artifact, latest)
    items = dashboard.why_probabilities(artifact, history, "2026-07", latest, max(-1.0, low), min(1.0, high))
    assert len(items) == 4
    assert "conditional estimate" in items[0] and "only the date differs" in items[0] and "2026-07" in items[0]
    counts = pd.read_csv(ROOT / "data/processed/nbk_decisions_clean.csv")["decision"].str.strip().str.title().value_counts()
    assert f"{int(counts['Hold'])} of {int(counts.sum())} decisions" in items[1]
    assert "overlap" in items[2] and "includes zero" in items[2]
    comparison = artifact["benchmark_comparison"]
    assert f"On the {comparison['holdout_n']} holdout decisions the RMSE ratio is {comparison['rmse_ratio_model_to_hold']:.3f}" in items[3]
    assert f"p = {artifact['diagnostics']['joint_slope_lr']['p_value']:.3f}" in items[3]
    assert items[3].endswith("This is a limitation of the model, not a data error.")
    assert not any("forecasts the next decision" in item for item in items)
    empty = dashboard.why_probabilities({}, pd.DataFrame(), "", {}, -0.1, 0.1)
    assert "UNKNOWN" in empty[0] and all("UNKNOWN" in item for item in empty[1:])
    at = AppTest.from_file(str(_app_copy(tmp_path)), default_timeout=30).run()
    overview = next(tab for tab in at.tabs if tab.label == "Overview")
    panel = next(box for box in overview.expander if box.label == "Why these probabilities?")
    assert [item.value for item in panel.markdown] == [f"- {item}" for item in items]


def test_dedication_is_static_above_the_score_and_changes_no_number(tmp_path):
    from src import app as dashboard

    assert not re.search(r"\d", dashboard.DEDICATION)
    at = AppTest.from_file(str(_app_copy(tmp_path)), default_timeout=30).run()
    nodes = list(_walk(at.main))
    kinds = [(getattr(node, "type", None), getattr(node, "value", None), getattr(node, "label", None)) for node in nodes]
    title = next(i for i, (kind, value, _) in enumerate(kinds) if kind == "title")
    dedication = next(i for i, (kind, value, _) in enumerate(kinds) if kind == "markdown" and value == dashboard.DEDICATION)
    score = next(i for i, (kind, _, label) in enumerate(kinds) if kind == "metric" and label == "Policy pressure score")
    assert title < dedication < score
    artifact = dashboard.load_artifact()
    expected = dashboard.policy_pressure_score(dashboard.ordered_probabilities(artifact, artifact["latest_feature_vector"]))
    assert next(m.value for m in at.metric if m.label == "Policy pressure score") == f"{expected:+.3f}"
    for relative in ("model/artifact.json", "outputs/numbers_for_note.json"):
        assert dashboard.DEDICATION not in (ROOT / relative).read_text(encoding="utf-8")


def test_demo_answers_on_rounds_and_hold_use_the_generated_numbers():
    import pandas as pd

    text = (ROOT / "docs" / "demo_script.md").read_text(encoding="utf-8")
    counts = pd.read_csv(ROOT / "data/processed/nbk_decisions_clean.csv")["decision"].str.strip().str.title().value_counts()
    hold = text.split("<!-- generated:hold-answer:start -->", 1)[1].split("<!--", 1)[0]
    assert f"({int(counts['Hold'])} of {int(counts.sum())} decisions" in hold
    numbers = json.loads((ROOT / "outputs" / "numbers_for_note.json").read_text(encoding="utf-8"))["numbers"]
    month = (pd.Period(numbers["latest_decision_date"]["value"], "M") - ingest.ASSUMED_LAG_MONTHS).strftime("%Y-%m")
    rounds = text.split("<!-- generated:rounds-answer:start -->", 1)[1].split("<!--", 1)[0]
    assert f"factor data month {month}" in rounds and "conditional estimate" in rounds
    assert "| 1:15–1:45 | Why these probabilities? |" in text