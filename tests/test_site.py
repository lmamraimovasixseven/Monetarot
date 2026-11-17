"""Блок G: сайт совпадает со свежей сборкой; числа из журнала; 360 px, бюджет скорости, палитра, alt, без CDN."""

from __future__ import annotations

import csv
import functools
import http.server
import json
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


# ----------------------------------------------------------------------------- D42: wording, signs and honest placeholders

ZERO_WITH_SIGN = re.compile(r"(?<![\w.])[-−+]0\.0+(?![0-9]*[1-9])(?![0-9])")


def _artifact() -> dict:
    import json

    return json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))


def _js_lines(body: str, full: bool = False, prefix: str = "") -> list[str]:
    engine = ["node"] if shutil.which("node") else (["cscript", "//nologo", "//E:JScript"] if shutil.which("cscript") else None)
    if engine is None:
        pytest.skip("no JavaScript engine")
    source = (ROOT / "src" / "site_assets" / "app.js").read_text(encoding="utf-8")
    if not full:
        source = source.split("(function () {")[0]
    script = ROOT / ".pytest-temp" / "site_js_lines.js"
    script.parent.mkdir(exist_ok=True)
    script.write_text("var out = (typeof console !== 'undefined') ? function (s) { console.log(s); } : function (s) { WScript.Echo(s); };\n"
                      + prefix + source + "\n" + body, encoding="utf-8")
    return subprocess.run([*engine, str(script)], capture_output=True, text=True, check=True).stdout.splitlines()


def test_no_signed_zero_on_the_site_or_from_the_formatters():
    from src import site_dashboard as sd

    assert sd.signed(-0.0001, 3) == "0.000" and sd.signed(0.0004, 3) == "0.000" and sd.signed(-0.04, 1) == "0.0"
    assert sd.signed(0.002, 3) == "+0.002" and sd.signed(-0.002, 3) == "-0.002" and sd.plain(-0.00004, 4) == "0.0000"
    for name in PAGES:
        found = ZERO_WITH_SIGN.search((SITE / name).read_text(encoding="utf-8"))
        assert not found, (name, found.group(0))
    lines = [line.strip() for line in _js_lines("out(signed(-0.0001, 3)); out(signed(-0.04, 1)); out(signed(0.0004, 3)); "
                                                "out(signed(0.002, 3)); out(signed(-0.002, 3)); out(fixed(-0.001, 2));")]
    assert lines == ["0.000", "0.0", "0.000", "+0.002", "-0.002", "0.00"]


def test_home_page_states_one_holdout_sentence_and_one_answer():
    text = (SITE / "index.html").read_text(encoding="utf-8")
    plain_text = re.sub(r"<[^>]+>", "", text)
    ledger = site_build.Ledger()
    low, high = float(ledger.raw("n:rmse_ratio_ci_low")), float(ledger.raw("n:rmse_ratio_ci_high"))
    undistinguished = low <= 1 <= high and float(ledger.raw("n:dm_squared_error_p")) >= 0.05
    box = re.search(r'id="verdict-box">(.*?)</div>', text, re.S).group(1)
    assert ("cannot be distinguished from Always Hold" in box) == undistinguished
    assert plain_text.count("Holdout RMSE ratio") == 1 and "Effect of the data update" not in text and "Past performance" not in text
    assert "option 1" not in text and "((" not in plain_text and ". if " not in plain_text
    decision = _artifact()["decision"]
    action = "Extend duration." if decision["p_cut"] > decision["binary_threshold_p_cut"] else "Do not extend duration."
    step7 = text[text.index('id="step-7"'):]
    assert re.search(r'id="answer"><strong>([^<]+)</strong>', step7).group(1) == action
    assert step7.index('id="answer"') < step7.index("three-outcome")
    assert not re.search(r">0\d [A-Z][a-z]+ \d{4}<", text), "dates without a leading zero"


def test_chart_titles_are_conclusions_drawn_from_the_chart_data():
    d = _artifact()["dashboard"]
    text = (SITE / "index.html").read_text(encoding="utf-8")
    titles = re.findall(r"<figcaption><strong>(.*?)</strong>", text)
    track = d["track_record"]
    holdout = [i for i, day in enumerate(track["dates"]) if day >= track["holdout_start"]]
    if all(track["score"][i] < 0 for i in holdout):
        assert "below zero throughout the holdout" in titles[0]
    actual = [track["actual"][i] for i in holdout]
    if actual.count(0) * 2 > len(actual):
        assert "held the rate at most decisions" in titles[0]
    values = [row[1] for row in d["contributions"]["rows"]]
    if all(v < 0 for v in values):
        assert titles[1].startswith("All ") and "towards a cut" in titles[1]
    largest = sorted(d["contributions"]["rows"], key=lambda row: abs(row[1]), reverse=True)[:2]
    assert all(row[0].split()[0].lower() in titles[1] for row in largest)


