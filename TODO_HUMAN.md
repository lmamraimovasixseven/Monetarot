# TODO_HUMAN

Only facts that are still `UNKNOWN` or unconfirmed are listed. Do not infer or invent values. Enter series facts in `docs/facts_to_fill.csv` and project facts in `docs/facts_to_fill.md`, then run `python run.py facts`.

## Do now (added 2026-11-12, in order)

1. **Commit and push `docs/forecast_log.csv` immediately** (with `data/processed/forecast_scores.json` and `outputs/forecast_scores.md`). The forecast for 2026-12-04 was logged on 2026-11-12 from a working tree with uncommitted changes (`git_worktree` column); the GitHub commit time is the external timestamp that shows it was made before the decision. Commit the other changes of 2026-11-12 in the same push.
2. **Push the comparison tag** `before-data-update-2026-09-07` (`git push origin before-data-update-2026-09-07`) so that `python run.py compare` and the CI workflow can read the OLD version on GitHub.
3. **Approve or change the promotion rule** (K = 8 prospective decisions and the three conditions) in `docs/development_plan.md`, section (e), and record the date of your decision in its "Approval" section. Until then no candidate can be promoted.
4. **Verify the export jump at the source** (section "Found in the review of 2026-11-06" below).
5. Fill `docs/ai_use.md` and `docs/contributions.md` from your own records (questionnaire below).
6. Update the pitch and the technical note from `outputs/version_comparison.md` (OLD vs NEW, generated) and the README; do not type numbers from memory.

## Бриф «The Decision Desk» (добавлено 2026-11-13; ход работ в `docs/PROGRESS.md`)

- **Подтвердить решение и потери.** `config/decision_losses.json`: формулировка решения («казначей/портфельный менеджер с тенговыми госбумагами до 4 декабря 2026 решает, удлинять или сокращать дюрацию») и матрица потерь помечены как допущение. Подтвердите или замените, затем `python run.py decision`.

