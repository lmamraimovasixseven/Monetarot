"""Static site site/ (block G): `python run.py site`.

Reads only model/artifact.json, the files it points to (evidence ledger, forecast logs, outputs/ tables) and the
project documents. Every number on a page comes from ledger/evidence_ledger.csv by id and carries the attribute
data-ledger="id" (`python run.py trace <id>`). Charts are inline SVG in the Okabe–Ito palette (colour-blind safe), each
with a conclusion title and an aria-label. No external fonts, scripts or CDN. The site is English: Russian text from the
artifact and the generated documents goes through src/site_i18n.py (D41), and every written file is checked for
Cyrillic.
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

from src import site_dashboard as sd
from src.site_i18n import assert_no_cyrillic, tr

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
ASSETS_SRC = ROOT / "src" / "site_assets"
LEDGER = ROOT / "ledger" / "evidence_ledger.csv"
ARTIFACT = ROOT / "model" / "artifact.json"
PALETTE = {"blue": "#0072B2", "orange": "#E69F00", "vermillion": "#D55E00", "green": "#009E73", "sky": "#56B4E9",
           "grey": "#6E6E6E", "black": "#000000", "shade": "#FFF4D6"}
PAGES = [("index.html", "Home"), ("evidence.html", "Evidence"), ("methods.html", "Methods and limits"), ("run.html", "Run it yourself"),
         ("sources.html", "Sources"), ("team.html", "Team"), ("data.html", "Data"), ("patterns.html", "Patterns"),
         ("corridor.html", "Corridor"), ("forecasts.html", "Forecast log"), ("redteam.html", "Red-team response"),
         ("asof.html", "As-of view")]
DESCRIPTIONS = {
    "index.html": "Should a bond manager extend duration before the next National Bank of Kazakhstan rate decision? Forecast, evidence and risks.",
    "evidence.html": "Holdout comparison, falsification, diagnostics, robustness, stress tests and history of the NBK decision model.",
    "methods.html": "Methods, limits, open statuses and the decision memo of the NBK decision model.",
    "run.html": "How to rebuild the data, model, forecasts and this site offline with one command.",
    "sources.html": "Data sources, publication and retrieval dates, and the data audit by series.",
    "team.html": "Who did what in the project.",
    "data.html": "Downloadable data files and data provenance.",
    "patterns.html": "Seasonality tests, STL window choice and flagged outliers.",
    "corridor.html": "Scenario tool: policy-rate corridor from the carry-trade point of view.",
    "forecasts.html": "Append-only log of forecasts made before NBK decisions.",
    "redteam.html": "Response to the red-team review.",
    "asof.html": "What the data looked like at past decision dates.",
}
EN_CLASS = {"Increase": "a rate hike", "Hold": "a hold", "Decrease": "a rate cut"}
EN_ACTION = {"lengthen": "extend duration", "keep": "keep duration", "shorten": "shorten duration"}
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December"]


def plain_date(iso: str | None) -> str:
    """2026-12-04 → 4 December 2026."""
    if not iso:
        return ""
    year, month, day = (int(part) for part in iso.split("-"))
    return f"{day} {MONTH_NAMES[month - 1]} {year}"
DOWNLOADS = ["data/processed/nbk_decisions_clean.csv", "data/processed/model_panel.csv", "ledger/evidence_ledger.csv",
             "ledger/forecast_ledger.csv", "docs/forecast_log.csv", *[f"data/raw/{p.name}" for p in sorted((ROOT / "data" / "raw").glob("*.csv"))]]


class Ledger:
    """Source of every number on the site: the value by id from the evidence ledger; the ids used are recorded."""

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
            value = sd.signed(number, digits) if signed else sd.plain(number, digits)
            value += "%" if pct else ""
        return f'<span class="num" data-ledger="{html.escape(key)}">{html.escape(value)}</span>'


def esc(text: Any) -> str:
    return html.escape(str(text))


def page(title: str, body: str, current: str) -> str:
    nav = " ".join(f'<a href="{href}"{" aria-current=\"page\"" if href == current else ""}>{esc(label)}</a>'
                   for href, label in PAGES)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · Monetarot</title><meta name="description" content="{esc(DESCRIPTIONS[current])}">
<link rel="icon" href="data:,"><link rel="stylesheet" href="assets/style.css"></head>
<body><header><p class="brand">Monetarot · NBK rate decisions</p><nav aria-label="Site sections">{nav}</nav></header>
<main>{body}</main>
<footer><p>Generated by <code>python run.py site</code> from <code>model/artifact.json</code>. Every number has a row in the
<a href="data/evidence_ledger.csv">evidence ledger</a>.</p></footer></body></html>
"""


# ----------------------------------------------------------------------------- charts

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
        parts.append(f'<text x="{left - 4}" y="{y(tick) + 4:.1f}" text-anchor="end" font-size="11" fill="{PALETTE["black"]}">{sd.plain(tick, 2)}</text>')
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
        parts.append(f'<text x="{left + length + 6:.1f}" y="{top + bar_h / 2 + 4:.1f}" font-size="12" fill="{PALETTE["black"]}">{sd.plain(value, 3)}</text>')
    return f'<figure><figcaption><strong>{esc(title)}</strong></figcaption>{"".join(parts)}</svg></figure>'


# ----------------------------------------------------------------------------- markdown → html (tables, paragraphs, lists)

