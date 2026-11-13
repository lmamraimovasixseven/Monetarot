"""docs/DATA.md: аудит каждого ряда, собранный из файлов (`python run.py ledger`)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd

from src import external_data
from src.facts import series_audit

ROOT = Path(__file__).resolve().parents[1]
DATA_DOC = ROOT / "docs" / "DATA.md"
FACTS_CSV = ROOT / "docs" / "facts_to_fill.csv"
SCREEN = ROOT / "data" / "processed" / "data_anomalies.json"
CALENDAR = ROOT / "config" / "intervention_calendar.csv"

# Известные свойства рядов, записанные в документах проекта (не из памяти): ссылка на документ в скобках.
KNOWN = {
    "base_rate_history.csv": ("Ставка после решения, вступившего в силу в этом месяце; строки до 2026-09 из таблицы prg.kz, "
                              "2026-10 со страницы НБ РК (docs/manual_steps_found.md).",
                              "Решения вступают в силу в понедельник/вторник после объявления в пятницу; в 5 случаях "
                              "объявление в предыдущем месяце (docs/model_spec.md, D20)."),
    "inflation_history.csv": ("Годовая инфляция ИПЦ, % (y/y); месячной m/m в проекте нет.",
                              "НДС 12%→16% с 2026-01-01 (config/intervention_calendar.csv) даёт сдвиг уровня цен в январе 2026."),
    "consumption_history_updated.csv": ("Индекс физического объёма розничной торговли, y/y %.",
                                        "Эпизод 2020-03...2020-06 (резкое падение и восстановление) помечен как временный."),
    "export_history.csv": ("Экспорт, тыс. долл. США, месячные значения (проверено по итогу «январь-август»); ряд смешивает "
                           "два издания: строки до 2026-07 и строка 2026-08 из более нового издания (D22).",
                           "Скачок 2026-06 на новый уровень помечен; проверка по источнику ждёт человека."),
    "import_history.csv": ("Импорт, тыс. долл. США; два издания, как у экспорта (D22); новое издание пересматривает "
                           "2026-01...2026-07 на +0.01%...+1.34% (docs/manual_steps_found.md).",
                           "Январское падение повторяется по годам: сезонный разрыв, не ошибка."),
    "loans_individuals_history.csv": ("Кредиты физлицам, млн тенге (остатки на конец месяца по файлу НБ РК).",
                                      "Ряд нестационарен (ADF и KPSS, outputs/annex_unit_roots.csv)."),
    "loans_legal_entities_history.csv": ("Кредиты юрлицам, млн тенге.", "Резкие изменения 2015-06, 2015-08, 2019-01 помечены экраном."),
}
EXTERNAL_HANDLED = {
    "ru_key_rate": "ставка меняется внутри месяца → средневзвешенное по дням (external_data.monthly_step_rate)",
    "ru_cpi_yoy": "ИПЦ как индекс «тот же месяц прошлого года = 100» → y/y = индекс − 100 (external_data.cpi_yoy)",
    "cn_policy_rate": "ставка меняется внутри месяца → средневзвешенное по дням",
    "cn_cpi_yoy": "январь/февраль смещаются Новым годом по лунному календарю → флаг lunar_new_year_month",
    "usd_kzt": "курс публикуется только по рабочим дням → среднее по опубликованным дням, без заполнения пропусков",
    "usd_rub": "то же, что USD/KZT; праздники РФ не совпадают с праздниками РК → дни не выравниваются",
    "usd_cny": "то же; праздники КНР (неделя Нового года) дают месяцы с малым числом дней (колонка days)",
}


def build() -> str:
    with Path(FACTS_CSV).open(encoding="utf-8", newline="") as handle:
        facts = {row["series_file"]: row for row in csv.DictReader(handle)}
    screen = json.loads(SCREEN.read_text(encoding="utf-8")) if SCREEN.is_file() else {"flags": []}
    calendar = pd.read_csv(CALENDAR)
    lines = ["<!-- Сгенерировано `python run.py ledger` (src/data_doc.py); не править руками. -->",
             "# Аудит данных по рядам", "",
             "Каждый ряд: покрытие, пропуски, ревизии, определение, смены классификации, календарные особенности. "
             "Числа посчитаны из файлов; известные свойства взяты из документов проекта (ссылки в тексте). "
             "Значения в data/raw никогда не меняются; флаги только помечают.", ""]
    for name in sorted(facts):
        audit = series_audit(ROOT / "data" / "raw", name)
        flags = [f for f in screen["flags"] if f["series_file"] == name]
        events = calendar[calendar["series_affected"] == name]
        definition, calendar_note = KNOWN.get(name, ("UNKNOWN", "UNKNOWN"))
        lines += [f"## `{name}`", "",
                  f"- Покрытие: {audit['first']} – {audit['last']}, {audit['rows']} строк; пропущенных месяцев {audit['missing_months']}, "
                  f"дубликатов {audit['duplicate_months']}.",
                  f"- Определение: {definition}",
                  f"- Источник: {facts[name]['publisher']}; публикация {facts[name]['publication_date']}, получено "
                  f"{facts[name]['retrieval_date']}; ревизии после публикации: {facts[name]['revised_after_release']}.",
                  "- Смены классификации: UNKNOWN (в документах источника не проверялись).",
                  f"- Календарные особенности: {calendar_note}",
                  f"- Флаги экрана скачков: {len(flags)}" + (f" ({', '.join(f['month'] for f in flags)})" if flags else "") + ".",
                  f"- События календаря вмешательств: {len(events)}" + (
                      f" ({'; '.join(f'{r.date} {r.type}' for r in events.itertuples())})" if len(events) else "") + ".", ""]
    lines += ["## Новые источники (блок E)", "",
              "| Ряд | Файл | Статус | Обрабатываемая особенность |", "|---|---|---|---|"]
    config = external_data.sources()
    for name, state in external_data.status().items():
        lines.append(f"| {config[name]['title']} | `data/raw/external/{config[name]['file']}` | {state} | {EXTERNAL_HANDLED[name]} |")
    lines += ["", "Пока файлы содержат только заголовок, особенность обработана в коде и проверена тестами на "
              "синтетических данных (tests/test_external_data.py), но в реальных данных не наблюдалась.", ""]
    return "\n".join(lines)


def main() -> int:
    DATA_DOC.write_text(build(), encoding="utf-8", newline="\n")
    print(f"Wrote {DATA_DOC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
