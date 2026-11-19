# Omitted-variable check (exploratory)

Exploratory: added on 2026-11-16 after the holdout had been seen, at the instructor's request. The frozen specification, its holdout verdict and the pre-registration do not change.

Usable decisions 89: estimation 71 (2016-03-15 to 2024-07-15), holdout 18 (2024-09-02 to 2026-10-27). Controls: Bank of Russia key rate, China policy rate (BIS; LPR 1Y / benchmark lending rate), ECB deposit facility rate; calendar-day mean of the month (external_data.monthly_step_rate), level in percent, aligned to decision month minus the assumed release lag like the six factors.

## Six coefficients by specification (HC0 standard errors)

| Factor | frozen | plus_ru_key_rate | plus_cn_policy_rate | plus_ecb_deposit_rate | plus_all_three |
|---|---|---|---|---|---|
| inflation | 0.038 (0.071; p 0.586) | 0.060 (0.073; p 0.414) | 0.016 (0.068; p 0.816) | 0.064 (0.072; p 0.371) | 0.082 (0.080; p 0.302) |
| exports | 0.013 (0.010; p 0.207) | 0.028 (0.013; p 0.031) | 0.005 (0.013; p 0.674) | -0.004 (0.012; p 0.758) | 0.006 (0.015; p 0.702) |
| imports | -0.004 (0.018; p 0.806) | -0.028 (0.023; p 0.217) | -0.003 (0.019; p 0.881) | 0.006 (0.022; p 0.781) | -0.005 (0.024; p 0.846) |
| corporate_lending | -0.052 (0.049; p 0.292) | -0.004 (0.051; p 0.937) | 0.005 (0.053; p 0.928) | 0.014 (0.049; p 0.778) | 0.012 (0.060; p 0.843) |
| household_lending | 0.070 (0.026; p 0.008) | 0.080 (0.028; p 0.005) | 0.127 (0.043; p 0.003) | 0.141 (0.038; p 0.000) | 0.121 (0.052; p 0.019) |
| consumption | -0.005 (0.020; p 0.802) | 0.024 (0.024; p 0.313) | 0.002 (0.020; p 0.905) | 0.029 (0.026; p 0.252) | 0.036 (0.028; p 0.208) |

## Added controls

| Specification | Control estimates (p) | HC0 Wald (df) | p | Holm p | LR | LR p | max VIF |
|---|---|---|---|---|---|---|---|
| plus_ru_key_rate | ru_key_rate -0.366 (0.000) | 12.177 (1) | 0.000 | 0.001 | 13.292 | 0.000 | 2.77 |
| plus_cn_policy_rate | cn_policy_rate 2.665 (0.109) | 2.573 (1) | 0.109 | 0.109 | 2.754 | 0.097 | 4.74 |
| plus_ecb_deposit_rate | ecb_deposit_rate -1.146 (0.000) | 18.729 (1) | 0.000 | 0.000 | 23.575 | 0.000 | 2.79 |
| plus_all_three | ru_key_rate -0.165 (0.220); cn_policy_rate -0.747 (0.711); ecb_deposit_rate -1.052 (0.002) | 17.403 (3) | 0.001 | 0.001 | 26.002 | 0.000 | 8.15 |

## Holdout

| Specification | RMSE ratio to Always Hold | RPS | DM sq. error vs frozen (p) | DM RPS vs frozen (p) |
|---|---|---|---|---|
| frozen | 0.995 | 0.154 | — | — |
| plus_ru_key_rate | 1.674 | 0.396 | 3.760 (0.002) | 4.766 (0.000) |
| plus_cn_policy_rate | 1.360 | 0.263 | 2.598 (0.019) | 2.706 (0.015) |
| plus_ecb_deposit_rate | 1.295 | 0.232 | 2.086 (0.052) | 2.073 (0.054) |
| plus_all_three | 1.507 | 0.316 | 2.928 (0.009) | 3.374 (0.004) |

## Cross-check: base-rate change in percentage points, OLS with HC1

| Factor | OLS six factors (p) | OLS with controls (p) | Same sign as ordered logit (six / with controls) |
|---|---|---|---|
| inflation | -0.032 (0.301) | -0.036 (0.315) | no / no |
| exports | 0.001 (0.695) | -0.001 (0.873) | yes / no |
| imports | 0.007 (0.202) | 0.005 (0.327) | no / no |
| corporate_lending | 0.014 (0.349) | 0.038 (0.196) | no / yes |
| household_lending | 0.020 (0.008) | 0.035 (0.116) | yes / yes |
| consumption | -0.001 (0.764) | 0.006 (0.357) | yes / yes |

## Partner-rate what-if (exploratory, not used for the forecast; D59)

Exploratory, not used for the forecast (D59): each extended specification, estimated on the estimation sample, evaluated at the factor and partner-rate values of the last usable decision; the score is P(Increase) - P(Decrease); the change is for one partner rate moved by the stated points with the other inputs fixed; delta-method 95% interval with the HC0 covariance of the slopes and cut-points.

Last usable decision: 2026-10-27.

| Specification | Cut-points | Latest index | Latest score | Partner rate (latest) | Move | Score change | 95% interval | Interval includes zero |
|---|---|---|---|---|---|---|---|---|
| plus_ru_key_rate | -2.302; 1.065 | -2.595 | -0.548 | ru_key_rate (14.00) | +1 | -0.094 | -0.150 to -0.037 | no |
| plus_ru_key_rate | -2.302; 1.065 | -2.595 | -0.548 | ru_key_rate (14.00) | -1 | 0.102 | 0.046 to 0.157 | no |
| plus_cn_policy_rate | 12.062; 15.073 | 9.877 | -0.893 | cn_policy_rate (3.00) | +1 | 0.585 | 0.217 to 0.953 | no |
| plus_cn_policy_rate | 12.062; 15.073 | 9.877 | -0.893 | cn_policy_rate (3.00) | -1 | -0.098 | -0.402 to 0.205 | yes |
| plus_ecb_deposit_rate | 1.613; 5.459 | -0.089 | -0.842 | ecb_deposit_rate (2.25) | +1 | -0.102 | -0.242 to 0.038 | yes |
| plus_ecb_deposit_rate | 1.613; 5.459 | -0.089 | -0.842 | ecb_deposit_rate (2.25) | -1 | 0.219 | 0.053 to 0.384 | no |
| plus_all_three | -2.973; 0.972 | -4.152 | -0.759 | ru_key_rate (14.00) | +1 | -0.029 | -0.097 to 0.039 | yes |
| plus_all_three | -2.973; 0.972 | -4.152 | -0.759 | ru_key_rate (14.00) | -1 | 0.032 | -0.037 to 0.102 | yes |
| plus_all_three | -2.973; 0.972 | -4.152 | -0.759 | cn_policy_rate (3.00) | +1 | -0.111 | -0.855 to 0.633 | yes |
| plus_all_three | -2.973; 0.972 | -4.152 | -0.759 | cn_policy_rate (3.00) | -1 | 0.165 | -1.087 to 1.417 | yes |
| plus_all_three | -2.973; 0.972 | -4.152 | -0.759 | ecb_deposit_rate (2.25) | +1 | -0.142 | -0.579 to 0.295 | yes |
| plus_all_three | -2.973; 0.972 | -4.152 | -0.759 | ecb_deposit_rate (2.25) | -1 | 0.244 | -0.171 to 0.658 | yes |

Generated by `python run.py ovb` into model/extensions/ovb_check.json; model/artifact.json is not changed.
