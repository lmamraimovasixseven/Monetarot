"""Visual and interactive pieces of the static site (D56), built at site-build time from stored values only.

Every chart is inline SVG with an action title, an aria-label and a <title>; every number shown as text carries
data-ledger (existing ledger ids only, so the evidence ledger and the artifact do not change). The browser part
(src/site_assets/app.js) only adds behaviour on top: without JavaScript each block reads as a static chart, list or table.
The glossary sentences live here, in src/, and are written into the pages by `glossarize`.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any

from src import site_dashboard as sd

PALETTE = sd.PALETTE  # D57: one palette for the site (Okabe–Ito hues tuned for the dark panels)
Z95 = 1.96  # whiskers drawn as estimate +/- 1.96 x stored HC0 standard error; the interval itself is not stored


def esc(text: Any) -> str:
    return html.escape(str(text))


# ----------------------------------------------------------------------------- glossary (F6)

GLOSSARY = {
    "ordered logit": (r"\bordered logit\b", "A regression for ordered outcomes (cut, hold, hike) that gives a probability for each outcome."),
    "HC0": (r"\bHC0\b", "White's heteroskedasticity-consistent standard errors, which do not assume equal error variance."),
    "Holm": (r"\bHolm\b", "A step-down correction of p-values when several hypotheses are tested together."),
    "RPS": (r"\bRPS\b", "Ranked probability score: squared error of the cumulative class probabilities; lower is better."),
    "Diebold-Mariano": (r"\bDiebold[–-]Mariano\b", "A test of whether two forecasts have the same expected loss."),
    "Always Hold": (r"\bAlways Hold\b", "The benchmark that predicts no change in the base rate at every decision."),
    "ledger": (r"\bevidence ledger\b|\bledger\b", "The evidence ledger: one CSV row per number on the site, with its source, script and test."),
    "prereg": (r"\bpreregistration\b|\bprereg\b", "The preregistration: target, method and scoring rule, frozen before the outcome is known."),
}
SKIP_TAGS = {"a", "code", "pre", "script", "style", "h1", "h2", "h3", "h4", "h5", "h6", "summary", "button", "label",
             "option", "select", "title", "svg", "nav", "header", "footer", "th", "td", "caption", "figcaption", "output",
             "textarea", "dt"}
VOID_TAGS = {"br", "img", "input", "meta", "link", "hr", "wbr", "source", "col", "area", "base", "embed", "track"}
TOKEN = re.compile(r"(<[^>]+>)")


def _walk(text: str):
    """Yield (token, skip) pairs: tags as they are, and text with a flag telling whether it sits in a skipped element."""
    stack: list[tuple[str, bool]] = []
    for token in TOKEN.split(text):
        if not token:
            continue
        if token.startswith("<"):
            match = re.match(r"<\s*(/)?\s*([a-zA-Z0-9]+)", token)
            if match and not token.startswith("<!"):
                closing, name = match.group(1), match.group(2).lower()
                if closing:
                    while stack:
                        if stack.pop()[0] == name:
                            break
                elif name not in VOID_TAGS and not token.endswith("/>"):
                    skip = name in SKIP_TAGS or ('class="num' in token) or ('class="gloss' in token) or ("data-ledger" in token)
                    stack.append((name, skip))
            yield token, True
        else:
            yield token, any(s for _, s in stack)


def glossarize(body: str) -> str:
    """Wrap the first use of each glossary term in running text (not in headings, links, code, tables or charts)."""
    done: set[str] = set()
    out = []
    for token, skip in _walk(body):
        if skip or token.startswith("<"):
            out.append(token)
            continue
        for key, (pattern, sentence) in GLOSSARY.items():
            if key in done:
                continue
            match = re.search(pattern, token, flags=re.I if key in ("ordered logit", "ledger", "prereg") else 0)
            if not match:
                continue
            done.add(key)
            slug = re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-")
            wrapped = (f'<span class="gloss" tabindex="0" aria-describedby="gloss-{slug}">{match.group(0)}'
                       f'<span class="gloss-tip" role="tooltip" id="gloss-{slug}">{esc(sentence)}</span></span>')
            token = token[:match.start()] + wrapped + token[match.end():]
            break  # one term per text token keeps the offsets simple; the next token can take the next term
        out.append(token)
    return "".join(out)


# ----------------------------------------------------------------------------- read-more cards (F1, F4)

SENTENCE_END = re.compile(r"[.!?](?=\s+[A-Z(“\"<])")


def _first_sentence_split(inner: str) -> int | None:
    """Offset in `inner` just after the first sentence that ends at the top level (outside any tag), or None."""
    depth, offset = 0, 0
    for token in TOKEN.split(inner):
        if token.startswith("<"):
            if re.match(r"<\s*/", token):
                depth -= 1
            elif not token.endswith("/>") and not re.match(r"<\s*(br|img|input|wbr)\b", token):
                depth += 1
        elif depth == 0:
            match = SENTENCE_END.search(token)
            if match:
                return offset + match.end()
        offset += len(token)
    return None


def _first_colon_split(inner: str) -> int | None:
    """Fallback for a one-sentence paragraph: the lead-in before the first top-level colon ("The complication:")."""
    depth, offset = 0, 0
    for token in TOKEN.split(inner):
        if token.startswith("<"):
            if re.match(r"<\s*/", token):
                depth -= 1
            elif not token.endswith("/>") and not re.match(r"<\s*(br|img|input|wbr)\b", token):
                depth += 1
        elif depth == 0 and ": " in token:
            cut = offset + token.index(": ") + 1
            return cut if 6 <= len(re.sub(r"<[^>]+>", "", inner[:cut])) <= 80 else None
        offset += len(token)
    return None


def read_card(inner: str, min_chars: int = 160, extra_class: str = "") -> str | None:
    """`<p class="read-card">` with the first sentence (or the lead-in before a colon) as its head and the rest in
    `.card-rest`; None if the paragraph is short or cannot be split. The wording is unchanged."""
    if len(re.sub(r"<[^>]+>", "", inner)) < min_chars:
        return None
    cut = _first_sentence_split(inner)
    if cut is None or not inner[cut:].strip():
        cut = _first_colon_split(inner)
    if cut is None or not inner[cut:].strip():
        return None
    cls = f"read-card {extra_class}".strip()
    return f'<p class="{cls}"><span class="card-head">{inner[:cut]}</span> <span class="card-rest">{inner[cut:].strip()}</span></p>'


def cardify(body: str, min_chars: int = 160) -> str:
    """Long paragraphs (plain, caption or summary) become read-more cards; the wording is unchanged."""
    def swap(match: re.Match) -> str:
        return read_card(match.group(2), min_chars, match.group(1) or "") or match.group(0)
    return re.sub(r'<p(?: class="(caption|summary)")?>(.*?)</p>', swap, body, flags=re.S)


# ----------------------------------------------------------------------------- on-this-page navigation (F7)

def onpage_nav(body: str) -> str:
    """A sticky "On this page" list of the page's h2 headings; links use the h2 id, else the enclosing section id."""
    targets = []
    for match in re.finditer(r'(<section id="([^"]+)">\s*)?<h2(?: id="([^"]+)")?[^>]*>(.*?)</h2>', body, flags=re.S):
        target = match.group(3) or match.group(2)
        label = re.sub(r"<[^>]+>", "", match.group(4)).strip()
        if target and label:
            targets.append((target, label))
    if len(targets) < 3:
        return body
    links = "".join(f'<li><a href="#{esc(t)}">{esc(label)}</a></li>' for t, label in targets)
    nav = f'<nav class="onpage" aria-label="On this page"><p class="onpage-title">On this page</p><ul>{links}</ul></nav>'
    if "<!-- onpage -->" in body:  # D57: the home page places the list after its answer panels and research links
        return body.replace("<!-- onpage -->", nav, 1)
    match = re.search(r"</h1>", body)
    if match:
        return body[:match.end()] + nav + body[match.end():]
    match = re.search(r'<section id="step-1">', body)
    return body[:match.start()] + nav + body[match.start():] if match else nav + body


