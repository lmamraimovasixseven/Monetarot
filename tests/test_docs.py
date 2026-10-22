"""Checks on the hand-written Stage C documents: format, consistency with the artifact, no invented content."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ARTIFACT = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))
NUMBERS = json.loads((ROOT / "outputs" / "numbers_for_note.json").read_text(encoding="utf-8"))["numbers"]


def test_deviations_use_the_three_line_format_and_state_no_preregistration():
    text = (DOCS / "deviations.md").read_text(encoding="utf-8")
    assert "**No time-stamped pre-registration exists.**" in text
    entries = re.split(r"(?m)^### ", text)[1:]
    assert len(entries) >= 10
    for entry in entries:
        bullets = [line for line in entry.splitlines() if line.startswith("- ")]
        assert [b.split(":**")[0] for b in bullets] == [
            "- **What changed", "- **Why", "- **What the original specification produced"], entry.splitlines()[0]


def test_model_spec_signs_and_mechanism_p_values_match_the_results():
    text = (DOCS / "model_spec.md").read_text(encoding="utf-8")
    section = text.split("## Mechanisms and expected signs", 1)[1].split("\n## ", 1)[0]
    expected = ARTIFACT["diagnostics"]["expected_sign_check"]["expected_signs"]
    rows = [line for line in section.splitlines() if line.startswith("| `")]
    assert len(rows) == len(ARTIFACT["model"]["feature_names"])
    for row in rows:
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        name = cells[0].strip("`")
        estimate = ARTIFACT["model"]["parameters"][name]
        assert cells[1] == expected[name]
        assert cells[2] == ("+" if estimate > 0 else "−")
        same_sign = cells[1] == ("+" if estimate > 0 else "-")
        significant = NUMBERS[f"p_holm_{name}"]["value"] < 0.05
        assert cells[3].startswith("yes" if same_sign else "no"), name
        assert ("not significant" in cells[3]) == (not significant), name
        mechanism = cells[4]
        assert mechanism, f"{name}: mechanism missing"
        # Every p-value quoted in the student's text must be the one in outputs/numbers_for_note.json.
        assert f"raw p = {NUMBERS[f'p_raw_{name}']['display']}" in mechanism, name
        for holm in re.findall(r"Holm p = ([0-9.]+)", cells[3] + mechanism):
            assert holm == NUMBERS[f"p_holm_{name}"]["display"], name
    assert "MECHANISM_IN_STUDENT_WORDS" in section
    assert "\n\n## Cointegration: why no test was run" in text
    holdout = f"ceil(20% × {NUMBERS['n_usable']['display']})"
    assert holdout in text and f"**{NUMBERS['n_holdout']['display']} observations**" in text


REFERENCE_DOIS = {
    "10.1080/23322039.2024.2411768",
    "10.1016/0167-2231(93)90009-L",
    "10.1016/j.cbrev.2017.06.002",
    "10.1016/j.jmacro.2013.05.001",
    "10.1002/for.3144",
}


def test_references_todo_is_a_checklist_without_citations():
    # The no-citation rule applies only to this checklist; the references themselves live in references.md.
    text = (DOCS / "references_TODO.md").read_text(encoding="utf-8")
    assert "docs/references.md" in text
    for item in ("Claim-level check", "Italics", "Method references"):
        assert item in text, item
    assert not re.search(r"10\.\d{4,}/|https?://|\(\d{4}\)", text), "no citation, DOI or URL in the checklist"


def test_references_contain_exactly_the_five_supplied_dois_and_meet_the_requirement():
    text = (DOCS / "references.md").read_text(encoding="utf-8")
    dois = set(re.findall(r"https://doi\.org/(10\.\S+?)(?=\s|$)", text, re.M))
    assert dois == REFERENCE_DOIS
    assert len(re.findall(r"https?://", text)) == 5, "no other URLs"
    entries = [line for line in text.splitlines() if re.search(r"https://doi\.org/", line)]
    surnames = [entry.split(",")[0] for entry in entries]
    assert surnames == ["Kwizera", "Taylor", "Turkay", "van den Hauwe", "Yoon"]
    rows = [line for line in text.splitlines() if re.match(r"^\| (Kwizera|Taylor|Turkay|van den Hauwe|Yoon)", line)]
    assert len(rows) == 5
    recent = [row for row in rows if row.split("|")[3].strip() == "yes"]
    assert len(recent) == 2 and all("2024" in row for row in recent)
    assert all("yes (student-stated)" in row.split("|")[2] for row in rows)
    for row in rows:
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        assert cells[3] == "checked by the student (stated; date 2026-10-07)", cells[0]
        assert "Abstract checked on RePEc" in cells[4] and "to be confirmed by the student" in cells[4], cells[0]
        assert "full text not read" in cells[4], cells[0]
        assert cells[5].startswith("Planned, to be matched with the note: "), cells[0]
    assert "verified" not in text.lower()

def test_demo_script_has_six_steps_eighteen_questions_and_real_file_references():
    text = (DOCS / "demo_script.md").read_text(encoding="utf-8")
    questions = re.findall(r"(?m)^(\d+)\. \*\*", text)
    assert [int(q) for q in questions] == list(range(1, 21))
    for step in ("Start", "Headline", "Move the scenario", "Disconnect and reload", "Decision rule"):
        assert f"| {step} |" in text
    for path in set(re.findall(r"`((?:src|docs|data|outputs|tests|scripts|config|model)/[^`*]+?)`", text)):
        if not path.endswith("/"):
            assert (ROOT / path).exists(), path
    remote = "https://github.com/lmamraimovasixseven/monetarot.git"
    assert remote in text and remote in (ROOT / ".git" / "config").read_text(encoding="utf-8")


def test_demo_answers_that_state_results_match_the_numbers():
    # Q7: household lending is the only meaningful one-SD move; Q8: most checks flip, one survives.
    assert NUMBERS["econ_meaningful_factors"]["value"] == "household lending"
    assert NUMBERS["p_holm_household_lending"]["value"] < 0.05
    assert sum(NUMBERS[f"p_holm_{name}"]["value"] < 0.05 for name in ARTIFACT["model"]["feature_names"]) == 1
    assert NUMBERS["robustness_flipped_benchmark_count"]["value"] * 2 > NUMBERS["robustness_check_count"]["value"]
    assert NUMBERS["robustness_survivor_count"]["value"] == 1
    assert NUMBERS["oos_winner"]["value"] == "Always Hold"


AI_USE_TOOLS = ("Codex", "GitHub Copilot", "Claude Code", "Claude, chat interface")
AI_USE_SECTIONS = ("What we did ourselves", "What the AI did", "The main prompts", "Suggestions we rejected or changed",
                   "How we checked the work", "Statement")
AI_USE_ALLOWED_DATES = {"2026-10-07", "2026-10-16", "2026-10-17", "2026-10-19"}


def _markdown_tables(text: str) -> list[list[list[str]]]:
    """Every markdown table as a list of rows of cells (header first, separator excluded)."""
    tables, current = [], []
    for line in text.splitlines() + [""]:
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            current.append(cells)
        elif current:
            tables.append(current)
            current = []
    return tables


def _section(text: str, title: str) -> str:
    return text.split(f"## {title}", 1)[1].split("\n## ", 1)[0]


def test_ai_use_records_only_stated_facts_and_invents_no_prompts():
    text = (DOCS / "ai_use.md").read_text(encoding="utf-8")
    problems = []

    # Structure: the four tools in a "Tool | What it did | When | Notes" table, and every section.
    for section in AI_USE_SECTIONS:
        if f"## {section}" not in text:
            problems.append(f"missing section: {section}")
    tables = _markdown_tables(text)
    tool_table = next((table for table in tables if table and table[0] and table[0][0] == "Tool"), None)
    if tool_table is None:
        problems.append("no tool table")
    else:
        if tool_table[0] != ["Tool", "What it did", "When", "Notes"]:
            problems.append(f"tool table header is {tool_table[0]}, expected Tool | What it did | When | Notes")
        rows = {row[0]: row for row in tool_table[2:]}
        for tool in AI_USE_TOOLS:
            if not any(name.startswith(tool) for name in rows):
                problems.append(f"tool missing from the table: {tool}")
        for name, row in rows.items():
            notes = row[3] if len(row) > 3 else ""
            if not ("version" in notes.lower() and "UNKNOWN" in notes):
                problems.append(f"{name}: tool version must be written as UNKNOWN in Notes (found {notes!r})")
            if name.startswith("Codex") and (len(row) < 3 or row[2] != "UNKNOWN"):
                problems.append(f"Codex dates must be UNKNOWN (found {row[2] if len(row) > 2 else ''!r})")

    # Every table row has as many cells as its header (the separator row included).
    for table in tables:
        header = len(table[0])
        for row in table[1:]:
            if len(row) != header:
                problems.append(f"table starting {table[0][0]!r}: a row has {len(row)} cells, header has {header}")
                break

    # No invented prompts: only short summaries, no quoted prompt strings or code blocks.
    prompts = _section(text, "The main prompts") if "## The main prompts" in text else ""
    for line in prompts.splitlines():
        if re.search(r'["“”«»]', line) or line.strip().startswith("```"):
            problems.append(f"quoted prompt text in 'The main prompts': {line.strip()[:60]!r}")
        item = re.match(r"^\d+\.\s+(.*)$", line.strip())
        if item and len(item.group(1).split()) > 40:
            problems.append(f"prompt summary longer than 40 words: {item.group(1)[:60]!r}")

    # Statement with two signature lines (name and date).
    if "## Statement" in text:
        statement = _section(text, "Statement")
        signatures = [line for line in statement.splitlines()
                      if re.search(r"\b\d{4}-\d{2}-\d{2}\s*$", line.strip()) and len(line.split()) >= 2]
        if len(signatures) < 2:
            problems.append(f"Statement needs two signature lines with a date (found {len(signatures)})")

    # Dates only from the allowed list; no open markers.
    other_dates = sorted(set(re.findall(r"\d{4}-\d{2}-\d{2}", text)) - AI_USE_ALLOWED_DATES)
    if other_dates:
        problems.append(f"dates outside the allowed list: {other_dates}")
    if "[[TO FILL" in text:
        problems.append("[[TO FILL markers remain")

    # Kept rules: automated checks are not a human review; responsibility for numbers and references.
    if "do not replace a human review" not in text:
        problems.append("the automated checks must be described as not replacing a human review")
    if "outputs/numbers_for_note.json" not in text or "responsible for checking every number" not in text:
        problems.append("the responsibility for numbers (outputs/numbers_for_note.json) must be stated")

    assert not problems, "docs/ai_use.md:\n- " + "\n- ".join(problems)


def test_model_spec_justifies_not_testing_cointegration_without_typed_results():
    text = (DOCS / "model_spec.md").read_text(encoding="utf-8")
    section = text.split("## Cointegration: why no test was run", 1)[1]
    for phrase in ("ordinal", "I(0)", "household lending fails both ADF and KPSS", "RB09", "main model is unchanged"):
        assert phrase in section, phrase
    for path in re.findall(r"`((?:outputs|docs)/[^`]+)`", section):
        assert (ROOT / path).exists(), path
    assert not re.search(r"\d+\.\d+", section), "no typed results in the justification"

def test_demo_generated_answers_match_the_numbers_and_the_timing_adds_up():
    text = (DOCS / "demo_script.md").read_text(encoding="utf-8")
    rows = re.findall(r"(?m)^\| (\d+):(\d\d)–(\d+):(\d\d) \|", text)
    assert rows[0][:2] == ("0", "00") and rows[-1][2:] == ("5", "00")
    for previous, current in zip(rows, rows[1:]):
        assert previous[2:] == current[:2], "steps must be contiguous"
    robustness = text.split("<!-- generated:robustness-answer:start -->", 1)[1].split("<!--", 1)[0]
    assert (f"in {NUMBERS['robustness_flipped_benchmark_count']['display']} of "
            f"{NUMBERS['robustness_check_count']['display']} checks") in robustness
    assert f"only {NUMBERS['robustness_survivors']['display']} reproduces" in robustness
    lag = text.split("<!-- generated:lag-answer:start -->", 1)[1].split("<!--", 1)[0]
    assert "upper bounds" in lag and "RB07" in lag and NUMBERS["robustness_RB07_name"]["display"] in lag
    assert "pip install" not in text.split("## Script", 1)[1].split("## Twenty", 1)[0]