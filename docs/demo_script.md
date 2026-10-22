# Five-minute demo script and examiner questions

Read numbers **from the screen**, not from this script; they come from `model/artifact.json` and change if the model is re-estimated. Anything marked STUDENT is a fact only the student can supply.

## Script (five minutes)

| Time | Step | What to do and say |
|---|---|---|
| 0:00–0:30 | Start | The environment is prepared in advance: the repository is cloned (`git clone https://github.com/lmamraimovasixseven/monetarot.git`) and the packages are installed as in `README.md`. Show the project folder and run `python run.py`. Say: "One command starts the site; it only reads `data/processed/` and `model/artifact.json` and fits nothing." |
| 0:30–1:15 | Headline | On the landing view, read the **policy pressure score** with its **unit** (P(Increase) − P(Decrease), from −1 to +1), the **period** (decision date and factor-data month) and the **latest change**. Point to the next-decision probabilities and the warning that the model does not beat Always Hold. |
| 1:15–1:45 | Why these probabilities? | On the Overview tab, point to the "Why these probabilities?" panel under the two round blocks: both rounds are the same conditional estimate from the latest factor values, Hold is the most common decision, the Increase and Decrease intervals overlap, and the model does not beat Always Hold. Read its numbers from the screen. |
| 1:45–2:45 | Move the scenario | Open **Drivers and scenario**. Read the three largest driver contributions, then choose a factor in the selector (household lending by default) and move its slider: the scenario score and its 95% band both change. Say: "The band uses the stored covariance and the delta method; nothing is re-estimated." |
| 2:45–3:45 | Disconnect and reload | Turn the network off and reload the page. The **CACHED DATA** label appears at once and the page still renders, because the calendar check runs in the background with a two-second limit. Turn the network back on. |
| 3:45–4:30 | Decision rule | <!-- generated:decision-rule:start -->State the chosen rule: option 1, direction flag (band clear of zero) (`decision_rule_option` in `docs/facts_to_fill.md`), for the named user, a bank treasury analyst who, before an NBK base-rate meeting, needs to know whether the model shows a distinguishable tilt in rate pressure. Say it in the form "if the indicator moves beyond X, do Y, because Z" as worded in `docs/decision_rule.md`, read today's status from the screen, and say that it is a monitoring rule, not a forecast.<!-- generated:decision-rule:end --> |
| 4:30–5:00 | Reproducibility | Run `python run.py regression`: it re-estimates the main model in memory, prints each estimate, robust SE and p-value next to the stored one with PASS or FAIL, and writes nothing. Mention `python -m src.check` (rebuilds everything in a temporary folder and compares within the artifact's tolerance) and `python run.py test`. Show the **Evidence** tab's robustness table if time allows. |

## Twenty likely examiner questions

### Data

1. **Where do the data come from?** Six CSVs were extracted manually from Excel files of the Bureau of National Statistics and the National Bank of Kazakhstan, and the base-rate history from a prg.kz table that cites NBK press releases (titles, URLs and dates in `data/raw/SOURCES.md`).
2. **How are monthly factors matched to irregular decision dates?** Each decision takes the exact value for the month a fixed number of months before the decision month (`config/release_lag.json`, `apply_release_lag` in `src/ingest.py`), with no interpolation or fill (`docs/data_audit.md`).
3. **Is there look-ahead bias?** <!-- generated:lag-answer:start -->It cannot be ruled out. Real release lags are UNKNOWN, and file update dates give only upper bounds (true lag ≤ bound). The model assumes data for month M−2 are available at a decision in month M, about 45 days later (median 44; 31 to 59); exports and imports (66 days) exceed the assumed availability at every decision (88 of 88); consumption (37 days) exceeds the assumed availability at decisions early in the month (15 of 88), so look-ahead cannot be ruled out there. The nearest existing check is RB07 ("Ordered logit: release lag 3 months"), which shifts all factors; a check that shifts only the trade series was not run (`outputs/release_lag_check.md`, `outputs/robustness_table_short.md`).<!-- generated:lag-answer:end -->
4. **Did you change the raw data?** No: `data/raw/` CSVs are only read, their hashes are recorded in `data/raw/SOURCES.md`, and units are compared with the column names without overwriting either (`docs/data_audit.md`).

### Model

5. **Why an ordered logit?** The outcome is ordered (Decrease < Hold < Increase) but the gaps are not equal-sized, which an ordered logit respects (`docs/model_spec.md`).
6. **Does the model beat the benchmark?** No: its holdout RMSE is not below Always Hold's. Read the RMSE ratio (model ÷ Always Hold) from the screen, in the warning on the Overview tab or the holdout table on the Evidence tab; it is also in `outputs/oos_comparison.md`.
7. **Which factor matters?** <!-- generated:q7-answer:start -->Only household lending is significant after Holm adjustment (raw p 0.005, Holm p 0.031; `outputs/results_table.md`), and it is the only one-SD move that is economically meaningful by the stated rule (`outputs/economic_size.md`). In RB09 ("Differenced non-stationary factors") its coefficient is 0.3100 (raw p 0.281, Holm p 0.651; `outputs/robustness_table.md`), so the only significant factor loses significance when its non-stationarity is removed.<!-- generated:q7-answer:end -->
8. **Is the result robust?** <!-- generated:robustness-answer:start -->No: in 6 of 9 checks the model beats Always Hold on that check's own holdout, and only RB06 reproduces both the signs and the conclusion (`outputs/robustness_table_short.md`).<!-- generated:robustness-answer:end -->
9. **How did you handle multiple testing?** Holm across the six slopes, a single unadjusted joint LR test, raw diagnostics, and Holm within each robustness specification (`docs/deviations.md`, D6).

### App

10. **Does the app estimate anything?** No: `src/app.py` only reads the artifact and `data/processed/`, and a test checks for estimator calls in its source (`tests/test_backtest_ui.py`).
11. **How is the uncertainty band computed?** With the delta method and the stored HC0 covariance in `score_and_delta_band` (`src/app.py`).
12. **What happens without internet?** The calendar check runs in a background thread with a two-second limit and the page shows the CACHED DATA label (`tests/test_acceptance.py`, check 7).
13. **What if the model file is missing?** The page shows a plain message naming `model/artifact.json` and the command to rebuild it (`tests/test_acceptance.py`, check 8).

### Tests and reproducibility

14. **How do you know the numbers reproduce?** `python -m src.check` re-runs ingest, model, report and facts in a temporary folder and compares every number with the committed files within the tolerance stored in the artifact (`src/check.py`).
15. **How do you keep the repository clean and free of secrets?** The test session fails if `git status` changes (`tests/conftest.py`), and `scripts/scan_secrets.py` scans the working tree and the full git history.

### Purpose and use

16. **Why use a model that does not beat Always Hold?** It is a monitoring tool, not a forecast: it shows the pressure toward a hike or a cut with an uncertainty band and a rule for one named user (`docs/decision_rule.md`). Always Hold wins because Hold is the most common outcome, and we show that result openly in the Evidence tab (`outputs/oos_comparison.md`).
17. **What did you add beyond the basic assignment?** <!-- generated:new-element:start -->We extend ordered-outcome models of central-bank decisions, published for US Federal Reserve decisions, to National Bank of Kazakhstan base-rate decisions, using a combination of six domestic factors (inflation, exports, imports, corporate lending, household lending, consumption).<!-- generated:new-element:end -->
18. **When does the decision rule fire?** Only when the whole 95% band of the policy pressure score is entirely above or below zero. Read the band and today's status from the decision-rule panel on the Overview tab (`docs/decision_rule.md`).
19. **Why are both rounds identical?** <!-- generated:rounds-answer:start -->Both rounds use the latest available factor values (factor data month 2026-07), because future factor values are unknown, so both blocks are the same conditional estimate and only the date differs; this is not an error and not a separate forecast for each date (the "Why these probabilities?" panel on the Overview tab).<!-- generated:rounds-answer:end -->
20. **Why does Hold dominate?** <!-- generated:hold-answer:start -->Hold was the most common NBK decision in the sample (49 of 90 decisions in `data/processed/nbk_decisions_clean.csv`), so Hold gets the highest probability and always predicting Hold is hard to beat (`outputs/oos_comparison.md`).<!-- generated:hold-answer:end -->
