"""Скриншоты для docs/site_parity.md: каждая вкладка Render-приложения (src/app.py, локально) и страницы site/.

Запуск (необязательный, не входит в CI и `run.py update`): `python scripts/site_parity_shots.py`.
Нужен пакет playwright (`pip install playwright`) и установленный Google Chrome (channel="chrome") —
браузеры Playwright не скачиваются. Пишет JPEG в docs/site_parity/. Ничего не оценивает и не меняет данные.
"""

from __future__ import annotations

import functools
import http.server
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "site_parity"
PORT = 8611
TABS = ["Overview", "Drivers and scenario", "Evidence", "Data and provenance"]
SITE_PAGES = ["index.html", "evidence.html", "data.html", "methods.html"]


def shoot_render(browser) -> None:
    process = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(ROOT / "src" / "app.py"), "--server.port", str(PORT),
                                "--server.headless", "true", "--browser.gatherUsageStats", "false"], cwd=ROOT,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(f"http://localhost:{PORT}/_stcore/health", timeout=1)
                break
            except OSError:
                time.sleep(0.5)
        # Высокое окно: у Streamlit внутренний скролл, full_page снимает только окно.
        page = browser.new_page(viewport={"width": 1400, "height": 7000})
        page.goto(f"http://localhost:{PORT}", wait_until="networkidle")
        page.wait_for_selector("text=Next scheduled NBK decisions", timeout=60000)
        time.sleep(4)
        for i, tab in enumerate(TABS):
            page.get_by_role("tab", name=tab).click()
            time.sleep(3)
            for summary in page.locator("[data-testid='stExpander'] summary").all():
                if summary.is_visible():
                    summary.click()
                    time.sleep(1)
            height = page.evaluate("() => Math.max(...[...document.querySelectorAll('*')].map(e => e.scrollHeight))")
            page.set_viewport_size({"width": 1400, "height": min(int(height) + 200, 16000)})
            time.sleep(2)
            page.screenshot(path=str(OUT / f"render_{i}_{tab.split()[0].lower()}.jpg"), full_page=True, type="jpeg", quality=55)
        page.close()
    finally:
        process.terminate()


def shoot_site(browser) -> None:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "site"))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for width in (1400, 360):
            page = browser.new_page(viewport={"width": width, "height": 900})
            for name in SITE_PAGES:
                page.goto(f"http://127.0.0.1:{server.server_port}/{name}", wait_until="load")
                page.screenshot(path=str(OUT / f"site_{width}_{name.removesuffix('.html')}.jpg"), full_page=True, type="jpeg", quality=55)
            page.close()
    finally:
        server.shutdown()


def shrink(path: Path, width: int = 800) -> None:
    """Меньше места в репозитории: не шире 800 px, JPEG качества 50."""
    image = Image.open(path).convert("RGB")
    if image.width > width:
        image = image.resize((width, round(image.height * width / image.width)))
    image.save(path, "JPEG", quality=50, optimize=True)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome")
        shoot_render(browser)
        shoot_site(browser)
        browser.close()
    for path in sorted(OUT.glob("*.jpg")):
        shrink(path)
    print(f"Wrote screenshots to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
