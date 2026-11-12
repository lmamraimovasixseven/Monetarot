# Falsification verdicts

Rules are evaluated as written in `docs/model_spec.md`. The primary joint LR decision uses its raw p-value. The adjusted column is shown for transparency; it does not replace the specified rule.

| rule | statistic | threshold | verdict | raw p-value | adjusted p-value | p-value family | adjusted transparency verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Joint LR test of all six slopes is not rejected at 10% (raw p-value) | 14.35097885022735 | raw p >= 0.10 | not falsified | 0.02595204549055389 | 0.02595204549055389 | pre-specified joint LR test (single primary test; no adjustment) | not falsified |
| Any factor has an opposite-sign coefficient significant at 5% (raw p-value) | no opposite-sign significant factors | opposite sign and raw p < 0.05 | not falsified | {'inflation': 0.585584486141336, 'exports': 0.2065779566137408, 'imports': 0.8061093096042594, 'corporate_lending': 0.2919196703229595, 'household_lending': 0.007904753144179258, 'consumption': 0.8016382635693907} | {'inflation': 1.0, 'exports': 1.0, 'imports': 1.0, 'corporate_lending': 1.0, 'household_lending': 0.04742851886507554, 'consumption': 1.0} | six slope-coefficient p-values (Holm across six) | not falsified |
| Holdout expected-score RMSE ratio is >= 1 | 0.9949030629786558 | RMSE_model / RMSE_Always_Hold >= 1 | not falsified | not applicable | not applicable | not applicable (RMSE criterion has no p-value) | same rule; p-value adjustment not applicable |

The finite class-frequency log-score comparator is secondary and was added after the specification freeze. The pre-specified winner remains determined only by expected-score RMSE versus Always Hold.
