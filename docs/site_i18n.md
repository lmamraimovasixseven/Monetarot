# Английский сайт: откуда приходил русский текст и как он переводится (D41)

Сайт `site/` (`python run.py site`, `src/site_build.py`) целиком на английском. Русские документы вне сайта (docs/,
DEFENCE_QA, шаблоны, TODO_HUMAN.md) не менялись. Часть строк, которые сайт показывает, русская в источнике: она лежит в
`model/artifact.json` или в сгенерированных документах. Их хеши и содержимое связаны с `docs/forecast_log.csv`, prereg и
проверками append-only, поэтому источники не трогаются: сайт переводит такие строки при сборке через `src/site_i18n.py`.

Как работает `src/site_i18n.py::tr`:
1. точная фраза из словаря `PHRASES`;
2. шаблон (`PATTERNS`): строка должна совпасть целиком, группы (числа, даты, имена файлов) переносятся как есть или
   переводятся рекурсивно, поэтому перевод не ломается при обновлении данных;
3. фрагменты (`FRAGMENTS`): названия источников, пути навигации и заголовки колонок в кавычках внутри английского текста;
4. если кириллица осталась, `UntranslatedError` с текстом строки: `python run.py site` падает и не публикует русский
   текст. Нужно добавить фразу или шаблон в `src/site_i18n.py`.

После сборки `assert_no_cyrillic` проверяет каждую страницу и каждый файл в `site/assets/`. Тест
`tests/test_site.py::test_site_is_english_without_cyrillic` повторяет проверку по закоммиченному сайту; список
разрешённых имён собственных в кириллице (`ALLOWED_CYRILLIC`) пуст. Файлы данных в `site/data/` не проверяются и не
меняются.

## Источники русских строк

| Источник строки | Файл | Как попадает на сайт | Как переведено |
|---|---|---|---|
| Заголовки, шаги, подписи, меню, `<title>`, `aria-label`, подвал, тексты страниц Methods and limits, Run it yourself, Sources, Team, Data, Patterns, Corridor, Forecast log, As-of view, Evidence | `src/site_build.py` | HTML-шаблоны страниц | переписаны на английском в коде |
| Ссылка на журнал прогнозов под карточками, текстовые ячейки таблиц | `src/site_dashboard.py` | HTML главной и Evidence | ссылка переписана; текстовые ячейки через `tr` |
| Текст ползунка потерь, вывод коридора, ключи партнёров, комментарии | `src/site_assets/app.js` | `site/assets/app.js` | переписаны на английском |
| Подписи положения в коридоре | `src/site_assets/corridor.js` | `site/assets/corridor.js` | английские версии меток `src/carry_corridor.py`; совпадение `tr(метка Python)` проверяет `tests/test_carry_corridor.py` |
| Комментарии стилей | `src/site_assets/style.css` | `site/assets/style.css` | переписаны на английском |
| `decision.decision`, `decision_status`, `loss_status` | `model/artifact.json` (из `config/decision_losses.json`, `src/decision_rule.py`) | шаг 1 главной, статусы на methods.html | `PATTERNS` (дата из текста) и `PHRASES` |
| `reality_check.target` | `model/artifact.json` (`src/forecast_desk.py`) | дата в шаге 4 | дата берётся из строки регулярным выражением |
| `carry_corridor`: `partner_notes`, `current.status`, `fx_regression.status`, `credit_constraint.note`, `benchmark`, `panel_note`, `defaults_status`, ключи «Россия»/«Китай» | `model/artifact.json` (`src/carry_corridor.py`) | corridor.html | `PHRASES`, шаблоны «месяц …», «мало наблюдений (N)» |
| `patterns`: вердикты сезонности, `transform`, причины выбросов, `action`, метка as-of | `model/artifact.json` (`src/patterns.py`, `src/vintages.py`) | patterns.html, asof.html | `PHRASES` и шаблоны причин с числом месяцев и процентом |
| `dashboard.provenance.series`: названия источников, пути навигации, заголовки колонок | `model/artifact.json` (из `docs/facts_to_fill.csv`) | data.html | `FRAGMENTS`; под таблицей сказано, что названия даны в переводе, оригинал в `docs/facts_to_fill.csv` |
| Пределы модели (заголовок и текст) | `src/model_card.py::limits` | шаг 6 главной, methods.html | `PHRASES` и шаблоны с числами |
| Decision memo | `docs/decision_memo.md` (`src/decision_rule.py`) | methods.html | построчно через `md_to_html` → `tr` |
| Решения по методам (окно STL) | `docs/DECISIONS.md` (`src/patterns.py`) | patterns.html | построчно, шаблоны «окно N» и абзаца |
| Аудит данных по рядам | `docs/DATA.md` (`src/data_doc.py`) | sources.html | построчно, шаблоны пунктов «Покрытие / Определение / Источник …» |
| Издатели и URL внешних рядов | `config/external_sources.json` | sources.html, таблица «Corridor sources» | `PHRASES` |
| Ответ красной команде | `docs/redteam_response.md` (шаблон, заполняет человек) | redteam.html | `PHRASES`; если человек впишет пункты по-русски, сборка упадёт и попросит перевод |
| Состав команды | `docs/contributions.md` | team.html | уже на английском |

## Что не переводится

Числа, даты, имена рядов и файлов, команды и идентификаторы журнала доказательств. Даты на сайте — ISO (`2026-12-04`)
или «4 December 2026»; десятичный разделитель — точка.
