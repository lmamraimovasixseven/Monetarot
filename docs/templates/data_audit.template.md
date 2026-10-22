<!-- Template for docs/data_audit.md. Edit here, then run `python run.py facts`.
     r.* values are computed from data/raw/, data/processed/, src/ingest.py, config/ and the fact form. -->
# Data audit: frequency and alignment

Facts computed by `python run.py facts` from the raw files, the processed panel and `src/ingest.py`. Nothing here changes the estimation.

## All raw files

{{r.frequency_table}}

## Units

Units come from `docs/facts_to_fill.csv` (student statement) and are compared with the unit hint in each CSV column name. A conflict is reported, not resolved: neither the form nor the CSV header is changed.

{{r.units_table}}

- Units recorded in the form: {{r.units_recorded}} of {{r.raw_file_count}} files. Conflicts with the column-name hint: {{r.unit_conflicts}}. Scale not stated in the form: {{r.unit_scale_unstated}}.
- The model uses 12-month log growth for exports, imports and both lending series, so a constant unit scale (thousand vs million) cancels out of the model inputs; the currency does not, because the growth of a USD or KZT value includes exchange-rate and price movements.

## Consumption series (`{{r.audit_file}}`)

### (a) Frequency and date range of the CSV

- Column `{{r.audit_column}}`; {{r.audit_rows}} rows from {{r.audit_first}} to {{r.audit_last}}; missing months {{r.audit_missing_months}}; duplicate months {{r.audit_duplicate_months}}.
- Frequency: {{r.audit_frequency}}.
- Month-to-month repeats: {{r.audit_repeats}} of {{r.audit_pairs}} consecutive pairs are equal; the longest run of one identical value is {{r.audit_longest_run}} months.
- Form (student statement): {{r.audit_form_notes}}

### (b) How the values reach the decision dates

- `src/ingest.py` reads the file with `read_monthly_series`, keeps the values as levels (consumption is not in `LOG_GROWTH_FEATURES`), reindexes to calendar months with `complete_month_calendar` and selects one month per decision with `apply_release_lag` → `align_to_decision_months`.
- `complete_month_calendar` leaves a missing month as missing; `align_to_decision_months` looks up exactly one reference month. Fill or interpolation calls found in `src/ingest.py`: {{r.fill_calls_in_ingest}}. {{r.fill_verdict}}
- Check against the data: for all {{r.audit_decisions}} usable decisions in `data/processed/model_panel.csv`, the consumption value equals the raw CSV value at the reference month (mismatches: {{r.audit_mismatches}}).
- Reuse of one value: in {{r.audit_shared_months}} reference months, two or more decisions fall in the same calendar month and therefore use the same consumption value ({{r.audit_shared_decisions}} decisions in total). This is a repeated lookup, not an interpolation.

### (c) Release-lag rule

- Each decision uses the value for the calendar month {{r.assumed_lag_months}} months before the decision month (`assumed_release_lag_months` in `config/release_lag.json`), the same rule as for every factor.
- Real publication lag from the form: {{r.audit_form_lag}}. Whether the assumption holds is reported in `outputs/release_lag_check.md`.
- Source (form): publisher {{r.audit_form_publisher}}; URL {{r.audit_form_url}}; retrieved {{r.audit_form_retrieval}}.
