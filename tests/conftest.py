"""Shared pytest setup: repo-local temporary directories and a git cleanliness guard."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
# Ignored by .gitignore. The default basetemp under the Windows user profile is
# not reliably writable here, so every tmp_path lives under the repository.
TEMP_ROOT = ROOT / ".pytest-temp"


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    # Must run before the tmp_path plugin reads --basetemp.
    if config.option.basetemp is None:
        TEMP_ROOT.mkdir(exist_ok=True)
        config.option.basetemp = str(TEMP_ROOT / "run")


def pytest_unconfigure(config: pytest.Config) -> None:
    shutil.rmtree(TEMP_ROOT, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def repo_temp_dir():
    """Provide the repo-local temp root and delete it when the session ends."""
    TEMP_ROOT.mkdir(exist_ok=True)
    yield TEMP_ROOT
    shutil.rmtree(TEMP_ROOT, ignore_errors=True)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, check=True,
    ).stdout.decode("utf-8", errors="replace")


def git_fingerprint() -> dict[str, str]:
    """Status lines plus content hashes, so edits to already-dirty files are caught."""
    status = _git("status", "--porcelain=v1", "--untracked-files=all")
    diff_hash = hashlib.sha256(_git("diff", "HEAD", "--binary").encode("utf-8")).hexdigest()
    untracked = {}
    for line in status.splitlines():
        if line.startswith("?? "):
            path = ROOT / line[3:].strip().strip('"')
            if path.is_file():
                untracked[line[3:]] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"status": status, "diff_sha256": diff_hash, "untracked": repr(sorted(untracked.items()))}


@pytest.fixture(scope="session", autouse=True)
def git_tree_unchanged(repo_temp_dir):
    """Fail the session if any test changed tracked or untracked repository files."""
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        yield
        return
    before = git_fingerprint()
    yield
    after = git_fingerprint()
    if after != before:
        pytest.fail(
            "The test run modified repository files.\n"
            f"git status before:\n{before['status'] or '(clean)'}\n"
            f"git status after:\n{after['status'] or '(clean)'}",
            pytrace=False,
        )