# ----------------------------------------------------------------------------- generic horizontal bars with sources

def bar_chart(title: str, alt: str, rows: list[dict[str, Any]], *, digits: int = 3, chart_id: str = "",
              width: int = 640, left: int = 190) -> str:
    """Horizontal bars from zero; each row: label, value, ledger id, colour, optional gap_before. Bars open the source popup."""
    bar, gap = 20, 8
    height = sum(bar + gap + (14 if r.get("gap_before") else 0) for r in rows) + gap
    top_value = max(r["value"] for r in rows) * 1.15 or 1.0
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(alt)}"><title>{esc(alt)}</title>']
    y = gap
    for r in rows:
        y += 14 if r.get("gap_before") else 0
        length = (width - left - 70) * r["value"] / top_value
        shown = sd.plain(r["value"], digits)
        parts.append(f'<text x="{left - 6}" y="{y + bar / 2 + 4:.1f}" text-anchor="end" font-size="12" fill="{PALETTE["black"]}">{esc(r["label"])}</text>'
                     f'<rect class="src-bar" x="{left}" y="{y:.1f}" width="{max(length, 1.5):.1f}" height="{bar}" fill="{r["colour"]}" '
                     f'data-ledger="{esc(r["ledger"])}" data-shown="{esc(shown)}" data-tip="{esc(r["label"])}: {esc(shown)}"><title>{esc(r["label"])}: {esc(shown)}</title></rect>'
                     f'<text x="{left + length + 6:.1f}" y="{y + bar / 2 + 4:.1f}" font-size="12" fill="{PALETTE["black"]}">{esc(shown)}</text>')
        y += bar + gap
    parts.append("</svg>")
    attr = f' id="{chart_id}"' if chart_id else ""
    return f'<figure{attr} class="ichart"><figcaption><strong>{esc(title)}</strong></figcaption>{"".join(parts)}</figure>'