def test_evidence_page_states_the_criterion_not_a_winner():
    text = (SITE / "evidence.html").read_text(encoding="utf-8")
    assert "Winner" not in text and "Everything the Render app shows" not in text
    criterion = re.search(r'id="ev-criterion">(.*?)</p>', text).group(1)
    ratio = float(site_build.Ledger().raw("dashboard:evidence/ratio"))
    assert criterion.startswith("Meets the pre-specified criterion" if ratio < 1 else "Does not meet the pre-specified criterion")
    assert "Effect of the data update" in text, "the full paragraph stays on Evidence"


def test_corridor_starts_at_the_current_rate_and_gives_no_verdict_without_partner_data():
    block = _artifact()["carry_corridor"]
    text = (SITE / "corridor.html").read_text(encoding="utf-8")
    form = re.search(r'<form id="corridor"[^>]*>', text).group(0)
    attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', form))
    has_data = all(v is not None for v in block["partner_real_rates"].values())
    assert attrs["data-partner-data"] == str(has_data).lower() and attrs["autocomplete"] == "off"
    inputs = dict(re.findall(r'<input id="c-(\w+)"[^>]*value="([^"]+)"', text))
    assert float(inputs["rate"]) == float(block["nbk_rate"])
    # A browser that restored an old slider position (9) must still start from the value in the page.
    stubs = ("var els = {};\nfunction el(id, attrs, value) { els[id] = {attrs: attrs, value: value, defaultValue: value, textContent: '', "
             "getAttribute: function (k) { return this.attrs.hasOwnProperty(k) ? this.attrs[k] : null; }, addEventListener: function () {}}; }\n"
             "var document = {getElementById: function (id) { return els.hasOwnProperty(id) ? els[id] : null; }, querySelectorAll: function () { return []; }};\n"
             "if (typeof JSON === 'undefined') { var JSON = {parse: function (s) { return eval('(' + s + ')'); }}; }\n"
             f"el('corridor', {{'data-inflation': '{attrs['data-inflation']}', 'data-credit': '{attrs['data-credit']}', 'data-partner-data': '{attrs['data-partner-data']}', 'data-missing': '{attrs.get('data-missing', '')}'}}, null);\n"
             "el('corridor-out', {}, null);\n"
             + "".join(f"el('c-{k}', {{}}, '{v}'); el('o-{k}', {{}}, null);\n" for k, v in inputs.items())
             + "els['c-rate'].value = '9';\n"
             + (ROOT / "src" / "site_assets" / "corridor.js").read_text(encoding="utf-8") + "\n")
    # ASCII only: cscript writes in the console code page, which is not UTF-8 under PYTHONUTF8=1 (acceptance A10).
    lines = _js_lines("out(els['o-rate'].textContent); out(els['corridor-out'].textContent.replace(/[^ -~]/g, '-'));",
                      full=True, prefix=stubs)
    assert float(lines[0]) == float(block["nbk_rate"])
    if not has_data:
        missing = attrs.get("data-missing", "")
        assert lines[1].endswith("Illustration with your assumptions; no partner data" + (f" for {missing}" if missing else "") + ".")
        assert not any(label in lines[1] for label in ("below the corridor", "above the corridor", "inside the corridor", "corridor broken"))


def test_redteam_asof_and_run_pages_have_no_bare_placeholders():
    template = (ROOT / "docs" / "redteam_response.md").read_text(encoding="utf-8")
    redteam = (SITE / "redteam.html").read_text(encoding="utf-8")
    if "[FILL IN]" in template:
        assert "has not taken place yet" in redteam and "[FILL IN]" not in redteam and "<table" not in redteam
    for name in PAGES:
        assert "[FILL IN]" not in (SITE / name).read_text(encoding="utf-8"), name
    assert "UNKNOWN" not in (SITE / "team.html").read_text(encoding="utf-8")
    asof = (SITE / "asof.html").read_text(encoding="utf-8")
    assert "What the model could have known on a past decision date." in asof
    rows = re.findall(r"<tr><td>\w+</td><td>[\d-]+</td>(.*?)</tr>", asof)
    assert rows
    for row in rows:
        cells = re.findall(r"<td>(.*?)</td>", row)
        assert cells[1] == "units not documented" or ('data-ledger="' in cells[0] and cells[1]), row
    assert "(needs make; on Windows run the python commands above)" in (SITE / "run.html").read_text(encoding="utf-8")
    assert 'class="nowrap">Known from</th>' in (SITE / "patterns.html").read_text(encoding="utf-8")


