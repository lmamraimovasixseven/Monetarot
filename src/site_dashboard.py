"""Элементы Render-приложения (src/app.py) на статичном сайте: карточки раундов, метрики, таблицы, графики, слайдер.

Все значения берутся из блока `dashboard` model/artifact.json через журнал доказательств (Ledger из
src/site_build.py), каждое число помечено data-ledger. Форматы чисел повторяют src/app.py (_metric_text, _fmt3,
_probability_display). Соответствие элементов: docs/site_parity.md.
"""

from __future__ import annotations

import html
import json
import re
from datetime import date
from typing import Any

from src.site_i18n import tr as english

# Палитра Render (зелёный / синий / красный) в оттенках Okabe–Ito: различимы при дальтонизме; цвет никогда не
# единственный признак — у каждой полосы подпись и значок (▲ ■ ▼).
CLASS_TONE = {"Increase": "tone-increase", "Hold": "tone-hold", "Decrease": "tone-decrease"}
CLASS_MARK = {"Increase": "▲", "Hold": "■", "Decrease": "▼"}
CLASS_COLOUR = {"Increase": "#009E73", "Hold": "#6E6E6E", "Decrease": "#D55E00"}
DISPLAY = ["Increase", "Hold", "Decrease"]


def esc(text: Any) -> str:
    return html.escape(str(text))


def md_inline(text: str) -> str:
    """**жирный** из фраз app.py → <strong>; остальное экранируется."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc(text))


def signed(value: float, digits: int) -> str:
    """Round first, then sign (D42): a value that rounds to zero is shown as 0.000, never as -0.000 or +0.000."""
    text = f"{value:.{digits}f}"
    if float(text) == 0:
        return f"{0.0:.{digits}f}"
    return ("+" if value > 0 else "") + text


def plain(value: float, digits: int) -> str:
    """Unsigned format without a negative zero: -0.00004 → 0.0000 (D42)."""
    text = f"{value:.{digits}f}"
    return f"{0.0:.{digits}f}" if float(text) == 0 else text


def fmt_number(value: float, kind: str) -> str:
    if kind in ("f3", "f3na"):
        return plain(value, 3)
    if kind == "s3":
        return signed(value, 3)
    if kind == "s4":
        return signed(value, 4)
    if kind == "s1":
        return signed(value, 1)
    if kind == "pct1":
        return f"{value * 100:.1f}%"
    if kind == "c2":
        return f"{0.0:.2f}" if float(f"{value:.2f}") == 0 else f"{value:,.2f}"
    if kind == "int":
        return f"{int(value)}"
    if kind == "g4":
        return f"{int(value)}" if float(value).is_integer() and abs(value) < 1e15 else plain(value, 4)
    raise ValueError(kind)


MISSING = {"f3": "not reported", "f3na": "n/a"}


def cell(L, key: str, value: Any, kind: str) -> str:
    """Ячейка таблицы: число — из журнала (data-ledger), текст — как есть."""
    if isinstance(value, list):
        return "–".join(cell(L, f"{key}/{i}", v, kind) for i, v in enumerate(value))
    if isinstance(value, bool) or not isinstance(value, (int, float)) or kind in ("text", "verdict", "flag"):
        return esc(MISSING.get(kind, "") if value is None else english(value) if isinstance(value, str) else value)
    shown = fmt_number(float(L.raw(key)), kind)
    return f'<span class="num" data-ledger="{esc(key)}">{esc(shown)}</span>'


def render_table(L, prefix: str, tbl: dict[str, Any], caption: str = "", element_id: str = "") -> str:
    head = "".join(f"<th>{esc(c)}</th>" for c in tbl["columns"])
    body = []
    for i, row in enumerate(tbl["rows"]):
        cells = []
        for j, (value, kind) in enumerate(zip(row, tbl["formats"])):
            css = ""
            if kind == "verdict":
                css = ' class="v-bad"' if value == "Falsified" else ' class="v-ok"'
            cells.append(f"<td{css}>{cell(L, f'{prefix}/rows/{i}/{j}', value, kind)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    cap = f"<caption>{esc(caption)}</caption>" if caption else ""
    attr = f' id="{element_id}"' if element_id else ""
    return f'<div class="scroll"{attr}><table>{cap}<thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


# ----------------------------------------------------------------------------- шапка и карточки (вкладка Overview)

def long_date(day: date | None) -> str:
    """Как forecast_card_html: FRIDAY, 4 DECEMBER 2026 (английские названия, как в Render)."""
    return f"{day.strftime('%A').upper()}, {day.day} {day.strftime('%B %Y').upper()}" if day else "DATE NOT CONFIRMED"


def short_date(day: date | None) -> str:
    return f"{day.day} {day.strftime('%B %Y')}" if day else "date not confirmed"


def _date(text: str | None) -> date | None:
    return date.fromisoformat(text) if text else None


def headline(L, d: dict) -> str:
    most = d["most_likely"]
    first = _date(d["rounds"]["default"][0])
    return f"""<div class="metrics" id="headline">
