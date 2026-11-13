"""Статичный сайт site/ (блок G): `python run.py site`.

Читает только model/artifact.json, файлы, на которые он ссылается (журнал доказательств, журналы прогнозов,
таблицы outputs/), и документы проекта. Каждое число на странице берётся из ledger/evidence_ledger.csv по id и
помечается атрибутом data-ledger="id" (`python run.py trace <id>`). Графики — встроенный SVG с палитрой
Okabe–Ito (безопасна для дальтоников), у каждого заголовок-вывод и aria-label. Без внешних шрифтов, скриптов и CDN.
"""

from __future__ import annotations

import csv
import html
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
ASSETS_SRC = ROOT / "src" / "site_assets"
LEDGER = ROOT / "ledger" / "evidence_ledger.csv"
ARTIFACT = ROOT / "model" / "artifact.json"
PALETTE = {"blue": "#0072B2", "orange": "#E69F00", "vermillion": "#D55E00", "green": "#009E73", "sky": "#56B4E9",
           "grey": "#6E6E6E", "black": "#000000"}
PAGES = [("index.html", "Главная"), ("methods.html", "Методы и пределы"), ("run.html", "Запусти сам"),
         ("sources.html", "Источники"), ("team.html", "Команда"), ("data.html", "Данные"), ("patterns.html", "Паттерны"),
         ("corridor.html", "Коридор"), ("forecasts.html", "Журнал прогнозов"), ("redteam.html", "Ответ красной команде"),
         ("asof.html", "Просмотр на дату t")]
DOWNLOADS = ["data/processed/nbk_decisions_clean.csv", "data/processed/model_panel.csv", "ledger/evidence_ledger.csv",
             "ledger/forecast_ledger.csv", "docs/forecast_log.csv", *[f"data/raw/{p.name}" for p in sorted((ROOT / "data" / "raw").glob("*.csv"))]]


class Ledger:
    """Источник всех чисел сайта: значение по id из журнала доказательств; используемые id записываются."""

    def __init__(self, path: Path = LEDGER) -> None:
        with Path(path).open(encoding="utf-8", newline="") as handle:
            self.values = {row["id"]: row["value"] for row in csv.DictReader(handle)}
        self.used: set[str] = set()

    def raw(self, key: str) -> str:
        if key not in self.values:
            raise KeyError(f"number {key!r} is not in ledger/evidence_ledger.csv")
        self.used.add(key)
        return self.values[key]

    def num(self, key: str, digits: int | None = None, pct: bool = False, signed: bool = False) -> str:
        value = self.raw(key)
        if digits is not None:
            number = float(value) * (100 if pct else 1)
            value = f"{number:+.{digits}f}" if signed else f"{number:.{digits}f}"
            value += "%" if pct else ""
        return f'<span class="num" data-ledger="{html.escape(key)}">{html.escape(value)}</span>'


def esc(text: Any) -> str:
    return html.escape(str(text))


