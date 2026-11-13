"""Model card и раздел «Пределы» сайта из одних и тех же фактов: `python run.py model-card`.

`limits()` возвращает список фактов (заголовок, текст); docs/model_card.md и страница сайта строятся из него,
поэтому расхождение невозможно. Все числа читаются из model/artifact.json, outputs/numbers_for_note.json
и outputs/legacy/mvp_backtest_results.json.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "model" / "artifact.json"
NUMBERS = ROOT / "outputs" / "numbers_for_note.json"
LEGACY = ROOT / "outputs" / "legacy" / "mvp_backtest_results.json"
VERSION = ROOT / "model" / "version_comparison.json"
CARD = ROOT / "docs" / "model_card.md"


def _load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).is_file() else {}


def past_failure(legacy: dict) -> str:
    metrics = {row["Model"]: row for row in legacy.get("metrics", [])}
    split = legacy.get("split", {})
    if not metrics:
        return "UNKNOWN (outputs/legacy/mvp_backtest_results.json отсутствует)"
    logit = metrics.get("Logistic Regression", {})
    hold = metrics.get("Hold benchmark", {})
    return (f"Первые классификаторы проекта (логистическая регрессия и случайный лес на уровнях факторов) на тесте "
            f"из {split.get('test_n')} решений ({split.get('test_start')} – {split.get('test_end')}) предсказали один и тот же "
            f"класс для всех решений; точность {logit.get('Accuracy', 'UNKNOWN'):.3f} против {hold.get('Accuracy', 'UNKNOWN'):.3f} "
            f"у Always Hold (outputs/legacy/). Урок: модель без бенчмарка и без проверки на трендовых уровнях факторов "
            f"выглядит рабочей, пока её не сравнить с «ничего не меняется».")


def limits(artifact: dict | None = None, numbers: dict | None = None, version: dict | None = None) -> list[dict[str, str]]:
    artifact = artifact if artifact is not None else _load(ARTIFACT)
    n = (numbers if numbers is not None else _load(NUMBERS)).get("numbers", {})
    version = version if version is not None else _load(VERSION)
    d = lambda key: n.get(key, {}).get("display", "UNKNOWN")  # noqa: E731
    stability = artifact.get("diagnostics", {}).get("parameter_stability", {})
    v = lambda key: n.get(key, {}).get("value")  # noqa: E731
    try:
        undistinguished = float(v("rmse_ratio_ci_low")) <= 1 <= float(v("rmse_ratio_ci_high")) and float(v("dm_squared_error_p")) >= 0.05
    except (TypeError, ValueError):
        undistinguished = None
    first_title = {True: "Модель не отличима от Always Hold", False: "Отличие от Always Hold по интервалу или тесту",
                   None: "Сравнение с Always Hold: UNKNOWN"}[undistinguished]
    return [
        {"title": first_title,
         "text": f"Отношение RMSE на holdout {d('rmse_ratio')}; 95% бутстрап-интервал {d('rmse_ratio_ci_low')}–{d('rmse_ratio_ci_high')}, "
                 f"тест Диболда–Мариано p = {d('dm_squared_error_p')} на {d('n_holdout')} решениях. Метка правила сменилась от "
                 f"одного нового решения: {version.get('sentence', 'UNKNOWN')}"},
        {"title": "Сравнение с частотами классов (RPS, дополнительная мера)",
         "text": f"RPS модели {d('rps_model')}, частот классов {d('rps_class_frequency')}, Always Hold {d('rps_hold')}."},
        {"title": "Параметры нестабильны" if stability.get("pass_fail") == "FAIL" else "Стабильность параметров",
         "text": f"LR-тест равенства наклонов 2015–2019 против 2020+: p = {d('stability_lr_p')} ({stability.get('pass_fail', 'UNKNOWN')})."},
        {"title": "Holdout не нетронутый",
         "text": "Holdout частично просматривался в ранних запусках; преререгистрации до анализа не было (D15); "
                 "по-настоящему вне выборки только прогнозы из docs/forecast_log.csv."},
        {"title": "Задержки публикации не проверены",
         "text": "Реальные лаги публикации UNKNOWN; принято «месяц решения минус 2». Винтажей нет: бэктесты рядов — revised-data."},
        {"title": "Названный прошлый провал", "text": past_failure(_load(LEGACY))},
    ]


def card(items: list[dict[str, str]]) -> str:
    body = "\n".join(f"### {item['title']}\n\n{item['text']}\n" for item in items)
    return ("<!-- Сгенерировано `python run.py model-card` (src/model_card.py); не править руками. -->\n"
            "# Model card\n\n"
            "**Назначение:** вероятности решения НБ РК (снижение / сохранение / повышение) для решения о дюрации "
            "(docs/decision_memo.md). **Не назначение:** прогноз размера шага ставки и курса.\n\n"
            "**Модель:** ordered logit на шести факторах (docs/model_spec.md), заморожена (docs/development_plan.md).\n\n"
            "## Пределы\n\n" + body)


def main() -> int:
    CARD.write_text(card(limits()), encoding="utf-8", newline="\n")
    print(f"Wrote {CARD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
