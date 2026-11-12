# Development plan: out-of-sample protocol from 2026-11-12 on

Written on 2026-11-12, **before** the next NBK decision (scheduled 2026-12-04 in `config/forecast_rounds.json`)
and before any of its data exist. Its purpose is to replace the missing pre-registration with a protocol
that is fixed in advance and timestamped by a public GitHub commit. Rules (a)–(d) and (f) are project rules; the
promotion rule (e) is a **proposal that the owner must approve**: until the owner's approval is recorded in the
"Approval" section below, no candidate can be promoted.

## (a) The main specification is frozen

The pre-specified ordered logit (six factors, transformations and timing in `docs/model_spec.md`), its split
rule (last ceil(20%) of usable decisions as holdout), its verdict rule (holdout RMSE ratio against Always
Hold, below 1 = criterion met) and its estimator stay as they are. Data updates re-run them
(`docs/RUNBOOK_data_update.md`); nothing is tuned. Any change requires the owner's explicit approval and a new
entry in `docs/deviations.md`.

## (b) The next decision

The next scheduled NBK decision is 2026-12-04 (announcement date, `config/forecast_rounds.json`, verified
against the NBK schedule page). The decision after it is UNKNOWN until the NBK publishes its 2027 schedule.

## (c) Forecasts are logged before each decision

Before every decision, `python run.py forecast-log` appends the frozen model's next-decision probabilities and
expected score to `docs/forecast_log.csv`, with the UTC time, the git commit of HEAD, the SHA-256 of
`model/artifact.json` and a hash of the input data. The log is committed and pushed the same day; the GitHub
commit time is the external timestamp. The command refuses a target date on or before the logging date and a
decision that is already in the data. Log rows are never edited or deleted (append-only, guarded by
`tests/test_data_contract.py`). After the decision is added to the data, `python run.py forecast-score` scores
the logged forecasts (RPS, squared error of the expected score, hit) next to Always Hold.

The forecast for 2026-12-04 is the model's probability at the latest decision in the data (2026-10-27), as stated
in `docs/deviations.md` D21; the factor month that the rule would use for 2026-12-04 (2026-10) is not in the data.

## (d) How candidate improvements may be explored

Candidates named so far: policy inertia (previous decision, ex-post real rate, the inflation change), a ridge
penalty, and extra factors (for example the KZT exchange rate and the oil price, which are not yet in the data and
would need sources recorded in `docs/facts_to_fill.csv`). They may be explored **only** by rolling-origin,
one-step-ahead evaluation inside the estimation sample of the frozen model (as `src/robust_eval.py` does), never on
the holdout and never on decisions after 2026-11-12. Each candidate is fixed (features, transformations, penalty
rule) and written into this file, with a commit, before its first prospective forecast is logged. A candidate's
prospective forecasts are logged by the same rule (c), next to the frozen model's.

## (e) Promotion rule (PROPOSAL, needs the owner's approval)

Pre-declared metrics, computed only on decisions taken after the candidate was fixed and logged (prospective
decisions):

1. mean ranked probability score (RPS), primary;
2. RMSE of the expected score (the metric of the frozen verdict rule), secondary;
3. a 95% moving-block bootstrap interval for the RPS difference (candidate minus frozen model) and for the RMSE
   ratio (candidate / Always Hold), as in `src/robust_eval.py`.

Proposed K = 8 prospective decisions (about one year at the NBK's eight scheduled meetings per year).

A candidate is promoted only if, after at least K = 8 prospective decisions, **all** of these hold:

- its mean RPS is lower than that of the frozen model, of Always Hold and of the class frequencies;
- its RMSE ratio against Always Hold is below 1;
- the 95% bootstrap interval for its RPS difference against the frozen model lies entirely below 0.

If the rule is not met after K decisions, the frozen model stays and evaluation continues; the rule is never
relaxed after seeing results. With eight decisions the interval will rarely exclude 0, so the expected outcome
is that the frozen model stays; this is accepted in advance.

## (f) Every promotion is a deviation

A promotion (or any change of the frozen specification) is recorded as the next free D-number in
`docs/deviations.md` (what changed / why / what the original produced), with the scores that met the rule.

## Approval

- Promotion rule (e), including K: UNKNOWN (owner to approve or change, then record date and decision here).