<div class="metric"><p class="m-label">Policy pressure score</p><p class="m-value">{L.num('dashboard:score', 3, signed=True)}</p>
<p class="m-cap">95% band: {L.num('dashboard:band/0', 3, signed=True)} to {L.num('dashboard:band/1', 3, signed=True)}</p><p class="m-cap">{esc(d['direction_flag'])}</p></div>
<div class="metric"><p class="m-label">Change versus previous decision</p><p class="m-value">{L.num('dashboard:score_change', 3, signed=True)}</p>
<p class="m-cap">Versus the decision of {esc(d['previous_decision'])}</p></div>
<div class="metric"><p class="m-label">Most likely next outcome</p><p class="m-value">{esc(most)} · {L.num(f'dashboard:probabilities/{most}', 1, pct=True)}</p>
<p class="m-cap">Most likely at the next decision: {esc(most)} ({L.num(f'dashboard:probabilities/{most}', 1, pct=True)}); conditional model estimate, calibration unverified</p></div>
<div class="metric"><p class="m-label">Next scheduled decision</p><p class="m-value" id="next-decision">{esc(short_date(first))}</p>
<p class="m-cap">Announcement date from the NBK calendar in config/forecast_rounds.json</p></div></div>"""


def context_strip(d: dict) -> str:
    return f"""<div class="context" id="context"><p>Unit: {esc(d['unit'])}</p>
