# Deviations from the model specification

**No time-stamped pre-registration exists.** `docs/model_spec.md` is a draft written after exploratory classifier backtests (`outputs/legacy/`). The only date attached to it is git commit `f763e16` ("Freeze model specification before estimation", dated 2026-10-16). A git commit date is set on the author's machine and is not an independent timestamp, so it does not prove the specification preceded the analysis. No holdout outcome was used to choose transformations, lags or the estimator.

Each entry has three lines: what changed, why, and what the original specification produced. Current results are not repeated here; they are generated into `outputs/` and `model/artifact.json`. Earlier versions of this file, including superseded numbers, are in git history.

### D1. Holdout size on usable transformed rows
- **What changed:** the holdout is the last ceil(20%) of the decisions that have all six transformed factors; the first two decisions are dropped because 12-month growth is undefined at their reference month.
- **Why:** the model can only be estimated and evaluated on rows with complete transformed factors.
- **What the original specification produced:** a holdout of 18 computed from all 90 decisions; the implemented rule also gives 18 (`n_holdout` in `outputs/numbers_for_note.json`).

### D2. HC0 robust covariance
- **What changed:** the robust standard errors use the HC0 score-based sandwich estimator.
- **Why:** the specification asked for robust HC errors without naming a variant; HC0 is the unscaled sandwich.
- **What the original specification produced:** no standard errors (it is a plan, not an estimation).

### D3. Brant-type proportional-odds test
- **What changed:** implemented as a robust Wald test that the slopes are equal in the two cumulative binary logits.
- **Why:** this tests the common-slope condition directly, using the cross-equation covariance of shared observations.
- **What the original specification produced:** it named a Brant-type or LR test but produced no statistic.

### D4. Fixed-date structural-break checks
- **What changed:** split-sample likelihood-ratio tests of intercept and trend shifts at fixed dates in the estimation period; a check with fewer than eight observations on one side is reported as not applicable.
- **Why:** the task allowed split-sample LR tests; the minimum side size avoids reporting under-supported comparisons.
- **What the original specification produced:** no break test definition or result.

### D5. Contributions to the latest score change
- **What changed:** each factor's contribution is the latest expected score minus the score with that factor reset to its previous usable decision value; contributions are not additive.
- **Why:** probabilities are nonlinear, and the specification did not define a decomposition.
- **What the original specification produced:** no contribution calculation.

### D6. Multiple-testing families
- **What changed:** Holm adjustment across the six slope p-values only; the joint LR test is a single primary test; diagnostics stay raw at 5%; robustness specifications are counted and Holm-adjusted within each specification. This replaced a first implementation that applied one run-wide Holm correction.
- **Why:** the run-wide correction mixed unrelated tests and was inconsistent with the falsification rules.
- **What the original specification produced:** no p-values; the superseded run-wide values remain only in git history.

### D7. Optimizer retry for the stability model
- **What changed:** the unrestricted interaction model for the stability LR test did not converge with BFGS and was refitted with L-BFGS; both attempts are logged in `outputs/spec_log.csv`.
- **Why:** the LR comparison needs a converged unrestricted fit; the specification itself was unchanged.
- **What the original specification produced:** no stability fit.

### D8. Class-frequency comparator added after the freeze
- **What changed:** a secondary comparator using estimation-sample class frequencies was added for the log score.
- **Why:** Always Hold has an infinite log score on a holdout with non-Hold decisions, so it cannot be compared on that metric.
- **What the original specification produced:** only the Always Hold benchmark; the comparator is labelled secondary and post-freeze everywhere.

### D9. Nine robustness specifications added after the freeze
- **What changed:** checks RB01–RB09 (alternative samples, estimators, inflation measures, release lags, growth windows and differenced factors) were run after the main estimation; none is used to select a model.
- **Why:** the task required robustness checks on alternative samples, specifications and measures.
- **What the original specification produced:** no robustness checks.

