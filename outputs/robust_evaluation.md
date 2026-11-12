# Exploratory robustness evaluation

> Exploratory: added on 2026-11-06 after the holdout had been seen. The pre-specified main model and its verdict are unchanged; holdout numbers here are non-confirmatory.

Implementation check: specification M0 reproduces the main model's holdout RMSE (0.620 vs 0.620; PASS).

## Rolling origin estimation sample

One-step-ahead forecasts for usable decisions 41-71 (inside the estimation sample), each model refitted on all earlier decisions. Uses no holdout data, so it is the fair basis for comparing specifications. Decisions 2020-12-15 to 2024-07-15 (n = 31).

| Id | Specification | n | RMSE | RMSE ratio vs Hold | 95% block-bootstrap CI | DM p (sq. error) | RPS | RPS skill vs Hold | DM p (RPS) | Log score | Hit rate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0 | Always Hold (pre-specified benchmark) | 31 | 0.718 | 1.000 | — | — | 0.258 | 0.000 | — | n/a | 0.484 |
| B1 | Class frequencies of the estimation window | 31 | 0.767 | 1.067 | 0.992–1.168 | 0.045 | 0.212 | 0.180 | 0.024 | 1.173 | 0.484 |
| B2 | Persistence: repeat the previous decision | 31 | 0.648 | 0.901 | 0.686–1.173 | 0.448 | 0.210 | 0.188 | 0.448 | n/a | 0.581 |
| M0 | Main ordered logit, six factors (unpenalized) | 31 | 0.752 | 1.047 | 0.871–1.187 | 0.547 | 0.213 | 0.176 | 0.211 | 1.233 | 0.419 |
| M1 | Main ordered logit, six factors, ridge (penalty by time-series CV) | 31 | 0.700 | 0.974 | 0.833–1.099 | 0.693 | 0.191 | 0.261 | 0.052 | 1.060 | 0.452 |
| P0 | Policy-rule ordered logit: inflation, its 3-month change, real rate, previous decision | 31 | 0.654 | 0.910 | 0.695–1.160 | 0.361 | 0.165 | 0.361 | 0.029 | 0.979 | 0.613 |
| P1 | Policy-rule features plus the five other factors, ridge (penalty by time-series CV) | 31 | 0.637 | 0.887 | 0.770–1.058 | 0.162 | 0.173 | 0.330 | 0.038 | 0.970 | 0.419 |

## Holdout fixed origin

Same protocol as the main model: fit once on the 71 estimation decisions, forecast the 18 holdout decisions. Non-confirmatory (holdout already seen). Decisions 2024-09-02 to 2026-10-27 (n = 18).

| Id | Specification | n | RMSE | RMSE ratio vs Hold | 95% block-bootstrap CI | DM p (sq. error) | RPS | RPS skill vs Hold | DM p (RPS) | Log score | Hit rate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0 | Always Hold (pre-specified benchmark) | 18 | 0.624 | 1.000 | — | — | 0.194 | 0.000 | — | n/a | 0.611 |
| B1 | Class frequencies of the estimation window | 18 | 0.625 | 1.003 | 0.909–1.162 | 0.959 | 0.159 | 0.184 | 0.249 | 0.949 | 0.611 |
| B2 | Persistence: repeat the previous decision | 18 | 0.667 | 1.069 | 0.707–1.658 | 0.717 | 0.222 | -0.143 | 0.717 | n/a | 0.556 |
| M0 | Main ordered logit, six factors (unpenalized) | 18 | 0.620 | 0.995 | 0.780–1.335 | 0.961 | 0.154 | 0.207 | 0.296 | 0.931 | 0.667 |
| M1 | Main ordered logit, six factors, ridge (penalty by time-series CV) | 18 | 0.614 | 0.984 | 0.864–1.180 | 0.797 | 0.154 | 0.209 | 0.207 | 0.927 | 0.611 |
| P0 | Policy-rule ordered logit: inflation, its 3-month change, real rate, previous decision | 18 | 0.773 | 1.240 | 0.768–2.035 | 0.260 | 0.220 | -0.131 | 0.714 | 1.227 | 0.389 |
| P1 | Policy-rule features plus the five other factors, ridge (penalty by time-series CV) | 18 | 0.826 | 1.324 | 0.837–2.294 | 0.145 | 0.254 | -0.308 | 0.438 | 1.470 | 0.278 |

## Holdout recursive

Refit before every holdout decision on all earlier decisions, as a real user would. Non-confirmatory (holdout already seen). Decisions 2024-09-02 to 2026-10-27 (n = 18).

