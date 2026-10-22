"""The ten acceptance checks, plus the calendar-refresh timing and src.check tests.

Every test writes only under pytest's tmp directories. Tests that need a
missing artifact or a different calendar source run a temporary copy of the
app (src/app.py resolves all paths relative to its own location).
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import app, check


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "src" / "app.py"
ARTIFACT_PATH = ROOT / "model" / "artifact.json"
SCRIPTS = ROOT / "scripts"
RENDER_LIMIT_SECONDS = 3.0
RENDER_TIME = re.compile(r"Cached dashboard render time: ([0-9.]+) seconds")
BAND = re.compile(r"95% delta-method band: \[([-+0-9.]+), ([-+0-9.]+)\]")
sys.path.insert(0, str(SCRIPTS))
import clean_install_check  # noqa: E402
import scan_secrets  # noqa: E402


# ---------------------------------------------------------------- helpers


def _artifact() -> dict:
    return json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))


def _headline_score(artifact: dict) -> float:
    return app.policy_pressure_score(app.ordered_probabilities(artifact, artifact["latest_feature_vector"]))


def make_app_copy(root: Path, *, calendar_source: str | None = None, artifact: bool = True) -> Path:
    """Copy the app and the files it reads into ``root``; return the copied app path."""
    (root / "src").mkdir(parents=True)
    shutil.copy2(APP_PATH, root / "src" / "app.py")
    shutil.copytree(ROOT / "data" / "processed", root / "data" / "processed")
    (root / "model").mkdir()
    if artifact:
        shutil.copy2(ARTIFACT_PATH, root / "model" / "artifact.json")
    (root / "config").mkdir()
    schedule = json.loads((ROOT / "config" / "forecast_rounds.json").read_text(encoding="utf-8"))
    if calendar_source is not None:
        schedule["source"] = calendar_source
    (root / "config" / "forecast_rounds.json").write_text(json.dumps(schedule), encoding="utf-8")
    return root / "src" / "app.py"


def render(path: Path, at: AppTest | None = None) -> tuple[AppTest, float, float | None]:
    """Run the app once; return it with wall-clock and in-app render seconds."""
    at = at or AppTest.from_file(str(path), default_timeout=30)
    started = time.perf_counter()
    at.run()
    wall = time.perf_counter() - started
    in_app = next((float(m.group(1)) for c in at.caption if (m := RENDER_TIME.search(c.value))), None)
    return at, wall, in_app


def landing_captions(at: AppTest) -> list[str]:
    in_tabs = {caption.value for tab in at.tabs for caption in tab.caption}
    return [caption.value for caption in at.caption if caption.value not in in_tabs]


def wait_for_refresh(at: AppTest, limit: float = 4.0) -> dict:
    state = at.session_state[app.REFRESH_STATE_KEY]
    deadline = time.monotonic() + limit
    while state["result"] is None and time.monotonic() < deadline:
        time.sleep(0.05)
    return state


def cached_labels(at: AppTest) -> list[str]:
    return [item.value for item in at.warning if item.value.startswith("CACHED DATA")]


@pytest.fixture
def offline(monkeypatch):
    """Simulate a machine with no network: every DNS lookup and connection fails."""
    def refuse(*args, **kwargs):
        raise OSError("network disabled by test")

    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture
def slow_server():
    """A local calendar server that waits 5 seconds before answering."""
    finished = threading.Event()

    class SlowHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(5)
            try:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"calendar")
            except OSError:
                pass  # the client gave up first, as intended
            finished.set()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), SlowHandler)
    server.daemon_threads = True
    server.block_on_close = False
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/calendar", finished
    server.shutdown()
    server.server_close()


# ------------------------------------------------- check 1: clean install


@pytest.mark.parametrize("block", ["windows", "posix"])
def test_readme_install_steps_map_to_fresh_venv_commands(tmp_path, block):
    steps = clean_install_check.readme_steps(block=block)
    assert not any("activate" in step.lower() for step in steps)  # no activation step
    venv = tmp_path / "venv"
    venv_python = str(clean_install_check.venv_python(venv))
    assert clean_install_check.plan(steps, venv) == [
        [sys.executable, "-m", "venv", str(venv)],
        [venv_python, "-m", "pip", "install", "-r", "requirements.txt"],
        [venv_python, "run.py", "--healthcheck"],
    ]


def test_install_blocks_have_no_activation_script_and_plan_handles_interpreter_paths(tmp_path):
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for block in ("windows", "posix"):
        match = clean_install_check._block(block).search(readme)
        assert match and "Activate.ps1" not in match.group(1), block
    assert "Activation is not needed" in readme and "running scripts is disabled" in readme
    venv = tmp_path / "venv"
    venv_python = str(clean_install_check.venv_python(venv))
    for interpreter in (r".venv\Scripts\python.exe", ".venv/Scripts/python.exe", r".VENV\SCRIPTS\PYTHON.EXE",
                        ".venv/bin/python"):
        assert clean_install_check.plan([f"{interpreter} run.py"], venv) == [[venv_python, "run.py", "--healthcheck"]]
        assert clean_install_check.plan([f"{interpreter} -m pip install -r requirements.txt"], venv) == [
            [venv_python, "-m", "pip", "install", "-r", "requirements.txt"]]
    assert clean_install_check.plan([r".venv\Scripts\Activate.ps1", "source .venv/bin/activate"], venv) == [None, None]
    with pytest.raises(SystemExit):
        clean_install_check.plan(["pip install -r requirements.txt"], venv)


@pytest.mark.slow
@pytest.mark.skipif(os.environ.get("KZ_SKIP_CLEAN_INSTALL") == "1", reason="KZ_SKIP_CLEAN_INSTALL=1")
def test_check_01_clean_install_in_fresh_venv_from_readme(tmp_path):
    # Output goes to a file, not a pipe: a lingering grandchild cannot block the test, and on
    # timeout the whole process tree is killed and the log is shown.
    log = tmp_path / "clean_install.log"
    limit = 2 * clean_install_check.DEFAULT_STEP_TIMEOUT + clean_install_check.PIP_TIMEOUT + 120
    with log.open("w", encoding="utf-8") as handle:
        process = subprocess.Popen(
            [sys.executable, "-u", str(SCRIPTS / "clean_install_check.py"), "--workdir", str(tmp_path / "install")],
            cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT, start_new_session=sys.platform != "win32",
        )
        try:
            returncode = process.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            clean_install_check._kill_tree(process)
            returncode = None
    output = log.read_text(encoding="utf-8", errors="replace")
    print(output)
    assert returncode is not None, f"clean install did not finish within {limit} s:\n{output}"
    assert returncode == 0, output
    assert "RESULT: PASS" in output


# ------------------------------------------------ check 2: one command


def test_check_02_one_command_starts_site_and_make_only_delegates():
    result = subprocess.run(
        [sys.executable, "run.py", "--healthcheck"], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
    )
    print(result.stdout)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Server health: ok" in result.stdout and "Dashboard rendered" in result.stdout

    recipes = [line.strip() for line in (ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
               if line.startswith("\t")]
    assert recipes and all(line.startswith("$(PYTHON) run.py") for line in recipes)
    source = (ROOT / "run.py").read_text(encoding="utf-8")
    assert "sys.executable" in source and '"make"' not in source and "shell=True" not in source


# ---------------------------------------------- check 3: landing view


def test_check_03_landing_view_shows_value_unit_period_and_latest_change():
    artifact = _artifact()
    at, _, _ = render(APP_PATH)
    assert not at.exception and not at.error
    score = _headline_score(artifact)
    metrics = {metric.label: metric.value for metric in at.metric}
    assert metrics["Policy pressure score"] == f"{score:+.3f}"
    assert metrics["Policy pressure score"] == f"{artifact['latest_prediction']['expected_score']:+.3f}"
    assert "Change versus previous decision" in metrics

    landing = landing_captions(at)
    unit = [text for text in landing if text.startswith("Unit:")]
    period = [text for text in landing if text.startswith("Period:")]
    change = [text for text in landing if text.startswith("Latest change:")]
    assert unit and "P(Increase)" in unit[0] and "−1" in unit[0] and "+1" in unit[0]
    assert period and artifact["latest_prediction"]["date"] in period[0]
    assert change and metrics["Change versus previous decision"] in change[0]
    assert re.search(r"\d{4}-\d{2}-\d{2}", change[0].split("decision of", 1)[1])


# --------------------------------------------- check 4: render < 3 s


def test_check_04_render_under_three_seconds_on_cached_data():
    render(APP_PATH)  # warm st.cache_data
    _, wall, in_app = render(APP_PATH)
    print(f"cached render: wall {wall:.3f} s, in-app {in_app:.3f} s")
    assert in_app is not None and in_app < RENDER_LIMIT_SECONDS
    assert wall < RENDER_LIMIT_SECONDS


# --------------------------------------- check 5: drivers equal artifact


def test_check_05_three_driver_contributions_on_screen_equal_artifact():
    rows = _artifact()["per_factor_contribution_to_latest_score_change"]
    expected = sorted(rows, key=lambda row: abs(row["expected_score_contribution_to_latest_change"]), reverse=True)[:3]
    at, _, _ = render(APP_PATH)
    drivers = [metric for metric in at.metric if metric.label.startswith("Driver ")]
    assert len(drivers) == 3
    for rank, (metric, row) in enumerate(zip(drivers, expected), start=1):
        value = row["expected_score_contribution_to_latest_change"]
        assert metric.label == f"Driver {rank}: {app.FEATURE_LABELS[row['feature']]}"
        assert metric.value == f"{value:+.4f}"
        assert float(metric.value) == pytest.approx(value, abs=5e-5)


# ----------------------------------------- check 6: slider moves output


def test_check_06_slider_changes_output_and_band_width():
    at, _, _ = render(APP_PATH)

    def read() -> tuple[str, float]:
        score = next(m.value for m in at.metric if m.label == "Scenario policy pressure score")
        low, high = map(float, next(BAND.search(c.value).groups() for c in at.caption if BAND.search(c.value)))
        return score, high - low

    score_before, width_before = read()
    slider = at.slider[0]
    start = slider.value
    target = slider.min if slider.value - slider.min > slider.max - slider.value else slider.max
    slider.set_value(target).run()
    score_after, width_after = read()
    print(f"slider {start} -> {target}: score {score_before} -> {score_after}, "
          f"band width {width_before:.3f} -> {width_after:.3f}")
    assert score_after != score_before
    assert width_after != pytest.approx(width_before, abs=1e-3)


# ------------------------------- check 7: offline shows the CACHED label


def test_check_07_offline_shows_cached_label_without_blocking(tmp_path, offline):
    path = make_app_copy(tmp_path)
    at, wall, in_app = render(path)
    print(f"network disabled: first render wall {wall:.3f} s, in-app {in_app:.3f} s")
    assert not at.exception
    assert cached_labels(at), "first render must show the CACHED label while the check is unresolved"
    assert in_app < RENDER_LIMIT_SECONDS

    state = wait_for_refresh(at)
    assert state["result"] == (False, "The configured calendar refresh request failed.")
    at, wall, in_app = render(path, at)
    print(f"network disabled: rerun after failure wall {wall:.3f} s, in-app {in_app:.3f} s")
    labels = cached_labels(at)
    assert labels and "request failed" in labels[0]


def test_slow_calendar_server_times_out_at_two_seconds_without_blocking_render(tmp_path, slow_server):
    url, server_finished = slow_server
    path = make_app_copy(tmp_path, calendar_source=url)
    at, wall, in_app = render(path)
    print(f"5 s slow server: first render wall {wall:.3f} s, in-app {in_app:.3f} s")
    assert not server_finished.is_set(), "first render finished only after the slow server answered"
    assert in_app < RENDER_LIMIT_SECONDS and wall < RENDER_LIMIT_SECONDS
    assert cached_labels(at)

    state = wait_for_refresh(at)
    assert state["result"] is not None and state["result"][0] is False
    assert state["elapsed"] <= app.REFRESH_TIMEOUT_SECONDS + 0.5
    print(f"5 s slow server: refresh request gave up after {state['elapsed']:.2f} s")
    at, wall, in_app = render(path, at)
    print(f"5 s slow server: rerun after timeout wall {wall:.3f} s, in-app {in_app:.3f} s")
    labels = cached_labels(at)
    assert labels and ("did not finish within 2 seconds" in labels[0] or "request failed" in labels[0])


def test_refresh_status_rules():
    assert app.REFRESH_TIMEOUT_SECONDS <= 2.0
    pending = {"started": 100.0, "result": None, "elapsed": None}
    assert app.refresh_status(pending, now=101.0)[0] == "pending"
    assert app.refresh_status(pending, now=102.0) == ("failed", "The calendar refresh request did not finish within 2 seconds.")
    assert app.refresh_status({"started": 0.0, "result": (True, "ok"), "elapsed": 0.3}, now=0.3) == ("ok", "ok")
    assert app.refresh_status({"started": 0.0, "result": (True, "ok"), "elapsed": 2.5}, now=2.5)[0] == "failed"
    assert app.refresh_status({"started": 0.0, "result": (False, "down"), "elapsed": 0.1}, now=0.1) == ("failed", "down")


# ------------------------------ check 8: missing model has a clear message


def test_check_08_renamed_artifact_gives_clear_missing_model_message(tmp_path):
    path = make_app_copy(tmp_path)
    artifact = tmp_path / "model" / "artifact.json"
    artifact.rename(artifact.with_name("artifact.json.renamed"))
    at, _, _ = render(path)
    assert not at.exception
    assert len(at.error) == 1
    message = at.error[0].value
    assert "Model artifact is missing" in message
    assert "model/artifact.json" in message and "python run.py model" in message
    assert not at.metric and not at.tabs


# ------------------------------- check 9: headline not a literal in app.py


def test_check_09_headline_number_is_not_a_literal_in_app_source():
    artifact = _artifact()
    score = _headline_score(artifact)
    source = APP_PATH.read_text(encoding="utf-8")
    renderings = {f"{score:+.3f}", f"{score:.3f}", repr(score), repr(artifact["latest_prediction"]["expected_score"])}
    renderings |= {str(round(score, digits)) for digits in range(2, 8)}
    assert not [text for text in renderings if text in source]
    constants = [node.value for node in ast.walk(ast.parse(source))
                 if isinstance(node, ast.Constant) and isinstance(node.value, (int, float))
                 and not isinstance(node.value, bool)]
    assert not [value for value in constants if abs(abs(value) - abs(score)) < 5e-4]
    at, _, _ = render(APP_PATH)
    assert next(m.value for m in at.metric if m.label == "Policy pressure score") == f"{score:+.3f}"


# ----------------------------------- check 10: secrets and personal data


def test_check_10_repo_and_git_history_have_no_secrets_or_personal_data():
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "scan_secrets.py")], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )
    print(result.stdout)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Content findings: 0" in result.stdout


def test_secret_scanner_detects_planted_samples():
    # Assembled at runtime so this file itself does not trip the repository scan.
    at, domain = "@", "example.org"
    planted = {
        "credential assignment": '{"api' + '_key": "' + "abcd1234" * 2 + '"}',
        "GitHub token": "ghp_" + "a" * 36,
        "AWS access key id": "AKIA" + "B" * 16,
        "private key block": "-----BEGIN RSA " + "PRIVATE KEY-----",
        "e-mail address": "contact: someone" + at + domain,
        "home-directory path with user name": "C:" + "\\Users\\someone\\project",
        "URL with embedded credentials": "https://user:pass" + at + domain + "/x",
    }
    for kind, text in planted.items():
        assert kind in {finding.kind for finding in scan_secrets._scan_text(text, "t", "t")}, kind
    assert not scan_secrets._scan_text("Co-Authored-By: Claude <noreply@anthropic.com>", "t", "t")


# --------------------------------------------------------- src.check


def test_src_check_reproduces_committed_results(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "src.check", "--workdir", str(tmp_path / "rebuild")], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
    )
    print(result.stdout)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RESULT: PASS" in result.stdout
    for item in ("headline: holdout RMSE ratio", "headline: latest policy pressure score",
                 "coefficient household_lending", "outputs/annex_diagnostics.md", "outputs/results_table.md",
                 "outputs/oos_comparison.md", "outputs/economic_size.md", "outputs/robustness_table_short.md",
                 "outputs/numbers_for_note.json headline_score",
                 "outputs/fig_history.png", "outputs/fig_oos.png", "outputs/fig_contributions.png", "README.md",
                 "facts: data/raw/SOURCES.md", "facts: data/processed/provenance.json", "facts: docs/indicator_card.md"):
        assert re.search(rf"^PASS\s+{re.escape(item)}", result.stdout, re.M), item
    assert not re.search(r"^(FAIL|SKIP)\s", result.stdout, re.M)


def test_src_check_flags_numbers_outside_tolerance(tmp_path):
    committed, rebuilt = tmp_path / "a.md", tmp_path / "b.md"
    committed.write_text("Generated at 2026-10-16T15:49:12+00:00. ratio 1.0017200 n 88\n", encoding="utf-8")
    rebuilt.write_text("Generated at 2026-10-17T09:00:00+00:00. ratio 1.0017300 n 88\n", encoding="utf-8")
    report = check.Report()
    check.compare_markdown(report, "x.md", committed, rebuilt, tolerance=1e-6)
    assert report.failed == 1
    report = check.Report()
    check.compare_markdown(report, "x.md", committed, rebuilt, tolerance=1e-4)
    assert report.failed == 0