### D10. Assumed release lag read from configuration
- **What changed:** the decision-month offset is read from `config/release_lag.json` instead of being written in code; its value was not changed.
- **Why:** so that real publication lags entered in `docs/facts_to_fill.csv` can be compared with the assumption (`outputs/release_lag_check.md`).
- **What the original specification produced:** the same offset (decision month minus two), stated as an unverified assumption.

### D11. Reporting rules added after estimation
- **What changed:** an economic-size rule (`outputs/economic_size.md`) and a result-blind rule for choosing three robustness checks (`outputs/robustness_table_short.md`).
- **Why:** the note needs a stated criterion for "economically meaningful" and one check per required kind.
- **What the original specification produced:** neither rule; both only summarise existing estimates and change no estimate.

## Provenance corrections

These corrections concern the recorded source metadata in `docs/facts_to_fill.csv`, not the model specification. The raw CSV files, the model and all numbers were not changed.

### D12. Unit of the trade series corrected in the provenance form
- **What changed:** the unit recorded for `export_history.csv` and `import_history.csv` was changed from "million US dollars (USD)" (commit `add580b`) to "thousand USD" (commit `cf317db`); the CSV files and their column names were not changed.
- **Why:** the unit check in `src/facts.py`, run by `python run.py facts`, reported a scale conflict between the form and the column names `exports_thousand_usd` and `imports_thousand_usd` in `docs/data_audit.md`; the student stated that the column names were right and her earlier "million" was a mistake, and the form was corrected on her instruction. The data were not wrong; only the recorded metadata was.
- **What the original specification produced:** the specification records no units for the raw series; the data, the model and every number were unaffected.

### D13. Source links corrected in the provenance form
- **What changed:** the consumption link was changed from stat.gov.kz element 454290 to element 4084 (commit `60bf49c`), and the base-rate link on prg.kz was changed from position parameter `pos=302;-4` to `pos=6;67` (commit `8fc167b`); the old links were removed from every generated file.
- **Why:** the student supplied the corrected links after reviewing the sources herself; no automated check detected the wrong links, because a check cannot tell whether a link points to the right source; tests added afterwards only ensure that the old links do not reappear.
- **What the original specification produced:** the specification records no source links; the data, the model and every number were unaffected.
## Replication check

### D14. Optimizer results that did not converge are reported as WARN by `src.check`
- **What changed:** `python -m src.check` now compares the markdown outputs line by line and reports lines from the parameter-stability LR test, from any fit marked NONCONVERGED, and from robustness check RB02 (and the entry `robustness_RB02_converged` in `outputs/numbers_for_note.json`) as WARN, "platform-sensitive (optimizer did not converge)", with the committed and rebuilt values; every other number keeps its tolerance and still fails, and no committed number was changed.
- **Why:** the BFGS attempt of the stability model (D7) and the RB02 fit on 42 observations stop before convergence, so where they stop depends on the platform's floating-point and linear-algebra details; on Linux with Python 3.13 the check reported these as failures (and, because numbers were compared as one list per file, a shifted number made every later number in the file fail), while the headline, the coefficients and the main tables matched; making these fits deterministic would require changing the optimizer and re-estimating, which would change committed numbers.
- **What the original specification produced:** the specification defines no replication check; the converged estimates (the main model, the L-BFGS stability fit that the reported stability test uses, and the other robustness checks) are unaffected, and their numbers in `outputs/numbers_for_note.json` are still checked strictly.

**D14 update.** After a further Linux run (Python 3.13), three more groups are handled by `src/check.py`; no estimation code, optimizer setting or committed number was changed. (1) The spec-log rows of type `expanding_window_fit` in `outputs/annex_diagnostics.md` record optimizer internals (such as fopt and gopt) that differ across platforms; they are reported as WARN, "platform-sensitive (optimizer internals)", with committed and rebuilt values, and this rule applies to no other row type. (2) Rounding-level differences caused by the optimizer's convergence tolerance (for example a cutpoint z-statistic differing in the sixth significant digit) are accepted in `outputs/annex_diagnostics.md` and `outputs/robustness_table.md` only, when the difference is at most 1e-4 both in absolute and in relative terms; `outputs/numbers_for_note.json`, `outputs/results_table.md`, `outputs/oos_comparison.md`, the falsification tables, `outputs/power_note.md` and the figures keep the 1e-6 tolerance. (3) The robustness count clause "Robustness checks converged: N; nonconverged or failed: M" depends on whether RB02 converges and is reported as WARN; the rest of that line is still checked at 1e-6. Any larger difference, and any difference in a main-model coefficient, standard error, p-value, the RMSE ratio or the latest score beyond 1e-6, is still a FAIL.

