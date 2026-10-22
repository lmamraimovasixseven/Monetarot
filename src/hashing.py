"""Shared content hashing helpers for files whose line endings may vary."""

from __future__ import annotations

import hashlib
from pathlib import Path


def normalized_sha256(path: str | Path) -> str:
    """Return SHA-256 of file bytes after replacing CRLF line endings with LF."""
    normalized_content = Path(path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(normalized_content).hexdigest()
