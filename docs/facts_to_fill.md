# Facts to fill (project)

> **Form for the student.** Replace `UNKNOWN` in the **Value** column only with facts you can prove.
> Keep `UNKNOWN` where you cannot. Then run `python run.py facts`, which validates this file and
> `docs/facts_to_fill.csv` and regenerates `data/raw/SOURCES.md`, `data/processed/provenance.json`,
> `docs/indicator_card.md`, `docs/decision_rule.md`, `docs/validity_facts.md` and
> `outputs/release_lag_check.md`. `python -m src.check` fails if those files disagree with the forms.
>
> Rules: dates are `YYYY-MM-DD` and not in the future; choice fields accept only the listed values;
> do not use the `|` character inside a value.

| Field | Value | Allowed values / format |
|---|---|---|
| `week2_indicator_name` | NBK base-rate decisions (increase / hold / decrease) | The indicator name (student statement) |
| `indicator_suggested_by` | the course instructor | Who suggested the indicator (student statement) |
| `indicator_suggested_on` | 2026-10-07 | Date of the suggestion, `YYYY-MM-DD` |
| `indicator_suggested_where` | during a discussion at a lecture | Where the suggestion was made (student statement) |
| `indicator_written_proof` | oral, no written proof | Written proof of the suggestion: where it is kept, or `oral, no written proof` |
| `week2_approval_status` | instructor-suggested on 2026-10-07 at a lecture; formal approval record UNKNOWN | Status of the Week 2 record for the indicator; do not claim a formal approval without a record |
| `week2_indicator_equals_nbk_base_rate_decision` | UNKNOWN | `yes`, `no` or `UNKNOWN`: does the formal Week 2 record name "NBK base-rate decision"? `UNKNOWN` while that record is unknown |
| `sampling_approval_who` | UNKNOWN | Who gave written approval of decision-date sampling |
| `sampling_approval_when` | UNKNOWN | Date of that approval, `YYYY-MM-DD` |
| `sampling_approval_proof_location` | UNKNOWN | Where the written proof is (file path in the repo, or where it is kept) |
| `spec_date_allowed_by` | the course instructor | Who allowed the specification to be dated by its commit (student statement) |
| `spec_date_allowed` | 2026-10-16 | The date the specification is accepted with: its commit date, `YYYY-MM-DD` |
| `spec_date_proof` | oral, no written proof | Written proof of that permission: where it is kept, or `oral, no written proof` |
| `spec_commit` | f763e16 | Commit that dated the specification (`git log` hash; student statement: instructor permission, oral, no written proof) |
| `named_user` | a bank treasury analyst who, before an NBK base-rate meeting, needs to know whether the model shows a distinguishable tilt in rate pressure | The named user of the indicator (person or role and organisation) |
| `decision_rule_option` | 1 | `1`, `2`, `3` (options in `docs/decision_rule.md`) or `UNKNOWN` |
| `new_element` | We extend ordered-outcome models of central-bank decisions, published for US Federal Reserve decisions, to National Bank of Kazakhstan base-rate decisions, using a combination of six domestic factors (inflation, exports, imports, corporate lending, household lending, consumption). | One sentence: the new element of this project |
| `model_refit_scope` | estimation_sample | `estimation_sample` (refit only on the estimation sample recorded in `model/artifact.json`), `all_data`, or `UNKNOWN` |

The per-series facts are in `docs/facts_to_fill.csv`. Column meanings:

| Column | Meaning |
|---|---|
| `publisher` | Organisation that publishes the series |
| `source_title` | Title of the source table or file, exactly as published |
| `table_or_series_identifier` | Official table name or series code |
| `url_or_api_query` | Stable URL or the exact API query |
| `navigation_path` | Menu path on the publisher's site |
| `publication_date` | Date the source file was published, `YYYY-MM-DD`, not in the future |
| `retrieval_date` | Date the data were downloaded, `YYYY-MM-DD` |
| `release_lag_days` | Calendar days from the last day of the reference month to publication; a non-negative integer |
| `revised_after_release` | `yes`, `no` or `UNKNOWN` |
| `unit` | Unit and currency of the CSV values (for example scale and currency, or year-on-year percent change); compared with the CSV column name, never overwriting it |
| `notes` | Anything else; dates written here must also be `YYYY-MM-DD` and not in the future |