## Specification timing

### D15. Specification timing
- **What changed:** No time-stamped Week-4 pre-registration was submitted. The instructor allowed the model specification (docs/model_spec.md) to be accepted with the date of its commit to the repository, 16 October 2026 (commit f763e16). The generated model artifact followed on the same day (commit b42071b). Exploratory backtests were run before the specification was committed; they are disclosed in docs/model_spec.md.
- **Why:** the specification was written after the project's data and decision history had been explored.
- **What the original specification produced:** none, because no time-stamped pre-registration exists.

## Changes of 2026-11-06 (review)

### D16. Figures are compared on block averages when pixels differ
- **What changed:** `src.check` first compares the three figures pixel by pixel, as before. When pixels differ but the image size is the same and no 16 × 16-pixel block average differs by more than 0.25 (0–1 scale), the item is reported as WARN instead of FAIL. Numbers in `outputs/numbers_for_note.json` are compared by the report test within the coefficient tolerance instead of byte by byte.
- **Why:** on another operating system font rasterization moves text and the tight layout by a pixel or two, so 5–10% of pixels differ although the plotted data are identical; the strict rule made `python run.py check` fail on every machine except the one that produced the committed figures. A changed plot element (an altered block of the image, a moved series) still fails; the data behind each figure are compared exactly elsewhere.
- **What the original specification produced:** FAIL for all three figures on Linux with the same matplotlib version.

### D17. Exploratory stress tests added after the holdout was seen
- **What changed:** `src/robust_eval.py` (`python run.py robust`) adds forecast-comparison inference, proper scoring rules, rolling-origin evaluation, alternative specifications (policy-rule features, ridge penalty) and a raw-data anomaly screen.
- **Why:** the main verdict rests on an RMSE ratio of 18 decisions without a measure of its uncertainty, and the log score cannot score the benchmark.
- **What the original specification produced:** unchanged. The pre-specified model, its holdout, its verdict, and every number produced by `python run.py model` and `python run.py report`. All holdout results of the new module are labelled non-confirmatory; specification comparisons are based on the rolling-origin evaluation inside the estimation sample.

### D18. The replication tools work on a copy without git
- **What changed:** `scripts/scan_secrets.py` scans every file under the project folder when the folder is not a git checkout (for example a "Download ZIP" copy) and reports that there is no history to scan; `tests/test_docs.py` checks the git remote in `.git/config` only when that file exists.
- **Why:** both failed with an error on a copy downloaded as ZIP from GitHub.
- **What the original specification produced:** a crash of the secret scan and of one documentation test outside a git checkout; results are unchanged inside a checkout.


## Changes of 2026-11-09 (data update)

### D19. Rebuild check compares only decisions present in both panels
- **What changed:** `python run.py data` (`src.ingest.main`) compares the rebuilt panel with the reference panel on the decision dates both contain and lists added and removed decision dates separately; cells of the common decisions are still compared within 1e-8.
- **Why:** after the decision effective 2026-10-27 was appended, the strict row-for-row comparison stopped with an error before reporting anything, although the 90 earlier decisions were unchanged.
- **What the original specification produced:** a `ValueError` ("decision dates do not match row for row") whenever a decision is appended; the panel itself was written identically in both versions.

### D20. Decision date stays the effective date; announcement-month sensitivity added
- **What changed:** the effective date is now stated in `docs/model_spec.md` as the definition of the decision date, including for the new decision of 2026-10-27 (announced 2026-10-23); checked announcement dates are recorded in `docs/nbk_announcement_dates.csv`; `src/robust_eval.py` adds an exploratory, non-confirmatory check that aligns the factors of the decisions announced in the previous calendar month to the announcement month.
- **Why:** the review of 2026-11-06 found that for decisions announced in the previous month the decision-month-minus-two rule uses a factor month one month fresher than the committee had; keeping one convention for the whole series avoids mixing two date definitions, and the sensitivity check shows the size of the effect without changing the main model.
- **What the original specification produced:** the specification said "decision month" without defining which date; the data already used effective dates, so the main model, its split rule and its verdict rule are unchanged.