<p>Period: NBK decision of {esc(d['latest_decision'])}, factor data month {esc(d['data_month'])} ({esc(d['lag_label'])})</p>
<p>Latest change: <span class="num" data-ledger="dashboard:score_change">{signed(d['score_change'], 3)}</span> versus the decision of {esc(d['previous_decision'])}</p>
<p>Local factor data and model artifact as of {esc(d['latest_decision'])}. A static page does not contact the calendar source; round dates come from config/forecast_rounds.json.</p></div>"""


def round_card(L, number: int, day: date | None, d: dict) -> str:
    rows = []
    for label in DISPLAY:
        value = float(L.raw(f"dashboard:probabilities/{label}"))
        rows.append(
            f'<div class="probability-row{" is-top" if label == d["most_likely"] else ""}">'
            f'<span class="probability-label"><span aria-hidden="true" class="mark {CLASS_TONE[label]}">{CLASS_MARK[label]}</span> {label}</span>'
            f'<span class="probability-track" role="img" aria-label="{label} {value * 100:.1f} percent">'
            f'<span class="probability-fill {CLASS_TONE[label]}" style="width:{max(0.0, min(100.0, value * 100)):.1f}%"></span></span>'
            f'<span class="probability-value">{L.num(f"dashboard:probabilities/{label}", 1, pct=True)}</span>'
            f'<span class="probability-interval">95% CI {L.num(f"dashboard:intervals/{label}/0", 1, pct=True)}–{L.num(f"dashboard:intervals/{label}/1", 1, pct=True)}</span></div>')
    head = "NEXT DECISION" if number == 1 else "SECOND NEXT DECISION"
    return (f'<section class="forecast-card" id="round-{number}"><div class="forecast-card-head">ROUND {number} &nbsp;·&nbsp; {head}</div>'
            f'<h3 class="forecast-date" data-round="{number}">{esc(long_date(day))}</h3>{"".join(rows)}'
            f'<div class="forecast-card-foot">{esc(d["card_foot"])}</div></section>')


def round_cards(L, d: dict) -> str:
    days = [_date(x) for x in d["rounds"]["default"]]
    rounds = json.dumps(d["rounds"]["dates"])
    message = f'<p class="caption" id="rounds-message">{esc(d["rounds"]["default_message"])}</p>' if d["rounds"]["default_message"] else '<p class="caption" id="rounds-message"></p>'
    return (f'<h3>Next scheduled NBK decisions</h3>'
            f'<div class="cards" id="round-cards" data-rounds="{esc(rounds)}" data-latest="{esc(d["latest_decision"])}" data-verified="{str(d["rounds"]["verified"]).lower()}">'
            + "".join(round_card(L, i, day, d) for i, day in enumerate(days, start=1)) + "</div>"
            f'<p class="caption" id="rounds-caption">{esc(d["rounds_caption"])}</p>{message}'
            f'<details id="why"><summary>Why these probabilities?</summary><ul>'
            + "".join(f"<li>{md_inline(item)}</li>" for item in d["why"]) + "</ul></details>")


def rule_head(head: str) -> str:
    """'Decision rule (option 1: direction flag (band clear of zero)), a monitoring rule, not a forecast.' →
    'Decision rule: direction flag (the 95% band of the score is clear of zero). A monitoring rule, not a forecast.' (D42).
    A heading of another shape is shown as stored."""
    match = re.fullmatch(r"Decision rule \(option [^:]+: (.+?) \(band (.+?)\)\), (.+?)\.", head)
    if not match:
        return head
    name, band, kind = match.groups()
    return f"Decision rule: {name} (the 95% band of the score is {band}). {kind[0].upper()}{kind[1:]}."


def sentence_case(text: str) -> str:
    """A sentence that starts after '. ' starts with a capital letter."""
    return re.sub(r"(\.\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)


def holdout_sentence(L) -> str:
    """One sentence on the holdout for the home page (D42); the full paragraph with the data-update effect stays on
    Evidence. The verdict follows rule 14: distinguishable only if the bootstrap interval and the DM test both separate."""
    low, high = float(L.raw("n:rmse_ratio_ci_low")), float(L.raw("n:rmse_ratio_ci_high"))
    interval_separates, test_separates = not (low <= 1 <= high), float(L.raw("n:dm_squared_error_p")) < 0.05
    if interval_separates and test_separates:
        verdict = "the bootstrap interval and the Diebold–Mariano test both separate the model from Always Hold"
    elif interval_separates or test_separates:
        verdict = "the bootstrap interval and the Diebold–Mariano test disagree on whether the model differs from Always Hold"
    else:
        verdict = "the model cannot be distinguished from Always Hold"
    return (f"Holdout RMSE ratio {L.num('n:rmse_ratio')} (95% interval {L.num('n:rmse_ratio_ci_low')}–{L.num('n:rmse_ratio_ci_high')}, "
            f"Diebold–Mariano p = {L.num('n:dm_squared_error_p')}): {verdict}.")


def boxes(L, d: dict) -> str:
    rule = d.get("decision_rule")
    rule_html = (f'<div class="box info" id="decision-rule"><strong>{esc(rule_head(rule["head"]))}</strong> {esc(sentence_case(rule["text"]))}</div>'
                 if rule else '<div class="box info" id="decision-rule">Decision rule: not recorded.</div>')
    return (f'<div class="box info" id="verdict-box">{holdout_sentence(L)} <a href="evidence.html#ev-holdout">Details on Evidence</a></div>{rule_html}'
            f'<p class="caption" id="forecast-log">{esc(d["forecast_log_sentence"])} <a href="forecasts.html">Forecast log</a>.</p>')


# ----------------------------------------------------------------------------- графики (SVG без библиотек)

def _days(text: str) -> int:
    return date.fromisoformat(text).toordinal()


NUMBER_WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]


def number_word(n: int) -> str:
    return NUMBER_WORDS[n] if 0 <= n < len(NUMBER_WORDS) else str(n)


def track_record_title(L, tr: dict) -> str:
    """Conclusion title of the track-record chart, computed from the holdout points of the chart (D42)."""
    holdout = [i for i, day in enumerate(tr["dates"]) if day >= tr["holdout_start"]]
    scores = [float(L.raw(f"dashboard:track_record/score/{i}")) for i in holdout]
    actual = [int(L.raw(f"dashboard:track_record/actual/{i}")) for i in holdout]
    if all(s < 0 for s in scores):
        sign, lean = "The score stayed below zero throughout the holdout", -1
    elif all(s > 0 for s in scores):
        sign, lean = "The score stayed above zero throughout the holdout", 1
    else:
        sign, lean = "The score changed sign during the holdout", None
    counts = {k: actual.count(k) for k in (-1, 0, 1)}
    top = max(counts, key=counts.get)
    if list(counts.values()).count(counts[top]) > 1:
        return sign
    verb = {-1: "cut", 0: "held the rate", 1: "hiked"}[top]
    how = "at most decisions" if counts[top] * 2 > len(actual) else "more often than anything else"
    joint = "and" if top == lean else "while"
    return f"{sign}, {joint} the NBK {verb} {how}"


def contributions_title(names: list[str], values: list[float]) -> str:
    """Conclusion title of the contributions chart, computed from the bars (D42)."""
    n, down, up = len(values), sum(v < 0 for v in values), sum(v > 0 for v in values)
    if down == n:
        head = f"All {number_word(n)} factors push the score towards a cut"
    elif up == n:
        head = f"All {number_word(n)} factors push the score towards a hike"
    else:
        head = f"{number_word(down).capitalize()} of {number_word(n)} factors push the score towards a cut, {number_word(up)} towards a hike"
    order = sorted(range(n), key=lambda i: abs(values[i]), reverse=True)[:2]
    first, second = (names[i].lower() for i in order)
    a, b = first.rsplit(" ", 1), second.rsplit(" ", 1)
    pair = f"{a[0]} and {second}" if len(a) == len(b) == 2 and a[1] == b[1] else f"{first} and {second}"
    return f"{head}; {pair} most" if down == n or up == n else f"{head}; largest: {pair}"


def svg_track_record(L, d: dict, palette: dict[str, str]) -> str:
    """Track record of the score: линия балла, фактические решения (значок + цвет), holdout затенён."""
    tr = d["track_record"]
    width, height, left, right, top, bottom = 640, 300, 44, 10, 14, 34
    xs = [_days(x) for x in tr["dates"]]
    x0, x1 = min(xs), max(xs)
    x = lambda v: left + (width - left - right) * (v - x0) / (x1 - x0)  # noqa: E731
    y = lambda v: top + (height - top - bottom) * (1.05 - v) / 2.1  # noqa: E731
    alt = ("Policy pressure score implied by the stored model at each NBK decision (line) and the actual decision "
           "(triangle up = hike, square = hold, triangle down = cut); the holdout period is shaded.")
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(alt)}"><title>{esc(alt)}</title>',
             f'<rect x="{x(_days(tr["holdout_start"])):.1f}" y="{top}" width="{x(x1) - x(_days(tr["holdout_start"])):.1f}" height="{height - top - bottom}" fill="{palette["shade"]}"/>',
             f'<line x1="{left}" y1="{y(0):.1f}" x2="{width - right}" y2="{y(0):.1f}" stroke="{palette["grey"]}" stroke-dasharray="4 4"/>',
             f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" stroke="{palette["grey"]}"/>']
    for tick in (-1.0, -0.5, 0.0, 0.5, 1.0):
        parts.append(f'<text x="{left - 4}" y="{y(tick) + 4:.1f}" text-anchor="end" font-size="11" fill="{palette["black"]}">{signed(tick, 1)}</text>')
    years = sorted({t[:4] for t in tr["dates"]})
    for year in years[1::2]:
        xv = x(date(int(year), 1, 1).toordinal())
        if left <= xv <= width - right:
            parts.append(f'<text x="{xv:.1f}" y="{height - 12}" text-anchor="middle" font-size="11" fill="{palette["black"]}">{year}</text>')
    path = " ".join(f"{'M' if i == 0 else 'L'}{x(v):.1f},{y(float(L.raw(f'dashboard:track_record/score/{i}'))):.1f}" for i, v in enumerate(xs))
    parts.append(f'<path d="{path}" fill="none" stroke="{palette["blue"]}" stroke-width="2"/>')
    names = {-1: "Decrease", 0: "Hold", 1: "Increase"}
    for i, (xv, day) in enumerate(zip(xs, tr["dates"])):
        actual = int(L.raw(f"dashboard:track_record/actual/{i}"))
        score = float(L.raw(f"dashboard:track_record/score/{i}"))
        cx, cy, colour, label = x(xv), y(actual), CLASS_COLOUR[names[actual]], names[actual]
        tip = f"<title>{day}: {label}, score {signed(score, 3)}</title>"
        if actual == 1:
            parts.append(f'<path d="M{cx:.1f},{cy - 5:.1f} L{cx + 4.5:.1f},{cy + 3:.1f} L{cx - 4.5:.1f},{cy + 3:.1f} Z" fill="{colour}">{tip}</path>')
        elif actual == -1:
            parts.append(f'<path d="M{cx:.1f},{cy + 5:.1f} L{cx + 4.5:.1f},{cy - 3:.1f} L{cx - 4.5:.1f},{cy - 3:.1f} Z" fill="{colour}">{tip}</path>')
        else:
            parts.append(f'<rect x="{cx - 3:.1f}" y="{cy - 3:.1f}" width="6" height="6" fill="{colour}">{tip}</rect>')
        parts.append(f'<circle cx="{cx:.1f}" cy="{y(score):.1f}" r="2" fill="{palette["blue"]}"><title>{day}: score {signed(score, 3)}</title></circle>')
    # Date slider (D54): a cursor line that app.js moves; hidden until the script runs, so the static chart is unchanged.
    parts.append(f'<line id="tr-cursor" x1="0" y1="{top}" x2="0" y2="{height - bottom}" stroke="{palette["black"]}" '
                 'stroke-width="1.5" stroke-dasharray="3 3" visibility="hidden" aria-hidden="true"/>')
    parts.append("</svg>")
    title = track_record_title(L, tr)
    legend = ('<p class="legend"><span class="key" style="border-color:#0072B2">Score (−1 cut … +1 hike)</span>'
              '<span><span class="mark tone-increase">▲</span> Increase</span><span><span class="mark tone-hold-grey">■</span> Hold</span>'
              '<span><span class="mark tone-decrease">▼</span> Decrease</span><span class="key" style="border-color:#FFF4D6">Holdout</span></p>')
    caption = (f"Blue line: the policy pressure score implied by the stored model at each decision. Dots: what the NBK actually "
               f"decided (−1 cut, 0 hold, +1 hike). Shaded: holdout from {tr['holdout_start']}, where the frozen model is "
               "forecasting out of sample; earlier values are in-sample fits and flatter the model. A useful score would sit "
               "above zero before hikes and below zero before cuts.")
    return (f'<figure id="track-record"><figcaption><strong>{esc(title)}</strong></figcaption>{"".join(parts)}'
            f'{legend}<p class="caption">{esc(caption)}</p></figure>' + track_slider(L, d))


def track_slider(L, d: dict) -> str:
    """Date slider under the track-record chart (D54). It only reads numbers already in the ledger: the score and the
    actual decision at each date, and the probabilities and 95% band, which are stored for the latest decision only.
    The block is hidden until app.js runs, so the page without JavaScript is unchanged."""
    tr, n = d["track_record"], len(d["track_record"]["dates"])
    # Scores rounded to 6 decimals here (the page shows 3; the full value is in the ledger window) to keep the page small.
    data = {"dates": tr["dates"], "holdout_start": tr["holdout_start"],
            "score": [round(float(L.raw(f"dashboard:track_record/score/{i}")), 6) for i in range(n)],
            "actual": [int(L.raw(f"dashboard:track_record/actual/{i}")) for i in range(n)],
            "stored": {"date": d["latest_decision"],
                       "p": {c: float(L.raw(f"dashboard:probabilities/{c}")) for c in ("Decrease", "Hold", "Increase")},
                       "band": [float(L.raw("dashboard:band/0")), float(L.raw("dashboard:band/1"))]}}
    return (f'<div id="track-slider" class="track-slider" hidden><label for="tr-pos">Decision date</label>'
            f'<input id="tr-pos" type="range" min="0" max="{n - 1}" step="1" value="{n - 1}" aria-describedby="tr-hint">'
            '<p id="tr-hint" class="caption">Drag or use the arrow keys.</p>'
            '<div id="tr-out" class="tr-out" aria-live="polite"></div>'
            f'<script type="application/json" id="track-json">{json.dumps(data, separators=(",", ":"))}</script></div>')


def svg_contributions(L, d: dict, palette: dict[str, str]) -> str:
    rows = d["contributions"]["rows"]
    values = [float(L.raw(f"dashboard:contributions/rows/{i}/1")) for i in range(len(rows))]
    width, left, right, bar, gap = 640, 150, 70, 22, 10
    height = gap + len(rows) * (bar + gap) + 20
    span = max(abs(v) for v in values) or 1.0
    lo, hi = min(0.0, min(values)), max(0.0, max(values))
    scale = (width - left - right) / ((hi - lo) or span)
    zero = left + (0 - lo) * scale
    alt = "Horizontal bars: contribution of each factor to the latest change of the score; labels show the signed value."
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(alt)}"><title>{esc(alt)}</title>',
             f'<line x1="{zero:.1f}" y1="{gap / 2}" x2="{zero:.1f}" y2="{height - 18}" stroke="{palette["grey"]}"/>']
    for i, (row, v) in enumerate(zip(rows, values)):
        top = gap + i * (bar + gap)
        x_start, length = (zero, v * scale) if v >= 0 else (zero + v * scale, -v * scale)
        colour = palette["blue"] if v >= 0 else palette["vermillion"]
        parts.append(f'<text x="{left - 6}" y="{top + bar / 2 + 4:.1f}" text-anchor="end" font-size="12" fill="{palette["black"]}">{esc(row[0])}</text>')
        parts.append(f'<rect x="{x_start:.1f}" y="{top}" width="{max(length, 0.5):.1f}" height="{bar}" fill="{colour}"><title>{esc(row[0])}: {signed(v, 4)}</title></rect>')
        parts.append(f'<text x="{(zero + v * scale + 6) if v >= 0 else (zero + 6):.1f}" y="{top + bar / 2 + 4:.1f}" font-size="12" fill="{palette["black"]}">{signed(v, 4)}</text>')
    parts.append("</svg>")
    title = contributions_title([row[0] for row in rows], values)
    return f'<figure><figcaption><strong>{esc(title)}</strong> (blue: pushes towards a hike, vermillion: towards a cut)</figcaption>{"".join(parts)}</figure>'


def drivers(L, d: dict, palette: dict[str, str]) -> str:
    rows = d["contributions"]["rows"]
    order = sorted(range(len(rows)), key=lambda i: abs(float(L.raw(f"dashboard:contributions/rows/{i}/1"))), reverse=True)[:3]
    cards = "".join(f'<div class="metric"><p class="m-label">Driver {rank}: {esc(rows[i][0])}</p>'
                    f'<p class="m-value">{L.num(f"dashboard:contributions/rows/{i}/1", 4, signed=True)}</p></div>'
                    for rank, i in enumerate(order, start=1))
    return (f'<div id="drivers"><h3>Latest score-change contributions</h3><p class="caption">Top three drivers by absolute contribution</p>'
            f'<div class="metrics three">{cards}</div>{svg_contributions(L, d, palette)}'
            + render_table(L, "dashboard:contributions", d["contributions"])
            + '<p class="caption">Contributions come from the model artifact; the stored method notes that they are not additive.</p></div>')


def svg_history(L, d: dict, palette: dict[str, str]) -> str:
    """History: базовая ставка (ступени) и направление решений −1/0/+1 (ступени), как _render_history."""
    h = d["history"]

    def step_chart(dates: list[str], key: str, n: int, lo: float, hi: float, ticks: list[tuple[float, str]], alt: str, colour: str, h_px: int) -> str:
        width, left, right, top, bottom = 640, 92, 10, 10, 26
        xs = [_days(t) for t in dates]
        x0, x1 = min(xs), max(xs)
        x = lambda v: left + (width - left - right) * (v - x0) / (x1 - x0)  # noqa: E731
        y = lambda v: top + (h_px - top - bottom) * (hi - v) / (hi - lo)  # noqa: E731
        values = [float(L.raw(f"{key}/{i}")) for i in range(n)]
        path, previous = [], None
        for i, (xv, v) in enumerate(zip(xs, values)):
            path.append(f"M{x(xv):.1f},{y(v):.1f}" if i == 0 else f"L{x(xv):.1f},{y(previous):.1f} L{x(xv):.1f},{y(v):.1f}")
            previous = v
        parts = [f'<svg viewBox="0 0 {width} {h_px}" role="img" aria-label="{esc(alt)}"><title>{esc(alt)}</title>',
                 f'<line x1="{left}" y1="{top}" x2="{left}" y2="{h_px - bottom}" stroke="{palette["grey"]}"/>']
        for value, label in ticks:
            parts.append(f'<text x="{left - 4}" y="{y(value) + 4:.1f}" text-anchor="end" font-size="11" fill="{palette["black"]}">{esc(label)}</text>')
        for year in sorted({t[:4] for t in dates})[1::2]:
            xv = x(date(int(year), 1, 1).toordinal())
            parts.append(f'<text x="{xv:.1f}" y="{h_px - 8}" text-anchor="middle" font-size="11" fill="{palette["black"]}">{year}</text>')
        parts.append(f'<path d="{" ".join(path)}" fill="none" stroke="{colour}" stroke-width="2"/></svg>')
        return "".join(parts)

    charts = []
    if h["base_rate"]:
        rates = [float(L.raw(f"dashboard:history/base_rate/{i}")) for i in range(len(h["base_rate"]))]
        lo, hi = min(rates) - 1, max(rates) + 1
        ticks = [(v, f"{v:g}%") for v in range(int(lo) + 1, int(hi) + 1, 2)]
        charts.append(step_chart(h["rate_dates"], "dashboard:history/base_rate", len(rates), lo, hi, ticks,
                                 "Step line: NBK base rate after each decision, percent.", palette["orange"], 200))
    charts.append(step_chart(h["dates"], "dashboard:history/score", len(h["dates"]), -1.2, 1.2,
                             [(-1, "Decrease (-1)"), (0, "Hold (0)"), (1, "Increase (+1)")],
                             "Step line: direction of each NBK decision (−1 decrease, 0 hold, +1 increase).", palette["black"], 230))
    # Conclusion title from the plotted series (audit D52): how often the NBK held and the range of the base rate.
    scores = [int(float(L.raw(f"dashboard:history/score/{i}"))) for i in range(len(h["dates"]))]
    title = f"The NBK held the rate at {scores.count(0)} of {len(scores)} decisions"
    if h["base_rate"]:
        peak = max(range(len(rates)), key=lambda i: rates[i])
        title += (f"; the base rate ranged from {min(rates):g}% to {max(rates):g}%, "
                  f"highest from {h['rate_dates'][peak]}")
    return (f'<section id="ev-history"><h2>History</h2><figure><figcaption><strong>{esc(title)}</strong></figcaption>'
            f'{"".join(charts)}</figure><p class="caption">{esc(h["source"])}</p></section>')


# ----------------------------------------------------------------------------- сценарий (вкладка Drivers and scenario)

def scenario(L, d: dict) -> str:
    m = d["model"]
    features = m["features"]
    model_json = {"features": features, "labels": m["labels"],
                  "slopes": [float(L.raw(f"dashboard:model/slopes/{i}")) for i in range(len(features))],
                  "cutpoints": [float(L.raw(f"dashboard:model/cutpoints/{i}")) for i in range(2)],
                  "names": m["covariance_names"],
                  "covariance": [[float(L.raw(f"dashboard:model/covariance/{i}/{j}")) for j in range(len(m["covariance_names"]))]
                                 for i in range(len(m["covariance_names"]))],
                  "latest": [float(L.raw(f"dashboard:model/latest/{i}")) for i in range(len(features))],
                  "z": float(L.raw("dashboard:model/z_975")),
                  "slider": [{"min": float(L.raw(f"dashboard:slider/{i}/min")), "max": float(L.raw(f"dashboard:slider/{i}/max")),
                              "step": float(L.raw(f"dashboard:slider/{i}/step")), "baseline": float(L.raw(f"dashboard:slider/{i}/baseline"))}
                             for i in range(len(features))]}
    default = features.index(d["slider_default"])
    options = "".join(f'<option value="{i}"{" selected" if i == default else ""}>{esc(label)}</option>' for i, label in enumerate(m["labels"]))
    s = model_json["slider"][default]
    probs = "".join(f'<div class="metric"><p class="m-label">Scenario P({label})</p><p class="m-value" id="sc-p-{label}">'
                    f'{L.num(f"dashboard:probabilities/{label}", 1, pct=True)}</p><p class="m-cap" id="sc-d-{label}">0.0 pp</p></div>' for label in DISPLAY)
    return f"""<div id="scenario"><h3>Scenario control</h3>
