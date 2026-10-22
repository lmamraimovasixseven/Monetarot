# TODO_HUMAN

Only facts that are still `UNKNOWN` or unconfirmed are listed. Do not infer or invent values. Enter series facts in `docs/facts_to_fill.csv` and project facts in `docs/facts_to_fill.md`, then run `python run.py facts`.

## Series provenance still UNKNOWN

- `base_rate_history.csv`: publication date and navigation path of the prg.kz table.
- Release lag in days (end of reference month to publication) for all seven files; without it, absence of look-ahead is not verified (`outputs/release_lag_check.md`). The single observed inflation issue date in the form is an observation, not a lag rule.
- Whether values were revised after release, for all seven files.
- For every file: which sheet, rows and columns of the downloaded Excel file were extracted into the CSV.

## Manual cleaning

- Manual cleaning steps beyond extracting years, months and the needed indicator: not documented for any file.
- `base_rate_history.csv` discrepancy: the owner reported removing duplicate months, an obsolete first header line, a blank line and a loader using `skiprows=1`; the current file starts with `year_month,rate`, has no preamble, and the referenced `src/data.py` is absent. Resolve this from the original editor or script if available.

## Decision calendar

- Source of the historical NBK decision dates in `config/nbk_decision_dates.csv` (copied from an earlier `nbk_decisions_clean.csv`; the official calendar document and its retrieval date are `UNKNOWN`).
- Retrieval date of the NBK decision-making schedule page linked in `config/forecast_rounds.json`.

## References

- Claim-level check: confirm the five abstract-level checks and the planned claims in `docs/references.md` by opening the sources, match each planned claim with the sentence in the note, and confirm the DOI of Taylor (1993) (`docs/references_TODO.md`).

## Project facts (`docs/facts_to_fill.md`)

- Week 2 indicator: instructor-suggested on 2026-10-07 at a lecture (oral, no written proof); formal approval record UNKNOWN.
- Written approval of decision-date sampling: who, when, and where the proof is.

## Student-only documents

- `docs/ai_use.md` (tools, purposes and the student's own work are recorded; still `[[TO FILL]]`): version of each tool; period of use; the person responsible for checking AI output; per tool (A01–A04) the dates, the files it produced, the exact prompts or export links, what was suggested, what was accepted, rejected or rewritten, and the human verification; who wrote the other files in `docs/`; the rejected or rewritten suggestions; and the signed, dated statement. Fill these from your own records only.
- `docs/contributions.md`: names, roles, contributions, signatures and dates, or a statement of individual work.