### D21. The next-decision forecast uses the latest decision's factors, not decision-month-minus-two data for the forecast date
- **What changed:** nothing in the code; the behaviour is now stated on the dashboard (limitations) and here. The forecast shown for the next NBK decision (2026-12-04) is the model's probability at the latest decision in the data (2026-10-27), whose factors are those of its own reference month (decision month minus two). The decision-month-minus-two rule applied to 2026-12-04 itself would need factor month 2026-10, which is not in `data/raw/`; no forecast row is built for a date outside the decision calendar.
- **Why:** building a forecast row for a future date would change the serving logic and need six new raw months; the owner decided on 2026-11-10 to keep the current behaviour.
- **What the original specification produced:** the same behaviour, not stated explicitly; the "next decision" probabilities therefore use data one decision older than the rule would use for the forecast date.

### D22. Trade rows for 2026-08 come from a newer edition of the publisher file
- **What changed:** `2026-08` was appended to `data/raw/export_history.csv` and `data/raw/import_history.csv` from the publisher files the owner put in `data/incoming/` (national total, column «тыс.долларов США», sheet «январь-август 2026г.»); the earlier rows were not changed (`docs/manual_steps_found.md`).
- **Why:** the decision of 2026-10-27 needs factor month 2026-08, which was missing; `data/raw/` may only be appended to, so earlier months were not replaced by the revised values of the new edition.
- **What the original specification produced:** the decision of 2026-10-27 could not be used (missing exports and imports); the new edition differs slightly from the existing CSV rows for 2026-01 to 2026-07 (revisions, listed in `docs/manual_steps_found.md`), so the series now mixes two editions at 2026-07/2026-08.

### D23. Anomaly flags count for the latest score over the whole 12-month growth window
- **What changed:** `anomalies_in_latest_inputs` in `src/robust_eval.py` treats a flagged monthly change of a growth factor (exports, imports, both lending series) as entering the latest score when it lies anywhere in the twelve months that make up the 12-month log growth at the reference month, or at the base month twelve months earlier; for level factors the rule is unchanged (reference month and the month before).
- **Why:** the 12-month log growth is the sum of the last twelve monthly log changes, so a level shift keeps moving the input for a year; with the new decision of 2026-10-27 (reference month 2026-08) the earlier rule dropped the export jump of 2026-06 although it still drives the export input, and the site would have removed its anomaly warning.
- **What the original specification produced:** the specification has no anomaly screen; the screen of D17 checked only the reference month, the month before it and the month twelve months earlier.

### D24. RB03 is reported as not comparable and left out of the robustness counts
- **What changed:** `src/report.py`, the dashboard and the generated documents count the checks in which the model beats Always Hold, the checks that survive and the checks whose benchmark conclusion differs from the main result over the comparable checks only; RB03 (binary logit, Increase vs not Increase) is labelled "not comparable" and is no longer eligible for the result-blind short table of D11, which now takes the first converged comparable check per kind. The "differs from the main result" count now uses the flag `same_benchmark_conclusion_as_primary` stored by `src/model.py` instead of comparing the winner label with the check label. RB03 is still estimated and shown in `outputs/robustness_table.md`.
- **Why:** the review of 2026-11-06 noted that a binary Increase-vs-not model cannot predict a decrease and its P(Increase) is compared with a −1/0/+1 score; the label comparison happened to work only while Always Hold was the main winner ("Always Hold" vs "Ordered Logit" and "Model beats Hold").
- **What the original specification produced:** the specification defines no robustness count; D9 and D11 counted RB03 like the other checks.

