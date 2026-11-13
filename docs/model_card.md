<!-- Сгенерировано `python run.py model-card` (src/model_card.py); не править руками. -->
# Model card

**Назначение:** вероятности решения НБ РК (снижение / сохранение / повышение) для решения о дюрации (docs/decision_memo.md). **Не назначение:** прогноз размера шага ставки и курса.

**Модель:** ordered logit на шести факторах (docs/model_spec.md), заморожена (docs/development_plan.md).

## Пределы

### Модель не отличима от Always Hold

Отношение RMSE на holdout 0.995; 95% бутстрап-интервал 0.780–1.335, тест Диболда–Мариано p = 0.961 на 18 решениях. Метка правила сменилась от одного нового решения: Effect of the data update (OLD = git tag before-data-update-2026-09-07, NEW = current files): usable decisions 88 → 89; estimation sample 70 → 71 decisions (ending 2024-06-03 → 2024-07-15); holdout 18 → 18 decisions (2024-07-15–2026-09-07 → 2024-09-02–2026-10-27). The holdout RMSE ratio changed from 1.002 to 0.995, so the pre-specified rule's label changed from "does not meet the pre-specified criterion (RMSE ratio not below 1)" to "meets the pre-specified criterion (RMSE ratio below 1)". 95% bootstrap intervals: OLD 0.828 to 1.230, NEW 0.780 to 1.335; both ratios lie inside both intervals, so the change does not show that the model forecasts better or worse than before.

### Сравнение с частотами классов (RPS, дополнительная мера)

RPS модели 0.154, частот классов 0.159, Always Hold 0.194.

### Параметры нестабильны

LR-тест равенства наклонов 2015–2019 против 2020+: p = 0.013 (FAIL).

### Holdout не нетронутый

Holdout частично просматривался в ранних запусках; преререгистрации до анализа не было (D15); по-настоящему вне выборки только прогнозы из docs/forecast_log.csv.

### Задержки публикации не проверены

Реальные лаги публикации UNKNOWN; принято «месяц решения минус 2». Винтажей нет: бэктесты рядов — revised-data.

### Названный прошлый провал

Первые классификаторы проекта (логистическая регрессия и случайный лес на уровнях факторов) на тесте из 16 решений (2024-10-14 – 2026-09-07) предсказали один и тот же класс для всех решений; точность 0.188 против 0.625 у Always Hold (outputs/legacy/). Урок: модель без бенчмарка и без проверки на трендовых уровнях факторов выглядит рабочей, пока её не сравнить с «ничего не меняется».
