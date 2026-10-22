<!-- Template for docs/decision_rule.md. Edit here, then run `python run.py facts`.
     n.* = outputs/numbers_for_note.json, f.* = docs/facts_to_fill.md, r.* = computed. -->
# Decision rule: three options (choices for the student)

> **These are options, not a decision.** The student chooses one (or none) and records the choice as `decision_rule_option` in `docs/facts_to_fill.md`. Current choice: **{{f.decision_rule_option}}**. Named user: **{{f.named_user}}**.
>
> Every option is a **monitoring** rule, not a forecast. {{n.verdict_sentence}} The model beats Always Hold in {{n.robustness_flipped_benchmark_count}} of {{n.robustness_check_count}} robustness checks, so the negative result is fragile too. No option claims predictive accuracy.

## Facts the options use (all from `outputs/numbers_for_note.json`)

- Latest score {{n.headline_score}} ({{n.latest_decision_date}}); 95% band {{n.headline_score_band_low}} to {{n.headline_score_band_high}}, width {{n.headline_score_band_width}} score points.
- Latest change {{n.latest_score_change}}; typical decision-to-decision move {{n.econ_typical_score_move}} (median in the estimation sample).
- Next decision: Increase {{n.next_round_probability_increase}}, Hold {{n.next_round_probability_hold}}, Decrease {{n.next_round_probability_decrease}}.

## Option 1: direction flag (band clear of zero)

- **Named user:** {{r.option1_user}}. Suits a user who needs to know only the direction of pressure before a meeting.
- **Rule:** if the 95% band of the score moves entirely above 0 (or entirely below 0), then flag a hawkish (or dovish) tilt and review rate-sensitive exposures before the next decision, because only then is the sign of the pressure distinguishable from balance, given a band about {{n.headline_score_band_width}} score points wide.
- **Today:** the band is {{n.headline_score_band_low}} to {{n.headline_score_band_high}}; triggered: {{r.option1_triggered}}.
- **Weakness:** a wide band means the flag fires rarely; the band reflects parameter uncertainty only, not model error.

## Option 2: momentum flag (change larger than a typical move)

- **Named user:** {{r.option2_user}}. Suits a user who writes a pre-meeting brief and needs to notice shifts.
- **Rule:** if the score moves by more than {{n.econ_typical_score_move}} between consecutive decisions, then add a "pressure shifted" note to the brief and name the driving factors from the dashboard, because a move larger than the typical move signals a change in the factor mix even while the level stays inside its band.
- **Today:** latest change {{n.latest_score_change}}; triggered: {{r.option2_triggered}}.
- **Weakness:** no uncertainty band exists for the change itself, so some flags will be noise.

## Option 3: class flag (Hold no longer the most likely class)

- **Named user:** {{r.option3_user}}. Suits a user who prepares funding-cost scenarios.
- **Rule:** if P(Increase) or P(Decrease) exceeds P(Hold) for the next decision, then prepare the matching rate scenario, because the model's most likely class is then not Hold.
- **Today:** most likely class {{r.option3_top_class}}; triggered: {{r.option3_triggered}}.
- **Weakness:** probabilities are not calibrated; the model's holdout log score ({{n.oos_model_log_score}}) is close to that of fixed class frequencies ({{n.oos_frequency_log_score}}).
