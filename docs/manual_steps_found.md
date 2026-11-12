# Manual source-file steps reported by the data owner

Original publisher downloads are unavailable. The owner reports that all seven CSVs were manually cleaned before upload; specific edits are not documented for six of the files.

| File | Owner-reported manual steps | What the current file verifies |
|---|---|---|
| `inflation_history.csv` | `UNKNOWN` — specific manual edits not documented. | Monthly labels and numeric values parse; no missing months or duplicate months in the current file. |
| `export_history.csv` | `UNKNOWN` — specific manual edits not documented. | Monthly labels and numeric values parse; no missing months or duplicate months in the current file. |
| `import_history.csv` | `UNKNOWN` — specific manual edits not documented. | Monthly labels and numeric values parse; no missing months or duplicate months in the current file. |
| `loans_individuals_history.csv` | `UNKNOWN` — specific manual edits not documented. | Monthly labels and numeric values parse; no missing months or duplicate months in the current file. |
| `loans_legal_entities_history.csv` | `UNKNOWN` — specific manual edits not documented. | Monthly labels and numeric values parse; no missing months or duplicate months in the current file. |
| `consumption_history_updated.csv` | `UNKNOWN` — specific manual edits not documented. | Monthly labels and numeric values parse; no missing months or duplicate months in the current file. |
| `base_rate_history.csv` | Owner reports duplicate months were removed and calendar continuity restored. Other edits are `UNKNOWN`. Owner also reports an obsolete header line and blank line, and that a loader skips the first line. | The file currently starts with `year_month,rate`; the audited file has no duplicate or missing months. `src/data.py` is absent from this checkout, so the reported loader behavior cannot be verified. |

## Processing described by the owner (not verified in the current source tree)

The owner reports that the project loader renames date/value columns to standardized names, converts dates to monthly periods, converts values to numeric types, removes exact duplicate date-value rows, and reindexes to a monthly calendar while leaving gaps as missing values rather than imputing them. The referenced `src/data.py` is not present in the current working tree, so these loader details are recorded as owner-reported rather than verified implementation behavior.

## Open discrepancy

The owner reports manual removal of duplicate months and restoration of calendar continuity for `base_rate_history.csv`; the current file is indeed continuous and duplicate-free, but its pre-cleaning state is unavailable. The reported stale header and blank line are not present in the current file. The older `data/raw/SOURCES.md` also records growth transformations for exports and individual loans, while all six feature columns in the existing 90-row clean panel match the corresponding raw **levels** at decision month minus two. These differences are retained for human review; no raw input or clean panel was changed.

## Rows appended after the review of 2026-11-06

Authorized by the project owner (instruction of 2026-11-09): new months may be appended to `data/raw/` from a source the owner names or from files in `data/incoming/`; existing rows are never overwritten or deleted.

| Date | File | Row appended | Source | Manual step |
|---|---|---|---|---|
| 2026-11-09 | `config/nbk_decision_dates.csv` | `2026-10-27` | NBK schedule table, column «Дата установления базовой ставки», row 27.10.2026 (https://nationalbank.kz/ru/news/grafik-prinyatiya-resheniy-po-bazovoy-stavke), retrieved 2026-11-09 | Effective date typed as the next line; same effective-date convention as the existing dates. The announcement date (2026-10-23, press release https://nationalbank.kz/ru/news/press-relizy/20503) is recorded in `docs/nbk_announcement_dates.csv`, not used by the model. |
| 2026-11-09 | `data/raw/base_rate_history.csv` | `2026-10,15.75` | Same NBK schedule row (rate 15,75) | One line appended. Convention found in the file: the month value is the rate after any decision that took effect in that month. This row comes from the NBK page, not from the prg.kz table the earlier rows came from. |

`data/processed/nbk_decisions_clean.csv` was not edited by hand; it was regenerated with `python run.py data`, which reported 0 differing cells on the 90 earlier decisions and one added date (2026-10-27).

### Trade rows for 2026-08 (appended 2026-11-10)

Input: two Excel files the project owner placed in `data/incoming/` (not committed; `data/incoming/` is in `.gitignore` because the files are 64 MB and 145 MB and their metadata sheet names a contact person):

- `Товарооборот в иностранной валюте (экспорт) (2).xlsx`
- `Товарооборот в иностранной валюте (импорт) (3) (1).xlsx`

Download URL and download date of these two files: UNKNOWN (listed in `TODO_HUMAN.md`). Their sheet «Метаданные» states: indicator code 312101, «Товарооборот в иностранной валюте - Экспорт» / «- Импорт», «Дата последней актуализации» Excel serial 46310 = 2026-10-15, «Дата следующей актуализации» 46342 = 2026-11-16.

Steps (no spreadsheet program was used; the `.xlsx` XML was read with the Python standard library, read-only):

1. Opened sheet «январь-август 2026г.» (the last sheet) in each file.
2. Row 2 holds the month headers; «август 2026 года*» starts at column Y. Row 3 gives the units of columns Y, Z, AA as «тонн», «дополнительная единица измерения», «тыс.долларов США». Column AA is the value in thousand USD, the same unit as `exports_thousand_usd` / `imports_thousand_usd` (`docs/facts_to_fill.csv`: thousand USD).
3. Row 4, label «Республики Казахстан», is the national total. Cell AA4 was taken: exports 9458915.0483200122, imports 5532062.0786499996.
4. Rounded to two decimals, as in the existing rows: exports `9458915.05`, imports `5532062.08`.
5. Appended one line `2026-08,<value>` to `data/raw/export_history.csv` and `data/raw/import_history.csv`. Neither file ended with a newline, so a newline was added before the new line; the bytes of every existing row are unchanged (verified against `git show HEAD:<file>`).

Checks made before appending:

- The eight monthly totals in row 4 (columns F, I, L, O, R, U, X, AA) sum to 60389037.06 (exports) and 42570157.51 (imports) thousand USD, equal to the «январь-август 2026 года*» totals in sheet «Показатель» (60389.04 and 42570.16, in million USD). The monthly cells are therefore monthly values, not cumulative totals.
- The unit line in sheet «Метаданные» differs between the two files («Тысяч долларов США» for exports, «Миллион долларов США» for imports); the «Показатель» sheet is in millions in both, and the monthly sheet headers say «тыс.долларов США» in both. The monthly sheet header was used.
- These files are a later edition than the one the existing CSV rows came from: for 2026-01 to 2026-07 they differ from the CSV by −0.02% to +0.21% (exports) and +0.01% to +1.34% (imports). The existing rows were not changed, so 2026-08 comes from a newer vintage than the earlier months.
- The export values for 2026-06 (9820130.49) and 2026-07 (10175921.46) in this edition confirm the jump recorded in the CSV (9816470.38, 10169912.74). See `TODO_HUMAN.md`.
