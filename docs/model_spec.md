# Draft model specification: NBK base-rate decisions

> **DRAFT - owner must review and edit**  
> This document specifies a proposed model; it reports no new estimation. It was written after earlier exploratory backtests and is not a pre-registration made before all analysis.

## Indicator and outcome

The indicator is the NBK base-rate decision at each scheduled meeting. Encode the ordered outcome as `y = -1` for Decrease, `y = 0` for Hold, and `y = +1` for Increase. The model is intended to estimate the ordered decision class and its class probabilities, not the size of a rate change.

## Proposed mechanisms and expected signs

The signs below are directional hypotheses for the association with a more hawkish (higher-scored) decision, conditional on the other included factors. They are not established causal effects. **DRAFT - owner must review and edit.**

| Factor | Expected sign | Proposed channel |
|---|---:|---|
| `inflation` | + | Higher year-on-year inflation can increase the need to tighten policy to contain price pressure and keep inflation expectations anchored. |
| `exports` | + | Faster export growth can support income and aggregate demand; stronger demand may add to domestic price pressure and the case for tighter policy. |
| `imports` | + | Faster import growth can signal stronger domestic absorption and demand. This sign is especially uncertain because import growth can also reflect supply, investment, or exchange-rate movements. |
| `corporate_lending` | + | Faster business-credit growth can ease financing constraints and support investment and demand, potentially increasing inflationary pressure. |
| `household_lending` | + | Faster household-credit growth can support household spending and demand, potentially increasing inflationary pressure. |
| `consumption` | + | Faster year-on-year consumption growth can indicate stronger household demand, which may add to price pressure and the case for tighter policy. |

The NBK's reaction function, the factor definitions, and the signs require owner review and supporting institutional context. The signs are falsifiable hypotheses, not restrictions imposed on estimated coefficients.

## Factor transformations and timing

Use the following proposed model-stage transformations. These are not transformations to apply while rebuilding the raw-level decision-date panel.

- **Inflation:** retain the observed value as a level, treating it as a year-on-year rate for this specification. Its exact source definition and units remain unverified, so the owner must confirm that interpretation.
- **Consumption:** retain the observed year-on-year rate as a level for the same reason. Its exact definition and units remain subject to source verification.
- **Exports, imports, corporate lending, household lending:** use 12-month log growth, defined as `log_growth_12m(x) = 100 * (log_level(x_t) - log_level(x_{t-12}))`. This removes the scale trend in the corresponding levels and is intended to produce a more stationary growth measure. The premise that the levels are non-stationary and the transformed series are I(0) is a working rationale to be checked, not a result established by this specification. `log_level` is the natural logarithm of a positive level; nonpositive inputs make this transformation undefined and must be handled explicitly rather than replaced with invented values. `first_difference` is a named alternative transformation, not an additional transform to apply on top of this 12-month growth measure.

**Release timing assumption:** align each factor to the calendar month two months before the decision month (decision month minus 2). This is an assumption, not a verified publication lag. Replace it with series-specific real publication/availability lags when verified; those lags are currently `UNKNOWN`. A month offset alone does not establish that each value was public on the decision date.

## Estimator and statistical rationale

The proposed estimator is an ordered logit with ordered cut-points and robust heteroskedasticity-consistent (HC) standard errors. Ordered logit matches the three outcome classes because Decrease < Hold < Increase is meaningful, while the numeric gaps between the classes are not assumed to represent equal rate-change magnitudes. The estimator models cumulative probabilities over that ordering rather than treating the class labels as unrelated categories.

Cointegration testing is not proposed for a specification whose regressors are transformed to I(0): conventional cointegration analysis addresses a long-run equilibrium relationship among non-stationary I(1) series, and the outcome here is an ordinal decision score rather than a continuous economic level. This is an argued modeling choice, not a universal claim that cointegration can never be relevant. It would be challenged if stationarity tests on the transformed regressors indicate persistent unit roots (for example, ADF and KPSS tests giving evidence against I(0)); then the transformations and model need review. If a revised theory instead retains I(1) levels and proposes a long-run equilibrium relation, an appropriate cointegration analysis would need to be specified for that design. No such test or estimation is performed here.

## Falsification and failure criteria

Treat the proposed predictive model as unsupported or falsified for its stated purpose if any of these checks specified here occurs:

1. A joint likelihood-ratio test of all six slope coefficients is not rejected at the 10% level.
2. Any factor has an estimated sign opposite to its expected sign above and is statistically significant at the 5% level. This is a factor-level diagnostic; interpretation should account for the six simultaneous sign checks.
3. On the specified chronological holdout, the model's expected-score RMSE divided by Always Hold's expected-score RMSE is greater than or equal to 1. This holdout is not fresh or untouched because prior exploration already evaluated a larger, overlapping recent-period test.

These criteria do not guarantee that passing the tests proves a correct or causal model. Report all results, including failures; do not tune the model against the final holdout.

## Benchmark

The benchmark is **Always Hold**, which predicts score 0 for every meeting. Hold was selected because it is the modal class in the project decision history. Compare the model and benchmark on identical chronological holdout observations.

## Evaluation plan

