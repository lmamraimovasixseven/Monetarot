"""Блок G: сайт совпадает со свежей сборкой; числа из журнала; 360 px, бюджет скорости, палитра, alt, без CDN."""

from __future__ import annotations

import csv
import functools
import http.server
import re
import shutil
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from src import app, decision_rule, site_build

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
PAGES = [name for name, _ in site_build.PAGES]
# Заглушки — в верхнем регистре (английское слово "unknown" во фразах Render заглушкой не является); извинения — в любом.
APOLOGY = re.compile(r"TODO|UNKNOWN|\[add link\]|\[FILL IN\]|FILL IN|(?i:извин|к сожалению|sorry|unfortunately|apolog)")


def test_committed_site_equals_a_fresh_build(tmp_path):
    site_build.build(tmp_path / "site")
    for path in sorted(p for p in (tmp_path / "site").rglob("*") if p.is_file()):
        relative = path.relative_to(tmp_path / "site")
        assert (SITE / relative).read_bytes() == path.read_bytes(), relative


def test_every_number_on_the_site_has_a_ledger_row():
    with (ROOT / "ledger" / "evidence_ledger.csv").open(encoding="utf-8", newline="") as handle:
        ids = {row["id"] for row in csv.DictReader(handle)}
    for name in PAGES:
        used = re.findall(r'data-ledger="([^"]+)"', (SITE / name).read_text(encoding="utf-8"))
        assert set(used) <= ids, (name, sorted(set(used) - ids)[:5])
    assert {"chart:holdout", "chart:base_rate"} <= ids


def test_show_it_home_page_has_no_placeholders_or_apologies():
    text = (SITE / "index.html").read_text(encoding="utf-8")
    assert not APOLOGY.search(text), APOLOGY.search(text).group(0)
    for step in ("1. The decision", "2. The tension", "3. The evidence", "4. The forecast", "5. The mechanism", "6. The risk", "7. The ask"):
        assert step in text
    assert text.count("<svg") <= 3 and '<html lang="en">' in text
    assert "awaiting confirmation" not in text and "USER ASSUMPTION" not in text, "service notes belong on methods.html"
    assert "with equal losses" in text and "calibration is unverified" in text
    assert "English summary" not in text, "the whole site is English; one short introduction is enough"


def test_home_page_follows_the_render_placement():
    text = (SITE / "index.html").read_text(encoding="utf-8")
    steps = {n: text.index(f'id="step-{n}"') for n in range(1, 8)}
    assert list(steps.values()) == sorted(steps.values())
    placed = {"track-record": 3, "drivers": 3, "round-cards": 4, "headline": 4, "scenario": 5, "anomaly-warning": 6,
              "look-ahead": 6, "falsification": 6, "freshness": 6}
    for element, step in placed.items():
        position = text.index(f'id="{element}"')
        assert steps[step] < position < steps.get(step + 1, len(text)), (element, step)
    assert 'id="render-link"' in text


def _parity_rows() -> list[dict[str, str]]:
    lines = [line for line in (ROOT / "docs" / "site_parity.md").read_text(encoding="utf-8").splitlines() if line.startswith("|")]
    header = [c.strip() for c in lines[0].strip("|").split("|")]
    return [dict(zip(header, (c.strip() for c in line.strip("|").split("|")))) for line in lines[2:]]


def test_every_parity_element_is_on_the_site():
    rows = _parity_rows()
    assert rows and {"Элемент Render", "Где на сайте", "Способ", "Статус", "Контрольный текст"} <= set(rows[0])
    for row in rows:
        targets = re.findall(r"`([a-z]+\.html)#([\w-]+)`", row["Где на сайте"])
        assert targets, row["Элемент Render"]
        for page_name, anchor in targets:
            html_text = (SITE / page_name).read_text(encoding="utf-8")
            scripts = "".join((SITE / src).read_text(encoding="utf-8") for src in re.findall(r'<script src="([^"]+)"', html_text))
            assert f'id="{anchor}"' in html_text, (row["Элемент Render"], page_name, anchor)
            assert row["Контрольный текст"] in html_text + scripts, (row["Элемент Render"], row["Контрольный текст"])
        assert row["Статус"] in {"перенесено", "иначе"}, row
        if row["Статус"] == "иначе":
            assert any(page_name == "methods.html" for page_name, _ in targets), "every difference is explained on methods.html"


