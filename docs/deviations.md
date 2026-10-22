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
