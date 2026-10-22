# Week 5 final audit — `kz-base-rate-model`

## Scope and evidence

The requested `Week5_Student_Guide.pdf` and `Week5_Lecture_Slides.pdf` were not found in the repository or the searched user profile. The rubric below therefore uses the criteria and point values transcribed in the audit request; it cannot verify exact wording, page references, or any additional requirements in the official course PDFs. No deleted files were restored. Git status before this audit showed extensive pre-existing user deletions and modifications; those were preserved.

The data and current MVP artifacts were checked directly. Input SHA-256 (CRLF normalized to LF) is `8bf4a1ae7f36eb61c021a7cf8a568f94a9e89271393e15d6c8a02b550cf75b59`.

## Rubric and project requirements

| Критерий | Требование | Статус | Доказательство | Что исправлено / что осталось |
|---|---|---|---|---|
| Доступность источника критериев | Проверить официальный Student Guide и Lecture Slides | NOT VERIFIED | PDF-файлы не найдены в репозитории или после поиска в доступном профиле пользователя | Нужны PDF для проверки точной формулировки и страниц рубрики. Этот отчёт опирается только на rubric из запроса. |
| Goal card (2 балла) | Заранее зафиксированные проверяемая цель, benchmark, критерий успеха и допустимый отрицательный результат | PARTIAL | `README.md` описывает классификацию решений, финальный 24-месячный holdout и Hold benchmark. `outputs/mvp_backtest_results.json` содержит текущие фактические метрики | `GOAL.md` удалён в рабочем дереве. Нельзя подтвердить, что цель и критерий успеха были зарегистрированы до моделирования; файл не восстановлен. |
| Bug hunt (3 балла) | Если это требует Guide — шесть реальных ошибок с местом, обнаружением, исправлением и доказательством | NOT VERIFIED | В рабочем дереве нет `BUGLOG.md`. Нынешние тесты подтверждают свойства текущей реализации, но сами по себе не доказывают шесть исторических ошибок, способы их обнаружения или исправления | Не стал выдавать диагностические ограничения данных за программные ошибки и не сочинял историю. Для завершения нужны исходные записи/подтверждения; точное требование Guide также не проверено. |
| Validity review (2 балла) | Data, Statistical, Predictive, Stability с метриками, benchmark и ограничениями | PARTIAL | `outputs/mvp_validity_report.json` содержит четыре категории. Data: 90 строк, 6 факторов, 0 пропусков признаков, 0 некорректных меток, 0 расхождений decision/base-rate change, 0 дублирующих дат. Predictive: Hold Accuracy 0,625; LR и RF 0,1875. Statistical помечена `DESCRIPTIVE ONLY`; Stability — 3 expanding folds по 6 решений до финального теста | `VALIDITY.md` удалён. Исходные файлы/временные vintages недоступны, поэтому происхождение, точные единицы и даты публикации признаков не подтверждены. Интерпретация структурных сканов остаётся exploratory. |
| Disclosure (2 балла) | AI-инструмент/модель/дата, цель, место, точный prompt, принятое/отклонённое/переписанное предложение и проверка; комментарии по правилам Guide | NOT VERIFIED | `AI_USE.md` удалён. Поиск в доступном исходном коде не нашёл записей `AI-assisted: see AI_USE Axx` | Не реконструировал prompts, даты или решения задним числом. Нужны подлинные записи пользователя; затем disclosure надо согласовать с кодом и официальным форматом Guide. |
| Contributions | Подтверждённые вклады участников и требуемые подписи | NOT VERIFIED | `CONTRIBUTIONS.md` удалён; данных об участниках/подписях в доступных источниках нет | Пользователь должен внести фактические вклады и получить подписи. Ничего не подписывал от имени участников. |
| Exit ticket | Ровно три предложения, отвечающие на три вопроса курса | FAIL | `EXIT_TICKET.md` отсутствует в рабочем дереве | Не создавал личную рефлексию и не придумывал отклонённое предложение ИИ. Пользователь должен написать три предложения по вопросам Guide. |
| Структура и entry point | Наличие `src/`, `tests/`, `data/`, `run_all.py`, запускаемого Streamlit entry point | PASS | Существуют `src/app.py`, `tests/`, `data/processed/nbk_decisions_clean.csv`, `run_all.py`. README запускает `python -m streamlit run src/app.py --server.port 8503`; тесты проверяют 4 вкладки | Корневой `app.py` удалён пользователем, но текущий entry point в `src/app.py` работает и соответствует README. Ничего не перемещал. |
| Reproducibility и хронологическая оценка | Повторяемый запуск, неизменные данные и финальная граница, benchmark на тех же тестовых строках | PASS | `run_all.py` валидирует метку по `base_rate_before/after`, использует cutoff latest date − 24 months и записывает SHA-256. `tests/test_mvp_pipeline.py` проверяет chronology, pipeline fit на train и неизменность CSV. Запуск ниже успешен | Основной split: train 74, test 16; sensitivity windows: 36m 66/24, 48m 58/32. Ни гиперпараметры, ни финальный cutoff не менялись. |
| Фактическая прогнозная способность | Сравнение с Always Hold без обещаний улучшения | PASS | `outputs/mvp_backtest_results.json`: 24m Hold Accuracy 0,625, LR 0,1875, RF 0,1875; обе модели предсказали Decrease 16/16. Тестовый состав: Increase 3, Hold 10, Decrease 3 | Отрицательный результат сохранён. В интерфейсе LR ниже Hold помечается `BELOW BENCHMARK`; вероятности обозначены некалиброванными (`src/app.py:596`). |
| Текущие вкладки и output-согласованность | Forecast, Backtest, Diagnostics & Tests должны читать актуальные результаты | PASS | `src/app.py:343` проверяет сохранённый backtest; вкладка Diagnostics использует `mvp_backtest_results.json`, `mvp_validity_report.json`, `mvp_period_predictions.csv` (`src/diagnostics_view.py:11`). `tests/test_backtest_ui.py` проверяет вкладки, матрицы и метрики | Отдельные `outputs/results.json`, `diagnostics_annex.md` и `robustness_annex.md` имеют прежнюю макромодель/схему и не подключены к текущим вкладкам. Файлы сохранены, но могут запутать ручную проверку комплекта. |
| Источники и признаки | Проверка raw CSV/Excel, единиц, преобразований и дат сопоставления | PARTIAL | `data/raw/SOURCES.md` содержит прежние заголовки/заявленные единицы, но указывает на неподтверждённую provenance. Соответствующие raw CSV, а также `data/processed/macro_factors_monthly.csv` удалены. Текущая панель имеет 90 дат решений | Сверка строк с raw источниками и проверка дат/единиц невозможны без файлов. Метаданные о `exports` также описывают percent-growth transformation, которую нельзя подтвердить по отсутствующему источнику. Файлы не восстанавливал. |
| Robustness и структурные проверки | Временные folds/периоды, ограничения и отсутствие ложной причинной интерпретации | PARTIAL | `outputs/mvp_backtest_results.json` содержит 24/36/48-месячные сравнения; `outputs/mvp_validity_report.json` — 3 pre-test expanding folds. `outputs/mvp_structural_break_summary.json` и таблица кандидатов помечают разрывы exploratory; bootstrap — 199 повторений | Сканы выполнены по нерегулярным датам решений, не по удалённому месячному ряду. Bootstrap p-values не скорректированы между признаками/формами и имеют разрешение 0,005. Это не доказательство причинности или устойчивого structural break. |
| Сдаваемый комплект и временные файлы | Исключить `.venv` и временные файлы из сдачи | PARTIAL | `.venv` содержит собственный `.gitignore`, поэтому Git его исключает. Корневой `.gitignore` удалён; `__pycache__/` видны в `git status` как untracked. Архив не создавался | Не удалял кэш и не восстанавливал `.gitignore`. Перед ручной упаковкой исключить `.venv`, `__pycache__`, `.pytest-tmp`, `.pytest_cache`; проверить, что в архив не попали legacy outputs, если курс их не требует. |