# ----------------------------------------------------------------------------- C1 factor effects

def factor_effects(L, d: dict) -> str:
    features = d["model"]["features"]
    rows = d["full_results"]["coefficients"]["rows"]
    key = "dashboard:full_results/coefficients/rows"
    items = []
    for i, row in enumerate(rows):
        if row[0] not in features:
            continue
        est = float(L.raw(f"{key}/{i}/1"))
        se = float(L.raw(f"{key}/{i}/2"))
        holm = float(L.raw(f"{key}/{i}/4"))
        items.append({"i": i, "name": row[0], "label": row[0].replace("_", " ").capitalize(), "est": est, "se": se, "holm": holm})
    span = max(abs(it["est"]) + Z95 * it["se"] for it in items) * 1.1
    width, left, right, bar, gap = 640, 150, 20, 22, 12
    height = gap + len(items) * (bar + gap) + 22
    x = lambda v: left + (width - left - right) * (v + span) / (2 * span)  # noqa: E731
    alt = ("Horizontal bars: estimated coefficient of each factor in the frozen ordered logit, with whiskers of plus and minus "
           "1.96 HC0 standard errors; bars to the right push towards a hike.")
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(alt)}"><title>{esc(alt)}</title>',
             f'<line x1="{x(0):.1f}" y1="4" x2="{x(0):.1f}" y2="{height - 20}" stroke="{PALETTE["grey"]}"/>',
             f'<text x="{x(0):.1f}" y="{height - 6}" text-anchor="middle" font-size="11" fill="{PALETTE["black"]}">0</text>']
    for slot, it in enumerate(items):
        y0 = gap + slot * (bar + gap)
        colour = PALETTE["blue"] if it["est"] >= 0 else PALETTE["vermillion"]
        lo, hi = it["est"] - Z95 * it["se"], it["est"] + Z95 * it["se"]
        shown = sd.signed(it["est"], 4)
        sig = " (significant after Holm)" if it["holm"] < 0.05 else ""
        parts.append(
            f'<g class="fx-row" data-name="{esc(it["label"])}" data-size="{abs(it["est"])!r}" data-slot="{slot}" style="transform:translate(0px,{y0}px)">'
            f'<text x="{left - 6}" y="{bar / 2 + 4}" text-anchor="end" font-size="12" fill="{PALETTE["black"]}">{esc(it["label"])}</text>'
            f'<rect class="src-bar" x="{min(x(0), x(it["est"])):.1f}" y="0" width="{max(abs(x(it["est"]) - x(0)), 1.5):.1f}" height="{bar}" fill="{colour}" '
            f'data-ledger="{key}/{it["i"]}/1" data-shown="{esc(shown)}" data-tip="{esc(it["label"])}: {esc(shown)}{esc(sig)}">'
            f'<title>{esc(it["label"])}: {esc(shown)}{esc(sig)}</title></rect>'
            f'<line x1="{x(lo):.1f}" y1="{bar / 2}" x2="{x(hi):.1f}" y2="{bar / 2}" stroke="{PALETTE["black"]}" stroke-width="1.5"/>'
            f'<line x1="{x(lo):.1f}" y1="{bar / 2 - 5}" x2="{x(lo):.1f}" y2="{bar / 2 + 5}" stroke="{PALETTE["black"]}"/>'
            f'<line x1="{x(hi):.1f}" y1="{bar / 2 - 5}" x2="{x(hi):.1f}" y2="{bar / 2 + 5}" stroke="{PALETTE["black"]}"/></g>')
    parts.append("</svg>")
    significant = [it["label"].lower() for it in items if it["holm"] < 0.05]
    largest = max(items, key=lambda it: abs(it["est"]))["label"].lower()
    title = (f"{len(significant)} of {len(items)} factors are significant after Holm"
             + (f" ({', '.join(significant)})" if significant else "")
             + f"; the largest estimate in absolute value is {largest}")
    return (f'<figure id="fx-chart" class="ichart"><figcaption><strong>{esc(title)}</strong></figcaption>'
            '<div class="chart-tools" role="group" aria-label="Sort the factors" hidden>'
            '<button type="button" class="pill" data-sort="model" aria-pressed="true">Model order</button>'
            '<button type="button" class="pill" data-sort="size" aria-pressed="false">Sort by size</button>'
            '<button type="button" class="pill" data-sort="name" aria-pressed="false">Sort by name</button></div>'
            f'{"".join(parts)}<p class="caption">Whiskers: estimate ± 1.96 × HC0 standard error, drawn from the stored values '
            "(the interval itself is not stored). Coefficients are per unit of each factor, so their sizes are not comparable "
            "across factors with different units. Click a bar for its source.</p></figure>")


