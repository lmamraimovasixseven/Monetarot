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

Provenance fields below are generated from `docs/facts_to_fill.csv` by `python run.py facts`; 61 of 77 cells are filled in and the rest are `UNKNOWN`. Shared-publisher status is not part of the form. Units in the form are compared with the column-name hints in each file section. Column-name unit hints below are not verified units. All file SHA-256 values are included so the observed inputs can be identified without modifying them.

### `base_rate_history.csv`

- Observed columns: `year_month`, `rate`; 133 rows; coverage 2015-09 through 2026-09.
- Missing months: 0; duplicate months: 0; missing/nonnumeric values: 0; IQR flags: 0.
- Unit (form, student statement): percent (source column header «Размер ставки, %»); column `rate` hint: none; check: no unit hint in the column name to compare. Neither the form nor the CSV header is changed.
- Publisher: secondary: prg.kz (table); primary: National Bank of Kazakhstan, as cited in the table's own notes (NBK press releases).
- Source title: Базовая ставка Национального Банка РК (2015-2026).
- Table or series identifier: Базовая ставка Национального Банка РК (2015-2026); no series code on the source page (student-stated); identified by title.
- URL or API query: https://prg.kz/document/?doc_id=36378707&pos=6;67.
- Navigation path: `UNKNOWN`.
- Publication date: `UNKNOWN`.
- Retrieval date: 2026-10-08.
- Release lag (days after the reference month ends): `UNKNOWN`.
- Revised after release: `UNKNOWN`.
- Unit (form): percent (source column header «Размер ставки, %»).
- Notes: The source is a table published on prg.kz, not an NBK publication. Its columns are «Дата установления ставки (с)», «Размер ставки, %», «Коридор базовой ставки, %» and «Примечание»; the notes column refers to NBK press releases (student statement). Upper bound from file update date: UNKNOWN; not applicable to the target.
- CSV in data/raw extracted manually by the student from the downloaded Excel file: years and months and the needed indicator only; sheet, rows and columns used: UNKNOWN.
- SHA-256 (CRLF normalized to LF): `775a2fe2ece4f5adb7562e2b30ee4e701f77edf6a24c76efdc91284bae31fc26`.

### `inflation_history.csv`

- Observed columns: `year_month`, `inflation`; 141 rows; coverage 2015-01 through 2026-09.
- Missing months: 0; duplicate months: 0; missing/nonnumeric values: 0; IQR flags: 4 (2022-11 through 2023-02).
- Unit (form, student statement): year-on-year percent change; column `inflation` hint: none; check: no unit hint in the column name to compare. Neither the form nor the CSV header is changed.
- Publisher: Bureau of National Statistics.
- Source title: Индекс потребительских цен по 12 основным разделам.
- Table or series identifier: Индекс потребительских цен по 12 основным разделам; no series code on the source page (student-stated); identified by title.
- URL or API query: https://stat.gov.kz/api/iblock/element/1549/file/ru/.
- Navigation path: Главная > Отрасли > Экономика > Статистика цен.
- Publication date: 2026-10-01.
- Retrieval date: 2026-10-08.
- Release lag (days after the reference month ends): `UNKNOWN`.
- Revised after release: `UNKNOWN`.
- Unit (form): year-on-year percent change.
- Notes: Observation only, not a release-lag rule: the February 2026 issue was published 2026-03-02. Derived by manual cleaning from the downloaded Excel file (student statement). Upper bound from file update date: 1 day; true release lag UNKNOWN.
- CSV in data/raw extracted manually by the student from the downloaded Excel file: years and months and the needed indicator only; sheet, rows and columns used: UNKNOWN.
- SHA-256 (CRLF normalized to LF): `229e1458627821378dbad18777e0a7e02f034988602df0a394d2aba4e669ab89`.

### `consumption_history_updated.csv`

