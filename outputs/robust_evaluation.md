# Exploratory robustness evaluation

> Exploratory: added on 2026-11-06 after the holdout had been seen. The pre-specified main model and its verdict are unchanged; holdout numbers here are non-confirmatory.

Implementation check: specification M0 reproduces the main model's holdout RMSE (0.625 vs 0.625; PASS).

## Rolling origin estimation sample

One-step-ahead forecasts for usable decisions 41-70 (inside the estimation sample), each model refitted on all earlier decisions. Uses no holdout data, so it is the fair basis for comparing specifications. Decisions 2020-12-15 to 2024-06-03 (n = 30).

| Id | Specification | n | RMSE | RMSE ratio vs Hold | 95% block-bootstrap CI | DM p (sq. error) | RPS | RPS skill vs Hold | DM p (RPS) | Log score | Hit rate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0 | Always Hold (pre-specified benchmark) | 30 | 0.707 | 1.000 | — | — | 0.250 | 0.000 | — | n/a | 0.500 |
| B1 | Class frequencies of the estimation window | 30 | 0.762 | 1.078 | 0.998–1.175 | 0.023 | 0.210 | 0.161 | 0.045 | 1.170 | 0.500 |
| B2 | Persistence: repeat the previous decision | 30 | 0.658 | 0.931 | 0.671–1.183 | 0.601 | 0.217 | 0.133 | 0.601 | n/a | 0.567 |
| M0 | Main ordered logit, six factors (unpenalized) | 30 | 0.741 | 1.047 | 0.861–1.194 | 0.568 | 0.207 | 0.170 | 0.255 | 1.215 | 0.433 |
| M1 | Main ordered logit, six factors, ridge (penalty by time-series CV) | 30 | 0.691 | 0.977 | 0.822–1.107 | 0.734 | 0.187 | 0.252 | 0.075 | 1.048 | 0.467 |
| P0 | Policy-rule ordered logit: inflation, its 3-month change, real rate, previous decision | 30 | 0.663 | 0.937 | 0.694–1.178 | 0.526 | 0.169 | 0.322 | 0.054 | 1.002 | 0.600 |
| P1 | Policy-rule features plus the five other factors, ridge (penalty by time-series CV) | 30 | 0.643 | 0.909 | 0.776–1.070 | 0.258 | 0.175 | 0.298 | 0.065 | 0.983 | 0.400 |

## Holdout fixed origin

Same protocol as the main model: fit once on the 70 estimation decisions, forecast the 18 holdout decisions. Non-confirmatory (holdout already seen). Decisions 2024-07-15 to 2026-09-07 (n = 18).

| Id | Specification | n | RMSE | RMSE ratio vs Hold | 95% block-bootstrap CI | DM p (sq. error) | RPS | RPS skill vs Hold | DM p (RPS) | Log score | Hit rate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0 | Always Hold (pre-specified benchmark) | 18 | 0.624 | 1.000 | — | — | 0.194 | 0.000 | — | n/a | 0.611 |
| B1 | Class frequencies of the estimation window | 18 | 0.624 | 1.000 | 0.926–1.143 | 0.992 | 0.158 | 0.188 | 0.229 | 0.946 | 0.611 |
| B2 | Persistence: repeat the previous decision | 18 | 0.667 | 1.069 | 0.866–1.633 | 0.717 | 0.222 | -0.143 | 0.717 | n/a | 0.556 |
| M0 | Main ordered logit, six factors (unpenalized) | 18 | 0.625 | 1.002 | 0.828–1.230 | 0.982 | 0.156 | 0.198 | 0.234 | 0.940 | 0.611 |
| M1 | Main ordered logit, six factors, ridge (penalty by time-series CV) | 18 | 0.616 | 0.988 | 0.891–1.145 | 0.815 | 0.154 | 0.206 | 0.187 | 0.929 | 0.611 |
| P0 | Policy-rule ordered logit: inflation, its 3-month change, real rate, previous decision | 18 | 0.754 | 1.210 | 0.881–1.961 | 0.310 | 0.210 | -0.080 | 0.817 | 1.183 | 0.389 |
| P1 | Policy-rule features plus the five other factors, ridge (penalty by time-series CV) | 18 | 0.801 | 1.285 | 0.933–2.185 | 0.174 | 0.242 | -0.242 | 0.516 | 1.402 | 0.333 |

## Holdout recursive

Refit before every holdout decision on all earlier decisions, as a real user would. Non-confirmatory (holdout already seen). Decisions 2024-07-15 to 2026-09-07 (n = 18).