# Proper names that may stay in Cyrillic on the site (none so far); data files in site/data/ are not checked.
ALLOWED_CYRILLIC: set[str] = set()


def test_site_is_english_without_cyrillic():
    """D41: every page, script and stylesheet of the site is English; Russian sources go through src/site_i18n.py."""
    files = [*SITE.glob("*.html"), *SITE.glob("assets/*.js"), *SITE.glob("assets/*.css")]
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8")
        words = set(re.findall("[Ѐ-ӿ]+", text)) - ALLOWED_CYRILLIC
        assert not words, (path.name, sorted(words)[:10])
        if path.suffix == ".html":
            assert '<html lang="en">' in text and '<meta name="description" content="' in text, path.name


def test_translation_layer_fails_loudly_and_keeps_numbers():
    from src import site_i18n

    with pytest.raises(site_i18n.UntranslatedError):
        site_i18n.tr("строка без перевода")
    reason = "новый уровень держится: в следующих 4 мес. (предварительно: меньше 6 мес.) сохраняется 87% скачка"
    english = site_i18n.tr(reason)
    assert "4 months" in english and "87%" in english and "fewer than 6 months" in english
    assert site_i18n.tr("plain English 0.995") == "plain English 0.995"


def test_readable_at_360px():
    css = (SITE / "assets" / "style.css").read_text(encoding="utf-8")
    for name in PAGES:
        assert 'name="viewport" content="width=device-width, initial-scale=1"' in (SITE / name).read_text(encoding="utf-8")
    fixed = [int(w) for prop, w in re.findall(r"(?<![-\w])(width|min-width)\s*:\s*(\d+)px", css)]
    assert all(w <= 360 for w in fixed), fixed
    assert "svg { width: 100%" in css and "overflow-x: auto" in css


def test_charts_have_alt_text_titles_and_colour_blind_safe_colours():
    allowed = {c.lower() for c in site_build.PALETTE.values()}
    for name in PAGES:
        text = (SITE / name).read_text(encoding="utf-8")
        for svg in re.findall(r"<svg.*?</svg>", text, flags=re.S):
            assert re.search(r'role="img" aria-label="[^"]{20,}"', svg) and "<title>" in svg
            colours = {c.lower() for c in re.findall(r'(?:fill|stroke)="(#[0-9A-Fa-f]{6})"', svg)}
            assert colours <= allowed, colours - allowed


def test_no_external_fonts_scripts_or_cdn():
    for path in [*SITE.glob("*.html"), *SITE.glob("assets/*")]:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r'<script[^>]+src="https?:|<link[^>]+href="https?:|@import|url\(https?:|fonts\.googleapis', text), path.name


def test_home_page_loads_within_the_budget():
    report_bytes = sum((SITE / p).stat().st_size for p in ("index.html", "assets/style.css", "assets/app.js"))
    assert report_bytes < 300_000  # < 2.4 s even at 1 Mbit/s
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        started = time.perf_counter()
        for resource in ("index.html", "assets/style.css", "assets/app.js"):
            with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/{resource}", timeout=3) as response:
                assert response.status == 200 and response.read()
        assert time.perf_counter() - started < 3.0
    finally:
        server.shutdown()


def test_threshold_slider_matches_python():
    engine = ["node"] if shutil.which("node") else (["cscript", "//nologo", "//E:JScript"] if shutil.which("cscript") else None)
    if engine is None:
        pytest.skip("no JavaScript engine")
    source = (ROOT / "src" / "site_assets" / "app.js").read_text(encoding="utf-8").split("(function () {")[0]
    ratios = [0.25, 0.5, 1.0, 1.585, 3.3]
    script = ROOT / ".pytest-temp" / "threshold.js"
    script.parent.mkdir(exist_ok=True)
    script.write_text(source + "var out = (typeof console !== 'undefined') ? function (s) { console.log(s); } : function (s) { WScript.Echo(s); };\n"
                      + "".join(f"out('' + threshold({r}));\n" for r in ratios), encoding="utf-8")  # строка: без локали
    values = subprocess.run([*engine, str(script)], capture_output=True, text=True, check=True).stdout.split()
    for r, v in zip(ratios, values):
        assert float(v) == pytest.approx(decision_rule.binary_threshold(1.0, r), abs=1e-9)


