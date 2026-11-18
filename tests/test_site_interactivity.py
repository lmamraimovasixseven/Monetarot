"""D54: clickable numbers (lazy per-page source index) and the date slider of the track-record chart."""

from __future__ import annotations

import functools
import http.server
import json
import re
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
REPORT = json.loads((SITE / "build_report.json").read_text(encoding="utf-8"))
BUDGET = json.loads((ROOT / "config" / "site_budget.json").read_text(encoding="utf-8"))
TEXT_FILES = [*SITE.glob("*.html"), *SITE.glob("assets/*"), *SITE.glob("data/sources-*.json")]


def _index(page: str) -> dict:
    return json.loads((SITE / "data" / f"sources-{page.removesuffix('.html')}.json").read_text(encoding="utf-8"))


def test_source_indexes_cover_every_ledger_id_used_on_the_site():
    covered = set()
    for path in SITE.glob("data/sources-*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["csv"] == "data/evidence_ledger.csv" and (SITE / data["csv"]).is_file()
        for key, refs in data["ids"].items():
            assert len(refs) == len(data["fields"]) and all(0 <= r < len(data["strings"]) for r in refs), key
        covered |= set(data["ids"])
    assert set(REPORT["ledger_ids_used"]) <= covered


def test_every_number_on_a_page_is_in_that_pages_index_with_the_ledger_values():
    import csv

    with (ROOT / "ledger" / "evidence_ledger.csv").open(encoding="utf-8", newline="") as handle:
        ledger = {row["id"]: row for row in csv.DictReader(handle)}
    for page in REPORT["pages"]:
        used = set(re.findall(r'data-ledger="([^"]+)"', (SITE / page).read_text(encoding="utf-8")))
        if not used:
            continue
        assert 'src="assets/app.js"' in (SITE / page).read_text(encoding="utf-8"), page
        data = _index(page)
        assert used <= set(data["ids"]), (page, sorted(used - set(data["ids"]))[:5])
        for key in sorted(used)[:50]:
            row = dict(zip(data["fields"], (data["strings"][r] for r in data["ids"][key])))
            assert all(row[field] == ledger[key][field] for field in data["fields"]), key


def test_slider_ids_written_by_the_script_are_in_the_home_index():
    data = json.loads(re.search(r'<script type="application/json" id="track-json">(.*?)</script>',
                                (SITE / "index.html").read_text(encoding="utf-8")).group(1))
    ids = set(_index("index.html")["ids"])
    n = len(data["dates"])
    assert {f"dashboard:track_record/score/{i}" for i in range(n)} <= ids
    assert {f"dashboard:probabilities/{c}" for c in ("Decrease", "Hold", "Increase")} | {"dashboard:band/0", "dashboard:band/1"} <= ids
    artifact = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))["dashboard"]
    assert data["dates"] == artifact["track_record"]["dates"] and data["actual"] == artifact["track_record"]["actual"]
    assert all(abs(a - b) < 1e-6 for a, b in zip(data["score"], artifact["track_record"]["score"]))
    assert data["stored"]["date"] == artifact["latest_decision"] == data["dates"][-1]


def test_no_page_loads_an_external_resource():
    for path in TEXT_FILES:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r'\bsrc="(?:https?:)?//|<link[^>]+href="(?:https?:)?//|url\(\s*["\']?(?:https?:)?//|@import|fetch\(\s*["\']https?:', text), path.name


def test_no_cyrillic_in_pages_assets_or_source_indexes():
    for path in TEXT_FILES:
        assert not re.search("[Ѐ-ӿ]", path.read_text(encoding="utf-8")), path.name