- Observed columns: `year_month`, `consumption_yoy`; 140 rows; coverage 2015-01 through 2026-08.
- Missing months: 0; duplicate months: 0; missing/nonnumeric values: 0; IQR flags: 17 (2015-10, 2015-11, 2015-12, 2016-01, 2020-03, 2020-04, 2020-05, 2020-07, 2021-01, 2021-04, 2022-01, 2022-04, 2022-06, 2023-01, 2023-11, 2024-10, 2024-11).
- Unit (form, student statement): year-on-year percent change; column `consumption_yoy` hint: year-on-year; check: agrees (year-on-year). Neither the form nor the CSV header is changed.
- Publisher: Bureau of National Statistics.
- Source title: Индексы физического объема розничной торговли по месяцам 2015-2026 годы.
- Table or series identifier: Индексы физического объема розничной торговли по месяцам 2015-2026 годы; no series code on the source page (student-stated); identified by title.
- URL or API query: https://stat.gov.kz/api/iblock/element/4084/file/ru/.
- Navigation path: Главная > Отрасли > Экономика > Статистика внутренней торговли > Розничная торговля.
- Publication date: 2026-10-07.
- Retrieval date: 2026-10-08.
- Release lag (days after the reference month ends): `UNKNOWN`.
- Revised after release: `UNKNOWN`.
- Unit (form): year-on-year percent change.
- Notes: Monthly series; the CSV holds the year-on-year percentage change, which the student checked against the source. Derived by manual cleaning from the downloaded Excel file (student statement). Upper bound from file update date: 37 days; true release lag UNKNOWN. Observation only, not a lag rule: the retail-trade February 2025 issue was published 2025-03-12 (12 days after the month ended).
- CSV in data/raw extracted manually by the student from the downloaded Excel file: years and months and the needed indicator only; sheet, rows and columns used: UNKNOWN.
- SHA-256 (CRLF normalized to LF): `e7cfb67381a5585d833d5eaa64e430aa34b1fb3af1e207c29c7179cb25b1eb63`.

### `export_history.csv`

- Observed columns: `year_month`, `exports_thousand_usd`; 139 rows; coverage 2015-01 through 2026-07.
- Missing months: 0; duplicate months: 0; missing/nonnumeric values: 0; IQR flags: 0.
- Unit (form, student statement): thousand USD; column `exports_thousand_usd` hint: thousand USD; check: agrees. Neither the form nor the CSV header is changed.
- Publisher: Bureau of National Statistics.
- Source title: Товарооборот в иностранной валюте (экспорт).
- Table or series identifier: Товарооборот в иностранной валюте (экспорт); no series code on the source page (student-stated); identified by title.
- URL or API query: https://stat.gov.kz/api/iblock/element/446905/file/ru/.
- Navigation path: Главная > Отрасли > Экономика > Статистика внешней, взаимной торговли и товарных рынков.
- Publication date: 2026-10-05.
- Retrieval date: 2026-10-08.
- Release lag (days after the reference month ends): `UNKNOWN`.
- Revised after release: `UNKNOWN`.
- Unit (form): thousand USD.
- Notes: Derived by manual cleaning from the downloaded Excel file (student statement). Upper bound from file update date: 66 days; true release lag UNKNOWN.
- CSV in data/raw extracted manually by the student from the downloaded Excel file: years and months and the needed indicator only; sheet, rows and columns used: UNKNOWN.
- SHA-256 (CRLF normalized to LF): `7f9d741d2374dbb1de7a5f3eaa240c5ec269996075d251ca56ab3f1bf30b073a`.

### `import_history.csv`

- Observed columns: `year_month`, `imports_thousand_usd`; 139 rows; coverage 2015-01 through 2026-07.
- Missing months: 0; duplicate months: 0; missing/nonnumeric values: 0; IQR flags: 0.
- Unit (form, student statement): thousand USD; column `imports_thousand_usd` hint: thousand USD; check: agrees. Neither the form nor the CSV header is changed.
- Publisher: Bureau of National Statistics.
- Source title: Товарооборот в иностранной валюте (импорт).
- Table or series identifier: Товарооборот в иностранной валюте (импорт); no series code on the source page (student-stated); identified by title.
- URL or API query: https://stat.gov.kz/api/iblock/element/446906/file/ru/.
- Navigation path: Главная > Отрасли > Экономика > Статистика внешней, взаимной торговли и товарных рынков.
- Publication date: 2026-10-05.
- Retrieval date: 2026-10-08.
- Release lag (days after the reference month ends): `UNKNOWN`.
- Revised after release: `UNKNOWN`.
- Unit (form): thousand USD.
- Notes: Derived by manual cleaning from the downloaded Excel file (student statement). Upper bound from file update date: 66 days; true release lag UNKNOWN.
- CSV in data/raw extracted manually by the student from the downloaded Excel file: years and months and the needed indicator only; sheet, rows and columns used: UNKNOWN.
- SHA-256 (CRLF normalized to LF): `bcfc45571f64b363085f56d204c71c6b219d2c455d98b2d745a65f4bd4a6260a`.

