<!-- Template for docs/indicator_card.md. Edit here, then run `python run.py facts`.
     n.* = outputs/numbers_for_note.json, f.* = docs/facts_to_fill.md, r.* = computed from the repo and docs/facts_to_fill.csv. -->
# Indicator card: NBK policy pressure score

Draft for the student's Table 1. Facts come from the repository and the fact forms; anything not known is `UNKNOWN`. Fill the forms (`docs/facts_to_fill.csv`, `docs/facts_to_fill.md`) and run `python run.py facts` to update this card.

| Row | Content |
|---|---|
| 1. Concept | Pressure toward a hike or a cut at the next NBK base-rate decision, read from six macro factors. Indicator (student statement): {{f.week2_indicator_name}}; Week 2 status: {{f.week2_approval_status}}. Named user: {{f.named_user}}. |
| 2. Formula | Score = P(Increase) − P(Decrease) from an ordered logit with HC0 robust covariance; see the formula below. |
| 3. Unit and scale | Probability difference; −1 (a cut is certain) to +1 (a hike is certain); 0 = balanced. Latest: {{n.headline_score}} on {{n.latest_decision_date}}, 95% band {{n.headline_score_band_low}} to {{n.headline_score_band_high}}. Input units (form): {{r.units_summary}}. Conflicts with CSV column names: {{r.unit_conflicts}}. |
| 4. Frequency and lag | One value per NBK decision date (irregular spacing). Raw files: {{r.monthly_complete_files}} of {{r.raw_file_count}} monthly with every calendar month present (`docs/data_audit.md`). Each decision uses the exact value for the month {{r.assumed_lag_months}} months before the decision month (assumption, `config/release_lag.json`); {{r.fill_short}}. Real lags known for {{r.real_lags_known}} of {{r.factor_series_count}} factor series (`outputs/release_lag_check.md`). |
| 5. Coverage | {{n.n_usable}} usable decisions, {{n.sample_usable_start}} to {{n.sample_usable_end}} ({{n.n_dropped}} dropped); estimation {{n.n_estimation}}, holdout {{n.n_holdout}}. |
| 6. Source and vintage | {{r.raw_file_count}} CSVs derived by manual cleaning from downloaded files. Publishers: {{r.publisher_summary}}. Retrieval dates: {{r.retrieval_summary}}. Single vintage; revisions known for {{r.revised_known}} series. Table below. |
| 7. Transformations | Levels for inflation and consumption (the consumption CSV already holds year-on-year % changes); 12-month log growth for exports, imports and both lending series; all aligned by `apply_release_lag` with an exact month lookup, {{r.fill_short}}. 12-month log growth removes the unit scale but not the currency effect (trade in USD, lending in KZT). Table below. |
| 8. Known weaknesses | {{n.verdict_sentence}} Model beats Always Hold in {{n.robustness_flipped_benchmark_count}} of {{n.robustness_check_count}} robustness checks; stability test {{n.stability_lr_flag}}; household lending non-stationary; release lag unverified; no vintages. List below. |

## 1. Concept

- Policy pressure at NBK base-rate decisions, as the model-implied balance between the probability of a hike and of a cut.
- Indicator (student statement): {{f.week2_indicator_name}}. Suggested by {{f.indicator_suggested_by}} on {{f.indicator_suggested_on}}, {{f.indicator_suggested_where}}; written proof: {{f.indicator_written_proof}}.
- Week 2 status: {{f.week2_approval_status}}. Same as "NBK base-rate decision" in the formal record: {{f.week2_indicator_equals_nbk_base_rate_decision}}.
- Written approval of decision-date sampling: {{f.sampling_approval_who}}, {{f.sampling_approval_when}}, proof at {{f.sampling_approval_proof_location}}.
- Named user: {{f.named_user}}. New element: {{f.new_element}}.

## 2. Formula

With factors x₁…x₆, slopes β and cutpoints κ₁ < κ₂ (stored in `model/artifact.json`):

