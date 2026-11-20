"""D60, D61: the home page tells the seven steps as a story. Presentation only: every number is a ledger row, connectors carry no
fact, nothing is folded or moved between steps, the rail counter exists only with JavaScript. Relations only (AGENTS.md
rule 10)."""

from __future__ import annotations

import csv
import html
import json
import re
from pathlib import Path

from src import site_build

ROOT = Path(__file__).resolve().parents[1]
HOME = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
ARTIFACT = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))


def _text(fragment: str) -> str:
    plain = re.sub(r'<span class="gloss-tip"[^>]*>.*?</span>', "", fragment, flags=re.S)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", plain))).strip()


def _step(n: int) -> str:
    """From the step's section tag to the next step (or the closing section); steps may contain nested sections."""
    rest = HOME.split(f'<section id="step-{n}">', 1)[1]
    end = f'<section id="step-{n + 1}">' if n < 7 else '<section id="read-further">'
    return rest.split(end, 1)[0]


def test_every_step_has_its_title_then_a_full_sentence_headline():
    for n, title in enumerate(site_build.STEP_TITLES, start=1):
        head = re.match(r'<h2><span class="step-tag">(.*?)</span>(.*?)</h2>', _step(n), re.S)
        assert head, n
        assert _text(head.group(1)) == f"{n}. {title}."
        sentence = _text(head.group(2))
        assert sentence[:1].isupper() and sentence.endswith(".") and len(sentence.split()) >= 6, (n, sentence)


def test_numbers_in_headlines_and_the_answer_are_ledger_rows():
    with (ROOT / "ledger" / "evidence_ledger.csv").open(encoding="utf-8", newline="") as handle:
        ids = {row["id"] for row in csv.DictReader(handle)}
    answer = re.search(r'<p class="story-answer" id="story-answer">(.*?)</p>', HOME, re.S).group(1)
    for fragment in [answer] + [re.match(r"<h2>(.*?)</h2>", _step(n), re.S).group(1) for n in range(1, 8)]:
        without_numbers = re.sub(r'<span class="num" data-ledger="[^"]+">[^<]*</span>', "", fragment)
        prose = re.sub(r'<span class="step-tag">.*?</span>', "", without_numbers)
        # Dates (day month year) are text from the schedule and the forecast log; every other figure must be a ledger span.
        prose = re.sub(r"\b\d{1,2} (January|February|March|April|May|June|July|August|September|October|November|December) \d{4}\b", "", prose)
        # "95%" names the interval level (a fixed method setting), not a data value.
        assert not re.search(r"\d", _text(prose).replace("95%", "")), _text(prose)
        assert set(re.findall(r'data-ledger="([^"]+)"', fragment)) <= ids


def test_connectors_carry_no_number_and_no_fact():
    links = re.findall(r'<p class="story-link">(.*?)</p>', HOME)
    assert links == [html.escape(c) for c in site_build.CONNECTORS] and len(links) == len(site_build.STEP_TITLES) - 1
    for n, text in enumerate(links, start=1):
        assert not re.search(r"\d|data-ledger|<", text)
        assert f'<p class="story-link">{text}</p>' in _step(n)


def test_first_screen_holds_the_question_the_answer_and_the_answer_desk():
    lead = HOME.split('<section class="lead" id="top">', 1)[1].split("</section>", 1)[0]
    assert lead.count("<h1>") == 1 and 'class="pscale"' in lead
    assert lead.index("<h1>") < lead.index('id="story-answer"') < lead.index('id="desk"')
    # The three panels of the answer desk stay in the opening section, as before D60.
    assert all(panel in lead for panel in ("desk-outcome", "desk-score", "desk-action")) and 'class="research"' not in lead
    probabilities = {c: float(ARTIFACT["dashboard"]["probabilities"][c]) for c in ("Increase", "Hold", "Decrease")}
    answer = _text(re.search(r'id="story-answer">(.*?)</p>', lead, re.S).group(1))
    most = max(probabilities, key=probabilities.get)
    assert answer.startswith(f"Most likely the NBK {site_build.CLASS_VERB[most]}:")
    order = [site_build.CLASS_WORD[c] for c in sorted(probabilities, key=lambda c: -probabilities[c])]
    assert re.findall(r"[a-z]+", answer.split(":", 1)[1]) == order