### `loans_individuals_history.csv`

- Observed columns: `year_month`, `loans_individuals_mln_kzt`; 140 rows; coverage 2015-01 through 2026-08.
- Missing months: 0; duplicate months: 0; missing/nonnumeric values: 0; IQR flags: 0.
- Unit (form, student statement): million KZT; column `loans_individuals_mln_kzt` hint: million KZT; check: agrees. Neither the form nor the CSV header is changed.
- Publisher: National Bank of Kazakhstan.
- Source title: Кредиты экономике от банков второго уровня (исторические данные).
- Table or series identifier: Кредиты экономике от банков второго уровня (исторические данные); no series code on the source page (student-stated); identified by title.
- URL or API query: https://nationalbank.kz/file/download/135680.
- Navigation path: Главная > Статистика > Денежно-кредитная и банковская статистика > Кредитный рынок > Кредиты экономике от банков второго уровня (исторические данные).
- Publication date: 2026-09-24.
- Retrieval date: 2026-10-08.
- Release lag (days after the reference month ends): `UNKNOWN`.
- Revised after release: `UNKNOWN`.
- Unit (form): million KZT.
- Notes: Same Excel file as loans_legal_entities_history.csv. Derived by manual cleaning from the downloaded Excel file (student statement). Upper bound from file update date: 24 days; true release lag UNKNOWN.
- CSV in data/raw extracted manually by the student from the downloaded Excel file: years and months and the needed indicator only; sheet, rows and columns used: UNKNOWN.
- SHA-256 (CRLF normalized to LF): `151c522fc0b3e115aa6ce962a9b035949316406c47cdabeb2f0e15b50b93431b`.

### `loans_legal_entities_history.csv`

- Observed columns: `year_month`, `loans_legal_entities_mln_kzt`; 140 rows; coverage 2015-01 through 2026-08.
- Missing months: 0; duplicate months: 0; missing/nonnumeric values: 0; IQR flags: 14 consecutive months, 2025-07 through 2026-08. These flags may indicate a distribution shift; they are not evidence of erroneous values.
- Unit (form, student statement): million KZT; column `loans_legal_entities_mln_kzt` hint: million KZT; check: agrees. Neither the form nor the CSV header is changed.
- Publisher: National Bank of Kazakhstan.
- Source title: Кредиты экономике от банков второго уровня (исторические данные).
- Table or series identifier: Кредиты экономике от банков второго уровня (исторические данные); no series code on the source page (student-stated); identified by title.
- URL or API query: https://nationalbank.kz/file/download/135680.
- Navigation path: Главная > Статистика > Денежно-кредитная и банковская статистика > Кредитный рынок > Кредиты экономике от банков второго уровня (исторические данные).
- Publication date: 2026-09-24.
- Retrieval date: 2026-10-08.
- Release lag (days after the reference month ends): `UNKNOWN`.
- Revised after release: `UNKNOWN`.
- Unit (form): million KZT.
- Notes: Same Excel file as loans_individuals_history.csv. Derived by manual cleaning from the downloaded Excel file (student statement). Upper bound from file update date: 24 days; true release lag UNKNOWN.
- CSV in data/raw extracted manually by the student from the downloaded Excel file: years and months and the needed indicator only; sheet, rows and columns used: UNKNOWN.
- SHA-256 (CRLF normalized to LF): `1d0e759f9993918eee84c85ac97bc0505a11601366f37eca647ee4622f9a63ed`.

## Rebuild conventions and limitations

The authoritative panel rule is the raw level of each of the six factors at decision calendar month minus two. Household lending is rounded to eight decimal places to preserve the existing panel storage precision; this is not a growth/log/difference transform. This reproduces the existing 90-row panel. The two-month offset is a reconstruction convention, not a verified publication lag. The prior one-month growth notes for exports and individual lending are obsolete, not used by the current panel, and must not be applied in `build_panel()`.

`data/raw/` files are immutable inputs. No source download, publisher identity, release timing, units, or revision history could be independently verified from the files themselves.
