"""Cross-platform entry point: `python run.py` starts the dashboard.

Other tasks: `python run.py data|model|report|facts|check|regression|test|all`. The Makefile only
delegates here, so make is optional on every platform.
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent
APP = ROOT / "src" / "app.py"
DEFAULT_PORT = 8503
TASKS = {
    "data": [[sys.executable, "-m", "src.ingest"]],
    "model": [[sys.executable, "-m", "src.model"]],
    "report": [[sys.executable, "-m", "src.report"], [sys.executable, "-m", "src.readme"]],
    "facts": [[sys.executable, "-m", "src.facts"]],
    "check": [[sys.executable, "-m", "src.check"]],
    "regression": [[sys.executable, "-m", "src.regression"]],
    "test": [[sys.executable, "-m", "pytest", "-q"]],
}
TASKS["all"] = TASKS["data"] + TASKS["model"] + TASKS["report"] + TASKS["facts"] + TASKS["test"]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _streamlit_command(port: int) -> list[str]:
    # Headless skips Streamlit's first-run e-mail prompt, which would block a fresh install.
    return [
        sys.executable, "-m", "streamlit", "run", str(APP),
        "--server.port", str(port),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]


def _wait_for_health(port: int, process: subprocess.Popen, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/_stcore/health"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except (URLError, OSError):
            pass
        time.sleep(0.25)
    return False


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def serve(port: int, open_browser: bool) -> int:
    process = subprocess.Popen(_streamlit_command(port), cwd=ROOT)
    try:
        if _wait_for_health(port, process, timeout=60):
            url = f"http://localhost:{port}"
            print(f"Dashboard running at {url} (Ctrl+C to stop)", flush=True)
            if open_browser:
                webbrowser.open(url)
        return process.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        _stop(process)


def healthcheck(port: int | None) -> int:
    """Start the server, confirm it answers, render the page once, then stop."""
    port = port or _free_port()
    process = subprocess.Popen(
        _streamlit_command(port), cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        if not _wait_for_health(port, process, timeout=60):
            print(f"FAIL: server did not report healthy on port {port}")
            return 1
        with urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
            page_ok = response.status == 200
        print(f"Server health: ok on port {port}; index page HTTP 200: {page_ok}")
    finally:
        _stop(process)

    from streamlit.testing.v1 import AppTest

    started = time.perf_counter()
    at = AppTest.from_file(str(APP)).run(timeout=60)
    elapsed = time.perf_counter() - started
    if at.exception or at.error or not at.title:
        print("FAIL: dashboard script did not render cleanly")
        for item in [*at.exception, *at.error]:
            print(f"  {item.value}")
        return 1
    print(f"Dashboard rendered: {at.title[0].value!r} in {elapsed:.2f} s")
    return 0 if page_ok else 1


def run_task(name: str) -> int:
    for command in TASKS[name]:
        print("+ " + " ".join(command[1:] if command[0] == sys.executable else command), flush=True)
        code = subprocess.call(command, cwd=ROOT)
        if code:
            return code
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("task", nargs="?", default="app", choices=["app", *TASKS])
    parser.add_argument("--port", type=int, default=None, help=f"dashboard port (default {DEFAULT_PORT})")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    parser.add_argument("--healthcheck", action="store_true",
                        help="start the server, verify it, render once, stop; exit code 0 on success")
    args = parser.parse_args(argv)
    if args.task != "app":
        return run_task(args.task)
    if args.healthcheck:
        return healthcheck(args.port)
    return serve(args.port or DEFAULT_PORT, open_browser=not args.no_browser)


if __name__ == "__main__":
    sys.exit(main())