def _js(body: str) -> list[str]:
    engine = ["node"] if shutil.which("node") else (["cscript", "//nologo", "//E:JScript"] if shutil.which("cscript") else None)
    if engine is None:
        pytest.skip("no JavaScript engine")
    source = (ROOT / "src" / "site_assets" / "app.js").read_text(encoding="utf-8").split("(function () {")[0]
    script = ROOT / ".pytest-temp" / "site_js.js"
    script.parent.mkdir(exist_ok=True)
    script.write_text(source + "var out = (typeof console !== 'undefined') ? function (s) { console.log(s); } : function (s) { WScript.Echo(s); };\n"
                      + body, encoding="utf-8")
    return subprocess.run([*engine, str(script)], capture_output=True, text=True, check=True).stdout.split()


def _js_list(values) -> str:
    return "[" + ", ".join(_js_list(v) if isinstance(v, list) else (f'"{v}"' if isinstance(v, str) else repr(float(v))) for v in values) + "]"


def test_scenario_slider_matches_python():
    """Ordered logit и 95% полоса в браузере = app.ordered_probabilities и app.score_and_delta_band до 1e-6."""
    import json
    import numpy as np

    artifact = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))
    m = artifact["dashboard"]["model"]
    literal = (f"var m = {{features: {_js_list(m['features'])}, slopes: {_js_list(m['slopes'])}, cutpoints: {_js_list(m['cutpoints'])}, "
               f"names: {_js_list(m['covariance_names'])}, covariance: {_js_list(m['covariance'])}, z: {m['z_975']!r}}};\n")
    rng = np.random.default_rng(11)
    scenarios = [list(m["latest"])]
    for slider in artifact["dashboard"]["slider"]:
        for value in (slider["min"], slider["max"], float(rng.uniform(slider["min"], slider["max"]))):
            x = list(m["latest"])
            x[m["features"].index(slider["feature"])] = value
            scenarios.append(x)
    body = literal + "".join(f"var p = orderedProbabilities(m, {_js_list(x)}), b = scoreBand(m, {_js_list(x)});"
                             " out(p.Decrease + '|' + p.Hold + '|' + p.Increase + '|' + b[0] + '|' + b[1] + '|' + b[2]);\n" for x in scenarios)
    lines = _js(body)
    assert len(lines) == len(scenarios)
    for x, line in zip(scenarios, lines):
        values = [float(v) for v in line.split("|")]
        features = dict(zip(m["features"], x))
        probabilities = app.ordered_probabilities(artifact, features)
        score, low, high = app.score_and_delta_band(artifact, features)
        expected = [probabilities["Decrease"], probabilities["Hold"], probabilities["Increase"], score, low, high]
        assert values == pytest.approx(expected, abs=1e-6)


def test_round_selection_and_dates_match_render():
    import json
    from datetime import date, timedelta

    from src import site_dashboard

    artifact = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))
    rounds = artifact["dashboard"]["rounds"]
    dates = rounds["dates"]
    # «сегодня» до, на и после каждой даты календаря и на дату последнего решения в данных
    days = [date.fromisoformat(d) for d in [*dates, artifact["dashboard"]["latest_decision"]]]
    todays = sorted({(d + timedelta(days=k)).isoformat() for d in days for k in (-1, 0, 1)})
    body = "".join(f"var r = nextRounds({_js_list(dates)}, '{t}', {str(rounds['verified']).lower()}); "
                   "out(r[0] + '|' + r[1] + '|' + longDate(r[0]).split(' ').join('_'));\n" for t in todays)
    lines = _js(body)
    path = ROOT / "config" / "forecast_rounds.json"
    for today, line in zip(todays, lines):
        first, second, shown = line.split("|")
        expected, _, _ = app.load_next_decisions(path, today=date.fromisoformat(today))
        got = [None if v in ("null", "undefined") else v for v in (first, second)]
        assert got == [d.isoformat() if d else None for d in expected], today
        assert shown.replace("_", " ") == site_dashboard.long_date(expected[0]), today


def test_pages_workflow_publishes_the_site_folder():
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert "actions/upload-pages-artifact" in workflow and "path: site" in workflow and "actions/deploy-pages" in workflow