# ----------------------------------------------------------------------------- C2 base vs extended (OVB)

def ovb_toggle(L, specs: list[tuple[str, str]]) -> str:
    base = "ovb:specifications"
    feature = "household_lending"
    if f"{base}/frozen/coefficients/{feature}/estimate" not in L.values:
        return ""
    vals = {s: (float(L.raw(f"{base}/{s}/coefficients/{feature}/estimate")), float(L.raw(f"{base}/{s}/coefficients/{feature}/hc0_se")),
                float(L.raw(f"{base}/{s}/coefficients/{feature}/p_value"))) for s, _ in specs}
    hi = max(e + Z95 * se for e, se, _ in vals.values()) * 1.1
    lo = min(0.0, min(e - Z95 * se for e, se, _ in vals.values())) * 1.1
    width, left, right, row, gap = 640, 170, 20, 26, 8
    height = gap + len(specs) * (row + gap) + 22
    x = lambda v: left + (width - left - right) * (v - lo) / (hi - lo)  # noqa: E731
    alt = "Dots with whiskers: household lending coefficient in the frozen model and in each model with added foreign policy rates."
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(alt)}"><title>{esc(alt)}</title>',
             f'<line x1="{x(0):.1f}" y1="4" x2="{x(0):.1f}" y2="{height - 20}" stroke="{PALETTE["grey"]}" stroke-dasharray="4 4"/>',
             f'<text x="{x(0):.1f}" y="{height - 6}" text-anchor="middle" font-size="11" fill="{PALETTE["black"]}">0</text>']
    for slot, (spec, name) in enumerate(specs):
        e, se, p = vals[spec]
        y = gap + slot * (row + gap) + row / 2
        colour = PALETTE["blue"] if spec == "frozen" else PALETTE["orange"]
        shown = sd.signed(e, 3)
        parts.append(f'<g class="ovb-row" data-spec="{spec}"><text x="{left - 6}" y="{y + 4:.1f}" text-anchor="end" font-size="12" fill="{PALETTE["black"]}">{esc(name)}</text>'
                     f'<line x1="{x(e - Z95 * se):.1f}" y1="{y:.1f}" x2="{x(e + Z95 * se):.1f}" y2="{y:.1f}" stroke="{colour}" stroke-width="2"/>'
                     f'<circle class="src-bar" cx="{x(e):.1f}" cy="{y:.1f}" r="6" fill="{colour}" data-ledger="{base}/{spec}/coefficients/{feature}/estimate" '
                     f'data-shown="{esc(shown)}" data-tip="{esc(name)}: {esc(shown)}"><title>{esc(name)}: {esc(shown)}</title></circle></g>')
    parts.append("</svg>")
    positive = sum(1 for e, _, _ in vals.values() if e > 0)
    significant = sum(1 for _, _, p in vals.values() if p < 0.05)
    title = (f"Household lending is positive in {positive} of {len(specs)} specifications and significant at 5% in "
             f"{significant} of {len(specs)}")
    buttons = "".join(f'<button type="button" class="pill" data-spec="{s}" aria-pressed="{"true" if i == 0 else "false"}">{esc(n)}</button>'
                      for i, (s, n) in enumerate(specs[1:]))
    readouts = "".join(
        f'<p class="ovb-readout" data-spec="{s}">{esc(n)}: household lending {L.num(f"{base}/{s}/coefficients/{feature}/estimate", 3, signed=True)} '
        f'(HC0 p {L.num(f"{base}/{s}/coefficients/{feature}/p_value", 3)}).</p>' for s, n in specs)
    return (f'<figure id="ovb-toggle" class="ichart"><figcaption><strong>{esc(title)}</strong></figcaption>'
            f'<div class="chart-tools" role="group" aria-label="Compare the frozen model with" hidden>{buttons}</div>'
            f'{"".join(parts)}<div class="ovb-readouts" aria-live="polite">{readouts}</div>'
            '<p class="caption">Exploratory, after the holdout was seen. Whiskers: estimate ± 1.96 × HC0 standard error, drawn from '
            "the stored values. With JavaScript, the chart shows the frozen model and the extended model you pick.</p></figure>")


