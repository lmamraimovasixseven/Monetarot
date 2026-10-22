# Prediction-collapse diagnostic: NBK base-rate MVP

Generated 2026-10-15 from the existing processed panel. Source SHA-256 (CRLF normalized to LF): `8bf4a1ae7f36eb61c021a7cf8a568f94a9e89271393e15d6c8a02b550cf75b59`. This report is diagnostic; no production model, features, parameters, target, dataset or holdout boundary is changed.

## Executive findings

- **No target-label, leakage, probability-column-order or missing-scaler defect was found.** The allowed predictors are the six listed below; `base_rate_before`, `base_rate_after`, and `decision` are not predictors. Both current classifiers are sklearn Pipelines with median imputation and `StandardScaler`; each step is fit inside the chronological training fold. The app maps `predict_proba` columns through `model.classes_`.
- **Class imbalance alone does not explain the collapse.** Pre-holdout training has Increase 14/74 (18.9%), Hold 39/74 (52.7%), Decrease 21/74 (28.4%): Decrease is not the majority. Balanced weights upweight Increase and Decrease relative to Hold.
- **Credit-level extrapolation is directly observed.** Corporate and household lending each exceed the full pre-test training range in all 16 final-test rows. This is associated with the collapse, but does not establish causality. On the current LR fit, mean standardized test values are +4.27 SD corporate lending and +3.59 SD household lending; mean Decrease logit contributions from those columns are +3.95 and +0.98. That identifies the fitted extrapolation pattern, not an economic causal effect.
- **Predicted dominant class changes with the test window.** Current LR and RF predict all Decrease on the 24-month tail, all Hold (RF) on 36 months, and all Increase on 48 months. This is unstable behavior, not a consistent Decrease rule.
- **A few pre-test variants score higher on 18 expanding-window validation outcomes, but the evidence is too small for replacement.** RF leaf=1 balanced and RF leaf=3 unweighted both score 0.556 accuracy / 0.649 balanced accuracy / 0.570 macro F1, versus Hold 0.444 / 0.333 / 0.205. Their observed folds contain only 18 outcomes and are not an untouched prospective test.

## Audit of implementation and target

| Check | Finding |
|---|---|
| Predictors | Exactly six: `inflation`, `exports`, `imports`, `corporate_lending`, `household_lending`, `consumption`. No target or before/after rate columns |
| Label formation | 90/90 decision labels agree with the sign/equality of `base_rate_after - base_rate_before` |
| Probability mapping | `classes_` is alphabetical (`Decrease`, `Hold`, `Increase`); helper remaps by class name |
| Scaling / missing values | Median imputation -> `StandardScaler` -> estimator within sklearn Pipeline; fitting uses training rows only |
| Time ordering | Fixed expanding folds and tail windows; no random shuffling |
| Availability / units | Exact publication dates and units cannot be verified from the current panel; raw monthly source files are absent and documentation says release timing is approximate |

### Class mix by calendar regime

| Period | n | Increase | Hold | Decrease |
|---|---:|---:|---:|---:|
| 2015-2019 | 33 | 4 | 17 | 12 |
| 2020-2022 | 27 | 10 | 15 | 2 |
| 2023-2024 pre-test | 14 | 0 | 7 | 7 |
| Final 24-month holdout | 16 | 3 | 10 | 3 |

Class shares shift over time: 2020-2022 has 10 increases and 2 decreases; pre-test 2023-September 2024 has zero increases and 7 each Hold/Decrease; the last 24 months have 10 Hold out of 16. This is descriptive evidence of a changing target mix, not proof of cause.

## Expanding-window experiment

Used the existing pre-test scheme: initial train n=56, then n=62 and n=68; six later rows validate each fold. All rows precede the 2024-09-07 final-test cutoff. The total is 18 forecasts. Individual validation folds omit one class.

| Fold | Train n / through | Validation dates (6 rows) | Train I/H/D | Validation I/H/D |
|---:|---|---|---:|---:|
| 1 | 56 / 2022-06-07 | 2022-07-26 to 2023-02-27 | 11/31/14 | 3/3/0 |
| 2 | 62 / 2023-02-27 | 2023-04-10 to 2023-11-27 | 14/34/14 | 0/3/3 |
| 3 | 68 / 2023-11-27 | 2024-01-22 to 2024-09-02 | 14/37/17 | 0/2/4 |