# ----------------------------------------------------------------------------- D43: one unit fact everywhere, look-ahead sentence


def test_data_methods_and_asof_state_the_same_raw_units():
    units = site_build.raw_units()
    data = (SITE / "data.html").read_text(encoding="utf-8")
    methods = (SITE / "methods.html").read_text(encoding="utf-8")
    asof = (SITE / "asof.html").read_text(encoding="utf-8")
    model = _artifact()["dashboard"]["model"]
    for feature, label in zip(model["features"], model["labels"]):
        if units.get(feature):
            fact = f"underlying source units: {units[feature]} (docs/facts_to_fill.csv)"
            stored = next(row[2] for row in _artifact()["dashboard"]["provenance"]["latest"]["rows"] if row[0] == label)
            if site_build.SOURCE_UNITS_UNKNOWN in stored:
                assert fact in data and fact in methods, label
            assert f"<td>{feature}</td>" in asof and units[feature] in asof
    if any(units.values()):
        assert site_build.SOURCE_UNITS_UNKNOWN not in data.replace("gives the underlying source units as unknown", "")


def test_look_ahead_box_is_one_sentence_with_ledger_total():
    text = (SITE / "index.html").read_text(encoding="utf-8")
    box = re.search(r'id="look-ahead">(.*?)</div>', text, re.S).group(1)
    assert box.startswith("Look-ahead cannot be excluded: real publication lags are not documented")
    assert "UNKNOWN" not in box and 'data-ledger="n:n_usable"' in box and 'href="evidence.html#ev-limitations"' in box
    total = site_build.Ledger().raw("n:n_usable")
    assert re.findall(r'data-ledger="n:n_usable">([^<]+)<', box) and set(re.findall(r'data-ledger="n:n_usable">([^<]+)<', box)) == {total}


# ----------------------------------------------------------------------------- D44: look-ahead counts have ledger rows


def test_look_ahead_counts_on_the_home_page_come_from_ledger_rows():
    import json

    limitation = json.loads((ROOT / "data" / "processed" / "provenance.json").read_text(encoding="utf-8"))["release_lag_limitation"]
    ledger_values = site_build.Ledger().values
    assert str(limitation["decisions"]) == ledger_values["n:n_usable"], "the box divides by n:n_usable"
    box = re.search(r'id="look-ahead">(.*?)</div>', (SITE / "index.html").read_text(encoding="utf-8"), re.S).group(1)
    shown = dict(re.findall(r'data-ledger="lookahead:(\w+)">([^<]+)<', box))
    expected = {s["feature"]: str(s["decisions_where_bound_exceeds_window"]) for s in limitation["series"]
                if s["decisions_where_bound_exceeds_window"]}
    assert shown == expected
    assert all(ledger_values[f"lookahead:{feature}"] == value for feature, value in shown.items())


def test_step_one_states_cost_of_error_without_this_note_and_who_benefits():
    """D52: the three Usefulness Test lines of the decision memo on the home page; losses come from the ledger."""
    home = (SITE / "index.html").read_text(encoding="utf-8")
    step1 = home.split('id="step-1"', 1)[1].split("</section>", 1)[0]
    for label in ("Cost of error:", "Without this note:", "Who benefits:"):
        assert f"<strong>{label}</strong>" in step1
    assert 'data-ledger="decision:binary_losses/lengthen_but_no_cut"' in step1
    assert 'data-ledger="decision:binary_losses/not_lengthen_but_cut"' in step1
    assert "Equal losses is an assumption" in step1 and "not a finding from interviews" in step1


def test_history_chart_title_states_a_conclusion_computed_from_the_data():
    history = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))["dashboard"]["history"]
    evidence = (SITE / "evidence.html").read_text(encoding="utf-8")
    title = re.search(r'id="ev-history"><h2>History</h2><figure><figcaption><strong>(.*?)</strong>', evidence).group(1)
    holds = sum(1 for v in history["score"] if int(v) == 0)
    assert title.startswith(f"The NBK held the rate at {holds} of {len(history['score'])} decisions")
    if history["base_rate"]:
        assert f"to {max(history['base_rate']):g}%" in title