# ----------------------------------------------------------------------------- C3 holdout comparison with a click panel

def holdout_panel(L) -> str:
    rps = [("Frozen model", float(L.raw("n:rps_model")), "n:rps_model", PALETTE["blue"]),
           ("Class frequencies", float(L.raw("n:rps_class_frequency")), "n:rps_class_frequency", PALETTE["sky"]),
           ("Always Hold", float(L.raw("n:rps_hold")), "n:rps_hold", PALETTE["grey"])]
    model, freq = rps[0][1], rps[1][1]
    relation = ("barely differs from" if abs(model - freq) < 0.05 * freq else "is lower than" if model < freq else "is higher than")
    chart = bar_chart(f"On holdout RPS the frozen model {relation} class frequencies (lower is better)",
                      "Bars: ranked probability score on the holdout for the frozen model, class frequencies and Always Hold.",
                      [{"label": n, "value": v, "ledger": k, "colour": c} for n, v, k, c in rps], chart_id="rps-chart")
    panel = (f'<div id="holdout-panel" class="click-panel"><p>Holdout RMSE ratio to Always Hold {L.num("n:rmse_ratio", 3)} '
             f'(95% bootstrap interval {L.num("n:rmse_ratio_ci_low", 3)}–{L.num("n:rmse_ratio_ci_high", 3)}); '
             f'Diebold–Mariano p = {L.num("n:dm_squared_error_p", 3)} on squared error.</p></div>')
    return (chart + '<button type="button" class="pill" id="holdout-toggle" aria-expanded="true" aria-controls="holdout-panel" hidden>'
            "RMSE ratio and Diebold–Mariano test</button>" + panel)