<p class="caption">Change one observed factor while holding the other latest inputs fixed. The interval uses the stored covariance and delta method.</p>
<script type="application/json" id="model-json">{json.dumps(model_json)}</script>
<label for="sc-factor">Factor to change</label><select id="sc-factor">{options}</select>
<label for="sc-value"><span id="sc-name">{esc(m['labels'][default])}</span>: <output id="sc-out">{plain(s['baseline'], 2)}</output></label>
<input id="sc-value" type="range" min="{s['min']!r}" max="{s['max']!r}" step="any" value="{s['baseline']!r}">
<p class="range-ends"><span id="sc-min">{plain(s['min'], 2)}</span><span id="sc-max">{plain(s['max'], 2)}</span></p>
<div class="metrics"><div class="metric"><p class="m-label">Scenario policy pressure score</p><p class="m-value" id="sc-score">{L.num('dashboard:score', 3, signed=True)}</p>
<p class="m-cap" id="sc-delta">0.000 vs latest</p></div></div>
<p class="caption" id="sc-band">95% delta-method band: [{L.num('dashboard:band/0', 3, signed=True)}, {L.num('dashboard:band/1', 3, signed=True)}]</p>
<div class="metrics three">{probs}</div>
<p class="caption">Only the selected factor moves; the other five stay at their latest values. Computed in your browser from the stored coefficients, cutpoints and covariance (same formulas as src/app.py).</p></div>"""
