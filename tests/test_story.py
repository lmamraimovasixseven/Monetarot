"""D60: the home page tells the seven steps as a story. Presentation only: every number is a ledger row, connectors carry no
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