### D25. Generated verdict wording with inference, RPS as a supplementary measure, and data-update text
- **What changed:** the pre-specified verdict sentence is unchanged and still follows the RMSE-ratio rule. Every place that shows it (README, `outputs/oos_comparison.md`, the dashboard, the generated documents) now adds a generated sentence on whether the 95% block-bootstrap interval of the ratio contains 1 and the Diebold–Mariano p-value is at least 0.05 ("cannot be distinguished from Always Hold in either direction"), and a sentence with the RPS of the model, Always Hold and the class frequencies, stating that the verdict stays RMSE-based. Class frequencies count as doing "almost as well" when the model's RPS gain over them is smaller than a quarter of its gain over Always Hold (`FREQUENCY_CLOSE_SHARE` in `src/app.py`); this wording rule was set on 2026-11-10 after the holdout RPS values had been seen, so it is not confirmatory. The README heading of the main result, the first limitation and the overview box are generated from the winner and the inference, and the overview uses a neutral warning box in both cases. Generated sentences on the policy-inertia specifications (fixed-origin, recursive and rolling-origin RPS, and whether the ranking changes with the design) and on the meaning of the holdout after the data update were added.
- **Why:** the review asked for the verdict to state that the sample cannot separate the model from the benchmark, for RPS to be shown, for the policy-inertia results to be reported as exploratory and unstable, and for the data update to be interpreted. After the update the RMSE ratio fell below 1, so the earlier hand-written "negative result" headings became wrong; generating them prevents that.
- **What the original specification produced:** the verdict rule (holdout RMSE ratio below 1 means the model beats Always Hold) is the specification's and is unchanged; the specification has no inference for the ratio and no RPS.

### D26. The archived classifier backtests stay on their original data vintage
- **What changed:** `src/legacy_classifier.load_data` keeps only decisions up to 2026-09-07 (`LEGACY_DATA_END`), and the period-backtest test filters the data the same way; the archived results in `outputs/legacy/`, `outputs/backtest_results.json` and `outputs/sealed_test_predictions.csv` are unchanged.
- **Why:** these superseded classifier backtests (prior exploration, disclosed in `docs/model_spec.md`) measure their test windows back from the latest decision, so appending the decision of 2026-10-27 silently changed an archived result and made the legacy runner stop ("Existing sealed prediction artifact does not match the fixed 24-month test").
- **What the original specification produced:** the specification does not use these backtests; they are a historical record and are not part of the main model, its holdout or its verdict.

## Changes of 2026-11-12 (update-proofing)

### D27. Release-lag upper bound uses the month of the dated edition, and the look-ahead sentence is generated everywhere
- **What changed:** `src/facts.py` computes a series' upper bound from the last month of the edition its publication date belongs to when the form note says "Publication date refers to the edition ending YYYY-MM." (exports and imports: the edition ending 2026-07, published 2026-10-05); the 2026-08 rows come from a newer edition whose stat.gov.kz date and retrieval date are UNKNOWN and stated so. One generated sentence ("Look-ahead cannot be excluded for N of M decisions for …") now appears in provenance, the README, the indicator card, validity facts, the demo script, `outputs/release_lag_check.md` and the dashboard; `python run.py facts` also re-renders the README. `tests/test_facts.py` recomputes the expected bounds and counts from the form, the raw files and the panel instead of asserting "at every decision".
- **Why:** after the 2026-08 append the code paired the earlier edition's date (2026-10-05) with the new last month, giving a 35-day bound and "8 of 89" that no source supports; the test hard-coded the earlier result ("89 of 89"), so each data update broke it. The owner did not confirm the newer edition's dates (2026-11-12), so they are UNKNOWN.
- **What the original specification produced:** the specification defines no bound; the code computed it from the CSV's last month (66 days before the append, an invalid 35 days after it) and hand-typed notes; the estimation, the model and every model number are unaffected.

