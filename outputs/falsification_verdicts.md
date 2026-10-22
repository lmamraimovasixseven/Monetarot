# Falsification verdicts

Rules are evaluated as written in `docs/model_spec.md`. The primary joint LR decision uses its raw p-value. The adjusted column is shown for transparency; it does not replace the specified rule.

| rule | statistic | threshold | verdict | raw p-value | adjusted p-value | p-value family | adjusted transparency verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Joint LR test of all six slopes is not rejected at 10% (raw p-value) | 15.240435352202809 | raw p >= 0.10 | not falsified | 0.018466879346204394 | 0.018466879346204394 | pre-specified joint LR test (single primary test; no adjustment) | not falsified |
| Any factor has an opposite-sign coefficient significant at 5% (raw p-value) | no opposite-sign significant factors | opposite sign and raw p < 0.05 | not falsified | {'inflation': 0.7538496075980295, 'exports': 0.18901726923832896, 'imports': 0.6658599015103904, 'corporate_lending': 0.39203994185091573, 'household_lending': 0.005119624993344942, 'consumption': 0.9437849512923012} | {'inflation': 1.0, 'exports': 0.9450863461916448, 'imports': 1.0, 'corporate_lending': 1.0, 'household_lending': 0.03071774996006965, 'consumption': 1.0} | six slope-coefficient p-values (Holm across six) | not falsified |
| Holdout expected-score RMSE ratio is >= 1 | 1.0017200516266327 | RMSE_model / RMSE_Always_Hold >= 1 | falsified | not applicable | not applicable | not applicable (RMSE criterion has no p-value) | same rule; p-value adjustment not applicable |

The finite class-frequency log-score comparator is secondary and was added after the specification freeze. The pre-specified winner remains determined only by expected-score RMSE versus Always Hold.
