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
