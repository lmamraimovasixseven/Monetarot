<!-- Template for data/raw/SOURCES.md. Edit here, then run `python run.py facts`.
     {{provenance:FILE}} comes from docs/facts_to_fill.csv; {{sha256:FILE}} is computed from data/raw/FILE. -->
# Raw source inventory

## Pre-cleaning disclosure

The data owner reports that all seven CSV files were cleaned manually before upload and that original publisher downloads are unavailable. These files must not be described as untouched publisher downloads. Specific cleaning steps are documented in `docs/manual_steps_found.md`; unknown steps remain listed in `TODO_HUMAN.md`.

The student states that the CSVs were derived by manual cleaning from the Excel files downloaded from the URLs listed under each file below, on the retrieval dates listed there. For a file whose URL is `UNKNOWN`, the original download is unknown. For files with a URL, the earlier statement that original publisher downloads are unavailable is superseded by this statement; the downloaded Excel files themselves are not in the repository.

For `base_rate_history.csv`, the owner reports removing duplicate months and restoring calendar continuity. The current file has no duplicate months or missing calendar months. The owner also reports an obsolete first header line and a blank line, but the current file begins with `year_month,rate`; no preamble is present in the bytes inspected on 2026-10-16. The claimed `src/data.py` loader is absent from the current working tree. This discrepancy is unresolved and recorded in `TODO_HUMAN.md`.

## Previous repository notes (preserved, historical and not authoritative)

The following inventory was already present. It is retained for history. Where it conflicts with the current file-level audit below, the audit is the observed state of the current files.

The former closing note is also retained as a historical claim: “Exact provenance and any download requests must be recovered from the data owner before publication. `run_all.py` needs no internet and rebuilds `data/processed/macro_factors_monthly.csv` from these raw files. Any future refresh/download requires an internet connection and a recorded retrieval date, URL/query, and vintage policy. No external source was fetched during this rebuild; the supplied files are not independently attributed or authenticated.” Its claim about the current `run_all.py` rebuild path is not verified in the present checkout.

| File | Column | Claimed measure / unit inferred from header | Frequency and observed coverage | Transformation |
|---|---|---|---|---|
| `base_rate_history.csv` | `rate` | Base rate, percent (header says `base_rate`; actual table header says `rate`) | Monthly labels, 2015-09–2026-09, gaps | Level; parser skips stale first two lines without changing raw file |
| `inflation_history.csv` | `inflation` | Inflation, percent (definition unspecified) | Monthly, 2015-01–2026-09 | Level |
| `consumption_history_updated.csv` | `consumption_yoy` | Consumption growth, year-on-year percent per header | Monthly, 2015-01–2026-08 | Level |
| `export_history.csv` | `exports_thousand_usd` | Exports, thousand USD | Monthly, 2015-01–2026-07 | One-month percent growth; undefined across gaps |
| `import_history.csv` | `imports_thousand_usd` | Imports, thousand USD | Monthly, 2015-01–2026-07 | Retained in processed panel; not in forecast specification |
| `loans_individuals_history.csv` | `loans_individuals_mln_kzt` | Individual loans, million KZT | Monthly, 2015-01–2026-08 | One-month percent growth; undefined across gaps |
| `loans_legal_entities_history.csv` | `loans_legal_entities_mln_kzt` | Legal-entity loans, million KZT | Monthly, 2015-01–2026-08 | Retained in panel; not in forecast specification |

## Current file-level audit (observed 2026-10-16)

The same CSV shape was found in all seven files: `year_month` plus one numeric column. Every parsed month was unique and every month between each file's endpoints was present. No missing numeric cells, malformed month labels, or non-numeric values were found. IQR flags use the 1.5×IQR rule and are statistical flags only; they do not establish data errors.

{{provenance_summary}} Column-name unit hints below are not verified units. All file SHA-256 values are included so the observed inputs can be identified without modifying them.

### `base_rate_history.csv`

