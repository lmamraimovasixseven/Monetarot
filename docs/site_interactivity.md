# Site interactivity: clickable numbers and the date slider (D54)

Two features of the static site in `site/`. Both use plain JavaScript and SVG, load nothing from outside the site, and add no numbers: they only show values that are already in `ledger/evidence_ledger.csv` and `model/artifact.json`. Without JavaScript every page reads as before.

## Where the code is

| Part | File | What it does |
|---|---|---|
| Browser code | `src/site_assets/app.js` | The pure functions `trackReadout`, `trackValueText` and `sourceRow` sit before the first `(function () {` block, so that the tests can run them in `cscript` or Node. The source window and the slider are at the end of the immediately invoked block. |
| Styles | `src/site_assets/style.css` | The section "Clickable numbers and the source window (D54)" and "Date slider under the track-record chart (D54)". The colours are the existing palette variables. |
| Source index | `src/site_build.py`: `Ledger.page_used`, `write_source_index`, `source_index_name`, `build` | For each page, the ledger ids that the page uses are written to `site/data/sources-<page>.json`. Each file has `fields`, a table of `strings` (each repeated text stored once) and `ids` (id → indexes into `strings`, in the order of `fields`). `build` also adds `assets/app.js` to every page that has a `data-ledger` number. |
| Slider markup | `src/site_dashboard.py`: `svg_track_record`, `track_slider` | `svg_track_record` adds a hidden cursor line to the chart. `track_slider` writes the hidden slider block and a JSON block (`id="track-json"`) with the dates, scores, actual decisions, the holdout start, and the probabilities and 95% band stored for the latest decision. |
| Budget | `config/site_budget.json` | The home-page size before D54 and the allowed growth (15 KB). |
| Tests | `tests/test_site_interactivity.py` | Index coverage, values equal to the ledger, no external resources, no Cyrillic, size budget, slider logic (JS), and a browser test (Playwright, skipped without a local Chrome). |

## How it works

- **Clickable numbers.** On load, `app.js` turns every element with `data-ledger` into a focusable button, with a dotted underline and the hint "Show source". A click, Enter or Space opens the source window, which first shows the id and the value on the page. On the first click the page's index is fetched once. Then the window adds the value, source, retrieval date, transformation, script, where the number is used, and the command `python run.py trace <id>`. Esc, the Close button or a click outside closes it, and focus returns to the number. Opened from a file (`file://`), or when the fetch fails, the window says so and keeps the id, the value and the link to `data/evidence_ledger.csv`.
- **Date slider.** It sits under the track-record chart on the home page, step 3. The slider moves the cursor line to the dot of the chosen decision; the dots' `cx` values come from the chart itself. The readout shows the date, the score, the NBK decision (cut, hold, hike) and "in-sample fit" or "holdout (out of sample)". The model probabilities and the 95% band are shown only for the date for which they are stored; for every other date it says "not stored for this date". The slider sets `aria-valuetext`, and the readout is an `aria-live="polite"` region.

## How to change things

- **Texts.** The window labels are in `openPop` and `labels` in `app.js`. The slider's lines are in `showTrack` and `trackReadout`. Its label and hint are in `track_slider` in `src/site_dashboard.py`. The site is English: `python run.py site` fails if a page, asset or index file contains Cyrillic.
- **Styles.** Edit the two D54 sections of `style.css`. Keep the palette variables, so that the colours stay colour-blind safe, and keep a visible `:focus-visible` outline.
- **Rebuild.** `python run.py site`. Commit `site/` together with the source change: `test_committed_site_equals_a_fresh_build` compares them.
- **Run the checks.** `python -m pytest -q tests/test_site_interactivity.py tests/test_site.py`, then the full suite with `python -m pytest -q -k "not check_01"`, `python run.py check` and `python run.py acceptance`.

## How to add another clickable number

1. Make sure the number has a row in `ledger/evidence_ledger.csv`, written by `src/ledger.py`.
2. In the page function in `src/site_build.py`, write it with `L.num("<ledger id>", digits)`. This writes `<span class="num" data-ledger="<id>">`, records the id for the page, and the page's source index picks it up on the next `python run.py site`.
3. If the number is written by the browser, as the slider does, create a `span` with `data-ledger` and call `clickable(container)`. Also make sure the page function reads that id with `L.raw` during the build, so that the id is in the page's index. `test_slider_ids_written_by_the_script_are_in_the_home_index` shows the pattern.
4. Keep the home page within `config/site_budget.json`; anything large belongs in a file that is fetched on demand.

# Visual interactivity (D56)

Everything below is built by `python run.py site` from `src/`; never edit `site/` by hand. The Python side writes a complete static page: the chart, the list or the table. The browser side, in the D56 part of `src/site_assets/app.js`, only adds behaviour on top. Every control starts with `hidden` in the HTML and is shown by the script, so a page without JavaScript reads as before. All animations stop under `prefers-reduced-motion: reduce`. The styles are in the "D56" section of `src/site_assets/style.css`.