Variants below use the same 18 validation dates. They are fixed diagnostic contrasts, not an exhaustive search. No parameter or candidate was selected using the final 24 months.

### Overall temporal-validation scores

| Variant | Accuracy | Balanced acc. | Macro F1 | Predicted I/H/D | Fold accuracies |
|---|---:|---:|---:|---:|---|
| Always Hold | 0.444 | 0.333 | 0.205 | 0/18/0 | 0.500, 0.500, 0.333 |
| LR current (C=1, balanced, scaled) | 0.389 | 0.524 | 0.338 | 12/0/6 | 0.500, 0.000, 0.667 |
| LR explicit equivalent StandardScaler | 0.389 | 0.524 | 0.338 | 12/0/6 | 0.500, 0.000, 0.667 |
| LR no scaler (diagnostic) | 0.389 | 0.524 | 0.338 | 12/0/6 | 0.500, 0.000, 0.667 |
| LR C=0.1, balanced | 0.389 | 0.524 | 0.338 | 12/0/6 | 0.500, 0.000, 0.667 |
| LR C=10, balanced | 0.389 | 0.524 | 0.338 | 12/0/6 | 0.500, 0.000, 0.667 |
| LR C=1, unweighted | 0.444 | 0.565 | 0.422 | 11/1/6 | 0.500, 0.167, 0.667 |
| RF current (leaf=3, balanced) | 0.389 | 0.524 | 0.338 | 12/0/6 | 0.500, 0.000, 0.667 |
| RF leaf=1, balanced | 0.556 | 0.649 | 0.570 | 6/6/6 | 0.500, 0.500, 0.667 |
| RF leaf=5, balanced | 0.389 | 0.524 | 0.338 | 12/0/6 | 0.500, 0.000, 0.667 |
| RF leaf=3, unweighted | 0.556 | 0.649 | 0.570 | 6/6/6 | 0.500, 0.500, 0.667 |

### Per-class scores (validation)

Precision / recall / F1 are shown separately. Supports across the 18 validation dates: Increase 3, Hold 8, Decrease 7.

| Variant | Class | Precision | Recall | F1 | Actual n | Predicted n |
|---|---|---:|---:|---:|---:|---:|
| Always Hold | Increase | 0.000 | 0.000 | 0.000 | 3 | 0 |
| Always Hold | Hold | 0.444 | 1.000 | 0.615 | 8 | 18 |
| Always Hold | Decrease | 0.000 | 0.000 | 0.000 | 7 | 0 |
| LR current (C=1, balanced, scaled) | Increase | 0.250 | 1.000 | 0.400 | 3 | 12 |
| LR current (C=1, balanced, scaled) | Hold | 0.000 | 0.000 | 0.000 | 8 | 0 |
| LR current (C=1, balanced, scaled) | Decrease | 0.667 | 0.571 | 0.615 | 7 | 6 |
| LR explicit equivalent StandardScaler | Increase | 0.250 | 1.000 | 0.400 | 3 | 12 |
| LR explicit equivalent StandardScaler | Hold | 0.000 | 0.000 | 0.000 | 8 | 0 |
| LR explicit equivalent StandardScaler | Decrease | 0.667 | 0.571 | 0.615 | 7 | 6 |
| LR no scaler (diagnostic) | Increase | 0.250 | 1.000 | 0.400 | 3 | 12 |
| LR no scaler (diagnostic) | Hold | 0.000 | 0.000 | 0.000 | 8 | 0 |
| LR no scaler (diagnostic) | Decrease | 0.667 | 0.571 | 0.615 | 7 | 6 |
| LR C=0.1, balanced | Increase | 0.250 | 1.000 | 0.400 | 3 | 12 |
| LR C=0.1, balanced | Hold | 0.000 | 0.000 | 0.000 | 8 | 0 |
| LR C=0.1, balanced | Decrease | 0.667 | 0.571 | 0.615 | 7 | 6 |
| LR C=10, balanced | Increase | 0.250 | 1.000 | 0.400 | 3 | 12 |
| LR C=10, balanced | Hold | 0.000 | 0.000 | 0.000 | 8 | 0 |
| LR C=10, balanced | Decrease | 0.667 | 0.571 | 0.615 | 7 | 6 |
| LR C=1, unweighted | Increase | 0.273 | 1.000 | 0.429 | 3 | 11 |
| LR C=1, unweighted | Hold | 1.000 | 0.125 | 0.222 | 8 | 1 |
| LR C=1, unweighted | Decrease | 0.667 | 0.571 | 0.615 | 7 | 6 |
| RF current (leaf=3, balanced) | Increase | 0.250 | 1.000 | 0.400 | 3 | 12 |
| RF current (leaf=3, balanced) | Hold | 0.000 | 0.000 | 0.000 | 8 | 0 |
| RF current (leaf=3, balanced) | Decrease | 0.667 | 0.571 | 0.615 | 7 | 6 |
| RF leaf=1, balanced | Increase | 0.500 | 1.000 | 0.667 | 3 | 6 |
| RF leaf=1, balanced | Hold | 0.500 | 0.375 | 0.429 | 8 | 6 |
| RF leaf=1, balanced | Decrease | 0.667 | 0.571 | 0.615 | 7 | 6 |
| RF leaf=5, balanced | Increase | 0.250 | 1.000 | 0.400 | 3 | 12 |
| RF leaf=5, balanced | Hold | 0.000 | 0.000 | 0.000 | 8 | 0 |
| RF leaf=5, balanced | Decrease | 0.667 | 0.571 | 0.615 | 7 | 6 |
| RF leaf=3, unweighted | Increase | 0.500 | 1.000 | 0.667 | 3 | 6 |
| RF leaf=3, unweighted | Hold | 0.500 | 0.375 | 0.429 | 8 | 6 |
| RF leaf=3, unweighted | Decrease | 0.667 | 0.571 | 0.615 | 7 | 6 |

