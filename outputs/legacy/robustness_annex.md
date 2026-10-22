# Robustness annex

Expanding-window forecasts are repeated using macro input lags of one and three months; this checks sensitivity to uncertain release timing. The selected model remains lag two.

- **macro lag 2 (baseline):** model MAE=0.3652, benchmark MAE=0.2318; n=96
- **macro lag 1:** model MAE=0.3766, benchmark MAE=0.2318; n=96
- **macro lag 3:** model MAE=0.3377, benchmark MAE=0.2318; n=96

All variants remain small-sample associations and are not causal specifications. The two alternatives are sensitivity checks, not a search used to select the headline model.