# ----------------------------------------------------------------------------- C4 recall per class

def recall_chart(L, forecasters: list[tuple[str, str]], classes: list[str]) -> str:
    base = "classm:forecasters"
    colours = {"frozen_model": PALETTE["blue"], "class_frequencies": PALETTE["sky"], "always_hold": PALETTE["grey"]}
    rows = []
    for c in classes:
        for j, (key, name) in enumerate(forecasters):
            ledger = f"{base}/{key}/classes/{c}/recall"
            if ledger in L.values:
                rows.append({"label": f"{c}: {name}", "value": float(L.raw(ledger)), "ledger": ledger, "colour": colours[key],
                             "gap_before": j == 0 and bool(rows)})
    if not rows:
        return ""
    correct = int(float(L.raw("classm:summary/frozen_correct_non_hold")))
    total = int(float(L.raw("classm:summary/non_hold_decisions")))
    title = (f"By argmax the frozen model picks {correct} of the {total} cuts and hikes; class frequencies and Always Hold pick none"
             if correct else f"By argmax no forecaster picks any of the {total} cuts and hikes")
    if any(float(L.raw(f"{base}/{k}/classes/{c}/recall")) > 0 for c in classes if c != "Hold"
           for k, _ in forecasters[1:] if f"{base}/{k}/classes/{c}/recall" in L.values):
        title = f"By argmax the frozen model picks {correct} of the {total} cuts and hikes"
    return bar_chart(title, "Bars: recall per class (share of the decisions of each class whose highest-probability forecast is that class) "
                     "for the frozen model, class frequencies and Always Hold.", rows, chart_id="recall-chart", left=230)


# ----------------------------------------------------------------------------- D corridor band over time