def page(title: str, body: str, current: str) -> str:
    nav = " ".join(f'<a href="{href}"{" aria-current=\"page\"" if href == current else ""}>{esc(label)}</a>'
                   for href, label in PAGES)
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · Monetarot</title><link rel="stylesheet" href="assets/style.css"></head>
<body><header><p class="brand">Monetarot · решения НБ РК</p><nav aria-label="Разделы">{nav}</nav></header>
<main>{body}</main>
<footer><p>Сгенерировано <code>python run.py site</code> из <code>model/artifact.json</code>. Каждое число имеет строку в
<a href="data/evidence_ledger.csv">журнале доказательств</a>.</p></footer></body></html>
"""


# ----------------------------------------------------------------------------- графики

def svg_line(title: str, alt: str, series: list[tuple[str, list[float], str]], labels: list[str],
             y_label: str, width: int = 640, height: int = 260, points: list[tuple[int, float, str]] | None = None) -> str:
    values = [v for _, ys, _ in series for v in ys] + [p[1] for p in points or []]
    lo, hi = min(values), max(values)
    pad = (hi - lo) * 0.1 or 1.0
    lo, hi = lo - pad, hi + pad
    left, right, top, bottom = 48, 12, 16, 36
    n = max(len(labels) - 1, 1)
    x = lambda i: left + (width - left - right) * i / n  # noqa: E731
    y = lambda v: top + (height - top - bottom) * (hi - v) / (hi - lo)  # noqa: E731
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(alt)}" preserveAspectRatio="xMidYMid meet">',
             f"<title>{esc(alt)}</title>",
             f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" stroke="{PALETTE["grey"]}"/>',
             f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" stroke="{PALETTE["grey"]}"/>']
    for tick in (lo + pad, (lo + hi) / 2, hi - pad):
        parts.append(f'<text x="{left - 4}" y="{y(tick) + 4:.1f}" text-anchor="end" font-size="11" fill="{PALETTE["black"]}">{tick:.2f}</text>')
    for i in (0, len(labels) // 2, len(labels) - 1):
        parts.append(f'<text x="{x(i):.1f}" y="{height - 12}" text-anchor="middle" font-size="11" fill="{PALETTE["black"]}">{esc(labels[i])}</text>')
    for name, ys, color in series:
        path = " ".join(f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for i, v in enumerate(ys))
        parts.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2"><title>{esc(name)}</title></path>')
    for i, v, color in points or []:
        parts.append(f'<rect x="{x(i) - 3:.1f}" y="{y(v) - 3:.1f}" width="6" height="6" fill="{color}"/>')
    legend = "".join(f'<span class="key" style="border-color:{c}">{esc(n)}</span>' for n, _, c in series)
    return f'<figure><figcaption><strong>{esc(title)}</strong></figcaption>{"".join(parts)}</svg><p class="legend">{legend}<span class="axis">{esc(y_label)}</span></p></figure>'


def svg_bars(title: str, alt: str, bars: list[tuple[str, float, str]], width: int = 640, height: int = 200) -> str:
    top_value = max(v for _, v, _ in bars) * 1.15
    left, bottom, gap = 150, 24, 12
    bar_h = (height - bottom - gap * (len(bars) + 1)) / len(bars)
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(alt)}"><title>{esc(alt)}</title>']
    for i, (name, value, color) in enumerate(bars):
        top = gap + i * (bar_h + gap)
        length = (width - left - 60) * value / top_value
        parts.append(f'<text x="{left - 6}" y="{top + bar_h / 2 + 4:.1f}" text-anchor="end" font-size="12" fill="{PALETTE["black"]}">{esc(name)}</text>')
        parts.append(f'<rect x="{left}" y="{top:.1f}" width="{length:.1f}" height="{bar_h:.1f}" fill="{color}"/>')
        parts.append(f'<text x="{left + length + 6:.1f}" y="{top + bar_h / 2 + 4:.1f}" font-size="12" fill="{PALETTE["black"]}">{value:.3f}</text>')
    return f'<figure><figcaption><strong>{esc(title)}</strong></figcaption>{"".join(parts)}</svg></figure>'


# ----------------------------------------------------------------------------- markdown → html (таблицы, абзацы)

def md_to_html(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    out, table = [], []

    def flush() -> None:
        if table:
            rows = [r for r in table if not re.fullmatch(r"\|[\s\-|:]+\|", r)]
            cells = [[esc(c.strip()) for c in r.strip().strip("|").split("|")] for r in rows]
            head = "".join(f"<th>{c}</th>" for c in cells[0])
            body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in cells[1:])
            out.append(f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')
            table.clear()

    for line in text.splitlines():
        if line.startswith("|"):
            table.append(line)
            continue
        flush()
        if line.startswith("#"):
            level = min(len(line) - len(line.lstrip("#")) + 1, 4)
            out.append(f"<h{level}>{esc(line.lstrip('#').strip())}</h{level}>")
        elif line.strip():
            out.append(f"<p>{esc(line.strip())}</p>")
    flush()
    return "\n".join(out)


# ----------------------------------------------------------------------------- страницы

def index_page(L: Ledger, artifact: dict) -> str:
    decision = artifact["decision"]
    rc = artifact["reality_check"]
    holdout = pd.read_csv(ROOT / "outputs" / "annex_predictions.csv")
    rates = pd.read_csv(ROOT / "data" / "raw" / "base_rate_history.csv")
    L.raw("chart:holdout"), L.raw("chart:base_rate")
    p_cut = float(L.raw("decision:p_cut"))
    threshold = float(L.raw("decision:binary_threshold_p_cut"))
    action = "удлинять дюрацию" if p_cut > threshold else "не удлинять дюрацию"
    best = {"lengthen": "удлинить", "keep": "оставить", "shorten": "сократить"}[decision["best_action"]]
    ci_low, ci_high = float(L.raw("n:rmse_ratio_ci_low")), float(L.raw("n:rmse_ratio_ci_high"))
    chart1_title = (f"Модель и Always Hold на holdout неразличимы: отношение RMSE {float(L.raw('n:rmse_ratio')):.3f}, "
                    f"95% интервал {ci_low:.2f}–{ci_high:.2f} содержит 1" if ci_low <= 1 <= ci_high else
                    f"Отношение RMSE на holdout {float(L.raw('n:rmse_ratio')):.3f}, интервал не содержит 1")
    chart1 = svg_line(chart1_title, "Линия: ожидаемый балл модели на 18 решениях holdout; квадраты: фактические решения (−1 снижение, 0 сохранение, +1 повышение).",
                      [("ожидаемый балл модели", holdout["expected_score"].tolist(), PALETTE["blue"])],
                      holdout["decision_date"].tolist(), "балл: −1 снижение … +1 повышение",
                      points=[(i, float(v), PALETTE["vermillion"]) for i, v in enumerate(holdout["actual_score"])])
    chart2 = svg_line(f"Базовая ставка сейчас {rates['rate'].iloc[-1]:g}%: после пика идёт снижение",
                      "Линия: базовая ставка НБ РК по месяцам с 2015 года.",
                      [("базовая ставка, %", rates["rate"].tolist(), PALETTE["orange"])], rates["year_month"].tolist(), "%")
    rps = [("модель", float(L.raw("n:rps_model")), PALETTE["blue"]), ("частоты классов", float(L.raw("n:rps_class_frequency")), PALETTE["sky"]),
           ("Always Hold", float(L.raw("n:rps_hold")), PALETTE["grey"])]
    chart3 = svg_bars("По RPS модель почти не отличается от простых частот классов (меньше — лучше)",
                      "Столбцы: ранжированный вероятностный балл на holdout для модели, частот классов и Always Hold.", rps)
    limits = __import__("src.model_card", fromlist=["limits"]).limits()[:3]
    risk = "".join(f"<li><strong>{esc(i['title'])}.</strong> {esc(i['text'])}</li>" for i in limits)
    return f"""
