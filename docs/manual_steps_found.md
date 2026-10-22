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