## Результаты, сверенные по файлам

- `data/processed/nbk_decisions_clean.csv`: 90 строк, даты `2015-10-02`—`2026-09-07`; hash совпадает с указанным выше и с сохранённым в результатах.
- 24 месяца: 74 train / 16 test. Классы test: 3 Increase / 10 Hold / 3 Decrease. Hold Accuracy 0,625; LR и RF Accuracy 0,1875. Обе модели предсказали Decrease во всех 16 строках.
- Все 16 значений `corporate_lending` и `household_lending` в test выше максимума train. Это range shift, не объяснение ошибок.
- Альтернативные уровни, логарифмы и decision-interval growth сохранены как диагностические варианты; ни один не выбран для production. Они не показывают устойчивого превосходства над Hold.
- В Forecast вероятности берутся из `predict_proba()` и сопоставляются через `model.classes_`; подпись предупреждает, что они не откалиброваны.

## Команды и фактические проверки

1. `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=.pytest-tmp` — **25 passed**, 2 sklearn warnings. Предупреждения: `y_pred contains classes not in y_true` в коротких стабильностных folds; это связано с тем, что в отдельных блоках фактически отсутствует предсказанный класс. Ошибок тестов не было.
2. `.venv\Scripts\python.exe run_all.py` — **завершился с кодом 0**; пересоздал backtest/validity артефакты. Выводил предупреждения Streamlit о запуске вне Streamlit runtime и то же предупреждение sklearn.
3. `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=.pytest-tmp tests\test_backtest_ui.py` — **3 passed**.
4. `curl.exe --silent --show-error --fail --max-time 5 http://localhost:8503/_stcore/health` — ответ `ok`. Streamlit AppTest проверил вкладки во время тестов.
5. `git diff --check` — код возврата 0; Git сообщил о возможной нормализации LF/CRLF в уже изменённых `README.md`, `requirements.txt`, `run_all.py`, а также о недоступности `.pytest-tmp/` и `.pytest_cache/` при обходе.
6. После `run_all.py` SHA-256 CSV остался `8bf4a1ae7f36eb61c021a7cf8a568f94a9e89271393e15d6c8a02b550cf75b59`.

