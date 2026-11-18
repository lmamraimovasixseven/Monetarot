"""Browser smoke run of site/ (D56): every page at 1280 and 360 px, console errors and warnings, failed requests,
horizontal scroll, and the interactive features. With `shots`, screenshots go to docs/site_parity/d56_*.jpg.

Usage: python scripts/site_smoke.py [shots]   (needs playwright and a local Chrome; not part of CI or run.py update)
"""
import functools
import http.server
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = len(sys.argv) > 1 and sys.argv[1] == "shots"
OUT = ROOT / "docs" / "site_parity"
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "site"))
handler.log_message = lambda *a, **k: None
server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{server.server_port}"
problems = []
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        for width in (1280, 360):
            page = browser.new_page(viewport={"width": width, "height": 900})
            msgs, bad = [], []
            page.on("console", lambda m: msgs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
            page.on("pageerror", lambda e: msgs.append(f"pageerror: {e}"))
            page.on("response", lambda r: bad.append(f"{r.status} {r.url}") if r.status >= 400 else None)
            for name in sorted(q.name for q in (ROOT / "site").glob("*.html")):
                msgs.clear(); bad.clear()
                page.goto(f"{base}/{name}", wait_until="load")
                page.wait_for_timeout(300)
                sw = page.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
                if sw[0] > sw[1]:
                    problems.append(f"{width} {name} horizontal scroll {sw}")
                first = page.locator("span[data-ledger]:visible").first
                if first.count():
                    first.click()
                    try:
                        page.wait_for_selector("#src-pop dt:has-text('Script')", timeout=5000)
                    except Exception:
                        problems.append(f"{width} {name} popup did not load")
                    page.keyboard.press("Escape")
                if msgs or bad:
                    problems.append(f"{width} {name} console/network: {msgs + bad}")
                print(width, name, "ok" if not (msgs or bad) else msgs + bad, sw)
            # home interactions
            page.goto(f"{base}/index.html", wait_until="load")
            page.locator("#track-record").scroll_into_view_if_needed()
            page.wait_for_timeout(1500)
            dot = page.locator("#track-record circle.tr-dot").nth(40)
            dot.click()
            page.wait_for_selector("#src-pop dt:has-text('Script')", timeout=5000)
            print(width, "point popup:", page.locator("#src-pop dd").first.inner_text())
            page.keyboard.press("Escape")
            box = page.locator("#track-record svg").bounding_box()
            page.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
            print(width, "crosshair tip:", page.locator(".chart-tip").inner_text(), page.locator("#tr-hover").get_attribute("visibility"))
            if SHOTS:
                page.screenshot(path=str(OUT / f"d56_{width}_score_crosshair.jpg"), type="jpeg", quality=55,
                                clip={"x": 0, "y": max(0, box["y"] - 80), "width": width, "height": min(900, box["height"] + 420)})
            page.locator('[data-range="12m"]').click()
            page.wait_for_timeout(500)
            print(width, "12m dots:", page.locator("#track-record circle.tr-dot").count())
            page.locator('[data-class="Hold"]').click()
            print(width, "hold hidden:", page.evaluate("() => getComputedStyle(document.querySelector('#track-record .m-Hold')).display"))
            pos = page.locator("#tr-pos"); pos.focus()
            for _ in range(5):
                page.keyboard.press("ArrowLeft")
            print(width, "slider:", pos.get_attribute("aria-valuetext"))
            if SHOTS:
                page.screenshot(path=str(OUT / f"d56_{width}_score_12m_legend.jpg"), type="jpeg", quality=55,
                                clip={"x": 0, "y": max(0, box["y"] - 80), "width": width, "height": min(900, box["height"] + 420)})
            page.locator("#round-cards").scroll_into_view_if_needed()
            page.wait_for_timeout(1000)
            page.locator('[data-layout="overlay"]').click()
            print(width, "overlay ghosts:", page.locator(".probability-ghost").count())
            if SHOTS:
                page.locator("#step-4").screenshot(path=str(OUT / f"d56_{width}_rounds_overlay_timeline.jpg"), type="jpeg", quality=55)
            more = page.locator(".read-more:visible").first
            more.click(); print(width, "read more:", more.get_attribute("aria-expanded"))
            # evidence
            page.goto(f"{base}/evidence.html", wait_until="load")
            page.locator('#fx-chart [data-sort="size"]').click()
            page.locator('#ovb-toggle button[data-spec="plus_ecb_deposit_rate"]').click()
            page.locator("#holdout-toggle").click()
            print(width, "holdout panel visible:", page.locator("#holdout-panel").is_visible())
            page.locator("#recall-chart rect.src-bar").first.click()
            page.wait_for_selector("#src-pop dt:has-text('Script')", timeout=5000)
            page.keyboard.press("Escape")
            if SHOTS:
                page.wait_for_timeout(600)
                page.locator("#fx-chart").screenshot(path=str(OUT / f"d56_{width}_factor_effects.jpg"), type="jpeg", quality=55)
                page.locator("#ovb-toggle").screenshot(path=str(OUT / f"d56_{width}_ovb_toggle.jpg"), type="jpeg", quality=55)
            # corridor
            page.goto(f"{base}/corridor.html", wait_until="load")
            page.locator("#c-prem").fill("4")
            page.locator("#c-prem").dispatch_event("input")
            print(width, "corridor:", page.locator("#cb-out").inner_text()[:160])
            if SHOTS:
                page.locator("#corridor-band").screenshot(path=str(OUT / f"d56_{width}_corridor_band.jpg"), type="jpeg", quality=55)
            # forecasts
            page.goto(f"{base}/forecasts.html", wait_until="load")
            print(width, "countdown:", page.locator(".countdown").first.inner_text())
            page.locator("#series-table th button").nth(2).click()
            page.locator("#series-table-filter").fill("inflation")
            print(width, "filtered rows visible:", page.locator("#series-table tbody tr:visible").count())
            if SHOTS:
                page.screenshot(path=str(OUT / f"d56_{width}_forecast_log.jpg"), type="jpeg", quality=55, full_page=True)
                page.goto(f"{base}/methods.html", wait_until="load")
                page.locator(".pipe-node").nth(2).click()
                page.screenshot(path=str(OUT / f"d56_{width}_methods_pipeline.jpg"), type="jpeg", quality=55)
            if msgs:
                problems.append(f"{width} interactions console: {msgs}")
            page.close()
        browser.close()
finally:
    server.shutdown()
print("PROBLEMS:", problems)
sys.exit(1 if problems else 0)