<section class="lead"><h1>Удлинять ли дюрацию тенговых облигаций до заседания НБ РК?</h1>
<p class="summary" lang="en">English summary: an ordered-logit monitor of National Bank of Kazakhstan rate decisions, turned into a duration decision with an explicit loss function. The model cannot be told apart from "always hold"; the page shows that as prominently as any result.</p></section>
<section><h2>1. Решение</h2><p>{esc(decision['decision'])} <em>({esc(decision['decision_status'])}; потери — {esc(decision['loss_status'].split(':')[0].lower())})</em></p></section>
<section><h2>2. Напряжение</h2><p>Вероятность снижения ставки на заседании {esc(rc['target'].split('НБ РК ')[-1].split(' (')[0])}: {L.num('decision:p_cut', 1, pct=True)};
порог действия из функции потерь p* = {L.num('decision:binary_threshold_p_cut', 3)}. Сохранение: {L.num('decision:probabilities/Hold', 1, pct=True)}, повышение: {L.num('decision:probabilities/Increase', 1, pct=True)}.</p></section>
<section><h2>3. Доказательства</h2>{chart1}{chart2}{chart3}</section>
<section><h2>4. Прогноз</h2><p>Ожидаемая ставка после решения: {L.num('reality_check:expected_rate', 2)}%, 80% диапазон
{L.num('reality_check:interval_80/0', 2)}–{L.num('reality_check:interval_80/1', 2)}%; бенчмарк Always Hold: {L.num('reality_check:benchmark_always_hold', 2)}%.
Прошлый результат: отношение RMSE на holdout {L.num('n:rmse_ratio')} (интервал {L.num('n:rmse_ratio_ci_low')}–{L.num('n:rmse_ratio_ci_high')}, DM p = {L.num('n:dm_squared_error_p')}).
Прогноз записан до решения в <a href="forecasts.html">журнал прогнозов</a>.</p></section>
<section><h2>5. Механизм</h2><p>Порог зависит от того, во сколько раз упущенное снижение дороже ложного удлинения.</p>
<label for="ratio">Соотношение потерь r = L<sub>упущ.</sub>/L<sub>ложн.</sub>: <output id="ratio-out">1.0</output></label>
<input id="ratio" type="range" min="0.25" max="4" step="0.05" value="1" data-pcut="{p_cut!r}">
<p id="ratio-text" aria-live="polite">Порог p* = 0.500.</p></section>
<section><h2>6. Риск</h2><ul>{risk}</ul><p><a href="methods.html">Все пределы модели</a></p></section>
<section class="action"><h2>7. Действие</h2><p>Сейчас по бинарному правилу: <strong>{action}</strong>; по трёхисходным потерям: <strong>{best} дюрацию</strong>.
Ответ меняется, если вероятность снижения превысит {L.num('decision:binary_threshold_p_cut', 3)} или если упущенное снижение станет дороже ложного удлинения более чем в {L.num('decision:switch_ratio_miss_to_false', 2)} раза.</p></section>
<script src="assets/app.js"></script>
"""


def methods_page(L: Ledger) -> str:
    from src import model_card

    limits = "".join(f"<h3>{esc(i['title'])}</h3><p>{esc(i['text'])}</p>" for i in model_card.limits())
    return (f"<h1>Методы и пределы</h1><p>Модель: ordered logit на шести факторах, замороженная спецификация; holdout — последние "
            f"{L.num('n:n_holdout')} из {L.num('n:n_usable')} пригодных решений. {esc(L.raw('n:verdict_inference_sentence'))}</p>"
            f"<p>{esc(L.raw('n:rps_supplementary_sentence'))}</p><h2>Пределы</h2>{limits}"
            + md_to_html((ROOT / "docs" / "decision_memo.md").read_text(encoding="utf-8")))


def run_page() -> str:
    return """<h1>Запусти сам</h1><p>Всё работает офлайн из закоммиченных данных на Windows и Linux (Python 3.13).</p>