def test_only_the_research_index_moved_and_it_closes_the_page():
    assert HOME.index('<section id="read-further"><h2>Read further</h2>') > HOME.index('<section id="step-7">')
    assert HOME.count('class="research"') == 1 and HOME.index('class="research"') > HOME.index('id="read-further"')
    assert HOME.index('<section class="lead-notes" id="overview">') < HOME.index('<section id="step-1">')
    assert 'id="context"' in HOME.split('id="overview"', 1)[1].split('<section id="step-1">', 1)[0]


def test_every_block_stays_in_its_step():
    """The blocks of each step as before D60 (the placement test pins only some of them)."""
    expected = {1: ['id="usefulness"'], 2: ["with equal losses"], 3: ['id="track-record"', 'id="drivers"', "On RPS the model"],
                4: ['id="headline"', 'id="round-layout"', 'id="round-cards"', 'id="verdict-box"', 'id="decision-rule"',
                    'id="forecast-log"', "Expected rate after the decision", 'class="timeline"'],
                5: ['id="scenario"'],
                6: ['id="freshness"', 'id="anomaly-warning"', 'id="staleness"', 'id="look-ahead"', 'id="falsification"',
                    'id="ovb-risk"', "All model limits"],
                7: ['id="answer"', "three-outcome losses"]}
    for n, needles in expected.items():
        for needle in needles:
            assert needle in _step(n), (n, needle)


def test_nothing_is_folded_by_the_story():
    """Every block stays visible without a click: no D60 fold; the only read-more cards are the D56 ones made from long
    paragraphs."""
    assert "step-more" not in HOME
    # The one disclosure on the page is the "Why these probabilities?" block that was there before D60 (Render parity).
    assert re.findall(r"<details[^>]*>", HOME) == [m for m in re.findall(r"<details[^>]*>", HOME) if 'id="why"' in m]
    app = (ROOT / "src" / "site_assets" / "app.js").read_text(encoding="utf-8")
    assert 'all("p.read-card").forEach' in app and "step-more" not in app


def test_rail_is_created_by_script_only():
    assert "rail-pos" not in HOME
    app = (ROOT / "src" / "site_assets" / "app.js").read_text(encoding="utf-8")
    assert 'el("p", "", "rail-pos")' in app and 'setAttribute("aria-live", "polite")' in app
    onpage = re.search(r'<nav class="onpage".*?</nav>', HOME, re.S).group(0)
    assert re.findall(r'href="#(step-\d)"', onpage) == [f"step-{n}" for n in range(1, 8)]


def test_step_one_states_the_loss_as_an_assumption():
    head = _text(re.match(r"<h2>(.*?)</h2>", _step(1), re.S).group(1))
    assert "under our stated loss assumption of" in head
    losses = ARTIFACT["decision"]["binary_losses"]
    assert ("for a wrong call either way" in head) == (losses["lengthen_but_no_cut"] == losses["not_lengthen_but_cut"])
    assert "Equal losses is an assumption" in _step(1)


def test_step_four_headline_is_never_stronger_than_the_stored_verdict():
    ledger = site_build.Ledger()
    low, high = float(ledger.raw("n:rmse_ratio_ci_low")), float(ledger.raw("n:rmse_ratio_ci_high"))
    separates = (not (low <= 1 <= high), float(ledger.raw("n:dm_squared_error_p")) < 0.05)
    head = _text(re.match(r"<h2>(.*?)</h2>", _step(4), re.S).group(1))
    assert ("cannot be distinguished" in head) == (not any(separates))
    assert "better" not in head.lower() and "Holdout RMSE ratio" not in head


