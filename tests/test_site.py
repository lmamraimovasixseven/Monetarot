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

from src import decision_rule, site_build

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
PAGES = [name for name, _ in site_build.PAGES]
APOLOGY = re.compile(r"TODO|UNKNOWN|\[add link\]|FILL IN|извин|к сожалению|sorry|unfortunately|apolog", re.I)


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
    for step in ("1. Решение", "2. Напряжение", "3. Доказательства", "4. Прогноз", "5. Механизм", "6. Риск", "7. Действие"):
        assert step in text
    assert text.count("<svg") <= 3 and 'lang="en"' in text


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


def test_pages_workflow_publishes_the_site_folder():
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert "actions/upload-pages-artifact" in workflow and "path: site" in workflow and "actions/deploy-pages" in workflow