| Id | Specification | n | RMSE | RMSE ratio vs Hold | 95% block-bootstrap CI | DM p (sq. error) | RPS | RPS skill vs Hold | DM p (RPS) | Log score | Hit rate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0 | Always Hold (pre-specified benchmark) | 18 | 0.624 | 1.000 | — | — | 0.194 | 0.000 | — | n/a | 0.611 |
| B1 | Class frequencies of the estimation window | 18 | 0.628 | 1.007 | 0.939–1.129 | 0.846 | 0.160 | 0.177 | 0.225 | 0.958 | 0.611 |
| B2 | Persistence: repeat the previous decision | 18 | 0.667 | 1.069 | 0.707–1.658 | 0.717 | 0.222 | -0.143 | 0.717 | n/a | 0.556 |
| M0 | Main ordered logit, six factors (unpenalized) | 18 | 0.599 | 0.961 | 0.853–1.147 | 0.529 | 0.148 | 0.237 | 0.126 | 0.904 | 0.611 |
| M1 | Main ordered logit, six factors, ridge (penalty by time-series CV) | 18 | 0.594 | 0.953 | 0.858–1.114 | 0.412 | 0.149 | 0.234 | 0.140 | 0.909 | 0.611 |
| P0 | Policy-rule ordered logit: inflation, its 3-month change, real rate, previous decision | 18 | 0.635 | 1.018 | 0.675–1.457 | 0.905 | 0.156 | 0.197 | 0.434 | 0.962 | 0.722 |
| P1 | Policy-rule features plus the five other factors, ridge (penalty by time-series CV) | 18 | 0.607 | 0.973 | 0.702–1.361 | 0.838 | 0.144 | 0.262 | 0.241 | 0.935 | 0.722 |

Reading the table. RMSE is computed on the expected score (Decrease = −1, Hold = 0, Increase = +1), as in the main model. RPS (ranked probability score, lower is better) scores the full probability forecast and respects the class order; it is finite for Always Hold, unlike the log score (n/a = infinite because a forecast gave zero probability to an observed class). RPS skill = 1 − RPS/RPS(Hold); positive values favour the specification. DM p is the two-sided Harvey–Leybourne–Newbold-corrected Diebold–Mariano p-value against Always Hold. The bootstrap interval resamples blocks of 3 consecutive decisions (10000 draws, seed 42). Ridge penalties are chosen at every forecast origin by one-step RPS over the previous 12 decisions only.

## What the tables say (generated)

- The 95% block-bootstrap interval for the RMSE ratio (0.780 to 1.335) contains 1, and the Diebold–Mariano test (HLN-corrected) gives p = 0.961, so on 18 holdout decisions the model cannot be distinguished from Always Hold in either direction. The pre-specified verdict is the RMSE ratio rule of the main model and is not changed by this evaluation.
- Supplementary measure (exploratory, added after the holdout had been seen; the pre-specified verdict stays RMSE-based): the ranked probability score on the same holdout (lower is better) is 0.154 for the model, 0.194 for Always Hold and 0.159 for the class frequencies of the estimation sample. Simple class frequencies do almost as well as the model, so the six factors add little beyond the base rates of cuts, holds and hikes; most of the gain over Always Hold comes from admitting that cuts and hikes happen.
- Policy-inertia specifications (exploratory only; P0 = inflation, its 3-month change, the ex-post real rate and the previous decision; P1 = P0 plus the other five factors, ridge). RPS of the specification vs the main model M0 — P0: rolling origin inside the estimation sample 0.165 vs 0.213; fixed-origin holdout 0.220 vs 0.154; recursive holdout 0.156 vs 0.148 | P1: rolling origin inside the estimation sample 0.173 vs 0.213; fixed-origin holdout 0.254 vs 0.154; recursive holdout 0.144 vs 0.148. P0 has the lower RPS in 1 of 3 designs; P1 has the lower RPS in 2 of 3 designs. The ranking depends on the evaluation design, which is instability, not an improvement; neither specification replaces the pre-specified model.

## Next-meeting probabilities by specification

All specifications are fitted on every usable decision up to 2026-10-27. Factor inputs stay at their latest values; previous decision = -1, base rate = 15.75%.

| Id | Specification | P(Decrease) | P(Hold) | P(Increase) | Expected score |
|---|---|---|---|---|---|
| B0 | Always Hold (pre-specified benchmark) | 0.000 | 1.000 | 0.000 | 0.000 |
| B1 | Class frequencies of the estimation window | 0.281 | 0.551 | 0.169 | -0.112 |
| B2 | Persistence: repeat the previous decision | 1.000 | 0.000 | 0.000 | -1.000 |
| M0 | Main ordered logit, six factors (unpenalized) | 0.392 | 0.532 | 0.076 | -0.317 |
| M1 | Main ordered logit, six factors, ridge (penalty by time-series CV) | 0.392 | 0.532 | 0.076 | -0.317 |
| P0 | Policy-rule ordered logit: inflation, its 3-month change, real rate, previous decision | 0.596 | 0.373 | 0.030 | -0.566 |
| P1 | Policy-rule features plus the five other factors, ridge (penalty by time-series CV) | 0.649 | 0.337 | 0.014 | -0.636 |

## Announcement-date sensitivity (exploratory, non-confirmatory)

Exploratory sensitivity check, non-confirmatory: the main model keeps the effective-date convention; this check is not used to choose or change any model.