### D28. Data contract, append-only guard, jump screen in the data step, and generated counts in hand-written files
- **What changed:** `tests/test_data_contract.py` checks every raw file (columns `year_month` plus one numeric column, strictly increasing months without duplicates or gaps, units agreeing with `docs/facts_to_fill.csv`), the decision calendar (sorted, unique), that every decision whose reference months exist is usable and every other one is reported as dropped, that the holdout is ceil(20%) of the usable decisions, and that the processed panels equal a fresh rebuild; it also compares `data/raw/`, the decision calendar, `docs/nbk_announcement_dates.csv` and `docs/forecast_log.csv` with git HEAD row by row and fails if a committed row changed or disappeared (skipped without git). The modified-z jump screen moved from `src/robust_eval.py` to `src/data_screen.py` (method unchanged) and runs in `python run.py data`, writing `data/processed/data_anomalies.json` (read by the dashboard warning) and `outputs/data_anomalies.md`. Typed counts were replaced by generated text: the file audit in `data/raw/SOURCES.md`, the sample counts and announcement cases in `docs/model_spec.md` (generated blocks), the robustness note in `src/model.py` ("main 18-row holdout"), and the `src/robust_eval.py` docstring.
- **Why:** each data update broke tests and documents that held literal counts, dates or file coverage; the raw files were append-only by instruction only, with no automated guard; the screen ran only with the exploratory stress tests.
- **What the original specification produced:** the specification defines no data contract or screen; the estimation, the split rule, the verdict rule and every model number are unchanged (verified: identical parameters, RMSE ratio and latest score after re-running `python run.py model`).

### D29. Update tooling: `run.py needs`, `run.py compare`, runbook and CI on Linux and Windows
- **What changed:** `python run.py needs [dates]` prints the factor and base-rate months each decision needs and whether they are in `data/raw/`; `python run.py compare` (`src/compare.py`, also run by `python run.py report` and `python run.py check`) writes `outputs/version_comparison.md` and `model/version_comparison.json` from the artifact at git tag `before-data-update-2026-09-07` and the current files; `python run.py facts` also re-renders the README; `docs/RUNBOOK_data_update.md` lists the update steps; `.github/workflows/tests.yml` runs the tests (without the slow clean-install test) and the replication check on ubuntu-latest and windows-latest with Python 3.13.
- **Why:** the review and the data update showed that updates were done by hand without a checklist, and platform differences were found only by chance.
- **What the original specification produced:** no update procedure, comparison or CI; results are unchanged.

### D30. Verdict wording never claims a better model; effect of the data update and RPS shown next to RMSE
- **What changed:** a holdout RMSE ratio below 1 is now worded "meets the pre-specified criterion against Always Hold … This does not show that the model forecasts better." (`verdict_rule_sentence` in `src/app.py`, used by the report, README, generated documents and dashboard); robustness counts say "the RMSE ratio is below 1 in N of M comparable checks". A generated sentence (`version_change_sentence`, from `src/compare.py`) states the change of usable decisions, estimation and holdout windows, the RMSE ratio OLD → NEW and the label change, and whether both ratios lie in both bootstrap intervals. The dashboard's holdout table has an RPS column labelled supplementary. The verdict rule itself and the D25 inference sentence are unchanged.
- **Why:** after one decision was added the ratio crossed 1, and the earlier wording ("beats Always Hold") read as an improvement although the bootstrap interval and the Diebold–Mariano test cannot separate the model from the benchmark; the owner asked (2026-11-12) to keep the rule-based label but never to claim the model is better.
- **What the original specification produced:** the rule "ratio below 1 favors the model" with no wording requirement; the rule and every number are unchanged.

### D31. Forecast log and development plan (prospective protocol)
- **What changed:** `python run.py forecast-log` (`src/forecast_log.py`) appends the frozen model's next-decision forecast to `docs/forecast_log.csv` with UTC time, HEAD commit, working-tree state, artifact SHA-256 and data hash, refusing late, duplicate or already-decided targets; `python run.py forecast-score` scores logged forecasts once the decision is in the data and writes `data/processed/forecast_scores.json` (shown on the dashboard) and `outputs/forecast_scores.md`. `docs/development_plan.md` fixes, before the 2026-12-04 decision, that the main specification is frozen, how candidates may be explored (rolling origin inside the estimation sample only) and a proposed promotion rule (K = 8 prospective decisions) that awaits the owner's approval. The forecast for 2026-12-04 was logged on 2026-11-12.
- **Why:** there is no time-stamped pre-registration (D15); a forecast stored and pushed before each decision gives a genuinely out-of-sample record from now on.
- **What the original specification produced:** no prospective protocol; the model and its numbers are unchanged.

