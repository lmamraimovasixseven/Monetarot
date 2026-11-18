# Паритет: Render-приложение (src/app.py) → статичный сайт (site/)

Каждый элемент интерфейса прежнего Monetarot (Streamlit, `python run.py app`) и где он находится на статичном сайте
Decision Desk (`python run.py site`, GitHub Pages). Числа сайта берутся из блока `dashboard` в `model/artifact.json`
(`python run.py dashboard`, `src/dashboard_view.py`), который вызывает те же функции `src/app.py`; каждое число имеет
строку в `ledger/evidence_ledger.csv`. `tests/test_site.py::test_every_parity_element_is_on_the_site` читает таблицу
ниже и проверяет для каждой строки, что на странице есть элемент с указанным `id` и контрольный текст. Сайт целиком на
английском (D41), поэтому контрольные тексты — английские фразы со страницы.

Способ: **число** — готовое значение из артефакта в HTML; **JS** — пересчёт или выбор в браузере; **SVG** — график
без библиотек; **HTML** — таблица, плашка или раскрывающийся блок. Статус: **перенесено** — выглядит и работает как в
Render; **иначе** — статичная страница не может сделать то же, причина записана на странице «Methods and limits» (`methods.html#static-limits`).

Скриншоты (`python scripts/site_parity_shots.py`, нужен playwright и Google Chrome): `docs/site_parity/render_*.jpg`
(вкладки Render, раскрывающиеся блоки открыты) и `docs/site_parity/site_{1400,360}_*.jpg` (сайт на компьютере и на 360 px).

