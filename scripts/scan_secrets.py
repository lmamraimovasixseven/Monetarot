"""Scan the working tree and full `git log -p` history for secrets and personal data.

Usage: python scripts/scan_secrets.py [--json]

Content findings (files on disk and lines added or removed in any commit) are
failures. Commit author/committer identities are git metadata, not repository
content; they are listed for information and do not fail the scan.
Exit code: 0 when there are no content findings, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PATTERNS: dict[str, re.Pattern[str]] = {
    "private key block": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----"),
    "AWS access key id": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})\b"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "OpenAI/Anthropic-style API key": re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}\b"),
    "JSON Web Token": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "credential assignment": re.compile(
        r"(?i)\b(?:api[_-]?key|secret(?:[_-]?key)?|access[_-]?token|auth[_-]?token|token|passwd|password)\b"
        r"['\"]?\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"
    ),
    "URL with embedded credentials": re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@"),
    "e-mail address": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b"),
    "phone number (+7 format)": re.compile(r"\+7[\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}\b"),
    "home-directory path with user name": re.compile(
        r"(?i)\b[A-Z]:[\\/]+Users[\\/]+[^\\/\s\"'`]+|(?<![\w.])/(?:home|Users)/[A-Za-z0-9._-]+"
    ),
}
# Placeholders that are not personal data.
ALLOWED_VALUES = {
    "noreply@anthropic.com",  # Claude co-author trailer in commit messages
}
METADATA_LINE = re.compile(r"^(?:Author|Commit|Merge|Date):", re.IGNORECASE)
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".xlsx", ".xls", ".zip", ".pyc"}


@dataclass
class Finding:
    where: str
    location: str
    kind: str
    value: str


def _redact(kind: str, value: str) -> str:
    if kind in {"e-mail address", "home-directory path with user name", "phone number (+7 format)"}:
        return value
    return value[:6] + "…" + f"({len(value)} chars)"


def _scan_text(text: str, where: str, location: str) -> list[Finding]:
    findings = []
    for kind, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            value = match.group(0)
            if value in ALLOWED_VALUES:
                continue
            findings.append(Finding(where, location, kind, _redact(kind, value)))
    return findings


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True)
    return result.stdout.decode("utf-8", errors="replace")


def scan_working_tree() -> list[Finding]:
    findings = []
    for name in _git("ls-files", "-z", "--cached", "--others", "--exclude-standard").split("\0"):
        path = ROOT / name
        if not name or not path.is_file() or path.suffix.lower() in SKIP_SUFFIXES:
            continue
        data = path.read_bytes()
        if b"\0" in data[:4096]:
            continue
        for number, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), start=1):
            findings.extend(_scan_text(line, "working tree", f"{name}:{number}"))
    return findings


def scan_history() -> tuple[list[Finding], set[str], int]:
    """Scan every commit's message and diff; return content findings and author identities."""
    log = _git("log", "-p", "--all", "--no-color", "--format=commit %H%nAuthor: %an <%ae>%nCommit: %cn <%ce>%n%n%B")
    findings, identities, commits = [], set(), 0
    commit, file_name = "?", "?"
    for line in log.splitlines():
        if line.startswith("commit ") and len(line.split()) == 2 and len(line.split()[1]) == 40:
            commit, file_name, commits = line.split()[1][:7], "(commit message)", commits + 1
            continue
        if METADATA_LINE.match(line):
            identities.add(line.split(":", 1)[1].strip())
            continue
        if line.startswith("diff --git "):
            file_name = line.split(" b/", 1)[-1]
            continue
        if line.startswith(("+++", "---", "index ", "@@")):
            continue
        findings.extend(_scan_text(line, "git history", f"{commit} {file_name}"))
    return findings, identities, commits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="print a JSON report instead of text")
    args = parser.parse_args(argv)

    tree = scan_working_tree()
    history, identities, commits = scan_history()
    # Collapse repeats of the same value in the same file across commits.
    unique_history = {(f.kind, f.value, f.location.split(" ", 1)[1]): f for f in history}
    findings = tree + list(unique_history.values())

    if args.json:
        print(json.dumps({
            "commits_scanned": commits,
            "content_findings": [asdict(f) for f in findings],
            "commit_identities": sorted(identities),
        }, indent=2, ensure_ascii=False))
    else:
        print(f"Scanned working tree and {commits} commits of `git log -p --all`.")
        print(f"Content findings: {len(findings)}")
        for f in findings:
            print(f"  FAIL  [{f.where}] {f.location}: {f.kind}: {f.value}")
        print("Commit author/committer identities (git metadata, informational):")
        for identity in sorted(identities):
            print(f"  INFO  {identity}")
        print("RESULT: PASS" if not findings else "RESULT: FAIL")
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main())
