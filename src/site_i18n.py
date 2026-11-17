"""English layer of the static site (D41).

The site is English, but some of the text it shows is Russian at the source: strings stored in model/artifact.json
(blocks decision, reality_check, carry_corridor, patterns, dashboard provenance), strings returned by
src/model_card.py, and the generated documents docs/decision_memo.md, docs/DECISIONS.md, docs/DATA.md and
docs/redteam_response.md. Changing those sources would change the artifact hash recorded in docs/forecast_log.csv and
the frozen documents, so they stay as they are and the site translates them here while it writes HTML.

`tr(text)` returns the English text: an exact phrase, then a pattern whose groups (numbers, dates, file names) are
copied unchanged or translated recursively, then known fragments (source titles, navigation paths, quoted column
headers). If Cyrillic is left, it raises UntranslatedError naming the string, so `python run.py site` fails instead of
publishing Russian text; add the phrase or pattern below. `assert_no_cyrillic` is the final check on every written file.
"""

from __future__ import annotations

import re

CYRILLIC = re.compile("[Ѐ-ӿ]")


class UntranslatedError(ValueError):
    """Russian text reached the site without an English entry in src/site_i18n.py."""


MONTHS = {"января": "January", "февраля": "February", "марта": "March", "апреля": "April", "мая": "May", "июня": "June",
          "июля": "July", "августа": "August", "сентября": "September", "октября": "October", "ноября": "November",
          "декабря": "December"}