Обычный `pytest -q` ранее в этой среде не мог подготовить системный temp-каталог из-за Windows `PermissionError`; повторный запуск с указанным локальным `--basetemp` прошёл. Не менял тесты для обхода этой ошибки.

## Изменения в ходе этого аудита

- Создан только `outputs/week5_final_audit.md`.
- Источники, тесты, приложение, модель, старые артефакты и пользовательские Git-удаления не менялись этим аудитом. Команда `run_all.py` обновила только связанные MVP/backtest/validity outputs, перечисленные в её выводе.

## Что должен подтвердить пользователь

1. Предоставить официальные Week 5 PDF либо сверить этот отчёт с ними, включая точное правило «шесть ошибок» и требования к подписям.
2. Если соответствующие критерии должны быть представлены файлами, внести личные сведения в goal/bug/disclosure/contributions/exit-ticket документы. Нужны реальная предмодельная цель и дата, подтверждённые bug reports, точные AI prompts и решения по ним, фактические участники и подписи, а также собственный трёхпредложный exit ticket.
3. Решить, какие пользовательские legacy-артефакты должны войти в сдаваемый пакет, и вручную исключить virtualenv/кэши из архива. Ничего из этого не упаковывалось автоматически.

## Чек-лист перед сдачей

- [ ] Сверить rubric и баллы с официальными Week 5 PDF.
- [ ] Не восстанавливая удалённые версии автоматически, подготовить необходимые личные deliverables и подписи.
- [ ] Подтвердить точные AI disclosure details и six-bug evidence, если они требуются Guide.
- [ ] Собрать пакет без `.venv`, Python caches и лишних legacy-артефактов.
- [x] Запустить тесты, `run_all.py` и проверить доступность интерфейса.
- [x] Сверить метрики и неизменность исходного CSV.