### D32. Cross-platform tolerance for robust standard errors and p-values; remote URL without ".git"
- **What changed:** `python run.py regression` (`src/regression.py`) and `python run.py check` (`outputs/numbers_for_note.json`, keys `se_*`, `p_raw_*`, `p_holm_*`, `cutpoint_*_se`, `cutpoint_*_p_raw`) accept a robust (HC0) standard error or p-value that differs from the committed value by more than the coefficient tolerance (1e-6 absolute) when the difference is at most 1e-4 both in absolute and in relative terms (the existing D14 cross-platform tolerance); `check` reports such items as WARN with both values, `regression` as PASS. Estimates (coefficients and cutpoints), the log-likelihood, the RMSE ratio, the latest score and every verdict keep the strict 1e-6 tolerance. Two exact float comparisons in tests (`data/processed/data_anomalies.json` and `data/processed/forecast_scores.json` against a fresh computation) now compare floats within 1e-9 relative (`tests/_tolerance.py`) and everything else exactly. `tests/test_docs.py` accepts the git remote with or without the ".git" suffix, because actions/checkout records `https://github.com/<owner>/<repo>` without it (a real cause, not a tolerance). No estimated number was changed.
- **Why:** the GitHub CI run (Linux and Windows, Python 3.13) reported 24 PASS, 2 FAIL in `python run.py regression` and 4 failing tests. Re-estimating locally from the CSV copy of the panel, which changes the inputs only in the last binary digit, moves the estimates by about 3e-9 but the cutpoint robust SEs by about 2.3e-6 (relative 3e-6) and a cutpoint p-value by 1.3e-6, because they depend on where BFGS stops; another platform or library version produces the same effect, so the absolute 1e-6 rule failed on every machine except the one that produced the artifact. A relative 1e-9 rule would have been stricter than the measured noise of the estimates themselves, so the existing 1e-4 rule for second-order quantities was used instead.
- **What the original specification produced:** the specification defines no replication tolerance; before this change, robust SEs and p-values were compared at 1e-6 absolute, and the two JSON files and the remote URL were compared exactly.

### D33. Newton fallback for robustness fits that BFGS does not converge, and an RB02-only WARN rule
- **What changed:** in the robustness checks only, `_fit_ordered` in `src/model.py` continues a fit with Newton's method (analytic Hessian, at most 200 iterations) from the BFGS end point when BFGS reports non-convergence; when BFGS converges, nothing changes. `src/check.py` reports every `robustness_RB02_*` entry of `outputs/numbers_for_note.json` as WARN ("RB02 did not converge on this platform") when the rebuilt RB02 did not converge; every other entry, including the robustness counts, the main model and the verdicts, stays strict, and RB02 entries stay strict when RB02 converged. The main model, its fitting path, `model/artifact.json` and `outputs/` were not changed.
- **Why:** on GitHub CI (Linux, Python 3.13) BFGS stopped before convergence for RB02 (last 60 calendar months, 32 estimation decisions), so its numbers came from the stopping point; D14 already turned the RB02 lines of the markdown outputs into WARN, but `robustness_RB02_rmse_ratio` in `numbers_for_note.json` was compared at 1e-6 and failed, and `src.check` exited with code 1. RB02's likelihood is flat (L-BFGS reaches the same log-likelihood within 5.5e-9 at parameters 3e-4 away); Newton from a BFGS run stopped after 8 iterations reaches the committed RB02 estimates within 4.4e-10 and the robust SEs within 1.0e-7, and a simulated early-stopping platform now gives "converged: 9" and no FAIL in `python run.py check`.
- **What the original specification produced:** the specification defines no robustness optimizer; before this change a non-converged RB02 kept its stopping-point estimates, was marked NONCONVERGED, and its RMSE ratio failed the replication check on such platforms.
