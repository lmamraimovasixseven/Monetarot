# Покрытие брифа «The Decision Desk» (аудит 2026-11-13)

Аудит выполнен до начала работ по брифу (только чтение). Статус: **есть** / **частично** / **нет**. Колонка «Что строим» — план; фактическое выполнение отражается в `docs/PROGRESS.md`.

| Пункт брифа | Статус | Где в репозитории | Что строим |
|---|---|---|---|
| Usefulness Test (решение, без вас, изменение, цена ошибки, кому выгодно) | частично | `docs/decision_rule.md` (правило-флаг, именованный пользователь), `docs/indicator_card.md` | `docs/decision_memo.md`, `src/decision_rule.py` (порог из функции потерь), поле `decision` в артефакте |
| Минимум контента (данные, модель, прогноз, оценка, сайт) | частично | ordered logit, holdout, бенчмарк, Streamlit-дашборд | модуль прогноза рядов, паттерны, коридор, статичный сайт |
| Архитектура (README, AI_USE, CONTRIBUTIONS, DECLARATION, data/raw, data/processed, ledger, prereg, src, model/artifact.json, site, tests/acceptance.md) | частично | `README.md`, `docs/ai_use.md`, `docs/contributions.md`, `data/`, `src/`, `model/artifact.json`, `tests/` | корневые `AI_USE.md`, `CONTRIBUTIONS.md`, `DECLARATION.md` (генерация из docs), `ledger/`, `prereg/`, `site/`, `tests/acceptance.md` |
| A1 Решение и пользователь | частично | `docs/facts_to_fill.md` (named_user), `docs/decision_rule.md` | decision memo, решение «дюрация до 4 декабря» (ждёт подтверждения) |
| A2 Функция потерь и порог | нет | — | `src/decision_rule.py`, тесты порога и монотонности |
| A3 Журнал доказательств | частично | `outputs/numbers_for_note.json` (источник каждого числа), `data/raw/SOURCES.md` | `ledger/evidence_ledger.csv`, `python run.py ledger`, тест полноты |
| A4 Аудит данных | частично | `docs/data_audit.md`, `outputs/data_anomalies.md`, `tests/test_data_contract.py` | `docs/DATA.md` по каждому ряду, новые источники РФ/КНР/курсы (шаблоны) |
| A5 Календарь вмешательств, винтажи | нет | — | `config/intervention_calendar.csv`, `src/vintages.py` (состояние «на дату t»), тест cutoff |
| F1 Модуль прогноза (любой ряд, cutoff, горизонт, интервал) | нет | ordered logit прогнозирует только решение | `src/forecast_desk.py`, `python run.py forecast` |
| F2 Кандидаты, дифференцирование, AICc | нет | ADF/KPSS в `outputs/annex_unit_roots.csv` (для факторов) | кандидаты, AICc при одинаковом d, Ljung–Box |
| F3 Прокатный бэктест, покрытие, DM | частично | rolling-origin и DM в `src/robust_eval.py` (для решения) | бэктест рядов h=1/3, pinball, покрытие, «ловушки» |
| F4 Преререгистрация | частично | `docs/development_plan.md`, `docs/forecast_log.csv` (прогноз на 2026-12-04 зарегистрирован) | `prereg/prereg.md`, `prereg/candidates.json`, хеши, `python run.py prereg-check` |
| F5 Reality Check | частично | forecast-log/forecast-score (RPS, hit) | ожидаемая ставка с 80% интервалом, pinball, покрытие, запасная цель |
| F6 Model card, red team | частично | ограничения в README и на дашборде | `docs/model_card.md`, `docs/redteam_response.md`, страницы сайта |
| Семь шагов истории (решение → действие) | частично | вкладки Streamlit | главная `site/index.html` по семи шагам |
| Проверки сайта (360 px, < 3 с, дальтонизм, alt, без CDN) | частично | Streamlit проверяет скорость рендера (check_04) | статичный сайт с тестами ширины, веса, alt-текста, палитры |
| Правила честности (негативный результат так же заметен, «лучше» только с тестом) | есть | D25, D30, `AGENTS.md` п. 14 | сохранить во всех новых модулях |
| Одна команда обновления | частично | `python run.py all` | `python run.py update`, `make update`, запуск в CI |
| Update Drill (пять карточек) | нет | `docs/RUNBOOK_data_update.md` | `docs/UPDATE_DRILL.md`, `python run.py drill --card ...` |
| Приёмные проверки (12) | частично | `tests/test_acceptance.py` (10 проверок дашборда) | `tests/acceptance.md`, `python run.py acceptance`, `python run.py trace` |
| Защита и Quiz 2 | нет | — | `docs/DEFENCE_QA.md`, `docs/quiz2_sheet.md` |
| Коридор carry trade (требование преподавателя) | нет | — | `src/carry_corridor.py`, страница; данные РФ/КНР и курсы отсутствуют в проекте |

## Ограничения, известные до начала работ

- В проекте нет месячной инфляции m/m (файл содержит y/y), курсов USD/KZT, USD/RUB, USD/CNY и данных по России и Китаю. Значения из памяти не подставляются: создаются шаблоны и инструкции в `TODO_HUMAN.md`; модули работают на данных, когда они появятся, а до того показывают UNKNOWN.
- Старых винтажей рядов нет: любой бэктест по рядам помечается «revised-data backtest».
- Конфигурации Render в репозитории нет; ломать нечего.