- **Интерактивный сайт (D56): проверить людям.** (1) Глоссарий: восемь определений по одному предложению написаны ассистентом (`src/site_interactive.py`, `GLOSSARY`); подтвердите или поправьте формулировки. (2) Группировка ограничений на Methods and limits на «Caution» и «Note» сделана по словам в заголовках (`CAUTION_WORDS`); проверьте, согласны ли вы с ней. (3) Страница Red-team: карточки по каждому замечанию не построены, потому что ревью ещё не было (`docs/redteam_response.md` с [FILL IN]); после ревью их можно включить (см. `docs/site_interactivity.md`, F5). (4) Бюджет начальной загрузки главной поднят до 41 КБ роста (`config/site_budget.json`); подтвердите, что это приемлемо.
- **Дата заседания 4 декабря 2026 (D53, проверено 2026-11-17).** На сайте НБ РК в «2015 – 2026 Decision Making Schedule» (https://nationalbank.kz/en/news/grafik-prinyatiya-resheniy-po-bazovoy-stavke/rubrics/2365, то же на русской странице) последняя строка — «04.12.2026*», сноска «*Base rate announcement date»; совпадает с `config/forecast_rounds.json`. Перед решением проверьте ещё раз, не перенесена ли дата, и после решения запишите дату вступления в силу в `config/nbk_decision_dates.csv` по runbook.
- **Подтвердить долю экспорта по странам-партнёрам (Россия, Китай, ЕС) из данных Бюро национальной статистики; цифра 80% не подтверждена.** В проекте и на сайте эта доля нигде не используется (D50).
- **Проверка пропущенных переменных (D50, исследовательская).** Ставка ЕЦБ по депозитам взята из ECB Data Portal (FM.D.U2.EUR.4F.KR.DFR.LEV), получено 2026-11-16; FRED ECBDFR в тот день не открылся (соединение сброшено). Дата публикации: UNKNOWN. Результаты в `model/extensions/ovb_check.json` и `outputs/ovb_check.md`; решите, нужно ли что-то из них в технической записке (только с пометкой exploratory).
- **Данные России, Китая и курсы (блок E): все семь рядов есть (D46, D47).** Исходные файлы лежат в `data/incoming/external_2026-11-15/` и `data/incoming/external_2026-11-16/` (не в git), значения перенесены в `data/raw/external/` как опубликованы, без заполнения пропусков; издатель, URL и дата получения записаны в `config/external_sources.json`.
  - Закрыто: `ru_key_rate_daily.csv` и `usd_rub_daily.csv` (Bank of Russia, cbr.ru), `ru_cpi_yoy.csv` (таблица Банка России «Инфляция и ключевая ставка»; агрегатор, ИПЦ Росстата), `usd_kzt_daily.csv` (nationalbank.kz), `usd_cny_daily.csv` (FRED DEXCHUS, H.10 ФРС: курс в Нью-Йорке, не паритет CFETS), `cn_policy_rate_daily.csv` (BIS, Central bank policy rates, ряд D.CN; файл переименован из `cn_7d_reverse_repo_daily.csv`), `cn_cpi_yoy.csv` (OECD через FRED до 2025-04, релизы NBS stats.gov.cn с 2025-05 по 2026-09).
  - **Решите: ставка Китая — это не 7-дневное обратное РЕПО.** Ряд BIS D.CN по значениям — LPR 1Y (раньше базовая ставка по кредитам), то есть ориентир кредитования со спредом, а не доходность краткосрочного размещения. Реальная ставка Китая и коридор поэтому опираются на ставку кредитования. Сейчас коридор строит нижняя граница по России (её реальная ставка выше), поэтому выбор китайской ставки на границы пока не влияет; если нужна именно ставка 7-дневного обратного РЕПО, её придётся собрать из объявлений PBoC.
  - Проверьте: даты публикации (`release`) UNKNOWN для рядов, где издатель их не указывает (у BIS в выгрузке есть только дата обновления всего набора, 2026-11-12). Два дня с пропуском в ряде BIS (2024-07-20, 2024-07-21, OBS_STATUS M) оставлены пустыми; июль 2024 усреднён по остальным дням.
  - `python run.py update` не запускался (по просьбе владельца). Блок `forecast_desk` в артефакте ещё не видит курс USD/KZT; `python run.py desk` перезапишет `ledger/forecast_ledger.csv`, поэтому запускайте его, когда решите обновить журнал прогнозов рядов. Acceptance A03 проверяет USD/KZT на копии, где `update` выполняется.
- **Источник для повышения НДС 12%→16% с 2026-01-01.** В `config/intervention_calendar.csv` источник UNKNOWN: впишите ссылку на закон или официальное сообщение и дату публикации. Причина эпизода 2020-03...2020-06 в розничной торговле тоже UNKNOWN.

- **Закоммитить `prereg/` до 2026-12-04.** Заморозка преререгистрации действительна как внешняя отметка только после push на GitHub до решения.
- **Ответ красной команде.** Заполните `docs/redteam_response.md` после ревью другой команды.

- **Включить GitHub Pages.** GitHub → Settings → Pages → Build and deployment → Source: «GitHub Actions». После следующего push workflow `pages` опубликует `site/`; ссылку на сайт впишите в README.
- **Подписать `docs/declaration.md`.** Зоны светофора заполнены (D48); открыты только подпись и дата каждой участницы (таблица в конце, [FILL IN]). Корневой `DECLARATION.md` обновится командой `python -m src.root_docs` (или `python run.py update`).

- **Что ещё не записано для светофора (D48, D49).** Ответ Дарины об использовании ИИ внесён, в зелёной зоне перечислены все три ассистента (D49). Остались: (1) подписи и даты обеих участниц в `docs/declaration.md` ([FILL IN] в таблице в конце); (2) `docs/ai_use.md`: колонка «Kept by the team» и фраза «What the team kept, rejected or verified is [FILL IN] by the team» в разделе «Claude Code sessions recorded by the assistant». После заполнения `python -m src.root_docs` обновит корневые копии.
- **Подготовка к защите.** `docs/DEFENCE_QA.md` (40 вопросов, ответы своими словами) и `docs/quiz2_sheet.md` (лист нужно понять самой; Quiz 2 без ИИ).

## Series provenance still UNKNOWN

- `base_rate_history.csv`: publication date and navigation path of the prg.kz table.
- Release lag in days (end of reference month to publication) for all seven files; without it, absence of look-ahead is not verified (`outputs/release_lag_check.md`). The single observed inflation issue date in the form is an observation, not a lag rule.
- Whether values were revised after release, for all seven files.
- For every file: which sheet, rows and columns of the downloaded Excel file were extracted into the CSV.

## Manual cleaning

- Manual cleaning steps beyond extracting years, months and the needed indicator: not documented for any file.
- `base_rate_history.csv` discrepancy: the owner reported removing duplicate months, an obsolete first header line, a blank line and a loader using `skiprows=1`; the current file starts with `year_month,rate`, has no preamble, and the referenced `src/data.py` is absent. Resolve this from the original editor or script if available.

## Decision calendar

- Source of the historical NBK decision dates in `config/nbk_decision_dates.csv` (copied from an earlier `nbk_decisions_clean.csv`; the official calendar document and its retrieval date are `UNKNOWN`).
- Retrieval date of the NBK decision-making schedule page linked in `config/forecast_rounds.json`.

## References

- Claim-level check: confirm the five abstract-level checks and the planned claims in `docs/references.md` by opening the sources, match each planned claim with the sentence in the note, and confirm the DOI of Taylor (1993) (`docs/references_TODO.md`).

## Project facts (`docs/facts_to_fill.md`)

- Week 2 indicator: instructor-suggested on 2026-10-07 at a lecture (oral, no written proof); formal approval record UNKNOWN.
- Written approval of decision-date sampling: who, when, and where the proof is.

## Student-only documents

- `docs/ai_use.md` (tools, purposes and the student's own work are recorded; still `[[TO FILL]]`): version of each tool; period of use; the person responsible for checking AI output; per tool (A01–A04) the dates, the files it produced, the exact prompts or export links, what was suggested, what was accepted, rejected or rewritten, and the human verification; who wrote the other files in `docs/`; the rejected or rewritten suggestions; and the signed, dated statement. Fill these from your own records only.
- `docs/contributions.md`: names, roles, contributions, signatures and dates, or a statement of individual work.

### Questionnaire for `docs/ai_use.md` and `docs/contributions.md` (answer from your own records only)

The assistant did not write or change either file. Both already contain your earlier text; the table in `docs/ai_use.md` stops at 2026-10-19 and does not cover the review changes of 2026-11-06 (D16–D18) or the data update of 2026-11-09/10 (D19 onward). Answer each question in your own words; where you have no record, write UNKNOWN.

1. **Tools and versions.** For each AI tool (Codex, GitHub Copilot agent mode, Claude Code in VS Code, Claude chat, and any other): the exact product name and version or model, and the period of use (first and last date).
2. **Who made the changes of 2026-11-06.** Which tool or person wrote `src/robust_eval.py`, the dashboard additions and D16–D18? On which date? Where are the prompts or the session export?
3a. **Who made the changes of 2026-11-12 (D27–D31: release-lag edition rule, data-contract tests, jump screen in the data step, `run.py needs`/`compare`/`forecast-log`/`forecast-score`, CI workflow, runbook, development plan, verdict wording, the forecast logged for 2026-12-04).** Which tool, which prompt (paste or link it), and what did you decide yourself (for example: not supplying the trade dates, accepting the generated verdict wording, the promotion rule)?
3. **Who made the changes of 2026-11-09/10.** For the data update (D19–D26): which tool did it, which prompts did you give (paste or link them), and what did you decide yourself? Examples: authorizing the appends to `data/raw/`, supplying the Excel files, keeping the forecast basis (D21).
4. **What you wrote yourselves.** List the files, sections or sentences each of you wrote without AI. List the parts of the technical note and the pitch deck you wrote.
5. **What you checked.** For each AI-produced part you rely on, who checked it, how (re-ran, compared with the source, read the code), and on which date. In particular: the 2026-08 trade values against the Excel files; the NBK dates in `docs/nbk_announcement_dates.csv` against the NBK pages; the OLD vs NEW comparison table.
6. **What you rejected or rewrote.** AI suggestions you did not accept or changed substantially, with the reason.
7. **What you understand.** For each component (data pipeline, ordered logit and its diagnostics, Holm adjustment, bootstrap and Diebold–Mariano, RPS, the robustness checks, the dashboard), can each of you explain it without help? Name anything you cannot yet explain.
8. **Contributions.** Each person's role and contributions after 2026-10-18. The approximate share is filled (Linara Mamraimova 60%, Darina Baikazakova 40%; D48).
9. **Signed statement.** Date and sign the statement in `docs/ai_use.md` once the answers above are in.

## Found in the review of 2026-11-06

- **October decision added (done 2026-11-10).** The decision announced 2026-10-23 and effective 2026-10-27 (15.75%, confirmed on nationalbank.kz; see `docs/nbk_announcement_dates.csv` and `docs/manual_steps_found.md`) is in `config/nbk_decision_dates.csv` and `data/raw/base_rate_history.csv`, and the 2026-08 trade values it needs were appended from the files in `data/incoming/` (D22). The forecast for 2026-12-04 keeps using the latest decision's factors (D21); the 2026-10 factor values were skipped on the owner's instruction and remain UNKNOWN in `data/raw/`.
- **Check `export_history.csv`, 2026-06 and 2026-07.** Exports jump from 6,276,443.18 (2026-05) to 9,816,470.38 (2026-06) thousand USD (+56% in one month), and 2026-07 stays at 10,169,912.74; it is the largest monthly change in the file and the site keeps its anomaly warning. The values in the CSV were not changed. What is already established (2026-11-10, from the export file you put in `data/incoming/`, see `docs/manual_steps_found.md`): that edition shows the same jump (sheet «январь-август 2026г.», row 4 «Республики Казахстан»: May R4 = 6,275,164.49, June U4 = 9,820,130.49, July X4 = 10,175,921.46), and its eight monthly cells sum to the «январь-август 2026 года*» total in sheet «Показатель», so the values are monthly, not cumulative. What you still must check yourself:
  1. Open the publisher source recorded in `docs/facts_to_fill.csv` (https://stat.gov.kz/api/iblock/element/446905/file/ru/, Bureau of National Statistics, «Товарооборот в иностранной валюте (экспорт)»), sheet «январь-август 2026г.» (or the latest monthly sheet), row «Республики Казахстан», the «тыс.долларов США» column under «май 2026 года*», «июнь 2026 года*», «июль 2026 года*».
  2. Compare these three cells with `data/raw/export_history.csv` rows 2026-05, 2026-06, 2026-07 (differences of a few tenths of a percent are revisions between editions; a difference of tens of percent is an entry error).
  3. Check that the jump is economic, not a coding artefact: in the same sheet, sort the June 2026 commodity rows (columns S–U) by «тыс.долларов США» and compare the largest items with May (columns P–R); note which commodity code accounts for the increase. Optionally compare with a second publication of the same indicator (the Taldau link in sheet «Метаданные»: https://taldau.stat.gov.kz/ru/NewIndex/GetIndex/2972493).
  4. Also compare 2026-08 (column AA of the same sheet) with `data/raw/export_history.csv` row 2026-08. Factually, the three months after the jump (2026-06, 2026-07, 2026-08) all stay at the higher level in the CSV, so the change may be a level shift rather than a single-month typo; this does not establish that the values are correct. The jump screen (`outputs/data_anomalies.md`, regenerated by `python run.py data`) flags 2026-06 and marks that it enters the latest score.
  5. Write the result, the date you checked and the edition date («Дата последней актуализации» in sheet «Метаданные») in the `notes` of the `export_history.csv` row of `docs/facts_to_fill.csv`, then run `python run.py facts`. Do not change the CSV values: `data/raw/` is append-only; if a value is wrong, record it here and in `docs/deviations.md` and decide with the instructor how to handle it.
- **Provenance of the newer trade edition (2026-08 rows): UNKNOWN.** Asked on 2026-11-12; no dates were supplied, so they stay UNKNOWN. In `docs/facts_to_fill.csv`, `publication_date` 2026-10-05 and `retrieval_date` 2026-10-08 of `export_history.csv` and `import_history.csv` describe the earlier download (last month 2026-07); the notes now say "Publication date refers to the edition ending 2026-07.", and `python run.py facts` computes the upper bound from that edition's last month (D27). Still UNKNOWN: the update date shown on the stat.gov.kz page for element 446905 (exports) and element 446906 (imports) for the edition that contains 2026-08, and the date you downloaded the two files now in `data/incoming/`. The files' own sheet «Метаданные» says «Дата последней актуализации» 2026-10-15. If you confirm the page dates, update `publication_date`/`retrieval_date` and the notes of both rows, remove the "edition ending" sentence, and run `python run.py facts`.
- **Download URL and download date of the two Excel files in `data/incoming/`** (export and import, used for the 2026-08 rows): UNKNOWN. Record them in `docs/manual_steps_found.md` (section "Trade rows for 2026-08").
- **Announcement dates of nine early-month decisions: UNKNOWN.** 2015-10-02, 2016-02-02, 2016-10-04, 2018-06-05, 2018-09-04, 2018-12-05, 2019-03-05, 2019-06-04, 2020-02-04 took effect on day 1–5 of a month; whether the announcement fell in the previous month was not checked. If you check them, add rows (with the press-release link) to `docs/nbk_announcement_dates.csv` and run `python run.py all`.
- **Decision dates are effective dates, not announcement dates (decided: effective date kept; `docs/model_spec.md`, D20).** Most dates in `config/nbk_decision_dates.csv` are the Monday/Tuesday on which a decision took effect; the NBK announces on the preceding Friday (`config/forecast_rounds.json` uses announcement dates). For 2024-06-03, 2024-09-02, 2024-12-02, 2025-09-02 and 2025-12-01 (the fifth found on 2026-11-10) the announcement fell in the previous calendar month, so the "decision month minus two" rule uses a factor month one month later than was known at the announcement. Remaining for you: confirm that you accept the effective-date choice as written in `docs/model_spec.md`.
- **Second jump-screen flag in the latest inputs.** `outputs/data_anomalies.md` also flags `import_history.csv` 2026-01 as entering the latest score; the CSV shows a similar January drop in several earlier years (2016, 2020, 2021, 2022), so it may be seasonal. Check it against the publisher like the export jump if you rely on the latest score.
- **Calendar.** `config/forecast_rounds.json` still lists 2026-10-23, which has passed (the dashboard ignores past dates, so 2026-12-04 is shown as the next decision). The NBK schedule page checked on 2026-11-09 lists no 2027 dates, so the second next decision date is UNKNOWN; add it once the NBK publishes the 2027 schedule.

- **Render address of the interactive version: done (2026-11-14).** The owner gave https://monetarot.onrender.com/; it is recorded in `config/site_links.json` (`render_url`), the home page link "интерактивная версия" and README point to it.

## Site design (D57)

- **Source of the Muted Steel colour `#8FA3B8`: UNKNOWN.** The D57 brief says it was read from a PDF; no PDF with the palette is in the repository, so the hex was used as given (it passes WCAG AA: 6.72:1 on `#101A2B`, 5.73:1 on `#19283D`). If you have the source, check the hex against it and, if it differs, change `--steel` in `src/site_assets/style.css` and `PALETTE["black"]` in `src/site_dashboard.py` as described in `docs/site_design.md`, then run `python run.py site` and the tests.

## Site design (D58)

- **Muted Steel `#8FA3B8` (the D57 item above) is no longer used on the site.** D58 replaced the D57 palette with the Hallmark Editorial theme. The question of its source only matters if the dark theme comes back.
- **Bricolage Grotesque has no release tag.** The font was downloaded from the repository `ateliertriay/bricolage` at commit `8070cdb6a383aafd10792111cd94e4d472aa0f0c` (URL and sha256 in `docs/site_design.md`). If a tagged release appears, decide whether to switch to it.

## Partner rates page (D59)

- **Check the 2025 export shares against the final BNS table.** The shares in `data/raw/external/kz_export_shares_2025.csv` come from the primary BNS release of 16.02.2026 (Italy 19.8, China 19.2, Russia 10.3, Netherlands 7.6, Turkiye 4.9, Uzbekistan 4.5; total exports 79041.2 million US dollars), whose 2025 figures are marked preliminary.
  1. When the final 2025 table is published, open it on https://stat.gov.kz/en/industries/economy/foreign-market/spreadsheets/ (or the release list on the publications page).
  2. Compare the six shares and the total.
  3. If the full country table is available, note the euro-area total; it can then be added from that table only (not mixed with other sources).

  The secondary report (The Astana Times, 13 April 2026, https://astanatimes.com/2026/04/kazakhstans-top-10-export-partners-account-for-nearly-80-of-trade-in-2025/ and https://astanatimes.com/2026/04/kazakhstans-foreign-trade-in-2025-partners-and-trends/) gives a top-ten total that is not in the primary release; it is not used.
- **Publication dates of the external series: UNKNOWN.** `config/external_sources.json` gives `release` as UNKNOWN for the Bank of Russia key rate and CPI, the China policy rate (BIS gives only the dataset update date), the FRED part of the China CPI, the ECB deposit rate and the exchange rates. The partner-rates page shows the stored dates of the last values, not publication dates. If you can find the publication date of each series (or of the edition used), record it in the `release` field and run `python run.py ledger` and `python run.py site`.

## Home page story (D60): copy to approve

The sentences below are new on the home page and appear under our names; nothing else on the page changed. They are generated from stored values; the figures shown are today's ledger values. Approve or reword them; to reword one, change it in `src/site_build.py` (`index_page`, `CONNECTORS`) and run `python run.py site`.

- **Answer under the question:** "Most likely the NBK holds: hold 53.2%, cut 38.7%, hike 8.1%."
- **Step 1:** "Before 4 December 2026 a bond holder must decide whether to extend duration, under our stated loss assumption of 1.0 unit for a wrong call either way." The loss values in `config/decision_losses.json` are still not confirmed; the item "Подтвердить решение и потери" above stays open.
- **Step 2:** "Hold is most likely, but a cut is not ruled out: its 95% interval runs from 4.2% to 73.2%."
- **Step 3:** "The pressure score is -0.306, and its 95% band from -0.747 to +0.136 includes zero."
- **Step 4:** "On past decisions the model cannot be distinguished from simply predicting a hold."
- **Step 5:** "All six factors push the score towards a cut, household and corporate lending most; move one to see how far the score shifts." (the first part is the existing chart title).
- **Step 6:** "Look-ahead cannot be excluded: real publication lags are not documented." (existing sentence, now also the headline).
- **Step 7:** "Do not extend duration; the forecast was logged on 12 November 2026, and the NBK decision on 4 December 2026 is the next outcome it will be scored against."
- **Connectors:** "So what does the model expect?" / "But why is the model not more certain?" / "So can we trust it?" / "So what is behind the score, and what would change it?" / "And what could make it wrong?" / "So what should the holder do, and how will we know?"
- **Closing section heading:** "Read further". **Rail counter:** "Step n of 7".

## Home page Story view (D61): copy to approve

The sentences below are new on the home page and appear under our names; they are generated from stored values, and the figures shown are today's ledger values. Approve or reword them in `src/site_build.py` (`STORY_SCENE`, the `plain` list in `index_page`, `DETAILS_LABELS`, `VIEW_SWITCH`), then run `python run.py site`.

- **Opening scene:** "You hold tenge government bonds. Before the NBK decision named in the question, you must choose whether to extend duration. This page walks through what the model says, how sure it is, and what would change the answer."
- **Step 1:** "Under this assumption, you extend duration only if the probability of a cut is above 50.0%."
- **Step 2:** "A cut has a probability of 38.7%, below that threshold, so for now the rule says: do not extend duration." (Above the threshold: "above that threshold, so for now the rule says: extend duration.")
- **Step 3:** "In plain words: the score points towards a cut, but its band reaches past zero, so the direction is not clear." (Band clear of zero: "and its band stays on that side of zero."; score exactly zero: "the score sits at zero, so the direction is not clear.")
- **Step 4:** "On past decisions, you could not tell its errors apart from those of always assuming no change."
  - If the two checks disagree: "On past decisions, the two checks disagree on whether its errors differ from those of always assuming no change."
  - If both separate the model: "On past decisions, both checks tell its errors apart from those of always assuming no change."
- **Step 5:** "Moving a slider shows how far the score would shift if one input changed; it does not show what will happen."
- **Step 6:** "Read every number on this page with the limits in mind."
- **Step 7:** "For you, this means not extending duration now; the logged forecast will be compared with the next NBK decision." (When the rule says extend: "extending duration now"; with no log entry the second clause is dropped.)
- **Controls:** "Story view" / "Full view"; "Show all details for this step" / "Hide the details of this step" ("section" in the opening section).