- Observed columns: `year_month`, `rate`; 133 rows; coverage 2015-09 through 2026-09.
- Missing months: 0; duplicate months: 0; missing/nonnumeric values: 0; IQR flags: 0.
{{unit:base_rate_history.csv}}
{{provenance:base_rate_history.csv}}
- SHA-256 (CRLF normalized to LF): `{{sha256:base_rate_history.csv}}`.

### `inflation_history.csv`

- Observed columns: `year_month`, `inflation`; 141 rows; coverage 2015-01 through 2026-09.
- Missing months: 0; duplicate months: 0; missing/nonnumeric values: 0; IQR flags: 4 (2022-11 through 2023-02).
{{unit:inflation_history.csv}}
{{provenance:inflation_history.csv}}
- SHA-256 (CRLF normalized to LF): `{{sha256:inflation_history.csv}}`.

### `consumption_history_updated.csv`

- Observed columns: `year_month`, `consumption_yoy`; 140 rows; coverage 2015-01 through 2026-08.
- Missing months: 0; duplicate months: 0; missing/nonnumeric values: 0; IQR flags: 17 (2015-10, 2015-11, 2015-12, 2016-01, 2020-03, 2020-04, 2020-05, 2020-07, 2021-01, 2021-04, 2022-01, 2022-04, 2022-06, 2023-01, 2023-11, 2024-10, 2024-11).
{{unit:consumption_history_updated.csv}}
{{provenance:consumption_history_updated.csv}}
- SHA-256 (CRLF normalized to LF): `{{sha256:consumption_history_updated.csv}}`.

### `export_history.csv`

- Observed columns: `year_month`, `exports_thousand_usd`; 139 rows; coverage 2015-01 through 2026-07.
- Missing months: 0; duplicate months: 0; missing/nonnumeric values: 0; IQR flags: 0.
{{unit:export_history.csv}}
{{provenance:export_history.csv}}
- SHA-256 (CRLF normalized to LF): `{{sha256:export_history.csv}}`.

### `import_history.csv`

- Observed columns: `year_month`, `imports_thousand_usd`; 139 rows; coverage 2015-01 through 2026-07.
- Missing months: 0; duplicate months: 0; missing/nonnumeric values: 0; IQR flags: 0.
{{unit:import_history.csv}}
{{provenance:import_history.csv}}
- SHA-256 (CRLF normalized to LF): `{{sha256:import_history.csv}}`.

### `loans_individuals_history.csv`

- Observed columns: `year_month`, `loans_individuals_mln_kzt`; 140 rows; coverage 2015-01 through 2026-08.
- Missing months: 0; duplicate months: 0; missing/nonnumeric values: 0; IQR flags: 0.
{{unit:loans_individuals_history.csv}}
{{provenance:loans_individuals_history.csv}}
- SHA-256 (CRLF normalized to LF): `{{sha256:loans_individuals_history.csv}}`.

### `loans_legal_entities_history.csv`

- Observed columns: `year_month`, `loans_legal_entities_mln_kzt`; 140 rows; coverage 2015-01 through 2026-08.
- Missing months: 0; duplicate months: 0; missing/nonnumeric values: 0; IQR flags: 14 consecutive months, 2025-07 through 2026-08. These flags may indicate a distribution shift; they are not evidence of erroneous values.
{{unit:loans_legal_entities_history.csv}}
{{provenance:loans_legal_entities_history.csv}}
- SHA-256 (CRLF normalized to LF): `{{sha256:loans_legal_entities_history.csv}}`.

## Rebuild conventions and limitations

The authoritative panel rule is the raw level of each of the six factors at decision calendar month minus two. Household lending is rounded to eight decimal places to preserve the existing panel storage precision; this is not a growth/log/difference transform. This reproduces the existing 90-row panel. The two-month offset is a reconstruction convention, not a verified publication lag. The prior one-month growth notes for exports and individual lending are obsolete, not used by the current panel, and must not be applied in `build_panel()`.

`data/raw/` files are immutable inputs. No source download, publisher identity, release timing, units, or revision history could be independently verified from the files themselves.