Use the last 20% of observations in chronological order as the evaluation holdout: the current panel has 90 decisions, of which 88 have all six transformed factors (two early decisions lack 12-month growth at their reference month), so the holdout size is ceil(20% × 88) = ceil(17.6) = **18 observations** (corrected after estimation; see `docs/deviations.md`, D1). Because prior exploration already evaluated the larger recent 24-month test, these 18 observations overlap previously analyzed data and are not an untouched, prospective holdout. Use only earlier observations for model fitting and any model development. Do not use the holdout for feature selection, threshold choice, hyperparameter selection, or other tuning. The proposed transformations and estimator must be fit using training data only where a fit step is required.

For ordered-logit probabilities, define the expected score per observation as `E[y] = -1 * P(Decrease) + 0 * P(Hold) + 1 * P(Increase)`. Report:

- RMSE and MAE of expected score versus observed score for the model and the score-0 Always Hold benchmark, on the same holdout rows;
- the RMSE ratio `RMSE_model / RMSE_Always_Hold` (values below 1 favor the model; values at or above 1 fail the predictive criterion above);
- multiclass log score (negative mean log probability assigned to the observed class), with class-probability order stated. For the deterministic Always Hold benchmark, this score is infinite if the holdout contains any Increase or Decrease observation; report that behavior explicitly rather than smoothing it silently.

These are planned calculations only. No holdout metrics are calculated or reported by this specification.

## Prior exploration (disclosed)

Before this specification was written, the project backtested Logistic Regression and Random Forest classifiers using the six factors in level form, with a chronological final test. The legacy result file records a 24-month test of 16 observations, trained on 74 earlier observations; both model pipelines used a median imputer, Logistic Regression also used a standard scaler, and the models were compared with the Always Hold benchmark on the same test rows. The recorded accuracies were **0.188** for Logistic Regression, **0.188** for Random Forest, and **0.625** for Always Hold. In that 24-month test, both classifiers predicted Decrease for all 16 observations. These are prior exploratory results from `outputs/legacy/mvp_backtest_results.json`; the legacy artifact index is `outputs/legacy/INDEX.md`.

This specification is **NOT a time-stamped pre-registration made before all analysis**: no Week-4 pre-registration was submitted, and the instructor allowed it to be accepted with the date of its commit to the repository, 16 October 2026 (commit f763e16; see `docs/deviations.md`, D15). The previous tests and observed outcomes can influence the proposed factors, transformations, estimator, thresholds, and evaluation plan. Treat this document as a draft for owner review, not as evidence of prospective validation.

## Mechanisms and expected signs

Expected signs are the draft hypotheses above; estimated signs are the signs of the slopes in `model/artifact.json` (`model.parameters`), with significance in `outputs/results_table.md`. The mechanism column is for the student to write in their own words; it is intentionally blank.

| Factor | Expected sign | Estimated sign | Same as expected | MECHANISM_IN_STUDENT_WORDS |
|---|---|---|---|---|
| `inflation` | + | + | yes, not significant | When prices rise faster, NBK is more likely to raise or hold the rate to keep inflation expectations under control. The estimated sign matches (+), but it is not significant (raw p = 0.754). |
| `exports` | + | + | yes, not significant | Faster export growth brings more income into the economy, which raises demand and price pressure, so tightening becomes more likely. The estimated sign matches (+), but it is not significant (raw p = 0.189). |
| `imports` | + | − | no, not significant | Faster import growth usually means strong domestic demand, so we expected tightening. The estimated sign is negative, but the coefficient is statistically indistinguishable from zero (raw p = 0.666), so we do not interpret the sign. |
| `corporate_lending` | + | − | no, not significant | Faster business lending supports investment and demand, which can add to inflation, so we expected tightening. The estimated sign is negative, but it is indistinguishable from zero (raw p = 0.392), so we do not interpret the sign. |
| `household_lending` | + | + | yes, significant (Holm p = 0.031) | Faster household lending supports spending and demand, so we expected tightening. This is the only factor with a significant effect and the expected sign (raw p = 0.005, Holm p = 0.031). No small-sample correction beyond Holm was run. |
| `consumption` | + | − | no, not significant | Faster consumption growth means stronger household demand and price pressure, so we expected tightening. The estimated sign is negative, but the coefficient is essentially zero (raw p = 0.944), so we do not interpret the sign. |

## Cointegration: why no test was run

No cointegration test was run, and none is reported in the annexes. The reasons, and the evidence that weakens them:

- The dependent variable is an ordinal decision class (Decrease, Hold, Increase), not a continuous level. Cointegration tests such as Engle–Granger or Johansen look for a stationary linear combination of continuous non-stationary series, and they are not defined in the usual way for an ordinal outcome in an ordered logit.
- The specification transforms the factors so that they enter as growth rates or year-on-year changes (12-month log growth for exports, imports and both lending series; inflation and consumption are already year-on-year rates). The design assumption was that these inputs are I(0), which removes the long-run levels relationship that cointegration would describe.
- The unit-root tests do not fully support that assumption: household lending fails both ADF and KPSS, and the ADF test does not reject a unit root for inflation and corporate lending (`outputs/annex_unit_roots.csv`, `docs/validity_facts.md`). Their coefficients may therefore be affected by persistence that the design did not remove.
- The robustness check RB09 first-differences the non-stationary factors and re-estimates the model; its result is in `outputs/robustness_table_short.md`. It addresses non-stationarity directly but is not a cointegration test.
- The main model is unchanged by this section.