<pre><code>git clone https://github.com/lmamraimovasixseven/monetarot.git
cd monetarot
python -m pip install -r requirements-dev.txt
python run.py update      # данные → проверки → модель → прогнозы → журнал → site/
python run.py acceptance  # приёмные проверки
python run.py trace n:rmse_ratio</code></pre>
<p>Одна команда для make: <code>make update</code>.</p>"""


def sources_page() -> str:
    with (ROOT / "docs" / "facts_to_fill.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    body = "".join(f"<tr><td>{esc(r['series_file'])}</td><td>{esc(r['publisher'])}</td><td>{esc(r['url_or_api_query'])}</td>"
                   f"<td>{esc(r['publication_date'])}</td><td>{esc(r['retrieval_date'])}</td></tr>" for r in rows)
    external = json.loads((ROOT / "config" / "external_sources.json").read_text(encoding="utf-8"))["series"]
    ext = "".join(f"<tr><td>{esc(v['file'])}</td><td>{esc(v['publisher'])}</td><td>{esc(v['url'])}</td><td>{esc(v['release'])}</td>"
                  f"<td>{esc(v['retrieved'])}</td></tr>" for v in external.values())
    head = "<thead><tr><th>Файл</th><th>Издатель</th><th>URL</th><th>Публикация</th><th>Получено</th></tr></thead>"
    return (f"<h1>Источники</h1><div class=\"scroll\"><table>{head}<tbody>{body}</tbody></table></div><h2>Источники коридора</h2>"
            f"<div class=\"scroll\"><table>{head}<tbody>{ext}</tbody></table></div>" + md_to_html((ROOT / "docs" / "DATA.md").read_text(encoding="utf-8")))


def team_page() -> str:
    return "<h1>Команда</h1>" + md_to_html((ROOT / "docs" / "contributions.md").read_text(encoding="utf-8"))


def data_page() -> str:
    links = "".join(f'<li><a href="data/{Path(p).name}" download>{esc(p)}</a></li>' for p in DOWNLOADS if (ROOT / p).is_file())
    return f"<h1>Данные</h1><p>Файлы для скачивания (CSV, как в репозитории):</p><ul>{links}</ul>"


def patterns_page(L: Ledger, artifact: dict) -> str:
    block = artifact["patterns"]
    rows = "".join(f"<tr><td>{esc(k)}</td><td>{L.num(f'patterns:seasonality/{k}/F', 2)}</td><td>{L.num(f'patterns:seasonality/{k}/p_permutation', 3)}</td>"
                   f"<td>{L.num(f'patterns:seasonality/{k}/p_first_half', 3)}</td><td>{L.num(f'patterns:seasonality/{k}/p_second_half', 3)}</td>"
                   f"<td>{esc(v['verdict'])}</td></tr>" for k, v in block["seasonality"].items())
    episodes = "".join(f"<tr><td>{esc(e['series_file'])}</td><td>{esc(e['start'])}–{esc(e['end'])}</td><td>{esc(e['type'])}</td>"
                       f"<td>{esc(e['calendar_type'] or '—')}</td><td>{esc(e['reason'])}</td><td>{esc(e['known_at'])}</td></tr>"
                       for e in block["episodes"])
    return (f"<h1>Паттерны</h1><p>Преобразование: {esc(block['transform'])}. Ответ «нет» возможен и встречается.</p>"
            f"<div class=\"scroll\"><table><thead><tr><th>Ряд</th><th>F</th><th>p (перестановки)</th><th>p (1-я половина)</th><th>p (2-я половина)</th><th>Сезонность</th></tr></thead><tbody>{rows}</tbody></table></div>"
            + md_to_html((ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8"))
            + f"<h2>Выбросы (помечены, не удалены)</h2><div class=\"scroll\"><table><thead><tr><th>Ряд</th><th>Период</th><th>Тип (авто)</th><th>Тип (календарь)</th><th>Причина</th><th>Известно с</th></tr></thead><tbody>{episodes}</tbody></table></div>")


def corridor_page(L: Ledger, artifact: dict) -> str:
    block = artifact["carry_corridor"]
    partners = ", ".join(f"{esc(k)}: {esc(v if v is not None else block['partner_notes'][k])}" for k, v in block["partner_real_rates"].items())
    credit = block["credit_constraint"]
    return f"""<h1>Коридор ставки и carry trade</h1>