- η = β₁x₁ + … + β₆x₆
- P(Decrease) = Λ(κ₁ − η), P(Increase) = 1 − Λ(κ₂ − η), P(Hold) = the remainder, with Λ the logistic function
- **Score = P(Increase) − P(Decrease) = 1 − Λ(κ₂ − η) − Λ(κ₁ − η)**

Estimated cutpoints: κ₁ = {{n.cutpoint_1}}, κ₂ = {{n.cutpoint_2}}; slopes in `outputs/results_table.md`. Code: estimation `_fit_ordered` in `src/model.py` (statsmodels `OrderedModel`); serving `ordered_probabilities` and `policy_pressure_score` in `src/app.py`; band `score_and_delta_band` (delta method, HC0 covariance).

## 3. Unit and scale

- Probability difference, dimensionless, bounded by −1 and +1.
- Latest value {{n.headline_score}} ({{n.latest_decision_date}}); 95% band {{n.headline_score_band_low}} to {{n.headline_score_band_high}} (width {{n.headline_score_band_width}}).
- Input units (form, student statement), compared with the CSV column names:

{{r.units_table}}

- Next decision: Increase {{n.next_round_probability_increase}}, Hold {{n.next_round_probability_hold}}, Decrease {{n.next_round_probability_decrease}}.

## 4. Frequency and lag

- Frequency of the indicator: NBK base-rate decision dates (irregular; dates in `config/nbk_decision_dates.csv`).
- Frequency of the inputs (computed from the raw files; details in `docs/data_audit.md`):

{{r.frequency_table}}

- Alignment: `align_to_decision_months` looks up exactly one reference month per decision; fill or interpolation calls in `src/ingest.py`: {{r.fill_calls_in_ingest}}. Decisions in the same calendar month reuse one value ({{r.audit_shared_decisions}} decisions in {{r.audit_shared_months}} months).
- Assumed lag: month of decision minus {{r.assumed_lag_months}}; this offset tolerates real publication lags up to {{r.longest_lag_tolerated_days}} days for every decision.
- Real lags: known for {{r.real_lags_known}} of {{r.factor_series_count}} factor series; series where the assumption fails: {{r.release_lag_failures}}. Details: `outputs/release_lag_check.md`.

## 5. Coverage

- Decisions used: {{n.n_usable}} ({{n.sample_usable_start}} to {{n.sample_usable_end}}); dropped for missing factors: {{n.n_dropped}}.
- Estimation sample {{n.sample_estimation_start}} to {{n.sample_estimation_end}} ({{n.n_estimation}}); holdout {{n.sample_holdout_start}} to {{n.sample_holdout_end}} ({{n.n_holdout}}).

{{r.coverage_table}}

## 6. Source and vintage

{{r.sources_table}}

- The CSVs were derived by manual cleaning from the downloaded files (student statement; `data/raw/SOURCES.md`, `docs/manual_steps_found.md`). Values not in the form are `UNKNOWN`.
- Vintage: one current vintage per file; real-time vintages are not available.
- Input data hash (processed panel, normalized line endings): `{{n.data_sha256}}`.

## 7. Transformations

{{r.transformations_table}}

- 12-month log growth removes a constant unit scale (thousand vs million) but not the currency effect: growth of a USD trade value or a KZT loan stock includes price and exchange-rate movements.

## 8. Known weaknesses

- {{n.verdict_sentence}}
- The model beats Always Hold in {{n.robustness_flipped_benchmark_count}} of {{n.robustness_check_count}} robustness checks; only {{n.robustness_survivors}} survives the strict rule (`outputs/robustness_table_short.md`).
- Parameter stability rejected: p {{n.stability_lr_p}} ({{n.stability_lr_flag}}).
- Household lending fails both stationarity tests: ADF p {{n.unit_root_household_lending_adf_p}}, KPSS p {{n.unit_root_household_lending_kpss_p}} (table bound).
- Release lag assumed, not verified; no vintages; unit conflicts with CSV column names: {{r.unit_conflicts}}.
- Irregular decision-date sampling; small holdout ({{n.n_holdout}} decisions: {{n.holdout_actual_increase_count}} increases, {{n.holdout_actual_decrease_count}} decreases).
