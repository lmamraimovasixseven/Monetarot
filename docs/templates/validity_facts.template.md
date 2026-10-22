<!-- Template for docs/validity_facts.md. Edit here, then run `python run.py facts`.
     Tags: [source] = recorded in the repo or artifact; [estimate] = a model or test result; [assumption] = not verified. -->
# Validity facts

Bullet facts for the student's validity section. Numbers come from `outputs/numbers_for_note.json`, `config/release_lag.json` and the fact forms.

## Construct validity

- The indicator is P(Increase) − P(Decrease) for the next decision; it ignores the size of a rate change. [source]
- Indicator: {{f.week2_indicator_name}}; suggested by {{f.indicator_suggested_by}} on {{f.indicator_suggested_on}}, {{f.indicator_suggested_where}}; Week 2 status: {{f.week2_approval_status}}; written proof: {{f.indicator_written_proof}}. [source: student statement]
- The six factors are proxies: inflation for price pressure, consumption for demand, both lending series for credit conditions, exports and imports for the external sector. [assumption]
- Proxy omissions: no exchange rate, inflation expectations, oil price, foreign policy rates or fiscal stance enter the model. [source]
- Units (form): recorded for {{r.units_recorded}} of {{r.raw_file_count}} files; conflicts with CSV column names: {{r.unit_conflicts}}; provenance form cells filled: {{r.series_filled_cells}} of {{r.series_total_cells}}. [source]
- Trade is in USD and lending in KZT, so the 12-month log growth of trade mixes volume, price and exchange-rate effects, notably around the 2015 and 2022 devaluations; the model does not separate them. [assumption]

## Internal validity

- Omitted variables: the omitted series above may drive both the factors and the decisions. [assumption]
- Reverse causality: past base-rate decisions affect later lending, consumption and inflation, and these feed back into the factors. [assumption]
- Release lag: assumed decision month minus {{r.assumed_lag_months}}, tolerating real lags up to {{r.longest_lag_tolerated_days}} days; real lags known for {{r.real_lags_known}} of {{r.factor_series_count}} factor series. [assumption]
- Release-lag limitation: {{r.lag_limitation}} [assumption]
- Lag sensitivity: {{n.robustness_RB06_name}} gives {{n.robustness_RB06_benchmark_conclusion}}; {{n.robustness_RB07_name}} gives {{n.robustness_RB07_benchmark_conclusion}}. [estimate]
- Regimes: slope-stability LR test p {{n.stability_lr_p}} ({{n.stability_lr_flag}}), {{n.stability_split_n_early}} vs {{n.stability_split_n_late}} estimation decisions. [estimate]
- Household lending non-stationary: ADF p {{n.unit_root_household_lending_adf_p}}, KPSS p {{n.unit_root_household_lending_kpss_p}} (table bound). [estimate]

## External validity

- One central bank; decisions {{n.sample_usable_start}} to {{n.sample_usable_end}} ({{n.n_usable}} usable). [source]
- The holdout ({{n.sample_holdout_start}} to {{n.sample_holdout_end}}) overlaps earlier exploratory backtests; it is not untouched. [source]
- No real-time vintages; revisions known for {{r.revised_known}} of {{r.raw_file_count}} series. [source]

## Statistical validity

- Specifications run: {{n.total_specifications}} (main model plus {{n.robustness_check_count}} robustness checks). [source]
- Multiple-testing families: slopes: {{n.family_slope_coefficients}}; joint test: {{n.family_joint_slope_lr}}; diagnostics: {{n.family_diagnostics}}; robustness: {{n.family_robustness_specifications}}. [source]
- Household lending slope: raw p {{n.p_raw_household_lending}}, Holm p {{n.p_holm_household_lending}}; joint LR p {{n.joint_lr_p}}. [estimate]
- Power: {{n.n_estimation}} estimation decisions; holdout {{n.n_holdout}} with {{n.holdout_actual_increase_count}} increases and {{n.holdout_actual_decrease_count}} decreases; no power calculation was run (`UNKNOWN`), so power is likely low. [assumption]
- Out of sample: RMSE {{n.oos_model_rmse}} vs Always Hold {{n.oos_hold_rmse}}, ratio {{n.rmse_ratio}}. [estimate]
- Fragility of the negative result: the model beats Always Hold in {{n.robustness_flipped_benchmark_count}} of {{n.robustness_check_count}} checks ({{n.robustness_flipped_benchmark_ids}}); only {{n.robustness_survivors}} survives the strict rule. [estimate]
- Economic size: factors meaningful by the stated rule: {{n.econ_meaningful_factors}} (`outputs/economic_size.md`). [estimate]