def test_step_seven_scores_the_forecast_without_claiming_it_will_be_confirmed():
    head = _text(re.match(r"<h2>(.*?)</h2>", _step(7), re.S).group(1))
    with (ROOT / "docs" / "forecast_log.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    target = ARTIFACT["dashboard"]["rounds"]["default"][0]
    entries = [r for r in rows if r["target_decision_date"] == target]
    if entries:
        assert site_build.plain_date(entries[-1]["logged_at_utc"][:10]) in head
        assert "is the next outcome it will be scored against" in head
    assert "whether it was right" not in head and "will show" not in head


# ----------------------------------------------------------------------------- D61: Story view and Full view

APP = (ROOT / "src" / "site_assets" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "site" / "assets" / "style.css").read_text(encoding="utf-8")
LEDGER_SPAN = r'<span class="num" data-ledger="[^"]+">[^<]*</span>'


def _detail_ranges() -> list[tuple[int, int]]:
    """Spans of the elements Story view hides: every div whose class list holds "detail", and the overview section."""
    ranges, stack = [], []
    for m in re.finditer(r"<div\b([^>]*)>|</div>", HOME):
        if m.group(0).startswith("</"):
            start, hides = stack.pop()
            if hides:
                ranges.append((start, m.end()))
        else:
            cls = re.search(r'class="([^"]*)"', m.group(1))
            stack.append((m.start(), bool(cls and "detail" in cls.group(1).split())))
    assert not stack
    start = HOME.index('<section class="lead-notes" id="overview">')
    return ranges + [(start, HOME.index("</section>", start))]


def _hidden_in_story(needle: str) -> bool:
    i = HOME.index(needle)
    return any(a <= i < b for a, b in _detail_ranges())


def _d61_block() -> str:
    """The D61 code of app.js without its comments."""
    return re.sub(r"/\*.*?\*/", "", "/* D61." + APP.split("/* D61.", 1)[1].split("/* F7.", 1)[0], flags=re.S)


def test_story_view_is_the_default_with_javascript_and_full_view_without():
    script = re.search(r"<script>(.*?)</script>", HOME, re.S).group(1)
    assert script == site_build.VIEW_SCRIPT and HOME.index("<script>") < HOME.index('<section class="lead" id="top">')
    # Story view unless "full" was stored; storage that throws also gives Story view.
    key = re.fullmatch(r'var c=document\.documentElement\.classList;try\{if\(localStorage\.getItem\("([^"]+)"\)!=="full"\)'
                       r'c\.add\("story"\)\}catch\(e\)\{c\.add\("story"\)\}', script)
    assert key and key.group(1) == site_build.VIEW_KEY
    # Without JavaScript nothing sets the class, and every rule that hides content needs it, on screen only.
    assert not re.search(r'<html[^>]*class="[^"]*story', HOME)
    screen = CSS.split("@media screen {", 1)[1].split("\n}", 1)[0]
    hiding = [sel for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", CSS)
              if "display: none" in body and re.search(r"\.detail(?![\w-])|#overview", sel)]
    assert hiding and all(part.strip().startswith("html.story") for rule in hiding for part in rule.split(","))
    assert all(rule.strip() in screen for rule in hiding)


def test_no_javascript_fallback_shows_everything_and_no_control():
    switch = re.search(r'<div class="view-switch"[^>]*>(.*?)</div>', HOME, re.S)
    assert " hidden" in switch.group(0).split(">", 1)[0] and HOME.count('class="view-switch"') == 1
    assert re.findall(r'aria-pressed="(true|false)"', switch.group(1)) == ["true", "false"]
    toggles = re.findall(r'<button type="button" class="pill details-toggle"[^>]*>', HOME)
    assert toggles and all(" hidden" in t and 'aria-expanded="false"' in t for t in toggles)
    # The script only unhides the controls; print shows the full view without them.
    assert "views[0].parentNode.hidden = false" in _d61_block() and "b.hidden = false" in _d61_block()
    printed = CSS.split("@media print {", 1)[1].split("}", 1)[0]
    assert ".view-switch" in printed and ".details-toggle" in printed


def test_switch_state_persists_through_storage_inside_try():
    block = _d61_block()
    assert f'VIEW_KEY = "{site_build.VIEW_KEY}"' in block
    stored = "try { localStorage.setItem(VIEW_KEY, v); }"
    assert stored in block and "localStorage" not in block.replace(stored, "")
    assert 'setAttribute("aria-pressed"' in block and 'setAttribute("aria-expanded"' in block


def test_full_view_sentences_stay_in_the_html():
    """Story view only hides: the D61 script changes classes, attributes and its own button labels, never page content."""
    block = _d61_block()
    assert not re.search(r"removeChild|\.remove\(|innerHTML|outerHTML|insertAdjacent|replaceWith", block)
    assert re.findall(r"(\w+)\.textContent\s*=", block) == ["b"]
    # Text of the full view = text Story view shows + text of the hidden blocks; nothing else differs.
    ranges = sorted(_detail_ranges())
    outer = [(a, b) for a, b in ranges if not any((c, d) != (a, b) and c <= a and b <= d for c, d in ranges)]
    shown, last = [], 0
    for a, b in outer:
        shown.append(HOME[last:a])
        last = b
    shown.append(HOME[last:])
    glyphs = lambda part: re.sub(r"\s", "", _text(part))  # noqa: E731
    assert outer and len(glyphs(HOME)) == len(glyphs("".join(shown))) + sum(len(glyphs(HOME[a:b])) for a, b in outer)


def test_new_sentences_contain_no_digit_except_ledger_numbers():
    with (ROOT / "ledger" / "evidence_ledger.csv").open(encoding="utf-8", newline="") as handle:
        ids = {row["id"] for row in csv.DictReader(handle)}
    scene = re.search(r'<p class="story-scene" id="story-scene">(.*?)</p>', HOME, re.S).group(1)
    plain = [re.search(rf'<p class="story-plain" id="plain-{n}">(.*?)</p>', _step(n), re.S).group(1) for n in range(1, 8)]
    for fragment in [scene] + plain:
        prose = _text(re.sub(LEDGER_SPAN, "", fragment))
        assert not re.search(r"\d", prose) and "better" not in prose.lower(), prose
        assert set(re.findall(r'data-ledger="([^"]+)"', fragment)) <= ids
        assert prose[:1].isupper() and _text(fragment).endswith(".")
    assert _text(scene) == site_build.STORY_SCENE
    # Each plain sentence sits right under its headline.
    for n in range(1, 8):
        assert re.match(r'<h2>.*?</h2><p class="story-plain"', _step(n), re.S), n


def test_story_view_keeps_the_answer_and_the_main_visual_of_each_step():
    visible = {0: ['id="story-answer"', 'class="pscale"', "desk-action", "Portfolio implication", 'id="story-scene"'],
               1: ['id="plain-1"', 'id="usefulness"', "Cost of error", "Who benefits"], 2: ['id="plain-2"'],
               3: ['id="plain-3"', 'id="track-record"', 'id="track-slider"'], 4: ['id="plain-4"', 'id="verdict-box"'],
               5: ['id="plain-5"', 'id="scenario"'], 6: ['id="plain-6"', 'id="look-ahead"', 'id="anomaly-warning"', 'id="freshness"'],
               7: ['id="plain-7"', 'id="answer"', "three-outcome losses"]}
    if 'id="ratio"' in HOME:
        visible[2].append('id="ratio"')
    hidden = {0: ["desk-score", 'id="context"'], 3: ['id="drivers"', "On RPS the model"],
              4: ['id="headline"', 'id="round-cards"', 'id="decision-rule"', 'id="forecast-log"', 'class="timeline"'],
              6: ['id="staleness"', 'id="falsification"', 'id="ovb-risk"', "All model limits"]}
    for n, needles in visible.items():
        for needle in needles:
            assert not _hidden_in_story(needle), (n, needle)
    for n, needles in hidden.items():
        for needle in needles:
            assert _hidden_in_story(needle), (n, needle)
    for n in range(1, 7):
        assert not _hidden_in_story(f'<p class="story-link">{html.escape(site_build.CONNECTORS[n - 1])}</p>'), n


def test_each_step_with_hidden_blocks_has_one_button_for_its_own_step():
    for n in range(1, 8):
        part = _step(n)
        offset = HOME.index(f'<section id="step-{n}">')
        has_hidden = any(offset <= a < offset + len(part) for a, _ in _detail_ranges())
        controls = re.findall(r'class="pill details-toggle"[^>]*aria-controls="([^"]+)"', part)
        assert controls == ([f"step-{n}"] if has_hidden else []), n
    lead = HOME.split('<section class="lead" id="top">', 1)[1].split("</section>", 1)[0]
    assert re.findall(r'class="pill details-toggle"[^>]*aria-controls="([^"]+)"', lead) == ["top overview"]