def corridor_band(L, block: dict, hist: dict) -> str:
    months = hist["months"]
    if len(months) < 2:
        return ""
    premium, cap = float(block["defaults"]["premium"]), float(block["defaults"]["cap"])
    base = [i + r for i, r in zip(hist["inflation"], hist["max_partner_real"])]
    lo = min(min(hist["rate"]), min(base)) - 1
    hi = max(max(hist["rate"]), max(base) + 12) + 1  # the cap slider goes up to 12
    width, height, left, right, top, bottom = 640, 280, 44, 10, 12, 30
    x = lambda i: left + (width - left - right) * i / (len(months) - 1)  # noqa: E731
    y = lambda v: top + (height - top - bottom) * (hi - v) / (hi - lo)  # noqa: E731
    upper = [b + cap for b in base]
    lower = [b + premium for b in base]
    band = ("M" + " L".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(upper))
            + " L" + " L".join(f"{x(i):.1f},{y(v):.1f}" for i, v in reversed(list(enumerate(lower)))) + " Z")
    rate = "M" + " L".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(hist["rate"]))
    below = sum(1 for r, l in zip(hist["rate"], lower) if r < l)
    above = sum(1 for r, u in zip(hist["rate"], upper) if r > u)
    alt = ("Band: corridor lower and upper bound by month (KZ inflation plus the higher partner real rate plus the premium or the cap); "
           "line: NBK base rate.")
    parts = [f'<svg id="cb-svg" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(alt)}"><title>{esc(alt)}</title>',
             f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" stroke="{PALETTE["grey"]}"/>']
    for tick in range(int(lo) + 1, int(hi) + 1, 5):
        parts.append(f'<text x="{left - 4}" y="{y(tick) + 4:.1f}" text-anchor="end" font-size="11" fill="{PALETTE["black"]}">{tick}%</text>')
    for i, m in enumerate(months):
        if m.endswith("-01") and int(m[:4]) % 2 == 1:
            parts.append(f'<text x="{x(i):.1f}" y="{height - 10}" text-anchor="middle" font-size="11" fill="{PALETTE["black"]}">{m[:4]}</text>')
    parts.append(f'<path id="cb-band" d="{band}" fill="{PALETTE["sky"]}" fill-opacity="0.35" stroke="{PALETTE["blue"]}" stroke-width="1"/>')
    parts.append(f'<path d="{rate}" fill="none" stroke="{PALETTE["ink"]}" stroke-width="2"/></svg>')
    data = {"months": months, "base": [round(b, 6) for b in base], "rate": hist["rate"], "lo": lo, "hi": hi,
            "geom": [width, height, left, right, top, bottom]}
    inside = len(months) - below - above
    title = (f"At the default premium and cap the NBK rate was below the corridor in {below} of {len(months)} months, "
             f"inside in {inside} and above in {above}")
    return (f'<figure id="corridor-band" class="ichart"><figcaption><strong>{esc(title)}</strong></figcaption>{"".join(parts)}'
            f'<p class="legend"><span class="key" style="border-color:{sd.key_colour(PALETTE["sky"])}">Computed corridor, scenario (your premium and cap)</span>'
            f'<span class="key" style="border-color:{sd.key_colour(PALETTE["ink"])}">Actual NBK base rate</span></p>'
            f'<p id="cb-out" class="caption" aria-live="polite">Static view: premium {sd.plain(premium, 2)} pp and cap {sd.plain(cap, 2)} pp '
            "(the defaults, user assumptions). With JavaScript the band follows the premium and cap sliders below.</p>"
            "<p class=\"caption\">What-if on stated assumptions, not a model estimate: monthly band = KZ inflation + the higher of the "
            "Russian and Chinese real rates + premium (lower) or + cap (upper), computed from the files in data/raw/ and "
            "data/raw/external/. The credit constraint is not identified, so the upper bound is the cap only.</p>"
            f'<script type="application/json" id="cb-json">{json.dumps(data, separators=(",", ":"))}</script></figure>')


# ----------------------------------------------------------------------------- F2 pipeline and F3 timeline

def pipeline(stages: list[tuple[str, str, str]]) -> str:
    """Stages: (key, name, existing text with ledger spans). Static: a list with every text visible; JS: click to expand."""
    nodes = "".join(f'<li><button type="button" class="pipe-node" aria-expanded="true" aria-controls="pipe-{k}">{esc(n)}</button></li>'
                    for k, n, _ in stages)
    panels = "".join(f'<div class="pipe-panel" id="pipe-{k}"><p><strong>{esc(n)}.</strong> {text}</p></div>' for k, n, text in stages)
    return (f'<h2 id="pipeline">From data to a scored forecast</h2><ol class="pipeline" aria-label="Pipeline stages">{nodes}</ol>'
            f'<div class="pipe-panels">{panels}</div>')


def timeline(events: list[tuple[str, str, str, str]]) -> str:
    """Events: (ISO date, date as shown, label, file). Sorted by date; dates only from files in the repository."""
    items = "".join(f'<li><time datetime="{d}">{esc(shown)}</time><span>{esc(label)} <code>{esc(source)}</code></span></li>'
                    for d, shown, label, source in sorted(events))
    return f'<ol class="timeline" aria-label="Forecast timeline">{items}</ol>'


# ----------------------------------------------------------------------------- F4 limitation cards

CAUTION_WORDS = ("not distinguishable", "не отличима", "unstable", "нестабильны", "not untouched", "не нетронутый",
                 "not verified", "не проверены", "fails", "does not contain", "look-ahead")


def limit_cards(items: list[tuple[str, str]]) -> str:
    """Grouped cards: "Caution" (a stated failure or unverified assumption) and "Note"; icon and word, not colour alone."""
    groups = {"caution": [], "note": []}
    for title, text in items:
        kind = "caution" if any(w in title.lower() for w in CAUTION_WORDS) else "note"
        card = read_card(text, 120) or f"<p>{text}</p>"
        groups[kind].append(f'<article class="limit-card limit-{kind}"><h3><span class="sev sev-{kind}" aria-hidden="true"></span> '
                            f'<span class="sev-word">{"Caution" if kind == "caution" else "Note"}:</span> {esc(title)}</h3>{card}</article>')
    out = []
    for kind, label in (("caution", "Cautions"), ("note", "Notes")):
        if groups[kind]:
            out.append(f'<div class="limit-group"><p class="m-label">{label}</p>{"".join(groups[kind])}</div>')
    return "".join(out)