PHRASES: dict[str, str] = {
    **MONTHS,
    # decision block (config/decision_losses.json → artifact) and decision memo words
    "ждёт подтверждения человека": "awaiting confirmation by a person",
    "ДОПУЩЕНИЕ ПОЛЬЗОВАТЕЛЯ: значения потерь не подтверждены человеком (см. TODO_HUMAN.md)":
        "USER ASSUMPTION: the loss values are not confirmed by a person (see TODO_HUMAN.md)",
    "удлинить": "extend", "не удлинять": "do not extend",
    "удлинить дюрацию": "extend duration", "оставить дюрацию": "keep duration", "сократить дюрацию": "shorten duration",
    "меньше, чем у Always Hold": "lower than those of Always Hold",
    "не меньше, чем у Always Hold": "not lower than those of Always Hold",
    "- **Without you (без нас):** пользователь смотрит на текущую ставку и заявления НБ РК и по умолчанию считает, что "
    "ставка не изменится (Always Hold). Это и есть наш бенчмарк.":
        "- **Without you:** the user looks at the current rate and the NBK's statements and by default assumes that the "
        "rate will not change (Always Hold). That is our benchmark.",
    "- **Change (что меняется):** модель даёт вероятности снижения, сохранения и повышения ставки и переводит их в "
    "действие с дюрацией через явную функцию потерь.":
        "- **Change:** the model gives the probabilities of a cut, a hold and a hike and turns them into a duration "
        "action through an explicit loss function.",
    "- **Who benefits (кому выгодно):** держатели тенговых госбумаг (казначейства банков, портфельные управляющие); они "
    "видят не только вероятность, но и порог, при котором стоит действовать.":
        "- **Who benefits:** holders of tenge government bonds (bank treasuries, portfolio managers); they see not only "
        "the probability but also the threshold at which acting is worthwhile.",
    "## Порог из функции потерь": "## Threshold from the loss function",
    "Трёхисходное правило (ожидаемые потери, усл. ед.):": "Three-outcome rule (expected losses, notional units):",
    "Действие": "Action", "Ожидаемые потери": "Expected loss",
    "## Чувствительность порога к соотношению потерь": "## Sensitivity of the threshold to the loss ratio",
    "Чем дороже упущенное снижение по сравнению с ложным удлинением, тем ниже порог.":
        "The more a missed cut costs relative to a false extension, the lower the threshold.",
    # src/model_card.py::limits
    "Модель не отличима от Always Hold": "The model cannot be told apart from Always Hold",
    "Отличие от Always Hold по интервалу или тесту": "The interval or the test separates the model from Always Hold",
    "Сравнение с Always Hold: UNKNOWN": "Comparison with Always Hold: UNKNOWN",
    "Сравнение с частотами классов (RPS, дополнительная мера)": "Comparison with class frequencies (RPS, supplementary measure)",
    "Параметры нестабильны": "The parameters are unstable",
    "Стабильность параметров": "Parameter stability",
    "Holdout не нетронутый": "The holdout is not untouched",
    "Holdout частично просматривался в ранних запусках; преререгистрации до анализа не было (D15); по-настоящему вне "
    "выборки только прогнозы из docs/forecast_log.csv.":
        "The holdout was partly seen in early runs, and there was no preregistration before the analysis (D15); only "
        "the forecasts in docs/forecast_log.csv are truly out of sample.",
    "Задержки публикации не проверены": "Publication lags are not verified",
    "Реальные лаги публикации UNKNOWN; принято «месяц решения минус 2». Винтажей нет: бэктесты рядов — revised-data.":
        "Real publication lags: UNKNOWN; the model assumes \"decision month minus 2\". There are no data vintages, so "
        "the series backtests use revised data.",
    "Названный прошлый провал": "A named past failure",
    "UNKNOWN (outputs/legacy/mvp_backtest_results.json отсутствует)": "UNKNOWN (outputs/legacy/mvp_backtest_results.json is missing)",
    # carry_corridor block
    "UNKNOWN: данных нет (шаблон)": "UNKNOWN: no data (template file only)",
    "UNKNOWN: ряды ставки и инфляции не пересекаются": "UNKNOWN: the rate and inflation series do not overlap",
    "допущение пользователя (параметры ползунков)": "user assumption (slider settings)",
    "описательное соотношение, не причинная оценка; ограничение используется":
        "a descriptive relation, not a causal estimate; the constraint is used",
    "наклон не отрицательный: ограничение по кредиту не идентифицировано и не используется":
        "the slope is not negative, so the credit constraint is not identified and is not used",
    "UNKNOWN: нет реальных ставок партнёров": "UNKNOWN: no data for partner real rates",
    "UNKNOWN: нет данных USD/KZT и реальных ставок партнёров (TODO_HUMAN.md)":
        "UNKNOWN: no data for USD/KZT or partner real rates (TODO_HUMAN.md)",
    "связь значима на 5% (HC1)": "the relation is significant at 5% (HC1)",
    "связи не видно (p ≥ 0.05, HC1)": "no relation is visible (p ≥ 0.05, HC1)",
    "Панель по трём странам с фиксированными эффектами — только иллюстрация: три единицы не дают надёжных стандартных "
    "ошибок; строится, когда есть данные.":
        "A three-country panel with fixed effects is an illustration only: three units do not give reliable standard "
        "errors. It is built when the data are available.",
    "курс как случайное блуждание (прогноз изменения = 0)": "the exchange rate as a random walk (forecast change = 0)",
    "Россия": "Russia", "Китай": "China",
    "коридор сломан: нижняя граница выше верхней": "corridor broken: the lower bound is above the upper bound",
    "ниже коридора: риск оттока в carry trade": "below the corridor: risk of outflows into the carry trade",
    "выше коридора: риск избыточного притока и вреда кредиту": "above the corridor: risk of excessive inflows and harm to credit",
    "внутри коридора": "inside the corridor",
    # patterns block and docs/DECISIONS.md
    "да": "yes", "нет": "no", "нестабильно": "unstable", "слабо": "weak",
    "m/m: 100*diff(log) для уровней, первая разность для ставок": "m/m: 100*diff(log) for levels, first difference for rates",
    "тот же календарный месяц помечен в ≥ 3 годах": "the same calendar month is flagged in 3 or more years",
    "после флага нет наблюдений: тип пока не определён (помечен как одиночный)":
        "no observations after the flag, so the type is not yet known (marked as single)",
    "помечено, не удалено": "flagged, not removed",
    "revised-data backtest (текущие значения; доступность по допущению о публикации, не по реальным винтажам)":
        "revised-data backtest (current values; availability follows the publication-lag assumption, not real vintages)",
    "# Решения по методам": "# Method decisions",
    "## Окно STL по ревизиям последней точки": "## STL window chosen by revisions of the last point",
    "Ряд": "Series", "выбрано": "chosen",
    # docs/DATA.md (src/data_doc.py)
    "# Аудит данных по рядам": "# Data audit by series",
    "Каждый ряд: покрытие, пропуски, ревизии, определение, смены классификации, календарные особенности. Числа посчитаны "
    "из файлов; известные свойства взяты из документов проекта (ссылки в тексте). Значения в data/raw никогда не "
    "меняются; флаги только помечают.":
        "For each series: coverage, gaps, revisions, definition, classification changes and calendar features. The "
        "numbers are computed from the files; known properties come from the project documents (references in the "
        "text). Values in data/raw are never changed; flags only mark them.",
    "- Смены классификации: UNKNOWN (в документах источника не проверялись).":
        "- Classification changes: UNKNOWN (not checked in the source documents).",
    "Ставка после решения, вступившего в силу в этом месяце; строки до 2026-09 из таблицы prg.kz, 2026-10 со страницы "
    "НБ РК (docs/manual_steps_found.md).":
        "Rate after the decision that took effect in this month; rows up to 2026-09 from the prg.kz table, 2026-10 from "
        "the NBK page (docs/manual_steps_found.md).",
    "Решения вступают в силу в понедельник/вторник после объявления в пятницу; в 5 случаях объявление в предыдущем "
    "месяце (docs/model_spec.md, D20).":
        "Decisions take effect on the Monday or Tuesday after a Friday announcement; in 5 cases the announcement fell "
        "in the previous month (docs/model_spec.md, D20).",
    "Годовая инфляция ИПЦ, % (y/y); месячной m/m в проекте нет.": "Annual CPI inflation, % (y/y); the project has no monthly m/m series.",
    "НДС 12%→16% с 2026-01-01 (config/intervention_calendar.csv) даёт сдвиг уровня цен в январе 2026.":
        "VAT 12%→16% from 2026-01-01 (config/intervention_calendar.csv) shifts the price level in January 2026.",
    "Индекс физического объёма розничной торговли, y/y %.": "Physical volume index of retail trade, y/y %.",
    "Эпизод 2020-03...2020-06 (резкое падение и восстановление) помечен как временный.":
        "The 2020-03...2020-06 episode (sharp fall and recovery) is flagged as temporary.",
    "Экспорт, тыс. долл. США, месячные значения (проверено по итогу «январь-август»); ряд смешивает два издания: строки "
    "до 2026-07 и строка 2026-08 из более нового издания (D22).":
        "Exports, thousand US dollars, monthly values (checked against the January–August total); the series mixes two "
        "editions: rows up to 2026-07 and the 2026-08 row from a newer edition (D22).",
    "Скачок 2026-06 на новый уровень помечен; проверка по источнику ждёт человека.":
        "The 2026-06 jump to a new level is flagged; a check against the source is waiting for a person.",
    "Импорт, тыс. долл. США; два издания, как у экспорта (D22); новое издание пересматривает 2026-01...2026-07 на "
    "+0.01%...+1.34% (docs/manual_steps_found.md).":
        "Imports, thousand US dollars; two editions, as for exports (D22); the newer edition revises 2026-01...2026-07 "
        "by +0.01%...+1.34% (docs/manual_steps_found.md).",
    "Январское падение повторяется по годам: сезонный разрыв, не ошибка.":
        "The January drop repeats across years: a seasonal break, not an error.",
    "Кредиты физлицам, млн тенге (остатки на конец месяца по файлу НБ РК).":
        "Loans to individuals, million tenge (end-of-month stocks from the NBK file).",
    "Ряд нестационарен (ADF и KPSS, outputs/annex_unit_roots.csv).": "The series is non-stationary (ADF and KPSS, outputs/annex_unit_roots.csv).",
    "Кредиты юрлицам, млн тенге.": "Loans to legal entities, million tenge.",
    "Резкие изменения 2015-06, 2015-08, 2019-01 помечены экраном.": "Sharp changes in 2015-06, 2015-08 and 2019-01 are flagged by the screen.",
    "## Новые источники (блок E)": "## New sources (block E)",
    "Файл": "File", "Статус": "Status", "Обрабатываемая особенность": "Handled feature",
    "UNKNOWN: только шаблон (TODO_HUMAN.md)": "UNKNOWN: template only (TODO_HUMAN.md)",
    # docs/DATA.md, external sources with real data (D46)
    "значение на каждый рабочий день, ставка меняется внутри месяца → средняя по календарным дням, выходные берут последний "
    "рабочий день (external_data.monthly_step_rate)":
        "a value for every working day; the rate changes within the month → mean over calendar days, weekends take the last "
        "working day (external_data.monthly_step_rate)",
    "таблица Банка России даёт y/y в процентах; если бы пришёл индекс «тот же месяц прошлого года = 100», вычиталось бы 100 "
    "(external_data.cpi_yoy)":
        "the Bank of Russia table gives y/y in percent; an index with the same month of the previous year = 100 would have 100 "
        "subtracted (external_data.cpi_yoy)",
    "y/y в процентах (FRED); январь/февраль смещаются Новым годом по лунному календарю → флаг lunar_new_year_month":
        "y/y in percent (FRED); January and February shift with the lunar New Year → flag lunar_new_year_month",
    "отчёт НБ РК даёт значение на каждый календарный день (в выходные повторяется последний курс) → среднее по опубликованным "
    "дням, без заполнения пропусков":
        "the NBK report gives a value for every calendar day (weekends repeat the last rate) → mean over the published days, "
        "gaps are not filled",
    "курс Банка России публикуется по рабочим дням РФ → среднее по опубликованным дням; дни не выравниваются с USD/KZT":
        "the Bank of Russia rate is published on Russian working days → mean over the published days; days are not aligned "
        "with USD/KZT",
    "ECB Data Portal даёт значение на каждый календарный день → средняя по календарным дням (external_data.monthly_step_rate); только контроль в исследовательской проверке пропущенных переменных (D50), не в коридоре":
        "the ECB Data Portal gives a value for every calendar day → mean over the calendar days (external_data.monthly_step_rate); used only as a control in the exploratory omitted-variable check (D50), not in the corridor",
    "BIS даёт значение на каждый календарный день; пропуск (OBS_STATUS M) записан пустым и остаётся пропуском → средняя по "
    "календарным дням с значением (external_data.monthly_step_rate)":
        "BIS gives a value for every calendar day; a gap (OBS_STATUS M) is written empty and stays a gap → mean over the calendar "
        "days with a value (external_data.monthly_step_rate)",
    "y/y в процентах: OECD через FRED до 2025-04, релизы NBS с 2025-05; январь/февраль смещаются Новым годом по лунному "
    "календарю → флаг lunar_new_year_month":
        "y/y in percent: OECD via FRED to 2025-04, NBS releases from 2025-05; January and February shift with the lunar New Year "
        "→ flag lunar_new_year_month",
    "FRED DEXCHUS публикуется по рабочим дням США, дни без значения пропущены → среднее по опубликованным дням (колонка days)":
        "FRED DEXCHUS is published on US working days, days without a value are skipped → mean over the published days "
        "(column days)",
    "ставка меняется внутри месяца → средневзвешенное по дням (external_data.monthly_step_rate)":
        "the rate changes within the month → day-weighted average (external_data.monthly_step_rate)",
    "ИПЦ как индекс «тот же месяц прошлого года = 100» → y/y = индекс − 100 (external_data.cpi_yoy)":
        "CPI as an index with the same month of the previous year = 100 → y/y = index − 100 (external_data.cpi_yoy)",
    "ставка меняется внутри месяца → средневзвешенное по дням": "the rate changes within the month → day-weighted average",
    "январь/февраль смещаются Новым годом по лунному календарю → флаг lunar_new_year_month":
        "January and February move with the lunar New Year → flag lunar_new_year_month",
    "курс публикуется только по рабочим дням → среднее по опубликованным дням, без заполнения пропусков":
        "the rate is published on working days only → average over published days, gaps not filled",
    "то же, что USD/KZT; праздники РФ не совпадают с праздниками РК → дни не выравниваются":
        "as for USD/KZT; Russian holidays differ from Kazakh holidays → days are not aligned",
    "то же; праздники КНР (неделя Нового года) дают месяцы с малым числом дней (колонка days)":
        "the same; Chinese holidays (New Year week) give months with few days (column days)",
    "Пока файлы содержат только заголовок, особенность обработана в коде и проверена тестами на синтетических данных "
    "(tests/test_external_data.py), но в реальных данных не наблюдалась.":
        "While the files hold only a header, each feature is handled in code and tested on synthetic data "
        "(tests/test_external_data.py) but has not been observed in real data.",
    "Ключевая ставка Банка России": "Bank of Russia key rate",
    "Индекс потребительских цен, % к соответствующему месяцу прошлого года":
        "Consumer price index, % of the same month of the previous year",
    "Официальный курс тенге к доллару США": "Official tenge rate to the US dollar",
    "Официальный курс рубля к доллару США": "Official rouble rate to the US dollar",
    # config/external_sources.json
    "Банк России": "Bank of Russia", "Росстат": "Rosstat", "Народный банк Китая": "People's Bank of China",
    "Национальный Банк Казахстана": "National Bank of Kazakhstan",
    "UNKNOWN (раздел ключевой ставки на cbr.ru)": "UNKNOWN (key rate section on cbr.ru)",
    "UNKNOWN (раздел цен на rosstat.gov.ru)": "UNKNOWN (prices section on rosstat.gov.ru)",
    # docs/redteam_response.md
    "# Ответ красной команде": "# Red-team response",
    "Шаблон. Пункты чужой команды вносит человек после ревью; сайт показывает эту таблицу как есть. Каждое изменение по "
    "пункту записывается в `docs/deviations.md` (D-номер) и указывается в колонке «Изменение».":
        "Template. A person enters the other team's points after the review, and the site shows this table as it is. "
        "Each change made in response is recorded in `docs/deviations.md` (D number) and named in the \"Change\" column.",
    "№": "No.", "Пункт красной команды (дословно)": "Red-team point (verbatim)", "Наш ответ": "Our response",
    "Изменение (файл, D-номер) или «без изменений: почему»": "Change (file, D number) or \"no change: why\"",
}