| Элемент Render | Где на сайте | Способ | Статус | Контрольный текст |
|---|---|---|---|---|
| Заголовок «NBK Base-Rate Decision Forecast» и подзаголовок | `index.html#top` | число | перенесено | NBK Base-Rate Decision Forecast |
| Метрика «Policy pressure score» с 95% полосой | `index.html#headline` | число | перенесено | Policy pressure score |
| Подпись «Direction flag» под баллом | `index.html#headline` | число | перенесено | Direction flag: |
| Метрика «Change versus previous decision» | `index.html#headline` | число | перенесено | Change versus previous decision |
| Метрика «Most likely next outcome» с подписью «calibration unverified» | `index.html#headline` | число | перенесено | conditional model estimate, calibration unverified |
| Метрика «Next scheduled decision» | `index.html#next-decision` | JS | перенесено | Next scheduled decision |
| Предупреждение об устаревших данных (прошедшее заседание не в данных) | `index.html#freshness` | JS | перенесено | Data are out of date |
| Предупреждение о скачке в сырых данных | `index.html#anomaly-warning` | число | перенесено | Check the source data |
| Блок «Unit / Period / Latest change» | `index.html#context` | число | перенесено | Unit: probability difference |
| Статус проверки календаря («CACHED DATA» / «Calendar source responded») | `methods.html#static-limits` | HTML | иначе | NBK calendar check |
| Вкладки Overview / Drivers and scenario / Evidence / Data and provenance | `methods.html#static-limits` | HTML | иначе | Tabs. |
| Заголовок «Next scheduled NBK decisions» | `index.html#round-cards` | HTML | перенесено | Next scheduled NBK decisions |
| Карточка Round 1: дата, полоски Increase / Hold / Decrease, проценты, 95% CI | `index.html#round-1` | число + JS | перенесено | Round 1 |
| Карточка Round 2 (дата не подтверждена, те же вероятности) | `index.html#round-2` | число + JS | перенесено | Second next decision |
| Подпись карточки «Latest factor data as of … calibration is unverified» | `index.html#round-1` | число | перенесено | Conditional model estimates; calibration is unverified. |
| Подпись «Both rounds use the latest available factor values …» | `index.html#rounds-caption` | число | перенесено | the probabilities are identical and only the date differs |
| Сообщение календаря («Fewer than two confirmed future decision dates …») | `index.html#rounds-message` | JS | перенесено | Fewer than two confirmed future decision dates are available. |
| Раскрывающийся блок «Why these probabilities?» | `index.html#why` | HTML | перенесено | Why these probabilities? |
| Плашка с вердиктом holdout: на главной одно предложение (RMSE, бутстреп, DM), полный абзац с эффектом обновления данных на Evidence (D42) | `index.html#verdict-box` | число | перенесено | Holdout RMSE ratio |
| Плашка «Decision rule (option …), a monitoring rule, not a forecast» (на сайте «Decision rule: … A monitoring rule, not a forecast.», D42) | `index.html#decision-rule` | число | перенесено | A monitoring rule, not a forecast. |
| График «Track record of the score» с затенённым holdout (заголовок-вывод из данных графика, D42) | `index.html#track-record` | SVG | перенесено | throughout the holdout |
| Подпись к журналу прогнозов («Forecasts logged before the decision …») | `index.html#forecast-log` | число | перенесено | Forecasts logged before the decision |
| История: базовая ставка и направление решений, подпись источника | `evidence.html#ev-history` | SVG | перенесено | Original publisher |
| Вклады факторов: три метрики «Driver», столбчатая диаграмма, таблица, подпись | `index.html#drivers` | число + SVG | перенесено | Top three drivers by absolute contribution |
| Сценарий: выбор фактора, ползунок, балл сценария с полосой, три вероятности с изменением в п.п. | `index.html#scenario` | JS | перенесено | Scenario policy pressure score |
| Итоговая плашка Evidence («Robustness results are …») | `evidence.html#ev-summary` | число | перенесено | Robustness results are |
| Таблица «Holdout comparison» с RPS и подписями | `evidence.html#ev-holdout` | HTML | перенесено | Holdout comparison |
| Сравнение с Always Hold (RMSE ratio, Winner, правило; вместо «Winner» — критерий и различимость, D42) | `evidence.html#ev-criterion` | число | перенесено | pre-specified criterion (RMSE ratio |
| Фальсификация: три правила с вердиктами (на главной, шаг 6) | `index.html#falsification` | HTML | перенесено | Not falsified |
| Фальсификация на вкладке Evidence | `evidence.html#ev-falsification` | HTML | перенесено | Falsification |
| Таблица «Diagnostics» | `evidence.html#ev-diagnostics` | HTML | перенесено | What it checks |
| Таблица «Tests that do not apply to the ordinal model» | `evidence.html#ev-na` | HTML | перенесено | Tests that do not apply to the ordinal model |
| Устойчивость: все RB-проверки из artifact.json и подпись о несравнимости | `evidence.html#ev-robustness` | HTML | перенесено | Comparable with main score |
| Раскрывающийся блок «Full results stored in artifact» (коэффициенты, ковариация, расширяющееся окно, единичные корни, структурные сдвиги, экономический размер) | `evidence.html#ev-full` | HTML | перенесено | Full results stored in artifact |
| Таблица мощности «Power: minimum detectable effects» | `evidence.html#ev-power` | HTML | перенесено | Power: minimum detectable effects |
| Раздел «Limitations» (лаги публикации, RB09, критерий 3, время спецификации, holdout, основа прогноза) | `evidence.html#ev-limitations` | число | перенесено | Limitations |
| Предупреждение о look-ahead (на главной, шаг 6) | `index.html#look-ahead` | число | перенесено | Look-ahead cannot be excluded |
| Плашка устаревания: данные на дату последнего решения | `index.html#staleness` | число | перенесено | Data as of the NBK decision of |
| «Stress tests (exploratory)»: метка и выводы | `evidence.html#ev-stress` | число | перенесено | Stress tests (exploratory) |
| Переключатель «Evaluation design» и таблица по дизайну | `evidence.html#ev-designs` | JS | перенесено | Evaluation design |
| Таблица «Next-meeting probabilities under each specification» | `evidence.html#ev-forecasts` | HTML | перенесено | Next-meeting probabilities under each specification |
| Раскрывающийся блок «Raw-data anomaly screen» | `evidence.html#ev-anomalies` | HTML | перенесено | Raw-data anomaly screen |
| Таблица происхождения данных (поля из docs/facts_to_fill.csv) | `data.html#data-provenance` | HTML | перенесено | Data and provenance |
| Таблица «Field / Value» (лаг, пользователь, календарь, окно выборки, время оценки, хеш, seed) | `data.html#data-values` | HTML | перенесено | Random seed |
| Таблица «Factor / Latest value / Model input unit» | `data.html#data-latest` | HTML | перенесено | Model input unit |
| Строка «Cached dashboard render time» | `methods.html#static-limits` | HTML | иначе | Render time |
| Сортировка таблиц щелчком по заголовку | `methods.html#static-limits` | HTML | иначе | Table sorting |
| Ссылка на интерактивную версию (Render) | `index.html#render-link` | HTML | перенесено | interactive version |
| Порог p* «with equal losses» (при равных потерях) и ползунок потерь | `index.html#step-2` | JS | перенесено | with equal losses |
| Служебные пометки о статусе решения и потерь | `methods.html#statuses` | HTML | перенесено | Statuses awaiting a person |

## Что воспроизводится иначе и почему

- **Проверка календаря.** Render при открытии запрашивает источник календаря НБ РК (2 с) и пишет «CACHED DATA», если
  он не ответил. Статичная страница не обращается к внешним адресам (требование брифа); даты раундов берутся из
  `config/forecast_rounds.json`, а ближайшие два раунда выбираются в браузере по сегодняшней дате, как
  `app.load_next_decisions`. Без JavaScript показываются раунды после последнего решения в данных.
- **Вкладки.** Четыре вкладки Render разложены по семи шагам брифа на главной и по страницам «Evidence» и
  «Data»; повторы таблиц внутри «Full results stored in artifact» не дублируются, потому что те же таблицы стоят
  выше на той же странице.
- **Время отрисовки и сортировка таблиц** относятся к серверу Streamlit и его компоненту таблиц.
- **Формат чисел в сырых таблицах** («Full results»): четыре знака после запятой; Streamlit показывает числа в своём
  формате по умолчанию.
- **Цвета.** Зелёный / синий / красный Render заменены оттенками Okabe–Ito (#009E73, #0072B2, #D55E00), различимыми
  при дальтонизме; у каждой полосы есть подпись класса и значок ▲ ■ ▼, у вердиктов — ✓ / ✗.
- **Ползунок сценария** пересчитывает вероятности и 95% полосу в браузере по коэффициентам, порогам и ковариации из
  артефакта (ordered logit и дельта-метод, `src/site_assets/app.js`); совпадение с `app.ordered_probabilities` и
  `app.score_and_delta_band` до 1e-6 проверяет `tests/test_site.py::test_scenario_slider_matches_python`. Шаг ползунка
  свободный (`step="any"`), чтобы начальное значение точно совпадало с последним значением фактора.
- **Кликабельные числа и ползунок по датам (D54)** — только на статичном сайте, в Render их нет; описание в `docs/site_interactivity.md`. Скриншоты: `docs/site_parity/site_360_index_source_window.jpg`, `site_1280_index_source_window.jpg` (окно источника), `site_360_index_slider_latest.jpg`, `site_360_index_slider_earlier.jpg`, `site_1280_index_slider_latest.jpg`, `site_1280_index_slider_earlier.jpg` (ползунок в двух положениях).