<p>Сценарный инструмент, не прогноз курса. Реальная ставка = номинальная − инфляция y/y. Сейчас ({esc(block['month'])}): ставка НБ {L.num('carry_corridor:nbk_rate', 2)}%,
инфляция {L.num('carry_corridor:kz_inflation', 2)}%, реальная ставка {L.num('carry_corridor:kz_real_rate', 2)}%. Реальные ставки партнёров: {partners}.</p>
<p>Ограничение по кредиту: наклон роста кредита через 6 мес. на реальную ставку {L.num('carry_corridor:credit_constraint/slope', 3)} ({esc(credit['note'])}).</p>
<p>Регрессия изменения USD/KZT на реальный дифференциал: {esc(block['fx_regression']['status'])}. Бенчмарк: {esc(block['benchmark'])}. {esc(block['panel_note'])}</p>
<form id="corridor" data-inflation="{float(block['kz_inflation'])!r}" data-credit="{json.dumps(credit['credit_zero_real_rate'])}">
<label>Ставка НБ, %: <output id="o-rate"></output><input id="c-rate" type="range" min="5" max="25" step="0.25" value="{float(block['nbk_rate'])!r}"></label>
<label>Реальная ставка РФ, % (условное значение, данных нет): <output id="o-ru"></output><input id="c-ru" type="range" min="-5" max="15" step="0.25" value="{float(block['kz_real_rate'])!r}"></label>
<label>Реальная ставка КНР, % (условное значение, данных нет): <output id="o-cn"></output><input id="c-cn" type="range" min="-5" max="10" step="0.25" value="{float(block['kz_real_rate'])!r}"></label>
<label>Премия за риск, п.п.: <output id="o-prem"></output><input id="c-prem" type="range" min="0" max="6" step="0.25" value="{block['defaults']['premium']!r}"></label>
<label>Потолок реального дифференциала, п.п.: <output id="o-cap"></output><input id="c-cap" type="range" min="1" max="12" step="0.25" value="{block['defaults']['cap']!r}"></label>
</form><p id="corridor-out" aria-live="polite"></p>
<script src="assets/corridor.js"></script><script src="assets/app.js"></script>"""


def forecasts_page(L: Ledger) -> str:
    rows = []
    with (ROOT / "docs" / "forecast_log.csv").open(encoding="utf-8", newline="") as handle:
        for i, r in enumerate(csv.DictReader(handle)):
            rows.append(f"<tr><td>{esc(r['logged_at_utc'])}</td><td>{esc(r['target_decision_date'])}</td><td>{L.num(f'forecast_log:{i}:p_decrease')}</td>"
                        f"<td>{L.num(f'forecast_log:{i}:p_hold')}</td><td>{L.num(f'forecast_log:{i}:p_increase')}</td><td>{L.num(f'forecast_log:{i}:expected_score')}</td>"
                        f"<td><code>{esc(r['artifact_sha256'][:12])}</code></td></tr>")
    desk = []
    with (ROOT / "ledger" / "forecast_ledger.csv").open(encoding="utf-8", newline="") as handle:
        for i, r in enumerate(csv.DictReader(handle)):
            desk.append(f"<tr><td>{esc(r['series'])}</td><td>{esc(r['cutoff'])}</td><td>{esc(r['target_month'])}</td><td>{esc(r['method'])}</td>"
                        f"<td>{L.num(f'forecast_ledger:{i}:point', None)}</td><td>{L.num(f'forecast_ledger:{i}:lower_80')}</td><td>{L.num(f'forecast_ledger:{i}:upper_80')}</td></tr>")
    return (f"<h1>Журнал прогнозов</h1><p>Записи только добавляются; коммит на GitHub — внешняя отметка времени.</p>"
            f"<h2>Решение НБ РК (docs/forecast_log.csv)</h2><div class=\"scroll\"><table><thead><tr><th>Записано (UTC)</th><th>Заседание</th><th>P(снижение)</th><th>P(сохранение)</th><th>P(повышение)</th><th>Ожидаемый балл</th><th>Хеш артефакта</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
            f"<h2>Ряды (ledger/forecast_ledger.csv)</h2><div class=\"scroll\"><table><thead><tr><th>Ряд</th><th>Отсечка</th><th>Месяц</th><th>Метод</th><th>Точка</th><th>80% от</th><th>80% до</th></tr></thead><tbody>{''.join(desk)}</tbody></table></div>")


def redteam_page() -> str:
    return md_to_html((ROOT / "docs" / "redteam_response.md").read_text(encoding="utf-8"))


def asof_page(L: Ledger, artifact: dict) -> str:
    views = artifact["patterns"]["as_of_views"]
    options = "".join(f'<option value="{esc(t)}">{esc(t)}</option>' for t in views)
    blocks = []
    for t, view in views.items():
        series = "".join(f"<tr><td>{esc(k)}</td><td>{esc(v['last_month'])}</td><td>{L.num(f'patterns:as_of_views/{t}/series/{k}/last_value', 2)}</td></tr>"
                         for k, v in view["series"].items())
        episodes = "".join(f"<li>{esc(e['series_file'])} {esc(e['start'])}: {esc(e['type'])} (известно с {esc(e['known_at'])})</li>" for e in view["episodes"][-5:])
        blocks.append(f'<div class="asof" data-t="{esc(t)}" hidden><div class="scroll"><table><thead><tr><th>Ряд</th><th>Последний известный месяц</th><th>Значение</th></tr></thead><tbody>{series}</tbody></table></div>'
                      f"<p>Последние известные к этой дате эпизоды:</p><ul>{episodes}</ul></div>")
    return (f"<h1>Просмотр на дату t</h1><p>{esc(next(iter(views.values()))['label'])}.</p><label for=\"asof-t\">Дата решения:</label> "
            f"<select id=\"asof-t\">{options}</select>{''.join(blocks)}<script src=\"assets/app.js\"></script>")


def build(site: Path = SITE) -> dict[str, Any]:
    started = time.perf_counter()
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    L = Ledger()
    if site.exists():
        shutil.rmtree(site)
    (site / "assets").mkdir(parents=True)
    (site / "data").mkdir()
    for name in ("style.css", "app.js", "corridor.js"):
        shutil.copy(ASSETS_SRC / name, site / "assets" / name)
    for relative in DOWNLOADS:
        if (ROOT / relative).is_file():
            shutil.copy(ROOT / relative, site / "data" / Path(relative).name)
    contents = {"index.html": index_page(L, artifact), "methods.html": methods_page(L), "run.html": run_page(),
                "sources.html": sources_page(), "team.html": team_page(), "data.html": data_page(),
                "patterns.html": patterns_page(L, artifact), "corridor.html": corridor_page(L, artifact),
                "forecasts.html": forecasts_page(L), "redteam.html": redteam_page(), "asof.html": asof_page(L, artifact)}
    titles = dict(PAGES)
    for name, body in contents.items():
        (site / name).write_text(page(titles[name], body, name), encoding="utf-8", newline="\n")
    (site / ".nojekyll").write_text("", encoding="utf-8")
    report = {"pages": sorted(contents), "ledger_ids_used": sorted(L.used),
              "index_bytes_with_assets": sum((site / p).stat().st_size for p in ("index.html", "assets/style.css", "assets/app.js"))}
    (site / "build_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    report["seconds"] = round(time.perf_counter() - started, 2)
    return report


def main() -> int:
    report = build()
    print(f"Wrote site/: {len(report['pages'])} pages, {len(report['ledger_ids_used'])} ledger numbers, "
          f"index + assets {report['index_bytes_with_assets']} bytes, {report['seconds']} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