# Patterns: the whole string must match; groups are copied unchanged (numbers, dates, file names) or translated.
_PATTERNS: list[tuple[str, str]] = [
    (r"Казначей или портфельный менеджер, держащий тенговые госбумаги, до заседания НБ РК (\d{1,2}) (\w+) (\d{4}) решает, "
     r"удлинять или сокращать дюрацию\.",
     "A treasurer or portfolio manager holding tenge government bonds decides, before the NBK meeting on {0} {1} {2}, "
     "whether to extend or shorten duration."),
    (r"итог заседания НБ РК (\S+) \(ставка после решения\)", "outcome of the NBK meeting on {0} (rate after the decision)"),
    (r"\*\*Решение \(ждёт подтверждения человека\):\*\* (.+)", "**Decision (awaiting confirmation by a person):** {0}"),
    (r"\*\*Статус потерь:\*\* (.+)", "**Loss status:** {0}"),
    (r"- \*\*Cost of error \(цена ошибки\):\*\* удлинить дюрацию, а снижения нет \(потеря (\S+) усл\. ед\.\); не удлинить, "
     r"а снижение есть \(упущенная выгода (\S+) усл\. ед\.\)\. Значения — допущение пользователя\.",
     "- **Cost of error:** extending duration when no cut comes (loss: {0}, in notional units); not extending when a cut "
     "comes (forgone gain: {1}, in notional units). The values are a user assumption."),
    (r"Удлинять, если P\(снижение\) > p\* = L_false / \(L_false \+ L_miss\) = \*\*(\S+)\*\*\.",
     "Extend if P(cut) > p* = L_false / (L_false + L_miss) = **{0}**."),
    (r"Сейчас \(вероятности на решение (\S+)\) P\(снижение\) = \*\*(\S+)\*\*, поэтому бинарное правило: \*\*(.+)\*\*\.",
     "Now (probabilities as of the decision of {0}) P(cut) = **{1}**, so the binary rule says: **{2}**."),
    (r"Минимум ожидаемых потерь: \*\*(.+)\*\*\.", "Lowest expected loss: **{0}**."),
    (r"## Оценка прогноза потерями \(holdout (\S+) – (\S+), (\d+) решений\)",
     "## Forecast evaluation by losses (holdout {0} – {1}, {2} decisions)"),
    (r"Средние реализованные потери трёхисходного правила: модель (\S+), Always Hold (\S+), частоты классов (\S+)\. "
     r"У модели потери (.+)\. Это одна выборка из (\d+) решений без интервала; вывода «модель лучше» отсюда не следует\.",
     "Mean realised losses of the three-outcome rule: model {0}, Always Hold {1}, class frequencies {2}. The model's "
     "losses are {3}. This is one sample of {4} decisions without an interval; it does not show that the model is better."),
    # model_card.limits
    (r"Отношение RMSE на holdout (\S+); 95% бутстрап-интервал (\S+)–(\S+), тест Диболда–Мариано p = (\S+) на (\S+) "
     r"решениях\. Метка правила сменилась от одного нового решения: (.*)",
     "Holdout RMSE ratio {0}; 95% bootstrap interval {1}–{2}, Diebold–Mariano test p = {3} on {4} decisions. The rule's "
     "label changed after one new decision: {5}"),
    (r"RPS модели (\S+), частот классов (\S+), Always Hold (\S+)\.", "RPS: model {0}, class frequencies {1}, Always Hold {2}."),
    (r"LR-тест равенства наклонов 2015–2019 против 2020\+: p = (\S+) \((\S+)\)\.",
     "LR test of equal slopes, 2015–2019 against 2020+: p = {0} ({1})."),
    (r"Первые классификаторы проекта \(логистическая регрессия и случайный лес на уровнях факторов\) на тесте из (\S+) "
     r"решений \((\S+) – (\S+)\) предсказали один и тот же класс для всех решений; точность (\S+) против (\S+) у Always "
     r"Hold \(outputs/legacy/\)\. Урок: модель без бенчмарка и без проверки на трендовых уровнях факторов выглядит "
     r"рабочей, пока её не сравнить с «ничего не меняется»\.",
     "The project's first classifiers (logistic regression and random forest on factor levels) predicted the same class "
     "for every decision on a test of {0} decisions ({1} – {2}); accuracy {3} against {4} for Always Hold "
     "(outputs/legacy/). Lesson: a model without a benchmark and without a check on trending factor levels looks as if "
     "it works until it is compared with \"nothing changes\"."),
    # carry_corridor
    (r"месяц (\S+)", "month {0}"),
    (r"UNKNOWN: мало наблюдений \((\d+)\)", "UNKNOWN: too few observations ({0})"),
    (r"не запускалась: выборка слишком короткая \((\d+) мес\. < (\d+)\)", "not run: sample too short ({0} months, fewer than {1})"),
    (r"не запускалась: нет реальной ставки \((Россия|Китай)\)", "not run: no real rate for {0}"),
    (r"данные есть \((\d+) строк\)", "data present ({0} rows)"),
    # carry_corridor with partial partner data (D46); groups are file names or the partner labels Россия / Китай
    (r"UNKNOWN: данных нет \(шаблон: ([\w.]+(?:, [\w.]+)*)\)", "UNKNOWN: no data (template file only: {0})"),
    (r"UNKNOWN: нет реальной ставки: (Россия|Китай|Россия, Китай); по одной стране границы коридора не считаются",
     "UNKNOWN: no real rate for {0}; the corridor bounds are not computed from one country"),
    (r"КЗ − (Россия|Китай) \(нет данных: (Россия|Китай)\)", "KZ − {0} (no data: {1})"),
    (r"КЗ − (Россия|Китай)", "KZ − {0}"),
    (r"КЗ − наибольшая из: Россия, Китай", "KZ − the higher of Russia and China"),
    (r"UNKNOWN: нет данных USD/KZT \(data/raw/external/usd_kzt_daily\.csv — шаблон\)",
     "UNKNOWN: no USD/KZT data (data/raw/external/usd_kzt_daily.csv is a template)"),
    (r"UNKNOWN: ряды ставки и инфляции не пересекаются", "UNKNOWN: the rate and inflation series do not overlap"),
    (r"Источник, URL и дата получения каждого заполненного файла — в config/external_sources\.json \(D46, D47, D50\)\. "
     r"Только шаблон: ([\w.]+(?:, [\w.]+)*)\.",
     "The source, URL and retrieval date of every filled file are in config/external_sources.json (D46, D47, D50). Template only: {0}."),
    (r"Источник, URL и дата получения каждого заполненного файла — в config/external_sources\.json \(D46, D47, D50\)\. Все файлы заполнены\.",
     "The source, URL and retrieval date of every filled file are in config/external_sources.json (D46, D47, D50). All files are filled."),
    # patterns: outlier reasons (src/patterns.py)
    (r"в следующих (\d+) мес\. \(предварительно: меньше (\d+) мес\.\)", "over the next {0} months (provisional: fewer than {1} months),"),
    (r"в следующих (\d+) мес\.", "over the next {0} months,"),
    (r"(\d+) мес\. подряд, затем возврат: (.+) сохраняется (\S+) скачка", "{0} months in a row, then a return: {1} {2} of the jump persists"),
    (r"новый уровень держится: (.+) сохраняется (\S+) скачка", "the new level holds: {0} {1} of the jump persists"),
    (r"возврат: (.+) сохраняется (\S+) скачка", "a return: {0} {1} of the jump persists"),
    # docs/DECISIONS.md
    (r"Для каждого окна: средняя абсолютная ревизия сезонно скорректированного значения последней точки \(оценка по "
     r"данным до t против оценки по данным до t \+ (\d+)\), (\d+) последних начал\. Выбирается окно с наименьшей "
     r"ревизией; при равенстве — более короткое\.",
     "For each window: the mean absolute revision of the seasonally adjusted value of the last point (estimate from data "
     "up to t against the estimate from data up to t + {0}), over the last {1} origins. The window with the smallest "
     "revision is chosen; on a tie, the shorter one."),
    (r"окно (\d+)", "window {0}"),
    # docs/DATA.md
    (r"- Покрытие: (\S+) – (\S+), (\d+) строк; пропущенных месяцев (\d+), дубликатов (\d+)\.",
     "- Coverage: {0} – {1}, {2} rows; missing months {3}, duplicates {4}."),
    (r"- Определение: (.+)", "- Definition: {0}"),
    (r"- Источник: (.+); публикация (\S+), получено (\S+); ревизии после публикации: (\S+)\.",
     "- Source: {0}; published {1}, retrieved {2}; revised after release: {3}."),
    (r"- Календарные особенности: (.+)", "- Calendar features: {0}"),
    (r"- Флаги экрана скачков: (\d+)(.*)\.", "- Jump-screen flags: {0}{1}."),
    (r"- События календаря вмешательств: (\d+)(.*)\.", "- Intervention-calendar events: {0}{1}."),
]
PATTERNS = [(re.compile(rx), template) for rx, template in _PATTERNS]

