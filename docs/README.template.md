<!--
  Source of README.md. Do not edit README.md directly: edit this file, then run
  `python run.py report`. Every result number is a {{key}} placeholder filled from
  outputs/numbers_for_note.json, whose entries point to fields in model/artifact.json.
  After re-estimating, re-read the interpretive sentences (Main result, Robustness, Limitations).
-->
# NBK Policy Pressure Score

A read-only dashboard and replication package for one indicator: the **policy pressure score** for National Bank of Kazakhstan (NBK) base-rate decisions.

## The indicator

| | |
|---|---|
| **Value** | Policy pressure score = P(Increase) − P(Decrease) from an ordered logit on six factors (inflation, exports, imports, corporate lending, household lending, consumption). |
| **Unit** | Probability difference, from −1 (a cut is certain) to +1 (a hike is certain); 0 means balanced. |
| **Period** | One value per NBK base-rate decision date. Factor values are taken from the calendar month two months before the decision month (an assumption; see Limitations). |
| **Latest** | {{headline_score}} for the decision of {{latest_decision_date}} (95% delta-method band {{headline_score_band_low}} to {{headline_score_band_high}}), a change of {{latest_score_change}} from the previous decision. |
| **Next decision** | Increase {{next_round_probability_increase}} · Hold {{next_round_probability_hold}} · Decrease {{next_round_probability_decrease}}. Both upcoming rounds use the latest factor values, so their probabilities are identical. Meeting dates come from `config/forecast_rounds.json`. |

**Main result (negative).** {{verdict_sentence}} The model's holdout RMSE is {{oos_model_rmse}} against {{oos_hold_rmse}} for Always Hold, on {{n_holdout}} decisions from {{sample_holdout_start}} to {{sample_holdout_end}}. Household lending is the only slope that is significant after Holm adjustment (raw p {{p_raw_household_lending}}, Holm p {{p_holm_household_lending}}). In "{{robustness_RB09_name}}" (RB09, `outputs/robustness_table.md`) its coefficient is {{robustness_RB09_household_lending_coef}} (raw p {{robustness_RB09_household_lending_p_raw}}, Holm p {{robustness_RB09_household_lending_p_holm}}): the only significant factor loses significance when its non-stationarity is removed.

**Robustness is mixed.** A check "survives" when all six slope signs match the main model and the benchmark conclusion is the same. Checks that survive: {{robustness_survivor_count}} of {{robustness_check_count}} ({{robustness_survivors}}). In {{robustness_flipped_benchmark_count}} checks ({{robustness_flipped_benchmark_ids}}) the model beats Always Hold on that check's own holdout, so the negative result is itself fragile. Each check uses its own holdout, so their RMSE ratios are not directly comparable.

The largest contributions to the latest change come from {{driver_1_factor}} ({{driver_1_contribution}}), {{driver_2_factor}} ({{driver_2_contribution}}) and {{driver_3_factor}} ({{driver_3_contribution}}).

## Install
### Quick start (one command, no virtual environment)

Step 1. Open a terminal inside the project folder. The folder must contain `run.py`, `README.md`, `requirements.txt`, `src/`, `tests/` and `data/raw/`.

- Windows: open the project folder in File Explorer, click the address bar at the top, type `powershell` and press Enter. A terminal opens already in the right folder.
- VS Code (any system): File -> Open Folder -> choose the project folder, then Terminal -> New Terminal.
- macOS: right-click the folder -> New Terminal at Folder.

Check that you are in the right place: `dir` (Windows) or `ls` (macOS/Linux) must list `run.py` and `requirements.txt`.

Step 2. Run one command.

Windows PowerShell:

```powershell
py -m pip install -r requirements.txt; py run.py
```

macOS / Linux / Git Bash:

```bash
pip install -r requirements.txt && python run.py
```

The dashboard opens in the browser at http://localhost:8503. It works offline: it reads the saved CSV files in `data/`, downloads nothing and needs no API key. No virtual environment is needed, so there is nothing to activate. If `py` is not found, use `python` instead of `py`. Python 3.13 or 3.14 is recommended (3.11 or newer is required).

After the first installation you only need `py run.py` (or `python run.py`) to start the dashboard again.

### Alternative: isolated virtual environment
Tested on Python 3.14 (Windows) and 3.13 (Linux). Run from the repository root.

**Windows (PowerShell):**

<!-- install-steps:windows:start -->
```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py
```
<!-- install-steps:windows:end -->

**macOS / Linux:**