| Feature | Python (markup, data) | Browser (`app.js` block) | How to change |
|---|---|---|---|
| A. Score chart: crosshair tooltip, range buttons, line draw-in, class toggles, click a point for its source | `site_dashboard.svg_track_record` draws the static chart. `track_slider` writes the range and class buttons and the `track-json` block: dates, scores, actual decisions, holdout start, stored probabilities and band, and colours. | "A. Track record of the score" redraws the chart from `track-json` (`drawTrack`); its layout constants are the same as in `svg_track_record`. | Ranges: the `data-range` buttons in `track_slider` and the year arithmetic in `drawTrack`. Colours: `colors` in `track_slider`. Texts: `showTrack` and the tooltip line in `hover`. |
| B. Probability bars: grow into view, tooltip with value and CI, round 1 / round 2 side by side or overlay | `site_dashboard.round_card` (unchanged numbers); the `round-layout` buttons in `site_build.index_page` | "B. Probability bars" | Animation speed: `.probability-fill` transition in `style.css`. Overlay note: the `note` text in the B block. |
| C1. Factor effects with whiskers, sort by size or name | `site_interactive.factor_effects`: stored coefficients and HC0 standard errors from `dashboard.full_results` | "C1. Factor effects" | Whisker width: `Z95`. Labels and the title: `factor_effects`. |
| C2. Frozen against an extended model (household lending) | `site_interactive.ovb_toggle`: ids `ovb:specifications/*` from `model/extensions/ovb_check.json` | "C2. Frozen model against one extended model" | The specifications listed: `OVB_SPECS` in `site_build.py`. |
| C3. Holdout RPS bars with a click panel | `site_interactive.holdout_panel`: `n:rps_*`, `n:rmse_ratio*`, `n:dm_squared_error_p` | "C3. Click panel" | The panel text: `holdout_panel`. |
| C4. Recall per class | `site_interactive.recall_chart`: ids `classm:forecasters/*` | none; bars open the source window by click | Forecasters and classes: `CLASS_FORECASTERS` and `class_order`. |
| D. Corridor band over time with premium and cap sliders | `carry_corridor.history()` joins the monthly series that `build()` already uses; nothing is estimated. `site_interactive.corridor_band` draws the default band and writes `cb-json`. | "D. Corridor band over time" listens to `c-prem` and `c-cap`. | Slider ranges: the form in `site_build.corridor_page`. The y-axis covers caps up to 12 (`corridor_band`). |
| E. Forecast log: sort, filter, countdown | `site_build.forecasts_page`: the predicted class follows `forecast_log.score` (the most probable class); the outcome is read only from `data/processed/forecast_scores.json`, otherwise "pending". `table_filter` writes the filter box. | "E. Sortable, filterable tables" | Add `class="sortable"` and a `table_filter(...)` to any table to get the same behaviour. |
| F1/F4. Read-more cards and grouped limitation cards | `site_interactive.cardify` / `read_card`: the head is the paragraph's first sentence, or the lead-in before a colon. `limit_cards` groups the model-card limits into "Caution" and "Note" by the words in `CAUTION_WORDS`. | "F1, F4. Read-more cards" | Minimum length: `min_chars`. Grouping: `CAUTION_WORDS`. |
| F2. Pipeline diagram | `site_interactive.pipeline`; the stage texts and ledger ids are in `site_build.methods_page` (`stages`) | "F2. Pipeline" | Edit `stages`; use existing sentences and `L.num(...)` for numbers. |
| F3. Timeline | `site_build.forecast_timeline()` reads the dates from `docs/forecast_log.csv` and `prereg/freeze.json` | none | Add an event there; dates must come from files in the repository. |
| F5. Red-team cards | not built yet: the review has not taken place (`docs/redteam_response.md` still has [FILL IN]) | none | When the review is filled in, render one `read_card` per challenge in `redteam_page`. |
| F6. Glossary tooltips | `site_interactive.GLOSSARY` (one sentence per term) and `glossarize`: the first use on each page, outside headings, links, code, tables and charts | "F6. Glossary tips" keeps a tip on screen; Esc closes it | Add or edit a term in `GLOSSARY`. |
| F7. "On this page" | `site_interactive.onpage_nav`: pages with at least three h2 headings | "F7. On this page" highlights the section in view | Headings come from the page; give a new h2 an `id`, or put it in a `<section id>`. |

Checks: `python -m pytest -q tests/test_site_interactivity.py` covers the hooks, the data against the artifact, the fallbacks, LF line endings, local links, the double build and a browser smoke run, which is skipped without a local Chrome. `python scripts/site_smoke.py [shots]` repeats the browser run and, with `shots`, saves the screenshots `docs/site_parity/d56_*.jpg`.