# Fragments inside otherwise English text (provenance rows from docs/facts_to_fill.csv): Russian source titles,
# navigation paths and quoted column headers. Longest first, so a path is replaced before a title inside it.
_FRAGMENTS = {
    "Главная > Статистика > Денежно-кредитная и банковская статистика > Кредитный рынок > Кредиты экономике от банков "
    "второго уровня (исторические данные)":
        "Home > Statistics > Monetary and banking statistics > Credit market > Loans to the economy from second-tier "
        "banks (historical data)",
    "Главная > Отрасли > Экономика > Статистика внешней, взаимной торговли и товарных рынков":
        "Home > Industries > Economy > Statistics of foreign and mutual trade and commodity markets",
    "Главная > Отрасли > Экономика > Статистика внутренней торговли > Розничная торговля":
        "Home > Industries > Economy > Domestic trade statistics > Retail trade",
    "Главная > Отрасли > Экономика > Статистика цен": "Home > Industries > Economy > Price statistics",
    "Индексы физического объема розничной торговли по месяцам 2015-2026 годы":
        "Physical volume indices of retail trade by month, 2015-2026",
    "Кредиты экономике от банков второго уровня (исторические данные)":
        "Loans to the economy from second-tier banks (historical data)",
    "Базовая ставка Национального Банка РК (2015-2026)": "Base rate of the National Bank of the Republic of Kazakhstan (2015-2026)",
    "Индекс потребительских цен по 12 основным разделам": "Consumer price index by 12 main divisions",
    "Товарооборот в иностранной валюте (экспорт)": "Trade turnover in foreign currency (exports)",
    "Товарооборот в иностранной валюте (импорт)": "Trade turnover in foreign currency (imports)",
    "«Дата установления ставки (с)»": "“Date the rate was set (from)”",
    "«Коридор базовой ставки, %»": "“Base rate corridor, %”",
    "«Дата последней актуализации»": "“Date of last update”",
    "«Размер ставки, %»": "“Rate, %”",
    "«Примечание»": "“Note”",
    "«Метаданные»": "“Metadata”",
}
FRAGMENTS = sorted(_FRAGMENTS.items(), key=lambda item: -len(item[0]))


def tr(text: str) -> str:
    """English version of `text`; text without Cyrillic is returned unchanged."""
    if not isinstance(text, str) or not CYRILLIC.search(text):
        return text
    if text in PHRASES:
        return PHRASES[text]
    for pattern, template in PATTERNS:
        match = pattern.fullmatch(text)
        if match:
            return template.format(*(tr(group) if group else (group or "") for group in match.groups()))
    out = text
    for russian, english in FRAGMENTS:
        out = out.replace(russian, english)
    if CYRILLIC.search(out):
        raise UntranslatedError(f"no English entry in src/site_i18n.py for: {text!r}")
    return out


def assert_no_cyrillic(name: str, text: str) -> None:
    """Final check on a written site file."""
    match = CYRILLIC.search(text)
    if match:
        start = max(match.start() - 60, 0)
        raise UntranslatedError(f"{name}: Cyrillic text left on the site: {text[start:match.start() + 60]!r}")