The main model aligns every factor to the decision's effective month minus the assumed lag. For the decisions listed here the NBK announcement fell in the previous calendar month (`docs/nbk_announcement_dates.csv`), so this check aligns them to the announcement month instead: 2024-06-03, 2024-09-02, 2024-12-02, 2025-09-02, 2025-12-01.

Decisions effective on day 1-5 of a month whose announcement date is not documented (UNKNOWN; kept at the effective month): 2016-10-04, 2018-06-05, 2018-09-04, 2018-12-05, 2019-03-05, 2019-06-04, 2020-02-04.

| Design | n | Re-aligned decisions in window | RMSE ratio vs Hold (effective) | RMSE ratio vs Hold (announcement) | RPS (effective) | RPS (announcement) |
|---|---|---|---|---|---|---|
| rolling origin estimation sample | 31 | 1 | 1.047 | 1.047 | 0.213 | 0.213 |
| holdout fixed origin | 18 | 4 | 0.995 | 0.981 | 0.154 | 0.151 |
| holdout recursive | 18 | 4 | 0.961 | 0.959 | 0.148 | 0.148 |

## Raw-data anomaly screen

Modified z-score of monthly changes, flag at |z| ≥ 3.5 (Iglewicz and Hoaglin, 1993). A flag asks for the source value to be re-checked; it is not evidence of an error and nothing is changed in the data.

| Series | Month | Value | Previous month | Change | Modified z | Enters latest score |
|---|---|---|---|---|---|---|
| inflation_history.csv | 2015-10 | 9.40 | 4.40 | 5.000 (first difference) | 11.24 | no |
| inflation_history.csv | 2015-11 | 12.80 | 9.40 | 3.400 (first difference) | 7.64 | no |
| inflation_history.csv | 2016-10 | 11.50 | 16.60 | -5.100 (first difference) | -11.47 | no |
| inflation_history.csv | 2016-11 | 8.70 | 11.50 | -2.800 (first difference) | -6.30 | no |
| inflation_history.csv | 2022-03 | 12.00 | 8.70 | 3.300 (first difference) | 7.42 | no |
| inflation_history.csv | 2022-09 | 17.70 | 16.10 | 1.600 (first difference) | 3.60 | no |
| inflation_history.csv | 2023-03 | 18.10 | 21.30 | -3.200 (first difference) | -7.19 | no |
| export_history.csv | 2019-04 | 5201089.07 | 3433642.24 | 0.415 (monthly log change) | 3.62 | no |
| export_history.csv | 2026-06 | 9816470.38 | 6276443.18 | 0.447 (monthly log change) | 3.90 | yes |
| import_history.csv | 2016-01 | 1594493.32 | 2319829.46 | -0.375 (monthly log change) | -4.50 | no |
| import_history.csv | 2020-01 | 2553506.17 | 3525114.55 | -0.322 (monthly log change) | -3.90 | no |
| import_history.csv | 2021-01 | 2182365.23 | 3582678.38 | -0.496 (monthly log change) | -5.88 | no |
| import_history.csv | 2022-01 | 2847284.44 | 4320583.01 | -0.417 (monthly log change) | -4.98 | no |
| import_history.csv | 2026-01 | 4689133.01 | 7115016.38 | -0.417 (monthly log change) | -4.98 | yes |
| loans_legal_entities_history.csv | 2015-06 | 6713193.90 | 8094079.27 | -0.187 (monthly log change) | -10.79 | no |
| loans_legal_entities_history.csv | 2015-08 | 7258226.68 | 6634131.68 | 0.090 (monthly log change) | 5.01 | no |
| loans_legal_entities_history.csv | 2019-01 | 7150898.55 | 7789143.84 | -0.085 (monthly log change) | -5.00 | no |
| loans_legal_entities_history.csv | 2023-12 | 9685852.04 | 9034012.56 | 0.070 (monthly log change) | 3.85 | no |
| consumption_history_updated.csv | 2020-04 | -44.70 | -4.50 | -40.200 (first difference) | -11.30 | no |
| consumption_history_updated.csv | 2020-05 | -30.80 | -44.70 | 13.900 (first difference) | 3.91 | no |
| consumption_history_updated.csv | 2020-06 | 1.60 | -30.80 | 32.400 (first difference) | 9.11 | no |
| consumption_history_updated.csv | 2021-04 | 41.70 | 2.20 | 39.500 (first difference) | 11.10 | no |
| consumption_history_updated.csv | 2021-05 | 13.30 | 41.70 | -28.400 (first difference) | -7.98 | no |
| consumption_history_updated.csv | 2022-01 | -15.90 | 6.40 | -22.300 (first difference) | -6.27 | no |
| consumption_history_updated.csv | 2022-02 | 0.60 | -15.90 | 16.500 (first difference) | 4.64 | no |
| consumption_history_updated.csv | 2023-01 | 20.80 | 1.00 | 19.800 (first difference) | 5.56 | no |
| consumption_history_updated.csv | 2023-02 | 6.50 | 20.80 | -14.300 (first difference) | -4.02 | no |

Generated by `python run.py robust` (src/robust_eval.py).