### Validation confusion matrices

Rows are actual Increase/Hold/Decrease; columns are predicted Increase/Hold/Decrease.

| Variant | Matrix |
|---|---|
| Always Hold | I[0,3,0] H[0,8,0] D[0,7,0] |
| LR current (C=1, balanced, scaled) | I[3,0,0] H[6,0,2] D[3,0,4] |
| LR explicit equivalent StandardScaler | I[3,0,0] H[6,0,2] D[3,0,4] |
| LR no scaler (diagnostic) | I[3,0,0] H[6,0,2] D[3,0,4] |
| LR C=0.1, balanced | I[3,0,0] H[6,0,2] D[3,0,4] |
| LR C=10, balanced | I[3,0,0] H[6,0,2] D[3,0,4] |
| LR C=1, unweighted | I[3,0,0] H[5,1,2] D[3,0,4] |
| RF current (leaf=3, balanced) | I[3,0,0] H[6,0,2] D[3,0,4] |
| RF leaf=1, balanced | I[3,0,0] H[3,3,2] D[0,3,4] |
| RF leaf=5, balanced | I[3,0,0] H[6,0,2] D[3,0,4] |
| RF leaf=3, unweighted | I[3,0,0] H[3,3,2] D[0,3,4] |

### Validation probability diagnostics

Brier is mean row-wise sum of squared multiclass errors (range 0-2; lower is better). Log loss below indexes each true class after explicit `CLASS_ORDER` remapping. Small-sample scores are descriptive; no calibration curve or calibrator was fit.

| Variant | Brier | Log loss | Mean p(I/H/D) | Median max probability |
|---|---:|---:|---:|---:|
| LR current (C=1, balanced, scaled) | 0.947 | 2.236 | 56.7%/13.8%/29.4% | 86.1% |
| LR explicit equivalent StandardScaler | 0.947 | 2.236 | 56.7%/13.8%/29.4% | 86.1% |
| LR no scaler (diagnostic) | 0.917 | 2.336 | 56.2%/22.3%/21.6% | 73.5% |
| LR C=0.1, balanced | 0.894 | 1.561 | 60.5%/19.9%/19.6% | 72.6% |
| LR C=10, balanced | 0.959 | 2.782 | 56.0%/12.5%/31.6% | 87.6% |
| LR C=1, unweighted | 0.777 | 1.900 | 45.2%/28.6%/26.2% | 69.0% |
| RF current (leaf=3, balanced) | 0.692 | 1.181 | 45.6%/30.6%/23.8% | 58.7% |
| RF leaf=1, balanced | 0.638 | 1.182 | 34.5%/38.3%/27.2% | 53.9% |
| RF leaf=5, balanced | 0.753 | 1.221 | 52.1%/28.2%/19.7% | 61.0% |
| RF leaf=3, unweighted | 0.608 | 1.072 | 32.9%/46.4%/20.7% | 50.7% |

