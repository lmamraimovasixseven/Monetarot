"""Russia, China, ECB on corridor.html (D59): partner rates as context and mechanism, never as a proven driver.

Every number written on the page is a ledger row (`partners:` from model/extensions/partner_context.json, `ovb:` from
model/extensions/ovb_check.json, `carry_corridor:` from the artifact). The chart series are read at build time from the
stored files through src/partner_context.history() and embedded as JSON; site/assets/partners.js only redraws them
(series on or off, nominal or real, date range, crosshair) and picks among stored what-if rows. Nothing is estimated in
the browser or here.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Callable

from src import site_dashboard as sd
from src import site_interactive as si

ROOT = Path(__file__).resolve().parents[1]
CONTEXT_PATH = ROOT / "model" / "extensions" / "partner_context.json"
OVB_PATH = ROOT / "model" / "extensions" / "ovb_check.json"
PALETTE = sd.PALETTE
PARTNERS = ["ru_key_rate", "cn_policy_rate", "ecb_deposit_rate"]
NAMES = {"nbk": "NBK base rate", "ru_key_rate": "Russia key rate", "cn_policy_rate": "China policy rate",
         "ecb_deposit_rate": "ECB deposit rate"}
SHORT = {"ru_key_rate": "Russia", "cn_policy_rate": "China", "ecb_deposit_rate": "ECB"}
# Series colours from the palette (no outcome-class colour); each line also has its own dash, so colour is not the only cue.
SERIES_STYLE = {"nbk": ("ink", ""), "ru_key_rate": ("orange", ""), "cn_policy_rate": ("sky", "6 4"), "ecb_deposit_rate": ("black", "2 3")}
GEOM = [640, 300, 44, 12, 12, 30]  # width, height, left, right, top, bottom: the same numbers drive partners.js
OUTCOMES = [("Increase", "increase"), ("Hold", "hold"), ("Decrease", "decrease")]
GROUP_LABELS = [("rise", "After a partner rate rise"), ("cut", "After a partner rate cut"),
                ("mixed", "After both a rise and a cut"),
                ("change_matched_to_an_earlier_decision", "Partner change in the window, matched to an earlier NBK decision"),
                ("no_change_in_window", "Baseline: no partner change in the window")]
SPEC_FOR = {"ru_key_rate": "plus_ru_key_rate", "cn_policy_rate": "plus_cn_policy_rate", "ecb_deposit_rate": "plus_ecb_deposit_rate"}
TRADE_GROUP = {"russia": "russia", "china": "china", "italy": "euro", "netherlands": "euro"}
TRADE_GROUP_NAMES = {"russia": "Russia", "china": "China", "euro": "Euro area (named partners)", "other": "Other named partners"}
TRADE_GROUP_COLOUR = {"russia": "orange", "china": "sky", "euro": "black", "other": "blue"}


def esc(text: Any) -> str:
    return html.escape(str(text))


def context() -> dict[str, Any]:
    return json.loads(CONTEXT_PATH.read_text(encoding="utf-8"))


def available() -> bool:
    return CONTEXT_PATH.is_file() and OVB_PATH.is_file()


def mark(cls: str) -> str:
    tone = sd.CLASS_TONE[cls] if cls != "Hold" else "tone-hold-grey"
    return f'<span aria-hidden="true" class="mark {tone}">{sd.CLASS_MARK[cls]}</span> {cls}'


# ----------------------------------------------------------------------------- lead: the model check comes first

def finding(L, headline: str) -> str:
    label = json.loads(OVB_PATH.read_text(encoding="utf-8"))["label"]
    return (f'<p class="p-lead" id="partners-finding"><strong>Omitted-variable check (exploratory, after the holdout was seen):</strong> '
            f"{headline}</p><p class=\"caption\">{esc(label)} <a href=\"#partners-model\">What the model says</a>.</p>"
            "<p>On this page the Russian, Chinese and ECB rates are context and mechanism for the corridor, not a proven "
            "driver of NBK decisions.</p>")


# ----------------------------------------------------------------------------- trade shares (why these partners)

def trade(L, sources: dict[str, Any]) -> str:
    c = context()["trade"]
    spec = sources["context"]["kz_export_shares_2025"]
    shares = c["shares_pct"]
    top = max(shares.values())
    rows = []
    for key, value in shares.items():
        group = TRADE_GROUP.get(key, "other")
        width = 100 * value / top
        rows.append(f'<li class="tb-row tb-{group}"><span class="tb-name">{esc(key.capitalize())}'
                    + (f'<span class="tb-group"> {esc(TRADE_GROUP_NAMES[group])}</span>' if group in ("euro", "other") else "") + "</span>"
                    f'<span class="tb-track"><span class="tb-bar" style="--w:{width:.1f}%"></span></span>'
                    f'<span class="tb-val">{L.num(f"partners:trade/shares_pct/{key}", 1)}%</span></li>')
    year = c["year"]
    sums = (f"<p>Arithmetic on the stated shares: Russia and China together {L.num('partners:trade/sums_pct/russia_and_china', 1)}% "
            f"({L.num('partners:trade/shares_pct/russia', 1)} + {L.num('partners:trade/shares_pct/china', 1)}); the two named "
            f"euro-area partners, Italy and the Netherlands, {L.num('partners:trade/sums_pct/named_euro_area_partners', 1)}% "
            f"({L.num('partners:trade/shares_pct/italy', 1)} + {L.num('partners:trade/shares_pct/netherlands', 1)}). The euro-area "
            f"total may be higher: the release names {L.num('partners:trade/named_partners')} partners only, so no euro-area total "
            "is computed. These are main partners by export share; Italy and the Netherlands use the euro, whose policy rate the ECB sets.</p>")
    return (f'<h2 id="partners-trade">Where Kazakhstan\'s exports go, {esc(year)}</h2>'
            f'<figure id="trade-bars" class="ichart"><figcaption><strong>Italy, China and Russia take the largest named shares of '
            f"Kazakhstan's {esc(year)} exports</strong></figcaption>"
            f'<ul class="trade-bars" aria-label="Share of {esc(year)} exports by named partner, percent">{"".join(rows)}</ul>'
            f'<p class="caption">Total exports {L.num("partners:trade/total_exports_mln_usd", 1)} million US dollars. Source: '
            f'{esc(spec["publisher"])}, "{esc(spec["title"])}", <a href="{esc(spec["url"])}">{esc(spec["url"])}</a>; '
            f"published {esc(spec['release'])}; retrieved {esc(spec['retrieved'])}.</p></figure>{sums}")


# ----------------------------------------------------------------------------- line charts (explorer and spreads)

def _ticks(lo: float, hi: float) -> list[float]:
    span = hi - lo
    step = next(s for s in (0.5, 1, 2, 5, 10, 20) if span / s <= 6)
    first = int(lo // step + 1) * step
    out, v = [], first
    while v < hi:
        out.append(round(v, 6))
        v += step
    return out


def _svg(fig: str, data: dict[str, Any], mode: str, keys: list[str], unit: str, zero: bool, alt: str) -> str:
    width, height, left, right, top, bottom = GEOM
    series = data["modes"][mode]
    values = [v for k in keys if k in series for v in series[k] if v is not None] + ([0.0] if zero else [])
    lo, hi = min(values), max(values)
    pad = (hi - lo) * 0.06 or 1.0
    lo, hi = lo - pad, hi + pad
    months = data["months"]
    n = len(months) - 1
    x = lambda i: left + (width - left - right) * i / n  # noqa: E731
    y = lambda v: top + (height - top - bottom) * (hi - v) / (hi - lo)  # noqa: E731
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(alt)}"><title>{esc(alt)}</title><g class="pticks">']
    for tick in _ticks(lo, hi):
        parts.append(f'<line x1="{left}" y1="{y(tick):.1f}" x2="{width - right}" y2="{y(tick):.1f}" class="pgrid"/>'
                     f'<text x="{left - 4}" y="{y(tick) + 4:.1f}" text-anchor="end">{sd.plain(tick, 0 if tick == int(tick) else 1)}{esc(unit)}</text>')
    for i, m in enumerate(months):
        if m.endswith("-01") and int(m[:4]) % 2 == 1:
            parts.append(f'<text x="{x(i):.1f}" y="{height - 10}" text-anchor="middle">{m[:4]}</text>')
    parts.append("</g>")
    if zero:
        parts.append(f'<line class="pzero" x1="{left}" y1="{y(0):.1f}" x2="{width - right}" y2="{y(0):.1f}"/>')
    for key in keys:
        if key not in series:
            continue
        d, pen = [], "M"
        for i, v in enumerate(series[key]):
            if v is None:
                pen = "M"
                continue
            d.append(f"{pen}{x(i):.1f},{y(v):.1f}")
            pen = "L"
        parts.append(f'<path class="pline ps-{key}" d="{" ".join(d)}"/>')
    parts.append(f'<line class="pcursor" x1="0" y1="{top}" x2="0" y2="{height - bottom}" visibility="hidden"/></svg>')
    return "".join(parts)


def _series_buttons(keys: list[str], label: str) -> str:
    return "".join(f'<button type="button" class="pill" data-series="{k}" aria-pressed="true"><span class="key ks-{k}" aria-hidden="true"></span>'
                   f"{esc(label.format(name=SHORT.get(k, NAMES[k]), full=NAMES[k]))}</button>" for k in keys)


def _tools(fig: str, keys: list[str], label: str, real: bool) -> str:
    modes = ('<div class="chart-tools" role="group" aria-label="Nominal or real" hidden>'
             '<button type="button" class="pill" data-mode="nominal" aria-pressed="true">Nominal</button>'
             '<button type="button" class="pill" data-mode="real" aria-pressed="false">Real</button></div>') if real else ""
    ranges = ('<div class="chart-tools" role="group" aria-label="Date range" hidden>'
              + "".join(f'<button type="button" class="pill" data-range="{k}" aria-pressed="{"true" if k == "all" else "false"}">{t}</button>'
                        for k, t in (("all", "All months"), ("5y", "Last 5 years"), ("2y", "Last 2 years"))) + "</div>")
    series = f'<div class="chart-tools" role="group" aria-label="Series shown" hidden>{_series_buttons(keys, label)}</div>'
    return series + modes + ranges


def _legend(keys: list[str], label: str) -> str:
    return '<p class="legend">' + "".join(
        f'<span class="key ks-{k}">{esc(label.format(name=SHORT.get(k, NAMES[k]), full=NAMES[k]))}</span>' for k in keys) + "</p>"


def _fallback_table(data: dict[str, Any], keys: list[str], label: str, caption: str) -> str:
    modes = list(data["modes"])
    head = "".join(f"<th>{esc(label.format(name=SHORT.get(k, NAMES[k]), full=NAMES[k]))}{' (' + m + ')' if len(modes) > 1 else ''}</th>"
                   for m in modes for k in keys if k in data["modes"][m])
    body = []
    for i in range(len(data["months"]) - 1, -1, -1):
        cells = "".join(f"<td>{'' if data['modes'][m][k][i] is None else sd.plain(data['modes'][m][k][i], 2)}</td>"
                        for m in modes for k in keys if k in data["modes"][m])
        body.append(f"<tr><th>{data['months'][i]}</th>{cells}</tr>")
    return (f'<details class="ptable"><summary>{esc(caption)}</summary><div class="scroll"><table><thead><tr><th>Month</th>{head}</tr></thead>'
            f"<tbody>{''.join(body)}</tbody></table></div></details>")


def line_figure(fig: str, title: str, alt: str, data: dict[str, Any], keys: list[str], label: str, unit: str, zero: bool,
                real: bool, notes: str, table_caption: str) -> str:
    payload = dict(data, geom=GEOM, unit=unit, zero=zero,
                   labels={k: label.format(name=SHORT.get(k, NAMES[k]), full=NAMES[k]) for k in keys})
    return (f'<figure id="{fig}" class="ichart pchart"><figcaption><strong>{title}</strong></figcaption>'
            f"{_tools(fig, keys, label, real)}"
            f'<div class="pplot" tabindex="0" role="group" aria-label="{esc(alt)} Use the left and right arrow keys to read the values by month." '
            f'aria-describedby="{fig}-read">{_svg(fig, data, "nominal", keys, unit, zero, alt)}</div>'
            f"{_legend(keys, label)}"
            f'<p class="caption pread" id="{fig}-read" aria-live="polite">Static view: all months, nominal. With JavaScript, hover, touch or use the '
            "arrow keys on the chart to read each month; the buttons switch series, nominal or real, and the date range.</p>"
            f"{notes}{_fallback_table(data, keys, label, table_caption)}"
            f'<script type="application/json" class="pdata">{json.dumps(payload, separators=(",", ":"))}</script></figure>')


def _chart_data(hist: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    r = lambda vs: [None if v is None else round(v, 3) for v in vs]  # noqa: E731
    explorer = {"months": hist["months"], "modes": {
        "nominal": {k: r(hist[k]) for k in ["nbk", *PARTNERS]},
        "real": {"nbk": r(hist["nbk_real"]), **{k: r(hist[f"{k}_real"]) for k in PARTNERS if f"{k}_real" in hist}}}}

    def minus(a: list, b: list) -> list:
        return [None if p is None or q is None else round(p - q, 3) for p, q in zip(a, b)]

    spread = {"months": hist["months"], "modes": {
        "nominal": {k: minus(hist["nbk"], hist[k]) for k in PARTNERS},
        "real": {k: minus(hist["nbk_real"], hist[f"{k}_real"]) for k in PARTNERS if f"{k}_real" in hist}}}
    return explorer, spread


def rates(L, hist: dict[str, Any], sources: dict[str, Any]) -> str:
    c = context()
    explorer, spread = _chart_data(hist)
    no_real = [k for k in PARTNERS if f"{k}_real" not in hist]
    real_note = (f'<p class="caption preal-note">Real rate = nominal rate − year-on-year inflation, monthly (the calendar-day mean of the '
                 f"rate). {', '.join(NAMES[k] for k in no_real)}: nominal only; no euro-area inflation is stored, so the real view leaves it out.</p>"
                 if no_real else "")
    pubs = "; ".join(f"{NAMES[k]}: {esc(sources['series'][k]['publisher'])}, stored to {esc(c['latest'][k]['date'])}" for k in PARTNERS)
    latest = "; ".join(
        f"{NAMES[k]} {L.num(f'partners:latest/{k}/nominal', 2)}% on {esc(c['latest'][k]['date'])}"
        + (f" (real {L.num(f'partners:latest/{k}/real', 2)}% in {esc(c['latest'][k]['real_month'])})" if "real" in c["latest"][k] else "")
        for k in PARTNERS)
    figure = line_figure(
        "px", f"Partner rates next to the NBK base rate, {esc(hist['months'][0][:4])} to {esc(hist['months'][-1][:4])}",
        "Lines: NBK base rate and the Russia, China and ECB policy rates by month, percent.", explorer,
        ["nbk", *PARTNERS], "{full}", "%", False, True,
        real_note + f'<p class="caption">Monthly calendar-day mean of each stored daily rate ({pubs}); NBK base rate from '
        "data/raw/base_rate_history.csv. China's rate is a lending benchmark (LPR 1Y), see the limitations below.</p>",
        "Data table: monthly values, newest first")
    return (f'<h2 id="partners-rates">Partner rates next to the NBK base rate</h2>'
            f"<p>Latest stored values: NBK base rate {L.num('partners:latest/nbk/rate', 2)}% after the decision of "
            f"{esc(c['latest']['nbk']['date'])}; {latest}.</p>{figure}")


def spreads(L, hist: dict[str, Any]) -> str:
    c = context()
    _, spread = _chart_data(hist)
    s = c["spreads"]
    month = {s[k]["nominal_month"] for k in PARTNERS}
    above = all(float(L.raw(f"partners:spreads/{k}/nominal")) > 0 for k in PARTNERS)
    title = (f"In {esc(sorted(month)[-1])} the NBK base rate is above all three partner rates (nominal)" if above and len(month) == 1
             else "NBK base rate minus each partner rate, by month")
    nominal = "; ".join(f"{SHORT[k]} {L.num(f'partners:spreads/{k}/nominal', 2, signed=True)} pp ({esc(s[k]['nominal_month'])})" for k in PARTNERS)
    real = "; ".join(f"{SHORT[k]} {L.num(f'partners:spreads/{k}/real', 2, signed=True)} pp ({esc(s[k]['real_month'])})"
                     for k in PARTNERS if "real" in s[k])
    figure = line_figure(
        "sx", title, "Lines: NBK base rate minus the Russia, China and ECB rates by month, percentage points; dashed line at zero.",
        spread, PARTNERS, "NBK minus {name}", " pp", True, True,
        '<p class="caption preal-note">Real view: Kazakhstan real rate (NBK base rate − KZ inflation) minus the partner real rate; '
        "the ECB is nominal only. Above zero the NBK rate is the higher one.</p>",
        "Data table: monthly spreads, newest first")
    return (f'<h2 id="partners-spreads">Spread: NBK base rate minus each partner rate</h2>'
            f"<p>Latest spreads, nominal: {nominal}. Real (Kazakhstan real rate minus the partner real rate): {real}.</p>{figure}")


# ----------------------------------------------------------------------------- mechanism: stepped diagram + read more

def mechanism(L, block: dict[str, Any], intro: str, regression: str) -> str:
    identified = bool(block["credit_constraint"]["identified"])
    upper = ("KZ inflation + the higher of the Russian and Chinese real rates + cap, or the credit constraint if it is lower"
             if identified else
             "KZ inflation + the higher of the Russian and Chinese real rates + cap. The credit constraint is not identified, so "
             "the upper bound is the cap only")
    steps = [("Real rate", "nominal rate − year-on-year inflation."),
             ("Partner real rate", "a partner's monthly rate is the average over the calendar days of the month, minus its "
                                   "year-on-year inflation (Russia and China; no euro-area inflation is stored)."),
             ("Lower bound", "KZ inflation + the higher of the Russian and Chinese real rates + premium."),
             ("Upper bound", upper + "."),
             ("Reading", "below the corridor: risk of outflows into the carry trade; above the corridor: risk of excessive inflows "
                         "and harm to credit.")]
    items = "".join(f'<li><p><strong>{esc(t)}</strong>: {esc(d)}</p></li>' for t, d in steps)
    return (f'<h2 id="partners-mechanism">The carry-trade mechanism</h2>'
            f'<ol class="mech-steps" aria-label="How the corridor is built">{items}</ol>{si.cardify(intro)}{si.cardify(regression, 120)}')


# ----------------------------------------------------------------------------- what the model says (OVB, exploratory)

def _holdout_chart(L, specs: list[tuple[str, str]]) -> str:
    base = "ovb:specifications"
    vals = [(s, n, float(L.raw(f"{base}/{s}/holdout/rmse_ratio_to_always_hold"))) for s, n in specs]
    width, left, right, row, gap = 640, 170, 210, 24, 10
    height = gap + len(vals) * (row + gap) + 22
    hi = max(max(v for _, _, v in vals), 1.0) * 1.08
    x = lambda v: left + (width - left - right) * v / hi  # noqa: E731
    alt = "Bars: holdout RMSE ratio to Always Hold for the frozen model and each model with added partner rates; line at 1."
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(alt)}"><title>{esc(alt)}</title>']
    for slot, (spec, name, value) in enumerate(vals):
        y = gap + slot * (row + gap)
        colour = PALETTE["blue"] if spec == "frozen" else PALETTE["black"]
        shown = sd.plain(value, 3)
        verdict = "meets the criterion" if value < 1 else "does not meet it"
        parts.append(f'<text x="{left - 6}" y="{y + row / 2 + 4:.1f}" text-anchor="end" font-size="12" fill="{PALETTE["ink"]}">{esc(name)}</text>'
                     f'<rect class="src-bar" x="{left}" y="{y}" width="{x(value) - left:.1f}" height="{row}" fill="{colour}" '
                     f'data-ledger="{base}/{spec}/holdout/rmse_ratio_to_always_hold" data-shown="{shown}" data-tip="{esc(name)}: {shown}">'
                     f"<title>{esc(name)}: {shown}</title></rect>"
                     f'<text x="{x(value) + 6:.1f}" y="{y + row / 2 + 4:.1f}" font-size="12" fill="{PALETTE["ink"]}">{shown}, {verdict}</text>')
    parts.append(f'<line x1="{x(1):.1f}" y1="4" x2="{x(1):.1f}" y2="{height - 18}" stroke="{PALETTE["ink"]}" stroke-dasharray="4 4"/>'
                 f'<text x="{x(1):.1f}" y="{height - 4}" text-anchor="middle" font-size="11" fill="{PALETTE["ink"]}">1 = Always Hold</text></svg>')
    meets = [n for s, n, v in vals if v < 1]
    extended = [v for s, _, v in vals if s != "frozen"]
    frozen = dict((s, v) for s, _, v in vals)["frozen"]
    if frozen < 1 and all(v >= 1 for v in extended):
        title = "On the holdout only the frozen model meets the pre-specified criterion (RMSE ratio below 1)"
    else:
        title = f"On the holdout {len(meets)} of {len(vals)} specifications meet the pre-specified criterion (RMSE ratio below 1)"
    dm = "".join(
        f"<tr><th>{esc(n)}</th><td>{L.num(f'{base}/{s}/holdout/dm_squared_error_vs_frozen/mean_loss_difference', 3, signed=True)}</td>"
        f"<td>{L.num(f'{base}/{s}/holdout/dm_squared_error_vs_frozen/statistic', 2)}</td>"
        f"<td>{L.num(f'{base}/{s}/holdout/dm_squared_error_vs_frozen/p_value', 3)}</td></tr>" for s, n in specs if s != "frozen")
    return (f'<figure id="ovb-holdout" class="ichart"><figcaption><strong>{esc(title)}</strong></figcaption>{"".join(parts)}</figure>'
            '<div class="scroll"><table><caption>Diebold–Mariano test on squared error, extended model minus frozen model (HLN '
            "corrected); a negative mean difference favours the extended model</caption><thead><tr><th>Specification</th>"
            f"<th>Mean loss difference</th><th>Statistic</th><th>p</th></tr></thead><tbody>{dm}</tbody></table></div>")


def _interval_svg(low: float, high: float, point: float, lo: float, hi: float) -> str:
    width, left, right = 480, 12, 12
    x = lambda v: left + (width - left - right) * (v - lo) / (hi - lo)  # noqa: E731
    alt = (f"Score change {sd.signed(point, 3)} with its 95% interval from {sd.signed(low, 3)} to {sd.signed(high, 3)}; "
           "the vertical mark is zero.")
    return (f'<svg class="wi-line" viewBox="0 0 {width} 40" role="img" aria-label="{esc(alt)}"><title>{esc(alt)}</title>'
            f'<line class="wi-axis" x1="{left}" y1="14" x2="{width - right}" y2="14"/>'
            f'<line class="wi-zero" x1="{x(0):.1f}" y1="2" x2="{x(0):.1f}" y2="26"/>'
            f'<text x="{x(0):.1f}" y="38" text-anchor="middle">0</text>'
            f'<line class="wi-ci" x1="{x(low):.1f}" y1="14" x2="{x(high):.1f}" y2="14"/>'
            f'<circle class="wi-pt" cx="{x(point):.1f}" cy="14" r="5"/></svg>')


def what_if(L, ovb: dict[str, Any]) -> str:
    w = ovb["partner_what_if"]
    base = "ovb:partner_what_if/specifications"
    lag = int(ovb["sample"]["release_lag_months"])
    year, month = (int(p) for p in w["decision_date"][:7].split("-"))
    total = year * 12 + month - 1 - lag
    used = f"{total // 12}-{total % 12 + 1:02d}"
    bounds = [m[b] for e in w["specifications"].values() for mv in e["moves"].values() for k, m in mv.items()
              if isinstance(m, dict) for b in ("ci_low", "ci_high")]
    lo, hi = min(min(bounds), 0.0), max(max(bounds), 0.0)
    pad = (hi - lo) * 0.05
    rows, readouts = [], []
    combos = [(SPEC_FOR[p], p, "alone") for p in PARTNERS] + [("plus_all_three", p, "all") for p in PARTNERS]
    for spec, partner, variant in combos:
        entry = w["specifications"][spec]
        for move in ("plus_one", "minus_one"):
            m = entry["moves"][partner][move]
            key = f"{base}/{spec}/moves/{partner}/{move}"
            words = ("the interval includes zero: the direction of the change is not established"
                     if m["interval_includes_zero"] else "the interval excludes zero")
            sign = "+1" if m["move_points"] > 0 else "−1"
            spec_name = f"{SHORT[partner]} rate alone" if variant == "alone" else "all three partner rates"
            cells = (f"{L.num(f'{key}/score_change', 3, signed=True)} (95% interval {L.num(f'{key}/ci_low', 3, signed=True)} to "
                     f"{L.num(f'{key}/ci_high', 3, signed=True)}); {words}")
            rows.append(f"<tr><th>{esc(SHORT[partner])} {sign} point</th><td>{esc(spec_name)}</td><td>{cells}</td></tr>")
            readouts.append(f'<div class="wi-readout" data-partner="{partner}" data-variant="{variant}" data-move="{move}">'
                            f"<p>Model with {esc(spec_name)}: {esc(NAMES[partner])} {sign} point from "
                            f"{L.num(f'{base}/{spec}/moves/{partner}/latest_value', 2)}%: score change {cells}. Score at that decision "
                            f"{L.num(f'{base}/{spec}/latest_score', 3, signed=True)}.</p>"
                            f"{_interval_svg(m['ci_low'], m['ci_high'], m['score_change'], lo - pad, hi + pad)}</div>")
    picker = ('<div id="wi-picker" hidden><div class="chart-tools" role="group" aria-label="Partner rate">'
              + "".join(f'<button type="button" class="pill" data-partner="{p}" aria-pressed="{"true" if i == 0 else "false"}">{esc(SHORT[p])}</button>'
                        for i, p in enumerate(PARTNERS))
              + '</div><div class="chart-tools" role="group" aria-label="Model">'
              '<button type="button" class="pill" data-variant="alone" aria-pressed="true">This rate alone</button>'
              '<button type="button" class="pill" data-variant="all" aria-pressed="false">All three rates</button></div>'
              '<div class="chart-tools" role="group" aria-label="Move">'
              '<button type="button" class="pill" data-move="plus_one" aria-pressed="true">+1 point</button>'
              '<button type="button" class="pill" data-move="minus_one" aria-pressed="false">−1 point</button></div>'
              f'<div class="wi-readouts" aria-live="polite">{"".join(readouts)}</div>'
              '<p class="caption">Thick line: 95% interval; dot: score change; vertical mark: zero. One scale for all rows, so intervals compare across partners and models.</p></div>')
    table = ('<div class="scroll"><table id="wi-table"><thead><tr><th>Move</th><th>Model</th><th>Score change at that decision</th></tr></thead>'
             f"<tbody>{''.join(rows)}</tbody></table></div>")
    return (f'<h3 id="partners-what-if">Move one partner rate: exploratory, not used for the forecast</h3>'
            f"<p>{esc(w['label'])} Last usable decision: {esc(w['decision_date'])}; the partner rate used there is the monthly "
            f"mean of {esc(used)} (decision month minus the assumed release lag of {L.num('ovb:sample/release_lag_months')} months), "
            "not today's rate.</p>" + picker + table)


def model(L, ovb_toggle: str) -> str:
    ovb = json.loads(OVB_PATH.read_text(encoding="utf-8"))
    specs = [("frozen", "Frozen model"), ("plus_ru_key_rate", "+ Russia key rate"), ("plus_cn_policy_rate", "+ China policy rate"),
             ("plus_ecb_deposit_rate", "+ ECB deposit rate"), ("plus_all_three", "+ all three")]
    return (f'<h2 id="partners-model">What the model says</h2>'
            "<p>The frozen model has six Kazakh factors. The omitted-variable check added the partner rates one at a time and all "
            "three together, on the same decisions and the same estimation and holdout split.</p>"
            f"{ovb_toggle}{_holdout_chart(L, specs)}{what_if(L, ovb)}")


# ----------------------------------------------------------------------------- descriptive event table

def events(L) -> str:
    c = context()
    ev = c["events"]
    head = "".join(f"<th>{mark(cls)}</th>" for cls, _ in OUTCOMES)

    def row(label: str, prefix: str, entry: dict[str, Any]) -> str:
        caution = "none in the sample" if entry["n"] == 0 else "small n, read with caution" if entry["small_n"] else ""
        cells = "".join(f"<td>{L.num(f'{prefix}/{key}')}</td>" for _, key in OUTCOMES)
        return f"<tr><th>{esc(label)}</th><td>{L.num(f'{prefix}/n')}</td>{cells}<td>{esc(caution)}</td></tr>"

    tables = []
    for partner in PARTNERS:
        e = ev[partner]
        prefix = f"partners:events/{partner}"
        body = "".join(row(label, f"{prefix}/{group}", e[group]) for group, label in GROUP_LABELS)
        body += row("All NBK decisions in the sample", f"{prefix}/sample", e["sample"])
        tables.append(
            f'<div class="ev-partner" data-partner="{partner}"><h3>{esc(NAMES[partner])}</h3>'
            f"<p class=\"caption\">Sample: NBK decisions {esc(e['sample_period']['first'])} to {esc(e['sample_period']['last'])}; "
            f"{L.num(f'{prefix}/partner_changes_in_period')} changes of the {esc(NAMES[partner])} in the period "
            f"({L.num(f'{prefix}/partner_rises_in_period')} rises, {L.num(f'{prefix}/partner_cuts_in_period')} cuts).</p>"
            f'<div class="scroll"><table><thead><tr><th>NBK decisions</th><th>n</th>{head}<th>Note</th></tr></thead>'
            f"<tbody>{body}</tbody></table></div></div>")
    overall = ev["all_nbk_decisions"]
    period = ev["all_nbk_decisions_period"]
    picker = ('<div class="chart-tools" id="ev-picker" role="group" aria-label="Partner shown" hidden>'
              + "".join(f'<button type="button" class="pill" data-partner="{p}" aria-pressed="{"true" if i == 0 else "false"}">{esc(SHORT[p])}</button>'
                        for i, p in enumerate(PARTNERS)) + "</div>")
    d = c["definitions"]
    return (f'<h2 id="partners-events">NBK outcomes after partner rate changes</h2>'
            f"<p>Descriptive counts, not causal effects and not a forecast. A partner change is {esc(d['partner_change'])}; "
            f"{esc(d['matching'])}. Window: {L.num('partners:window_days')} calendar days. Rows with n below "
            f"{L.num('partners:small_n_threshold')} are marked small n.</p>"
            f"<p>All NBK decisions, {esc(period['first'])} to {esc(period['last'])}: n = {L.num('partners:events/all_nbk_decisions/n')}, of "
            + ", ".join(f"{L.num(f'partners:events/all_nbk_decisions/{key}')} {cls.lower()}" for cls, key in OUTCOMES)
            + f".</p>{picker}{''.join(tables)}"
            "<p class=\"caption\">The baseline row counts NBK decisions with no change of that partner rate in the window before them. "
            "Differences between rows are counts on few decisions; they do not separate a partner change from Kazakh inflation, "
            "lending or other news at the same time.</p>")


# ----------------------------------------------------------------------------- limitations as grouped cards

def limits(L, block: dict[str, Any], china_title: str, ovb_label: str, sources: dict[str, Any]) -> str:
    c = context()
    credit = block["credit_constraint"]
    items = [("China's rate is a lending benchmark",
              f"China's rate: {esc(china_title)}. It is a lending benchmark, not the return on a short-term deposit, so the real rate "
              "and the corridor for China rest on a lending rate (D47).", "caution"),
             ("The tenge regression is an in-sample association",
              "This is an in-sample association, not a causal estimate and not a forecast; omitted variables such as the oil price, "
              "global risk appetite and the rouble can bias it.", "caution"),
             ("Credit constraint" + (" not identified" if not credit["identified"] else ""),
              "Credit constraint: slope of credit growth 6 months ahead on the real rate "
              f"{L.num('carry_corridor:credit_constraint/slope', 3)}. "
              + ("The slope is not negative, so the credit constraint is not identified and is not used." if not credit["identified"]
                 else "A descriptive relation, not a causal estimate."), "caution" if not credit["identified"] else "note"),
             ("The omitted-variable check came after the holdout was seen", esc(ovb_label), "caution"),
             ("ECB rate: nominal only",
              "No euro-area inflation is stored, so the ECB deposit rate is shown in nominal terms only and is not part of the "
              "corridor definition.", "note"),
             ("Event counts are descriptive", f"{esc(c['definitions']['reading'].capitalize())}. {esc(c['definitions']['small_n'].capitalize())}.", "caution"),
             ("Trade shares: named partners only", esc(sources["context"]["kz_export_shares_2025"]["caveat"]), "note")]
    # Grouped under h3 heads (not label paragraphs) and with plain card text (no read-more card inside a card).
    out = ['<h2 id="partners-limits">Limitations</h2>']
    for kind, head, word in (("caution", "Cautions", "Caution"), ("note", "Notes", "Note")):
        cards = "".join(f'<article class="limit-card limit-{kind}"><h4><span class="sev sev-{kind}" aria-hidden="true"></span> '
                        f'<span class="sev-word">{word}:</span> {esc(title)}</h4><p>{text}</p></article>'
                        for title, text, k in items if k == kind)
        if cards:
            out.append(f'<div class="limit-group"><h3>{head}</h3>{cards}</div>')
    return "".join(out)