def inline(text: str) -> str:
    """Escaped text with **bold** and `code` from the markdown documents."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc(text))
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", text)


def md_to_html(text: str) -> str:
    """Headings, paragraphs, bullet lists and tables of a project document; each line goes through src/site_i18n.py."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    out, table, items = [], [], []

    def flush() -> None:
        if table:
            rows = [r for r in table if not re.fullmatch(r"\|[\s\-|:]+\|", r)]
            cells = [[inline(tr(c.strip())) for c in r.strip().strip("|").split("|")] for r in rows]
            head = "".join(f"<th>{c}</th>" for c in cells[0])
            body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in cells[1:])
            out.append(f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')
            table.clear()
        if items:
            out.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ul>")
            items.clear()

    for line in text.splitlines():
        if line.startswith("|"):
            table.append(line)
            continue
        if line.startswith("- "):
            items.append(tr(line)[2:])
            continue
        flush()
        if line.startswith("#"):
            english = tr(line)
            level = min(len(english) - len(english.lstrip("#")) + 1, 4)
            out.append(f"<h{level}>{inline(english.lstrip('#').strip())}</h{level}>")
        elif line.strip():
            out.append(f"<p>{inline(tr(line.strip()))}</p>")
    flush()
    return "\n".join(out)


# ----------------------------------------------------------------------------- pages

def site_links() -> dict[str, str]:
    """Addresses of the site and of the Render app (config/site_links.json); an unknown address is UNKNOWN and is not shown on the home page."""
    path = ROOT / "config" / "site_links.json"
    links = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return {"render_url": str(links.get("render_url") or "UNKNOWN"), "pages_url": str(links.get("pages_url") or "UNKNOWN")}


def raw_units() -> dict[str, str]:
    """Unit of the raw series behind each model factor, from docs/facts_to_fill.csv (column unit); '' if not documented."""
    from src.ingest import FEATURE_RULES

    with (ROOT / "docs" / "facts_to_fill.csv").open(encoding="utf-8", newline="") as handle:
        file_units = {r["series_file"]: (r["unit"] or "").strip() for r in csv.DictReader(handle)}
    units = {key: file_units.get(filename, "") for key, (filename, _) in FEATURE_RULES.items()}
    return {key: unit if unit and "UNKNOWN" not in unit else "" for key, unit in units.items()}


SOURCE_UNITS_UNKNOWN = "underlying source units UNKNOWN"


def unit_text(model: dict, label: str, text: str) -> str:
    """The artifact's model-input unit with 'underlying source units UNKNOWN' replaced by the unit documented in
    docs/facts_to_fill.csv, so Data, Methods and As-of state the same fact (D43). The artifact itself is unchanged."""
    feature = dict(zip(model["labels"], model["features"])).get(label)
    unit = raw_units().get(feature, "") if feature else ""
    return text.replace(SOURCE_UNITS_UNKNOWN, f"underlying source units: {unit} (docs/facts_to_fill.csv)") if unit else text


def aligned_latest(dashboard: dict) -> dict:
    """Copy of the 'Factor / Latest value / Model input unit' table with units aligned by unit_text."""
    table = dashboard["provenance"]["latest"]
    rows = [[row[0], row[1], unit_text(dashboard["model"], row[0], row[2])] for row in table["rows"]]
    return {**table, "rows": rows}


def look_ahead_box(L: Ledger, model: dict, sentence: str | None) -> str:
    """One sentence for step 6 (D43, D44): 'Look-ahead cannot be excluded: real publication lags are not documented
    (exports: N of M decisions; …)'. Each count is the ledger row lookahead:<factor> (from data/processed/provenance.json,
    src/ledger.py::look_ahead_rows) and the total is n:n_usable; factors with no affected decision are left out."""
    link = 'Details: <a href="evidence.html#ev-limitations">Evidence → Limitations</a>.'
    counts = [(feature, label) for feature, label in zip(model["features"], model["labels"])
              if f"lookahead:{feature}" in L.values and float(L.values[f"lookahead:{feature}"]) > 0]
    if not counts:
        return f"{esc(sentence or 'Look-ahead status: see Evidence → Limitations.')} {link}"
    counts.sort(key=lambda item: -float(L.values[f"lookahead:{item[0]}"]))
    parts = "; ".join(f"{esc(label.lower())}: {L.num(f'lookahead:{feature}')} of {L.num('n:n_usable')}"
                      + (" decisions" if i == 0 else "") for i, (feature, label) in enumerate(counts))
    extra = re.search(r"No upper bound is available for [^.]+\.[^.]*\.", sentence or "")
    return (f"Look-ahead cannot be excluded: real publication lags are not documented ({parts})."
            + (f" {esc(extra.group(0))}" if extra else "") + f" {link}")


def index_page(L: Ledger, artifact: dict) -> str:
    decision, rc, d = artifact["decision"], artifact["reality_check"], artifact["dashboard"]
    links = site_links()
    p_cut = float(L.raw("decision:p_cut"))
    threshold = float(L.raw("decision:binary_threshold_p_cut"))
    action = "Extend duration" if p_cut > threshold else "Do not extend duration"
    # Step 7 caveat: the binary answer flips when P(cut) crosses p*, in the direction that applies now.
    crossing = "falls below" if p_cut > threshold else "rises above"
    most = d["most_likely"]
    band_lo, band_hi = float(L.raw("dashboard:band/0")), float(L.raw("dashboard:band/1"))
    next_round = d["rounds"]["default"][0]
    question = (f"Should a bond manager extend duration before the NBK decision on {plain_date(next_round)}?" if next_round else
                "Should a bond manager extend duration before the next NBK decision?")
    # Step 2: the obvious view and one fact from the artifact that complicates it.
    obvious = (f"The obvious view: the most likely outcome is {EN_CLASS[most]} "
               f"({L.num(f'dashboard:probabilities/{most}', 1, pct=True)}).")
    if band_lo <= 0 <= band_hi:
        complication = (f"The complication: the probability of a cut ({L.num('dashboard:probabilities/Decrease', 1, pct=True)}) has a 95% interval of "
                        f"{L.num('dashboard:intervals/Decrease/0', 1, pct=True)}–{L.num('dashboard:intervals/Decrease/1', 1, pct=True)}, "
                        f"and the 95% band of the pressure score ({L.num('dashboard:band/0', 3, signed=True)} to {L.num('dashboard:band/1', 3, signed=True)}) "
                        "includes zero, so the model cannot tell pressure towards a cut from pressure towards a hike.")
    else:
        side = "above" if band_lo > 0 else "below"
        complication = (f"The complication: the 95% band of the pressure score ({L.num('dashboard:band/0', 3, signed=True)} to "
                        f"{L.num('dashboard:band/1', 3, signed=True)}) lies entirely {side} zero, although the most likely outcome is {EN_CLASS[most]}.")
    loss_slider = "" if d["losses_confirmed"] else (
        '<p>The loss ratio is an assumption. Move it to see how the threshold changes.</p>'
        '<label for="ratio">Loss ratio r = L<sub>miss</sub>/L<sub>false</sub>: <output id="ratio-out">1.00</output></label>'
        f'<input id="ratio" type="range" min="0.25" max="4" step="0.05" value="1" data-pcut="{p_cut!r}" aria-label="Loss ratio of a missed cut to a false extension">'
        '<p id="ratio-text" aria-live="polite"></p>')
    render_link = (f'<a id="render-link" href="{esc(links["render_url"])}">interactive version (Render)</a>'
                   if links["render_url"].startswith("https://") else
                   '<a id="render-link" href="methods.html#render-app">interactive version (Streamlit app)</a>')
    rps_model, rps_freq = float(L.raw("n:rps_model")), float(L.raw("n:rps_class_frequency"))
    rps = [("model", rps_model, PALETTE["blue"]), ("class frequencies", rps_freq, PALETTE["sky"]),
           ("Always Hold", float(L.raw("n:rps_hold")), PALETTE["grey"])]
    # Title wording from the numbers: within 5% of the class-frequency RPS reads as "barely differs".
    relation = ("barely differs from" if abs(rps_model - rps_freq) < 0.05 * rps_freq else
                "is lower than" if rps_model < rps_freq else "is higher than")
    chart_rps = svg_bars(f"On RPS the model {relation} simple class frequencies (lower is better)",
                         "Bars: ranked probability score on the holdout for the model, class frequencies and Always Hold.", rps)
    # Step 6 limits: the holdout comparison (first limit) is the verdict box of step 4 and the RPS comparison (second) is the
    # chart of step 3; the publication-lag limit is the look-ahead box of step 6 (D42: no repetition).
    limits = __import__("src.model_card", fromlist=["limits"]).limits()[2:4]
    risk = "".join(f"<li><strong>{esc(tr(i['title']))}.</strong> {esc(tr(i['text']))}</li>" for i in limits)
    anomaly = (f'<div class="box warn" id="anomaly-warning">{esc(d["anomaly_warning"])} '
               f'<a href="evidence.html#ev-anomalies">Raw-data anomaly screen</a></div>' if d["anomaly_warning"] else
               '<div class="box info" id="anomaly-warning">No flagged raw-data jump enters the latest score.</div>')
    target = re.search(r"\d{4}-\d{2}-\d{2}", rc["target"])
    return f"""
<section class="lead" id="top"><p class="eyebrow">{esc(d['title'])}</p>
<h1>{esc(question)}</h1>
<p class="summary">{esc(d['intro'])} The forecast is turned into a duration decision with an explicit loss function, and the holdout comparison with Always Hold is shown as prominently as the forecast.</p>
<p class="links">This page is static and fast; there is also an {render_link}. Detailed tables are on the <a href="evidence.html">Evidence</a> page.</p>
{sd.context_strip(d)}</section>
<section id="step-1"><h2>1. The decision</h2><p>{esc(tr(decision['decision']))}</p></section>
<section id="step-2"><h2>2. The tension</h2><p>{obvious}</p><p>{complication}</p>
<p>Action threshold p* = {L.num('decision:binary_threshold_p_cut', 3)} <strong>with equal losses</strong>; probability of a cut {L.num('decision:p_cut', 1, pct=True)}.</p>{loss_slider}</section>
<section id="step-3"><h2>3. The evidence</h2>{sd.svg_track_record(L, d, PALETTE)}{sd.drivers(L, d, PALETTE)}{chart_rps}
<p><a href="evidence.html">Holdout, falsification, diagnostics, robustness, stress tests, history</a></p></section>
<section id="step-4"><h2>4. The forecast</h2>{sd.headline(L, d)}{sd.round_cards(L, d)}{sd.boxes(L, d)}
<p>Expected rate after the decision of {esc(target.group(0) if target else 'the next meeting')}: {L.num('reality_check:expected_rate', 2)}%, 80% range
{L.num('reality_check:interval_80/0', 2)}–{L.num('reality_check:interval_80/1', 2)}%; Always Hold benchmark: {L.num('reality_check:benchmark_always_hold', 2)}%.</p></section>
<section id="step-5"><h2>5. The mechanism</h2><p>How the pressure changes if you move one factor and keep the others at their latest values.</p>{sd.scenario(L, d)}</section>
<section id="step-6"><h2>6. The risk</h2>
<div class="box warn" id="freshness" hidden></div>{anomaly}
<div class="box info" id="staleness">Data as of the NBK decision of {esc(d['latest_decision'])} (factor data month {esc(d['data_month'])}). The probabilities are not recomputed for later meetings.</div>
<div class="box warn" id="look-ahead">{look_ahead_box(L, d["model"], d["look_ahead_sentence"])}</div>
<h3>Falsification</h3>{sd.render_table(L, 'dashboard:evidence/falsification', d['evidence']['falsification'], element_id='falsification')}
<ul>{risk}</ul><p><a href="methods.html">All model limits</a></p></section>
<section class="action" id="step-7"><h2>7. The ask</h2><p class="answer" id="answer"><strong>{action}.</strong></p>
<p class="caption">Caveat: this is the binary rule with equal losses from step 2. Under the three-outcome losses the action is: {EN_ACTION[decision['best_action']]}.
The answer changes if the probability of a cut {crossing} {L.num('decision:binary_threshold_p_cut', 3)}, or if a missed cut becomes more than {L.num('decision:switch_ratio_miss_to_false', 2)} times as costly as a false extension.</p></section>
<script src="assets/app.js"></script>
"""


def evidence_page(L: Ledger, artifact: dict) -> str:
    d = artifact["dashboard"]
    ev, full, stress = d["evidence"], d["full_results"], d["stress"]

    def T(path: str, tbl: dict) -> str:
        return sd.render_table(L, f"dashboard:{path}", tbl)

    robustness_caption = (
        "Ratios in different rows use different holdouts and are not comparable with each other. The differenced non-stationary-factor "
        "check first-differences household and corporate 12-month log growth and inflation; other factors retain their main-model "
        f"transformations. Total specifications run: {ev['robustness_total']}. Checks marked not comparable are left out of the count "
        f"of checks with an RMSE ratio below 1 ({ev['noncomparable_reason']}).")
    full_parts = "".join(
        f"<h4>{esc(title)}</h4>" + T(f"full_results/{key}", full[key])
        for title, key in (("Robustness coefficients by specification", "coefficient_detail"), ("Main-model coefficients", "coefficients"),
                           ("Robust (HC0) covariance", "covariance"), ("Expanding-window coefficients", "expanding"),
                           ("All unit-root checks", "unit_roots"), ("Structural-break checks", "structural_breaks"),
                           ("Economic size from artifact", "economic_size")))
    designs = stress["designs"]
    buttons = "".join(f'<button type="button" class="design-tab" data-design="{esc(x["key"])}" aria-pressed="{"true" if i == 0 else "false"}">{esc(x["label"])}</button>'
                      for i, x in enumerate(designs))
    panels = "".join(f'<div class="design-panel" data-design="{esc(x["key"])}"><h4>{esc(x["label"])}</h4><p class="caption">{esc(x["caption"])}</p>'
                     + T(f"stress/designs/{i}/table", x["table"]) + "</div>" for i, x in enumerate(designs))
    power = (T("evidence/power", ev["power"]) + f'<p class="caption">At this sample size (N = {esc(ev["power_n"])}), failure to reject a zero slope is not evidence that the factor has no effect.</p>'
             if ev["power"] else "<p>Power table: not available.</p>")
    ratio = float(L.raw("dashboard:evidence/ratio"))
    low, high = float(L.raw("n:rmse_ratio_ci_low")), float(L.raw("n:rmse_ratio_ci_high"))
    criterion = "Meets the pre-specified criterion" if ratio < 1 else "Does not meet the pre-specified criterion"
    distinct = ("separated from Always Hold by both the bootstrap interval and the Diebold–Mariano test"
                if not (low <= 1 <= high) and float(L.raw("n:dm_squared_error_p")) < 0.05 else "not distinguishable from Always Hold")
    return f"""<h1>Evidence</h1><p>Holdout comparison, falsification, diagnostics, robustness, stress tests and history of the model. The numbers
come from the <code>dashboard</code> block of the artifact; the model is not re-estimated here.</p>
<div class="box info" id="ev-summary">{esc(ev['summary'])}</div><p>{esc(ev['inference'])}</p><p>{esc(ev['version_change'])}</p>
<h2 id="ev-holdout">Holdout comparison</h2>{T('evidence/holdout', ev['holdout'])}
<p class="caption">RPS = ranked probability score (lower is better), exploratory and supplementary; the pre-specified verdict is the RMSE ratio.</p>
<p class="caption">Always Hold assigns probability zero to Increase and Decrease, so the log score cannot be computed on a holdout that contains them.</p>
<p class="caption" id="ev-criterion">{criterion} (RMSE ratio {L.num('dashboard:evidence/ratio', 3)}); {distinct}.</p>
<p class="caption">{esc(ev['verdict_rule'])}</p><p>{esc(ev['rps_sentence'])}</p>
<h2 id="ev-falsification">Falsification</h2>{T('evidence/falsification', ev['falsification'])}
<h2 id="ev-diagnostics">Diagnostics</h2>{T('evidence/diagnostics', ev['diagnostics'])}
<p class="caption" id="ev-na">Tests that do not apply to the ordinal model</p>{T('evidence/diagnostics_na', ev['diagnostics_na'])}
<h2 id="ev-robustness">Robustness specifications</h2>{T('evidence/robustness', ev['robustness'])}<p class="caption">{esc(robustness_caption)}</p>
<details id="ev-full"><summary>Full results stored in artifact</summary>{full_parts}</details>
<h2 id="ev-power">Power: minimum detectable effects</h2>{power}
<h2 id="ev-limitations">Limitations</h2>{''.join(f'<p>{esc(s)}</p>' for s in ev['limitations'])}
<p class="caption">Generated from config/release_lag.json, docs/facts_to_fill.csv and the raw files by <code>python run.py facts</code>.</p>
<h2 id="ev-stress">Stress tests (exploratory)</h2><div class="box warn">{esc(stress['label'])}</div>
<ul>{''.join(f'<li>{esc(s)}</li>' for s in stress['sentences'])}</ul>
<div id="ev-designs"><p class="m-label">Evaluation design</p><div class="design-tabs" role="group" aria-label="Evaluation design">{buttons}</div>{panels}
<p class="caption">RPS = ranked probability score of the three-class forecast (0 perfect, 0.5 = Always Hold on a cut or hike). RPS skill = 1 − RPS / RPS(Always Hold). DM = Harvey–Leybourne–Newbold-corrected Diebold–Mariano test against Always Hold. Ridge penalties are chosen at each forecast origin from earlier decisions only.</p></div>
<h3 id="ev-forecasts">Next-meeting probabilities under each specification</h3>{T('stress/forecasts', stress['forecasts'])}
<p class="caption">Disagreement between rows is model uncertainty that the single headline band does not show. The policy-rule rows use the NBK's own previous decision and the ex-post real rate.</p>
<details id="ev-anomalies"><summary>Raw-data anomaly screen ({len(stress['anomalies']['rows'])} flagged months)</summary>{T('stress/anomalies', stress['anomalies'])}
<p class="caption">Modified z-score of monthly changes (log change for levels, first difference for rates); flag at |z| ≥ {esc(stress['z_threshold'])}. A flag means: re-check this value against the publisher. Nothing is changed.</p></details>
{sd.svg_history(L, d, PALETTE)}
<script src="assets/app.js"></script>"""


def methods_page(L: Ledger, artifact: dict) -> str:
    from src import model_card

    decision, d = artifact["decision"], artifact["dashboard"]
    links = site_links()
    limits = "".join(f"<h3>{esc(tr(i['title']))}</h3><p>{esc(tr(i['text']))}</p>" for i in model_card.limits())
    render = (f'<p>Address of the Render app: <a href="{esc(links["render_url"])}">{esc(links["render_url"])}</a>.</p>'
              if links["render_url"].startswith("https://") else
              f'<p>The address of the Render app is not recorded in the repository ({esc(links["render_url"])}; see TODO_HUMAN.md). The app '
              "runs locally: <code>python run.py app</code> (address http://localhost:8503).</p>")
    static = ("<ul><li><strong>Tabs.</strong> The four Render tabs (Overview, Drivers and scenario, Evidence, Data and provenance) are spread over the seven steps on the home page and over the Evidence and Data pages.</li>"
              "<li><strong>NBK calendar check.</strong> Each time it opens, Render queries the calendar source and shows "
              "“CACHED DATA” if the source does not answer within 2 s. The static page contacts no external address; the round dates "
              "come from config/forecast_rounds.json and are chosen in the browser from today's date.</li>"
              "<li><strong>Render time.</strong> The line “Cached dashboard render time” belongs to the Streamlit server; a static "
              "page has none.</li><li><strong>Table sorting.</strong> Streamlit tables sort when you click a column header; here "
              "they are static, in the same row order.</li><li><strong>Scenario slider.</strong> It is recomputed in the browser with the same "
              "formulas (ordered logit and the delta method) as src/app.py; a test checks the match to 1e-6.</li></ul>")
    units = "".join(f"<li>{esc(row[0])}: {esc(row[2])}</li>" for row in aligned_latest(d)["rows"])
    return (f"<h1>Methods and limits</h1><p>Model: ordered logit on {len(d['model']['features'])} factors, frozen specification; holdout = the last "
            f"{L.num('n:n_holdout')} of {L.num('n:n_usable')} usable decisions. {esc(L.raw('n:verdict_inference_sentence'))}</p>"
            f"<p>{esc(L.raw('n:rps_supplementary_sentence'))}</p>"
            f'<h2 id="statuses">Statuses awaiting a person</h2><ul><li>Decision: {esc(tr(decision["decision_status"]))}.</li>'
            f'<li>Losses: {esc(tr(decision["loss_status"]))}. Until they are confirmed, the home page labels p* “with equal losses” '
            "and shows a loss-ratio slider next to it.</li>"
            f'<li>Round dates: the calendar is {"marked as verified" if d["rounds"]["verified"] else "not marked as verified"} '
            f'(source: {esc(d["rounds"]["source"])}). If fewer than two future dates are known, the second round card shows '
            "“DATE NOT CONFIRMED” with the same probabilities.</li></ul><h3>Units of the model factors</h3><ul>" + units + "</ul>"
            f'<h2 id="render-app">Interactive version (Render)</h2>{render}'
            f'<h2 id="static-limits">What the static page does differently</h2>{static}'
            f"<h2>Limits</h2>{limits}"
            + md_to_html((ROOT / "docs" / "decision_memo.md").read_text(encoding="utf-8")))


def run_page() -> str:
    return """<h1>Run it yourself</h1><p>Everything runs offline from the committed data on Windows and Linux (Python 3.13).</p>
<pre><code>git clone https://github.com/lmamraimovasixseven/monetarot.git
cd monetarot
python -m pip install -r requirements-dev.txt
python run.py update      # data → checks → model → forecasts → ledger → site/
python run.py acceptance  # acceptance checks
python run.py trace n:rmse_ratio</code></pre>
<p>The same as one make command: <code>make update</code> (needs make; on Windows run the python commands above).</p>"""


def sources_page() -> str:
    with (ROOT / "docs" / "facts_to_fill.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    body = "".join(f"<tr><td>{esc(r['series_file'])}</td><td>{esc(tr(r['publisher']))}</td><td>{esc(r['url_or_api_query'])}</td>"
                   f"<td>{esc(r['publication_date'])}</td><td>{esc(r['retrieval_date'])}</td></tr>" for r in rows)
    external = json.loads((ROOT / "config" / "external_sources.json").read_text(encoding="utf-8"))["series"]
    ext = "".join(f"<tr><td>{esc(v['file'])}</td><td>{esc(tr(v['publisher']))}</td><td>{esc(tr(v['url']))}</td><td>{esc(v['release'])}</td>"
                  f"<td>{esc(v['retrieved'])}</td></tr>" for v in external.values())
    head = "<thead><tr><th>File</th><th>Publisher</th><th>URL</th><th>Published</th><th>Retrieved</th></tr></thead>"
    return (f"<h1>Sources</h1><div class=\"scroll\"><table>{head}<tbody>{body}</tbody></table></div><h2>Corridor sources</h2>"
            f"<div class=\"scroll\"><table>{head}<tbody>{ext}</tbody></table></div>" + md_to_html((ROOT / "docs" / "DATA.md").read_text(encoding="utf-8")))


def team_page() -> str:
    return "<h1>Team</h1>" + md_to_html((ROOT / "docs" / "contributions.md").read_text(encoding="utf-8"))


def data_page(L: Ledger, artifact: dict) -> str:
    dashboard = artifact["dashboard"]
    d = dashboard["provenance"]
    links = "".join(f'<li><a href="data/{Path(p).name}" download>{esc(p)}</a></li>' for p in DOWNLOADS if (ROOT / p).is_file())
    return (f"<h1>Data</h1><p>Files to download (CSV, as in the repository):</p><ul>{links}</ul>"
            '<h2 id="data-provenance">Data and provenance</h2>'
            + sd.render_table(L, "dashboard:provenance/series", d["series"])
            + '<p class="caption">Source fields come from docs/facts_to_fill.csv via <code>python run.py facts</code>. Release lag = days '
            "from the end of the reference month to publication. Source titles, navigation paths and column headers are published in "
            "Russian and are shown here in English translation; the original wording is in docs/facts_to_fill.csv.</p>"
            + sd.render_table(L, "dashboard:provenance/values", d["values"], element_id="data-values")
            + sd.render_table(L, "dashboard:provenance/latest", aligned_latest(dashboard), element_id="data-latest")
            + '<p class="caption">Where the stored model-input unit gives the underlying source units as unknown but '
            "docs/facts_to_fill.csv records the unit of the raw series, the recorded unit is shown (D43).</p>")


def patterns_page(L: Ledger, artifact: dict) -> str:
    block = artifact["patterns"]
    rows = "".join(f"<tr><td>{esc(k)}</td><td>{L.num(f'patterns:seasonality/{k}/F', 2)}</td><td>{L.num(f'patterns:seasonality/{k}/p_permutation', 3)}</td>"
                   f"<td>{L.num(f'patterns:seasonality/{k}/p_first_half', 3)}</td><td>{L.num(f'patterns:seasonality/{k}/p_second_half', 3)}</td>"
                   f"<td>{esc(tr(v['verdict']))}</td></tr>" for k, v in block["seasonality"].items())
    episodes = "".join(f"<tr><td>{esc(e['series_file'])}</td><td>{esc(e['start'])}–{esc(e['end'])}</td><td>{esc(e['type'])}</td>"
                       f"<td>{esc(e['calendar_type'] or '—')}</td><td>{esc(tr(e['reason']))}</td><td class=\"nowrap\">{esc(e['known_at'])}</td></tr>"
                       for e in block["episodes"])
    return (f"<h1>Patterns</h1><p>Transformation: {esc(tr(block['transform']))}. The answer “no” is possible and does occur.</p>"
            f"<div class=\"scroll\"><table><thead><tr><th>Series</th><th>F</th><th>p (permutations)</th><th>p (first half)</th><th>p (second half)</th><th>Seasonality</th></tr></thead><tbody>{rows}</tbody></table></div>"
            + md_to_html((ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8"))
            + f"<h2>Outliers (flagged, not removed)</h2><div class=\"scroll\"><table><thead><tr><th>Series</th><th>Period</th><th>Type (automatic)</th><th>Type (calendar)</th><th>Reason</th><th class=\"nowrap\">Known from</th></tr></thead><tbody>{episodes}</tbody></table></div>")


def corridor_page(L: Ledger, artifact: dict) -> str:
    block = artifact["carry_corridor"]
    rates = block["partner_real_rates"]
    labels = {key: tr(label) for key, label in block.get("partner_labels", {}).items()}
    differentials = block.get("real_differentials", {})
    partners = "; ".join(
        f"{esc(labels.get(k, k))}: {L.num(f'carry_corridor:partner_real_rates/{k}', 2)}% ({esc(tr(block['partner_notes'][k]))}"
        + (f"; real differential KZ − {esc(labels.get(k, k))} {L.num(f'carry_corridor:real_differentials/{k}', 2, signed=True)} pp"
           if differentials.get(k) is not None else "") + ")"
        if v is not None else f"{esc(labels.get(k, k))}: {esc(tr(block['partner_notes'][k]))}" for k, v in rates.items())
    credit = block["credit_constraint"]
    kz_real = float(block["kz_real_rate"])
    china_series = json.loads((ROOT / "config" / "external_sources.json").read_text(encoding="utf-8"))["series"]["cn_policy_rate"]
    china_caveat = (f'<p class="caption" id="china-rate">China\'s rate: {esc(tr(china_series["title"]))}. It is a lending benchmark, '
                    "not the return on a short-term deposit, so the real rate and the corridor for China rest on a lending rate (D47).</p>"
                    if rates.get("china") is not None else "")

    def partner(key: str) -> tuple[float, str]:
        value = rates.get(key)
        return (kz_real, " (illustrative value; no data)") if value is None else (float(value), f" (data: {tr(block['partner_notes'][key])})")

    (ru, ru_note), (cn, cn_note) = partner("russia"), partner("china")
    # Without a real rate for every partner the position verdict would rest on invented numbers: the page shows only the
    # corridor bounds of the user's assumptions (D42), and the bounds in the artifact stay UNKNOWN (D46).
    partner_data = "true" if all(v is not None for v in rates.values()) else "false"
    missing = ", ".join(labels.get(k, k) for k, v in rates.items() if v is None)
    fx = block["fx_regression"]
    if fx.get("status") == "ok":
        p = "carry_corridor:fx_regression"
        months = fx.get("differential_months", {})
        regression = (f"<p>Regression of the monthly change of 100·log USD/KZT (monthly mean of the official NBK rate) on the real "
                      f"differential {esc(tr(fx['differential']))}, months {esc(months.get('first', ''))}–{esc(months.get('last', ''))}: "
                      f"differential at t−1: coefficient {L.num(f'{p}/specifications/lag1/coef', 3, signed=True)} (HC1 s.e. "
                      f"{L.num(f'{p}/specifications/lag1/se', 3)}, p = {L.num(f'{p}/specifications/lag1/p', 3)}, R² = "
                      f"{L.num(f'{p}/specifications/lag1/r2', 3)}, n = {L.num(f'{p}/specifications/lag1/n')}); with t−1 and t−2: "
                      f"coefficient on t−1 {L.num(f'{p}/specifications/lag1_lag2/coef', 3, signed=True)} (p = "
                      f"{L.num(f'{p}/specifications/lag1_lag2/p', 3)}), VIF {L.num(f'{p}/vif/diff', 2)}. Verdict: {esc(tr(fx['verdict']))}. "
                      + ("The sign is positive: a higher differential is followed by a rise in USD/KZT (a weaker tenge), the "
                         "opposite of what carry-trade inflows would imply. "
                         if float(L.raw(f"{p}/specifications/lag1/coef")) > 0 else
                         "The sign is negative: a higher differential is followed by a fall in USD/KZT (a stronger tenge), as "
                         "carry-trade inflows would imply. ")
                      + "This is an in-sample association, not a causal estimate and not a forecast; omitted variables such as the "
                      "oil price, global risk appetite and the rouble can bias it.</p>"
                      f"<p>Benchmark: {esc(tr(block['benchmark']))}; mean absolute monthly change of 100·log USD/KZT "
                      f"{L.num(f'{p}/random_walk_mae_of_change', 3)}. {esc(tr(block['panel_note']))}</p>")
        # D47: the same regression on the differential to each partner separately.
        parts = []
        for key, item in fx.get("by_partner", {}).items():
            name = esc(labels.get(key, key))
            if item.get("status") == "ok":
                q = f"{p}/by_partner/{key}/specifications/lag1"
                parts.append(f"<li>KZ − {name}: coefficient on the differential at t−1 {L.num(f'{q}/coef', 3, signed=True)} "
                             f"(HC1 s.e. {L.num(f'{q}/se', 3)}, p = {L.num(f'{q}/p', 3)}, R² = {L.num(f'{q}/r2', 3)}, "
                             f"n = {L.num(f'{q}/n')}); {esc(tr(item['verdict']))}.</li>")
            else:
                parts.append(f"<li>KZ − {name}: {esc(tr(item['status']))}.</li>")
        if parts:
            regression += f'<p id="fx-by-partner">The same regression on the differential to each partner separately:</p><ul>{"".join(parts)}</ul>'
    else:
        regression = (f"<p>Regression of the USD/KZT change on the real differential: {esc(tr(fx['status']))}. "
                      f"Benchmark: {esc(tr(block['benchmark']))}. {esc(tr(block['panel_note']))}</p>")
    return f"""<h1>Policy-rate corridor and carry trade</h1>
<p>A scenario tool, not an exchange-rate forecast. Real rate = nominal rate − year-on-year inflation; a partner's monthly rate is the
average over the calendar days of the month. Now ({esc(block['month'])}): NBK rate {L.num('carry_corridor:nbk_rate', 2)}%,
inflation {L.num('carry_corridor:kz_inflation', 2)}%, real rate {L.num('carry_corridor:kz_real_rate', 2)}%. Partner real rates: {partners}.</p>{china_caveat}
<p id="corridor-bounds">Corridor bounds: {esc(tr(block['current']['status'])) if block['current']['status'] != 'ok' else
f"{L.num('carry_corridor:current/lower', 2)}–{L.num('carry_corridor:current/upper', 2)}% with the default risk premium and cap "
f"(upper bound set by {'the credit constraint' if block['current'].get('binding_upper') == 'credit' else 'the cap on the real differential'}); "
f"the NBK rate of {L.num('carry_corridor:nbk_rate', 2)}% is {esc(tr(block['current']['position']))}"}.</p>
<p>Credit constraint: slope of credit growth 6 months ahead on the real rate {L.num('carry_corridor:credit_constraint/slope', 3)} ({esc(tr(credit['note']))}).</p>
{regression}
<form id="corridor" autocomplete="off" data-inflation="{float(block['kz_inflation'])!r}" data-credit="{json.dumps(credit['credit_zero_real_rate'])}" data-partner-data="{partner_data}" data-missing="{esc(missing)}">
<label>NBK rate, %: <output id="o-rate"></output><input id="c-rate" type="range" min="5" max="25" step="0.25" value="{float(block['nbk_rate'])!r}"></label>
<label>Russia real rate, %{esc(ru_note)}: <output id="o-ru"></output><input id="c-ru" type="range" min="-5" max="15" step="0.05" value="{ru!r}"></label>
<label>China real rate, %{esc(cn_note)}: <output id="o-cn"></output><input id="c-cn" type="range" min="-5" max="10" step="0.05" value="{cn!r}"></label>
<label>Risk premium, pp: <output id="o-prem"></output><input id="c-prem" type="range" min="0" max="6" step="0.25" value="{block['defaults']['premium']!r}"></label>
<label>Cap on the real differential, pp: <output id="o-cap"></output><input id="c-cap" type="range" min="1" max="12" step="0.25" value="{block['defaults']['cap']!r}"></label>
</form><p id="corridor-out" aria-live="polite"></p>
<p class="caption">Default risk premium and cap: {esc(tr(block['defaults_status']))}.</p>
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
            desk.append(f"<tr><td>{esc(r['series'])}</td><td>{esc(r['cutoff'])}</td><td>{esc(r['target_month'])}</td><td>{esc(tr(r['method']))}</td>"
                        f"<td>{L.num(f'forecast_ledger:{i}:point', None)}</td><td>{L.num(f'forecast_ledger:{i}:lower_80')}</td><td>{L.num(f'forecast_ledger:{i}:upper_80')}</td></tr>")
    return (f"<h1>Forecast log</h1><p>Entries are only ever appended; the GitHub commit is the external timestamp.</p>"
            f"<h2>NBK decision (docs/forecast_log.csv)</h2><div class=\"scroll\"><table><thead><tr><th>Logged (UTC)</th><th>Meeting</th><th>P(cut)</th><th>P(hold)</th><th>P(hike)</th><th>Expected score</th><th>Artifact hash</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
            f"<h2>Series (ledger/forecast_ledger.csv)</h2><div class=\"scroll\"><table><thead><tr><th>Series</th><th>Cutoff</th><th>Month</th><th>Method</th><th>Point</th><th>80% lower</th><th>80% upper</th></tr></thead><tbody>{''.join(desk)}</tbody></table></div>")


def redteam_page() -> str:
    """The template in docs/redteam_response.md stays for the person who fills it; while it still has [FILL IN] cells the
    review has not happened and the page says so in one sentence instead of showing an empty table (D42)."""
    text = (ROOT / "docs" / "redteam_response.md").read_text(encoding="utf-8")
    if "[FILL IN]" in text:
        return ("<h1>Red-team response</h1><p>The red-team review has not taken place yet. "
                "Responses will be added here after it.</p>")
    return md_to_html(text)


def asof_page(L: Ledger, artifact: dict) -> str:
    views = artifact["patterns"]["as_of_views"]
    # A value without a documented unit is not shown (D42).
    units = raw_units()
    documented = bool
    options = "".join(f'<option value="{esc(t)}">{esc(t)}</option>' for t in views)
    blocks = []
    for t, view in views.items():
        series = "".join(f"<tr><td>{esc(k)}</td><td>{esc(v['last_month'])}</td>"
                         + (f"<td>{L.num(f'patterns:as_of_views/{t}/series/{k}/last_value', 2)}</td><td>{esc(tr(units.get(k, '')))}</td></tr>"
                            if documented(units.get(k, "")) else "<td>units not documented</td><td>units not documented</td></tr>")
                         for k, v in view["series"].items())
        episodes = "".join(f"<li>{esc(e['series_file'])} {esc(e['start'])}: {esc(e['type'])} (known from {esc(e['known_at'])})</li>" for e in view["episodes"][-5:])
        blocks.append(f'<div class="asof" data-t="{esc(t)}" hidden><div class="scroll"><table><thead><tr><th>Series</th><th>Last known month</th><th>Value</th><th>Unit</th></tr></thead><tbody>{series}</tbody></table></div>'
                      f"<p>Latest episodes known by this date:</p><ul>{episodes}</ul></div>")
    label = next(iter(views.values()))["label"]
    intro = ("What the model could have known on a past decision date. Revised-data backtest: current values, availability "
             "follows the publication-lag assumption, not real vintages." if label.startswith("revised-data backtest") else
             f"What the model could have known on a past decision date. {tr(label)}.")
    return (f"<h1>As-of view</h1><p>{esc(intro)}</p><label for=\"asof-t\">Decision date:</label> "
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
    contents = {"index.html": index_page(L, artifact), "evidence.html": evidence_page(L, artifact), "methods.html": methods_page(L, artifact), "run.html": run_page(),
                "sources.html": sources_page(), "team.html": team_page(), "data.html": data_page(L, artifact),
                "patterns.html": patterns_page(L, artifact), "corridor.html": corridor_page(L, artifact),
                "forecasts.html": forecasts_page(L), "redteam.html": redteam_page(), "asof.html": asof_page(L, artifact)}
    titles = dict(PAGES)
    for name, body in contents.items():
        text = page(titles[name], body, name)
        assert_no_cyrillic(name, text)
        (site / name).write_text(text, encoding="utf-8", newline="\n")
    for asset in sorted((site / "assets").iterdir()):
        assert_no_cyrillic(f"assets/{asset.name}", asset.read_text(encoding="utf-8"))
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