Current LR has 86.1% median maximum probability across the 18 validation cases, with log loss 2.236; this does not support treating its high confidence as reliability. The class-weight change from balanced to unweighted changes predictions on these fixed folds: LR Hold predictions 0 to 1, RF Hold predictions 0 to 6. The unweighted RF improves this small validation aggregate, but still requires independent prospective evidence.

## Sealed test and 24/36/48-month windows

The unchanged primary split has 74 train rows through 2024-09-02 (cutoff 2024-09-07) and 16 test rows from 2024-10-14 through 2026-09-07. The 36- and 48-month tails include the final 24-month period and are sensitivity summaries, not independent tests and not used for candidate selection.

| Window | Train n, classes I/H/D | Test n, actual I/H/D | Model | Acc. | Balanced acc. | Macro F1 | Predicted I/H/D |
|---:|---|---|---|---:|---:|---:|---:|
| 24m | 74, 14/39/21 | 16, 3/10/3 | Hold benchmark | 0.625 | 0.333 | 0.256 | 0/16/0 |
| 24m | 74, 14/39/21 | 16, 3/10/3 | Logistic Regression | 0.188 | 0.333 | 0.105 | 0/0/16 |
| 24m | 74, 14/39/21 | 16, 3/10/3 | Random Forest | 0.188 | 0.333 | 0.105 | 0/0/16 |
| 36m | 66, 14/37/15 | 24, 3/12/9 | Hold benchmark | 0.500 | 0.333 | 0.222 | 0/24/0 |
| 36m | 66, 14/37/15 | 24, 3/12/9 | Logistic Regression | 0.250 | 0.222 | 0.133 | 2/1/21 |
| 36m | 66, 14/37/15 | 24, 3/12/9 | Random Forest | 0.500 | 0.333 | 0.222 | 0/24/0 |
| 48m | 58, 12/32/14 | 32, 5/17/10 | Hold benchmark | 0.531 | 0.333 | 0.231 | 0/32/0 |
| 48m | 58, 12/32/14 | 32, 5/17/10 | Logistic Regression | 0.156 | 0.333 | 0.090 | 32/0/0 |
| 48m | 58, 12/32/14 | 32, 5/17/10 | Random Forest | 0.156 | 0.333 | 0.090 | 32/0/0 |

Primary 24m class metrics and confusion:

| Model | Matrix actual rows/predicted cols I/H/D | Increase P/R/F1 | Hold P/R/F1 | Decrease P/R/F1 |
|---|---|---:|---:|---:|
| Hold benchmark | I[0,3,0] H[0,10,0] D[0,3,0] | 0.000/0.000/0.000 | 0.625/1.000/0.769 | 0.000/0.000/0.000 |
| Logistic Regression | I[0,0,3] H[0,0,10] D[0,0,3] | 0.000/0.000/0.000 | 0.000/0.000/0.000 | 0.188/1.000/0.316 |
| Random Forest | I[0,0,3] H[0,0,10] D[0,0,3] | 0.000/0.000/0.000 | 0.000/0.000/0.000 | 0.188/1.000/0.316 |

Both classifiers have zero precision/recall/F1 for Increase and Hold on this test. For Decrease, precision is 0.188, recall 1.000 and F1 0.316. Hold benchmark has Hold precision 0.625, recall 1.000 and F1 0.769. The classifier's accuracy is 0.188 versus 0.625 for Hold.

### Probability quality on out-of-sample windows

| Window | Model | Brier | Log loss | Max probability min / median / max |
|---:|---|---:|---:|---:|
| 24m | Logistic Regression | 1.514 | 3.557 | 0.857 / 0.982 / 0.997 |
| 24m | Random Forest | 0.978 | 1.563 | 0.594 / 0.731 / 0.774 |
| 36m | Logistic Regression | 0.989 | 1.622 | 0.381 / 0.715 / 0.968 |
| 36m | Random Forest | 0.634 | 1.064 | 0.416 / 0.495 / 0.560 |
| 48m | Logistic Regression | 1.559 | 4.752 | 0.860 / 0.957 / 0.994 |
| 48m | Random Forest | 0.902 | 1.453 | 0.581 / 0.606 / 0.677 |