def test_home_page_initial_load_grows_by_at_most_the_budget():
    now = sum((SITE / p).stat().st_size for p in ("index.html", "assets/style.css", "assets/app.js"))
    assert now == REPORT["index_bytes_with_assets"]
    assert now - BUDGET["baseline_index_bytes_with_assets"] <= BUDGET["max_growth_bytes"]
    try:
        old = subprocess.run(["git", "show", f"{BUDGET['baseline_commit']}:site/build_report.json"], cwd=ROOT,
                             capture_output=True, text=True, encoding="utf-8", check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return  # shallow clone without the baseline commit: the recorded baseline is used
    assert json.loads(old)["index_bytes_with_assets"] == BUDGET["baseline_index_bytes_with_assets"]


def test_without_javascript_the_slider_is_hidden_and_the_chart_unchanged():
    home = (SITE / "index.html").read_text(encoding="utf-8")
    assert '<div id="track-slider" class="track-slider" hidden>' in home
    assert 'id="tr-cursor"' in home and 'visibility="hidden"' in home
    assert 'aria-describedby="tr-hint"' in home and "Drag or use the arrow keys." in home and 'aria-live="polite"' in home
    figure = home.split('<figure id="track-record">', 1)[1].split("</figure>", 1)[0]
    assert figure.count("<circle") == len(json.loads(re.search(r'id="track-json">(.*?)</script>', home).group(1))["dates"])


def _js(body: str) -> list[str]:
    engine = ["node"] if shutil.which("node") else (["cscript", "//nologo", "//E:JScript"] if shutil.which("cscript") else None)
    if engine is None:
        pytest.skip("no JavaScript engine")
    source = (ROOT / "src" / "site_assets" / "app.js").read_text(encoding="utf-8").split("(function () {")[0]
    script = ROOT / ".pytest-temp" / "site_interactivity.js"
    script.parent.mkdir(exist_ok=True)
    script.write_text(source + "var out = (typeof console !== 'undefined') ? function (s) { console.log(s); } : function (s) { WScript.Echo(s); };\n"
                      + body, encoding="utf-8")
    return subprocess.run([*engine, str(script)], capture_output=True, text=True, check=True).stdout.splitlines()


def test_slider_readout_logic():
    """trackReadout / trackValueText read stored values only; the label follows the holdout start."""
    t = ('var t = {dates: ["2020-01-10", "2024-09-02", "2026-10-27"], holdout_start: "2024-09-02", score: [0.12345, -0.0004, -0.3057],'
         ' actual: [1, 0, -1], stored: {date: "2026-10-27"}};\n')
    lines = _js(t + "var k, r; for (k = 0; k < 3; k++) { r = trackReadout(t, k); out(r.date + '|' + r.score + '|' + r.decision + '|' + r.sample + '|' + r.stored); }\n"
                "out(trackValueText(t, 1));\n")
    assert lines[0] == "2020-01-10|+0.123|hike|in-sample fit|false"
    assert lines[1] == "2024-09-02|0.000|hold|holdout (out of sample)|false"  # rounds to zero: no sign (D42)
    assert lines[2] == "2026-10-27|-0.306|cut|holdout (out of sample)|true"
    assert lines[3] == "2 September 2024: score 0.000, NBK decision hold, holdout (out of sample)"


def test_source_row_decodes_the_compact_index():
    lines = _js('var ix = {fields: ["value", "source"], strings: ["0.5", "model/artifact.json"], ids: {"a:b": [0, 1]}};\n'
                "var r = sourceRow(ix, 'a:b'); out(r.value + '|' + r.source); out('' + sourceRow(ix, 'missing'));\n")
    assert lines == ["0.5|model/artifact.json", "null"]


def test_browser_source_window_and_slider():
    """Playwright with a local Chrome; skipped where neither is installed (CI)."""
    sync_api = pytest.importorskip("playwright.sync_api")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_api.sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(channel="chrome")
            except Exception as exc:  # noqa: BLE001
                pytest.skip(f"no local Chrome for Playwright: {exc}")
            page = browser.new_page(viewport={"width": 360, "height": 800})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{server.server_port}/index.html", wait_until="load")
            number = page.locator("#step-2 [data-ledger]").first
            assert number.get_attribute("role") == "button" and number.get_attribute("tabindex") == "0"
            number.focus()
            page.keyboard.press("Enter")
            page.wait_for_selector("#src-pop dt:has-text('Script')", timeout=5000)
            text = page.locator("#src-pop").inner_text()
            assert number.get_attribute("data-ledger") in text and "python run.py trace" in text
            page.keyboard.press("Escape")
            assert page.locator("#src-pop").is_hidden()
            assert page.evaluate("() => document.activeElement.getAttribute('data-ledger')") == number.get_attribute("data-ledger")
            slider = page.locator("#tr-pos")
            assert "holdout (out of sample)" in slider.get_attribute("aria-valuetext")
            assert "Model probabilities:" in page.locator("#tr-out").inner_text()
            slider.focus()
            for _ in range(60):
                page.keyboard.press("ArrowLeft")
            assert "in-sample fit" in slider.get_attribute("aria-valuetext")
            assert "not stored for this date" in page.locator("#tr-out").inner_text()
            assert page.locator("#tr-cursor").get_attribute("visibility") == "visible"
            assert page.evaluate("() => document.documentElement.scrollWidth <= document.documentElement.clientWidth")
            assert not errors
            browser.close()
    finally:
        server.shutdown()