<!-- install-steps:posix:start -->
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```
<!-- install-steps:posix:end -->

Run these commands from the repository root (the folder that contains run.py), not from your home folder. Activation is not needed: the commands call the virtual-environment Python directly, so Windows' script-execution policy (the 'running scripts is disabled' error for Activate.ps1) does not apply. If `python` is not found on Windows, use `py` instead of `python` in the first line. To use the environment interactively you may activate it (`.venv\Scripts\Activate.ps1` on Windows, `source .venv/bin/activate` elsewhere), but nothing here depends on it.

## Run the site

```text
python run.py
```

This one command starts the dashboard at <http://localhost:8503> and opens a browser tab (`--port N` to change the port, `--no-browser` to stay in the terminal). `make` is optional; every Makefile target just calls `run.py`. The app only reads `data/processed/` and `model/artifact.json`; it never fits a model. When the calendar source cannot be reached within two seconds, the page shows a **CACHED DATA** label and keeps serving the local files.

## Regenerate all outputs

```text
python run.py data      # rebuild data/processed/ from data/raw/
python run.py model     # re-estimate; rewrites model/artifact.json and the annexes in outputs/
python run.py report    # tables, figures and numbers for the note, then this README
python run.py facts     # validate docs/facts_to_fill.* and regenerate SOURCES.md, provenance, card, rule, validity facts
python run.py all       # data, model, report, facts, then the tests
```

`python run.py report` writes `outputs/results_table.md`, `outputs/oos_comparison.md`, `outputs/economic_size.md`, `outputs/robustness_table_short.md`, `outputs/fig_history.png`, `outputs/fig_oos.png`, `outputs/fig_contributions.png` and `outputs/numbers_for_note.json`. Each entry in the numbers file has a `source` field that points to the artifact field it came from.

Facts that only a person can supply (publishers, URLs, retrieval dates, real release lags, the origin and status of the indicator, the named user) go into `docs/facts_to_fill.csv` and `docs/facts_to_fill.md`. `python run.py facts` validates them (dates must be `YYYY-MM-DD` and not in the future; lags must be whole days) and regenerates `data/raw/SOURCES.md`, `data/processed/provenance.json` (shown in the dashboard), `outputs/release_lag_check.md`, `docs/indicator_card.md`, `docs/decision_rule.md` and `docs/validity_facts.md`. The release-lag check compares the assumed offset in `config/release_lag.json` with the real lags; it never changes the estimation.

## Checks and tolerance

```text
python -m pip install -r requirements-dev.txt
python run.py test       # full pytest suite; tests write only to temporary folders
python run.py check      # same as python -m src.check
python run.py regression # re-estimate the main model in memory and compare it with the artifact; writes nothing
```

`python -m src.check` re-runs ingest, model and report in a temporary directory and compares the results with the committed files. It prints PASS, FAIL or WARN for each item (WARN only for results of optimizer runs that did not converge, which can differ slightly across platforms; see `docs/deviations.md`, D14): both processed panels, the headline scores, every coefficient, every number in `outputs/*.md`, every entry of `outputs/numbers_for_note.json`, the three figures (pixel by pixel), this README, and every file generated from the fact forms. Tolerances are stored in the artifact: {{tolerance_headline}} for the headline ({{tolerance_headline_name}} and the latest policy pressure score), and {{tolerance_coefficients}} for coefficients and every other number. The model uses a fixed random seed ({{seed}}), which is also recorded in the artifact.

`python run.py regression` re-fits only the main ordered logit, in memory, on the estimation sample recorded in `model/artifact.json`, and prints one PASS or FAIL line per estimate, robust standard error and p-value (and the log-likelihood) at the coefficient tolerance {{tolerance_coefficients}}; it writes nothing and exits with code 1 if any line fails.

Acceptance checks: `python -m pytest -q tests/test_acceptance.py`. Set `KZ_SKIP_CLEAN_INSTALL=1` to skip the slow fresh-venv install. The standalone scripts are `python scripts/clean_install_check.py` and `python scripts/scan_secrets.py`.

## Project structure

```text
run.py                    one entry point: site, data, model, report, check, test
src/ingest.py             raw CSVs -> data/processed/ panels
src/model.py              ordered logit, diagnostics, robustness -> model/artifact.json, outputs/annex_*
src/report.py             artifact + processed data -> note tables, figures, numbers
src/readme.py             docs/README.template.md + numbers -> README.md
src/facts.py              fact forms + numbers -> SOURCES.md, provenance.json, card, rule, validity facts
src/check.py              replication check against committed results
src/app.py                read-only Streamlit dashboard
data/raw/                 supplied source files (never edited)
data/processed/           cleaned panels used by the model and the app
model/artifact.json       fitted parameters, covariance, diagnostics, tolerances
outputs/                  generated tables, figures and annexes; outputs/legacy/ holds superseded work
config/                   decision dates, upcoming meeting calendar, assumed release lag
docs/                     fact forms, templates, indicator card, model specification, deviations, AI-use and contribution records
scripts/                  clean-install and secret-scan checks
tests/                    pytest suite, including tests/test_acceptance.py
```

## Limitations

- **Negative result against Always Hold.** The pre-specified benchmark wins on the holdout (RMSE ratio {{rmse_ratio}}; winner: {{oos_winner}}). The holdout overlaps an earlier exploratory backtest, so it is not untouched.
- **Release-lag assumption.** Factors are aligned to the month two months before each decision. Actual publication lags are unknown, so the absence of look-ahead is not verified. File update dates give only upper bounds on the lags; `outputs/release_lag_check.md` lists them and the decisions where possible look-ahead cannot be ruled out, and the Evidence tab of the site shows the same limitation. Alternative lags give: "{{robustness_RB06_name}}": {{robustness_RB06_benchmark_conclusion}} (survives {{robustness_RB06_survives}}); "{{robustness_RB07_name}}": {{robustness_RB07_benchmark_conclusion}} (survives {{robustness_RB07_survives}}).
- **Irregular decision-date sampling.** The {{n_usable}} usable observations ({{sample_usable_start}} to {{sample_usable_end}}; {{n_dropped}} dropped for missing factors) are NBK meeting dates, not equally spaced periods. Serial-correlation and unit-root tests assume regular spacing.
- **No data vintages.** The factors are current-vintage values. Revisions after each decision date are not tracked. Publisher, source title, URL, navigation path, publication and retrieval dates are recorded where known (student statement, `data/raw/SOURCES.md`); `base_rate_history.csv` comes from a table on prg.kz that cites NBK press releases. The source pages carry no series codes, so each series is identified by its title (student statement). Release lags and revision status are UNKNOWN for every file (see `TODO_HUMAN.md`). Units are recorded in `docs/facts_to_fill.csv` (student statement) and compared with the CSV column names in `docs/data_audit.md`; conflicts are reported there, not resolved. Trade is in USD and lending in KZT, so the growth rates of these series also carry exchange-rate and price effects.
- **Household lending is non-stationary.** For the transformed series, ADF does not reject a unit root (p {{unit_root_household_lending_adf_p}}) and KPSS rejects stationarity (reported p {{unit_root_household_lending_kpss_p}}, the bound of the KPSS lookup table). The one significant slope therefore rests on a series that fails both tests. Differencing it in "{{robustness_RB09_name}}" gives: survives {{robustness_RB09_survives}}; same signs {{robustness_RB09_same_signs}}; benchmark conclusion {{robustness_RB09_benchmark_conclusion}}.
- **Parameter instability.** A likelihood-ratio test of equal slopes in the earlier and later parts of the estimation sample rejects stability (p {{stability_lr_p}}; flag {{stability_lr_flag}}; {{stability_split_n_early}} and {{stability_split_n_late}} decisions; the split is recorded in the artifact).
- **Small sample.** {{n_estimation}} estimation and {{n_holdout}} holdout decisions. The holdout contains {{holdout_actual_increase_count}} increases and {{holdout_actual_decrease_count}} decreases.

## Declared borrowing

| What is reused | From | Where |
|---|---|---|
| Ordered logit estimator (`OrderedModel`) | statsmodels | `src/model.py` |
| Holm adjustment (`multipletests`), ADF and KPSS (`adfuller`, `kpss`), Ljung–Box (`acorr_ljungbox`), VIF (`variance_inflation_factor`) | statsmodels | `src/model.py` |
| Chi-square and normal distributions | SciPy | `src/model.py` |
| Data handling | pandas, NumPy | all modules |
| Dashboard and its test harness (`AppTest`) | Streamlit | `src/app.py`, `tests/` |
| Figures | matplotlib | `src/report.py` |
| Logistic regression and random forest (legacy classifier only) | scikit-learn | `src/legacy_classifier.py`, `outputs/legacy/` |
| Test runner | pytest | `tests/` |
| HC0 sandwich covariance, delta method, Brant-type proportional-odds test, Holm procedure | Standard statistical methods, implemented in this repository; bibliographic references are UNKNOWN (see `TODO_HUMAN.md`) | `src/model.py`, `src/app.py` |
| Raw data files | Derived by manual cleaning from Excel files published by the Bureau of National Statistics (stat.gov.kz) and the National Bank of Kazakhstan (nationalbank.kz), per the student; titles, URLs and dates in `data/raw/SOURCES.md`. `base_rate_history.csv` comes from a secondary table on prg.kz that cites NBK press releases; the table is not an NBK publication | `data/raw/` |
| Upcoming meeting dates | The NBK decision-making schedule page linked in `config/forecast_rounds.json` | `config/forecast_rounds.json` |
| Historical decision dates | Source UNKNOWN (see `TODO_HUMAN.md`) | `config/nbk_decision_dates.csv` |
| AI assistance | An AI coding assistant was used to write and revise code and documents; the student records the details in `docs/ai_use.md` | see `docs/ai_use.md` |

Literature references are in `docs/references.md`. Exact package versions are pinned in `requirements.txt` and recorded in the artifact. Contributions are recorded in `docs/contributions.md`.

## Legacy note (superseded classifier)

> **Legacy, not a current result.** An earlier version of this project classified decisions with logistic regression and random forest classifiers and reported their accuracy against a Hold benchmark. That work is superseded by the ordered-logit indicator above and is kept only for the record in `outputs/legacy/` (see `outputs/legacy/INDEX.md`; its metrics are in `outputs/legacy/mvp_backtest_results.json`). Do not quote it as a result of this project.