On the 16-row final test, LR maximum-probability median is 98.2% (range 85.7 to 99.7%), despite 18.8% accuracy; its Brier is 1.514 and log loss 3.557. RF maximum-probability median is 73.1% (59.4 to 77.4%), with 18.8% accuracy, Brier 0.978 and log loss 1.563. Always Hold's deterministic multiclass Brier on this actual class mix is 0.750; both classifiers are worse. These scores warn against reading high LR outputs as calibrated frequencies; n=16 is too small to establish calibration.

## Feature shift and break candidates

| Factor | Train range | Final test range | Outside train range |
|---|---:|---:|---:|
| inflation | 3.800 to 21.300 | 8.400 to 12.600 | 0/16 |
| exports | 2,642,269.730 to 7,718,603.470 | 5,121,405.040 to 10,169,912.740 | 1/16 |
| imports | 1,594,493.320 to 5,554,024.030 | 4,369,125.700 to 5,953,514.050 | 3/16 |
| corporate_lending | 6,964,726.106 to 9,795,119.292 | 9,937,739.584 to 12,646,863.745 | 16/16 |
| household_lending | 3,955,672.532 to 20,724,153.485 | 21,201,062.270 to 29,483,123.732 | 16/16 |
| consumption | -44.700 to 41.700 | 2.100 to 19.300 | 0/16 |

Both lending variables are beyond the complete training range for every held-out row; exports exceed it for 1/16, imports for 3/16, inflation/consumption for 0/16. In LR, the training-fitted scaler does not clip values. RF current feature importances are corporate lending 21.8%, household lending 24.6% (descriptive only).

Existing processed-panel exploratory scans flagged corporate-lending level mean break 2024-02-26 and household-lending mean break 2023-07-10 (moving-block bootstrap p=0.005). Raw monthly credit files are absent and these scan p-values are not adjusted over all features/forms. Interpret as candidate breaks, not confirmed economic mechanisms.

### Existing transformed-feature sensitivity (not used to choose)

| Window | Transform | Model | Accuracy | Macro F1 | Predicted I/H/D |
|---:|---|---|---:|---:|---:|
| 24m | Current six levels | Hold benchmark | 0.625 | 0.256 | 0/16/0 |
| 24m | Current six levels | Logistic Regression | 0.188 | 0.105 | 0/0/16 |
| 24m | Current six levels | Random Forest | 0.188 | 0.105 | 0/0/16 |
| 24m | Log lending levels (diagnostic) | Hold benchmark | 0.625 | 0.256 | 0/16/0 |
| 24m | Log lending levels (diagnostic) | Logistic Regression | 0.188 | 0.105 | 0/0/16 |
| 24m | Log lending levels (diagnostic) | Random Forest | 0.188 | 0.105 | 0/0/16 |
| 24m | Decision-interval lending growth (diagnostic) | Hold benchmark | 0.625 | 0.256 | 0/16/0 |
| 24m | Decision-interval lending growth (diagnostic) | Logistic Regression | 0.125 | 0.083 | 2/1/13 |
| 24m | Decision-interval lending growth (diagnostic) | Random Forest | 0.312 | 0.319 | 2/1/13 |
| 36m | Current six levels | Hold benchmark | 0.500 | 0.222 | 0/24/0 |
| 36m | Current six levels | Logistic Regression | 0.250 | 0.133 | 2/1/21 |
| 36m | Current six levels | Random Forest | 0.500 | 0.222 | 0/24/0 |
| 36m | Log lending levels (diagnostic) | Hold benchmark | 0.500 | 0.222 | 0/24/0 |
| 36m | Log lending levels (diagnostic) | Logistic Regression | 0.250 | 0.243 | 8/2/14 |
| 36m | Log lending levels (diagnostic) | Random Forest | 0.500 | 0.222 | 0/24/0 |
| 36m | Decision-interval lending growth (diagnostic) | Hold benchmark | 0.500 | 0.222 | 0/24/0 |
| 36m | Decision-interval lending growth (diagnostic) | Logistic Regression | 0.208 | 0.178 | 19/5/0 |
| 36m | Decision-interval lending growth (diagnostic) | Random Forest | 0.208 | 0.178 | 19/5/0 |
| 48m | Current six levels | Hold benchmark | 0.531 | 0.231 | 0/32/0 |
| 48m | Current six levels | Logistic Regression | 0.156 | 0.090 | 32/0/0 |
| 48m | Current six levels | Random Forest | 0.156 | 0.090 | 32/0/0 |
| 48m | Log lending levels (diagnostic) | Hold benchmark | 0.531 | 0.231 | 0/32/0 |
| 48m | Log lending levels (diagnostic) | Logistic Regression | 0.156 | 0.090 | 32/0/0 |
| 48m | Log lending levels (diagnostic) | Random Forest | 0.156 | 0.090 | 32/0/0 |
| 48m | Decision-interval lending growth (diagnostic) | Hold benchmark | 0.531 | 0.231 | 0/32/0 |
| 48m | Decision-interval lending growth (diagnostic) | Logistic Regression | 0.156 | 0.090 | 32/0/0 |
| 48m | Decision-interval lending growth (diagnostic) | Random Forest | 0.156 | 0.090 | 32/0/0 |

