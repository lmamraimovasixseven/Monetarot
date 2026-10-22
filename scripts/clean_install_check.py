"""Acceptance check 1: clean install in a fresh virtual environment from the README steps.

Usage: python scripts/clean_install_check.py [--workdir DIR] [--keep]

Reads the fenced block for this platform from README.md (between
`<!-- install-steps:windows:start -->` / `:end -->` on Windows, `install-steps:posix`
elsewhere) and runs each command in order:

* `python -m venv .venv`  -> creates a NEW venv inside the work directory;
* `python ...`            -> runs with that fresh venv's interpreter;
* activation lines        -> skipped (the venv interpreter is called directly);
* `python run.py`         -> run as `python run.py --healthcheck`, which starts
                             the server, checks it answers, renders the page
                             once, and stops (the plain command would block).

The repository itself is used read-only; the venv lives in the work directory.
Exit code 0 when every step succeeds.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
PLATFORM_BLOCK = "windows" if sys.platform == "win32" else "posix"


def _block(name: str) -> re.Pattern[str]:
    return re.compile(rf"<!-- install-steps:{name}:start -->\s*```[a-z]*\n(.*?)```\s*<!-- install-steps:{name}:end -->", re.S)


def readme_steps(text: str | None = None, block: str = PLATFORM_BLOCK) -> list[str]:
    text = README.read_text(encoding="utf-8") if text is None else text
    match = _block(block).search(text)
    if not match:
        raise SystemExit(f"README.md has no install-steps:{block} block")
    return [line.strip() for line in match.group(1).splitlines()
            if line.strip() and not line.strip().startswith("#")]


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


# The README calls the virtual-environment Python directly (no activation needed).
VENV_INTERPRETERS = {".venv/scripts/python.exe", ".venv/bin/python"}


def plan(steps: list[str], venv: Path) -> list[list[str] | None]:
    """Translate README lines into argv lists; None marks a skipped activation line."""
    commands: list[list[str] | None] = []
    for step in steps:
        words = step.split()
        if words[0].replace("\\", "/").lower() in VENV_INTERPRETERS:
            words = ["python", *words[1:]]
        if words[0] in {"source", "."} or "activate" in step.lower():
            commands.append(None)
        elif words[0] in {"python", "python3"} and words[1:3] == ["-m", "venv"]:
            commands.append([sys.executable, "-m", "venv", str(venv)])
        elif words[:2] == ["python", "run.py"] and len(words) == 2:
            commands.append([str(venv_python(venv)), "run.py", "--healthcheck"])
        elif words[0] in {"python", "python3"}:
            commands.append([str(venv_python(venv)), *words[1:]])
        else:
            raise SystemExit(f"Unrecognized README install step: {step}")
    return commands


DEFAULT_STEP_TIMEOUT = 300
PIP_TIMEOUT = 1200  # pip downloads and builds the pinned packages; every other step is quick


def _kill_tree(process: subprocess.Popen) -> None:
    """Stop a step and every process it started, so no child keeps running or holds files open."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
    else:
        import os
        import signal
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()


def step_timeout(command: list[str]) -> int:
    return PIP_TIMEOUT if "pip" in command else DEFAULT_STEP_TIMEOUT


def _run_step(command: list[str], log: Path, limit: int) -> tuple[int | None, str]:
    """Run one step with its output in a file (not a pipe); None as the code means it timed out."""
    with log.open("w", encoding="utf-8", errors="replace") as handle:
        process = subprocess.Popen(command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT,
                                   start_new_session=sys.platform != "win32")
        try:
            returncode: int | None = process.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            _kill_tree(process)
            returncode = None
    return returncode, log.read_text(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workdir", type=Path, default=None, help="where to create the fresh venv")
    parser.add_argument("--keep", action="store_true", help="keep the work directory afterwards")
    args = parser.parse_args(argv)

    workdir = args.workdir or Path(tempfile.mkdtemp(prefix="kz-clean-install-"))
    workdir.mkdir(parents=True, exist_ok=True)
    venv = workdir / "venv"
    if venv.exists():
        shutil.rmtree(venv)
    steps = readme_steps()
    failures = 0
    try:
        for step, command in zip(steps, plan(steps, venv)):
            if command is None:
                print(f"SKIP  {step}  (activation; the fresh venv interpreter is called directly)")
                continue
            started = time.perf_counter()
            limit = step_timeout(command)
            returncode, output = _run_step(command, workdir / "step.log", limit)
            elapsed = time.perf_counter() - started
            ok = returncode == 0
            failures += not ok
            status = "PASS" if ok else ("FAIL (timed out after %d s; process tree killed)" % limit
                                        if returncode is None else "FAIL")
            print(f"{status}  {step}  ({elapsed:.1f} s; ran: {' '.join(command)})", flush=True)
            tail = output.strip().splitlines()
            for line in (tail[-15:] if not ok else [line for line in tail if line.startswith(("Server health", "Dashboard rendered", "Successfully installed"))]):
                print(f"      {line[:300]}")
            if not ok:
                break
    finally:
        if not args.keep:
            shutil.rmtree(workdir, ignore_errors=True)
    print("RESULT: PASS" if failures == 0 else "RESULT: FAIL")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