| Id | Specification | n | RMSE | RMSE ratio vs Hold | 95% block-bootstrap CI | DM p (sq. error) | RPS | RPS skill vs Hold | DM p (RPS) | Log score | Hit rate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0 | Always Hold (pre-specified benchmark) | 18 | 0.624 | 1.000 | — | — | 0.194 | 0.000 | — | n/a | 0.611 |
| B1 | Class frequencies of the estimation window | 18 | 0.627 | 1.006 | 0.949–1.129 | 0.879 | 0.159 | 0.180 | 0.222 | 0.955 | 0.611 |
| B2 | Persistence: repeat the previous decision | 18 | 0.667 | 1.069 | 0.866–1.633 | 0.717 | 0.222 | -0.143 | 0.717 | n/a | 0.556 |
| M0 | Main ordered logit, six factors (unpenalized) | 18 | 0.623 | 1.000 | 0.886–1.148 | 0.995 | 0.157 | 0.193 | 0.160 | 0.945 | 0.611 |
| M1 | Main ordered logit, six factors, ridge (penalty by time-series CV) | 18 | 0.610 | 0.978 | 0.887–1.114 | 0.636 | 0.154 | 0.209 | 0.157 | 0.929 | 0.611 |
| P0 | Policy-rule ordered logit: inflation, its 3-month change, real rate, previous decision | 18 | 0.629 | 1.009 | 0.770–1.455 | 0.955 | 0.153 | 0.213 | 0.413 | 0.948 | 0.722 |
| P1 | Policy-rule features plus the five other factors, ridge (penalty by time-series CV) | 18 | 0.610 | 0.977 | 0.788–1.358 | 0.863 | 0.145 | 0.253 | 0.246 | 0.941 | 0.722 |

Reading the table. RMSE is computed on the expected score (Decrease = −1, Hold = 0, Increase = +1), as in the main model. RPS (ranked probability score, lower is better) scores the full probability forecast and respects the class order; it is finite for Always Hold, unlike the log score (n/a = infinite because a forecast gave zero probability to an observed class). RPS skill = 1 − RPS/RPS(Hold); positive values favour the specification. DM p is the two-sided Harvey–Leybourne–Newbold-corrected Diebold–Mariano p-value against Always Hold. The bootstrap interval resamples blocks of 3 consecutive decisions (10000 draws, seed 42). Ridge penalties are chosen at every forecast origin by one-step RPS over the previous 12 decisions only.

## Next-meeting probabilities by specification

All specifications are fitted on every usable decision up to 2026-09-07. Factor inputs stay at their latest values; previous decision = -1, base rate = 16.25%.

| Id | Specification | P(Decrease) | P(Hold) | P(Increase) | Expected score |
|---|---|---|---|---|---|
| B0 | Always Hold (pre-specified benchmark) | 0.000 | 1.000 | 0.000 | 0.000 |
| B1 | Class frequencies of the estimation window | 0.273 | 0.557 | 0.170 | -0.102 |
| B2 | Persistence: repeat the previous decision | 1.000 | 0.000 | 0.000 | -1.000 |
| M0 | Main ordered logit, six factors (unpenalized) | 0.293 | 0.596 | 0.111 | -0.182 |
| M1 | Main ordered logit, six factors, ridge (penalty by time-series CV) | 0.293 | 0.596 | 0.111 | -0.182 |
| P0 | Policy-rule ordered logit: inflation, its 3-month change, real rate, previous decision | 0.578 | 0.389 | 0.033 | -0.545 |
| P1 | Policy-rule features plus the five other factors, ridge (penalty by time-series CV) | 0.666 | 0.320 | 0.014 | -0.652 |

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
| export_history.csv | 2019-04 | 5201089.07 | 3433642.24 | 0.415 (monthly log change) | 3.59 | no |
| export_history.csv | 2026-06 | 9816470.38 | 6276443.18 | 0.447 (monthly log change) | 3.87 | yes |
| import_history.csv | 2016-01 | 1594493.32 | 2319829.46 | -0.375 (monthly log change) | -4.48 | no |
| import_history.csv | 2020-01 | 2553506.17 | 3525114.55 | -0.322 (monthly log change) | -3.88 | no |
| import_history.csv | 2021-01 | 2182365.23 | 3582678.38 | -0.496 (monthly log change) | -5.85 | no |
| import_history.csv | 2022-01 | 2847284.44 | 4320583.01 | -0.417 (monthly log change) | -4.95 | no |
| import_history.csv | 2026-01 | 4689133.01 | 7115016.38 | -0.417 (monthly log change) | -4.95 | no |
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