Log lending levels leave the 24m predictions and metrics unchanged. Decision-interval lending growth gives 24m LR accuracy 0.125 and RF 0.313, both below Hold at 0.625. Across 36/48m tails, no transform is a consistent improvement.

## Conclusion and recommendation

### Supported findings and open hypotheses

- **Confirmed checks:** target labels are consistent; predictors contain no target information; training is chronological; LR has the intended train-fitted scaler; class-probability order is correct. A simple pipeline/encoding bug was not found.
- **Observed conditions that co-occur with collapse:** complete out-of-range drift in both credit level features, a changing historical class mix, and severe LR overconfidence relative to its 16-row outcomes. RF is also all-Decrease at 24m but has lower confidence than LR. These are evidence for extrapolation/regime-shift concerns, not proof of causation.
- **Class weights matter in pre-test folds:** unweighted RF at leaf=3 changes forecasts from 12/0/6 to 6/6/6 and raises this 18-case score from 0.389/0.524/0.338 to 0.556/0.649/0.570 (accuracy/Balanced accuracy/Macro F1). This result requires independent validation.
- **Unknown:** verified units and actual release dates; source revisions; whether credit-level changes are economically comparable; whether alternatives generalize prospectively; probability calibration.

### Recommendation

Leave the current production code/model unchanged for now; keep Always Hold as the stronger primary 24m benchmark. Treat unweighted RF and smaller leaf size as research candidates only, not adopted alternatives: searching variants on the same 18 outcomes creates optimistic selection bias, and no variant was validated on a new untouched period. Retain the application's experimental-model wording.

### Work needed before a replacement

1. Predeclare more rolling-origin folds, with each fit limited to past rows and the sealed final 24 months reserved for one final evaluation.
2. Compare a small predeclared set (current versus unweighted class weights and RF leaf sizes) on identical folds; retain class metrics, confusion matrices, proper probability scores and fold variability.
3. Authenticate units and publication timing using source-vintage data before interpreting credit feature associations.
4. If testing calibration, fit it inside each training fold and score only on later untouched outcomes; do not describe probabilities as calibrated without evidence.
5. Only after such validation, version the candidate model settings, tests and outputs. No source code/model change was made for this diagnostic.

## Reproducibility and checks

- Input SHA-256 (CRLF normalized to LF): `8bf4a1ae7f36eb61c021a7cf8a568f94a9e89271393e15d6c8a02b550cf75b59`.
- Existing primary cutoff: `2024-09-07`; train n=74 through `2024-09-02`; test n=16 from `2024-10-14` through `2026-09-07`.
- Temporal experiments used only the three expanding folds ending before the final cutoff. Tail-period and final-test results above are reports of existing evaluations, not selection criteria.
- Candidate probability log loss was computed with class-name remapping into the displayed Increase/Hold/Decrease order.
- Full tests: `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=.pytest-tmp-collapse` - **32 passed, 2 sklearn warnings** (`y_pred` lacks a class in some small folds).
- Pipeline: `.venv\Scripts\python.exe run_all.py` - **completed successfully**; generated/refreshed the existing MVP backtest, validity, period, probability, alternative-specification, detailed-error, and structural-break outputs. The class metrics stayed Hold Accuracy 0.625 vs LR/RF 0.1875.
- Integrity after both commands: CSV SHA-256 (CRLF normalized to LF) remains `8bf4a1ae7f36eb61c021a7cf8a568f94a9e89271393e15d6c8a02b550cf75b59`; `mvp_backtest_results.json` still records cutoff `2024-09-07`, train n=74 through `2024-09-02`, test n=16 from `2024-10-14` through `2026-09-07`; saved MVP and sealed prediction artifacts each contain 16 / 16 rows.
