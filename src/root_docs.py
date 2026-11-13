"""Корневые файлы по раскладке брифа: AI_USE.md, CONTRIBUTIONS.md, DECLARATION.md (`python run.py update`).

Источник правды остаётся в docs/ (docs/ai_use.md, docs/contributions.md, docs/declaration.md), на них ссылаются
тесты и документы; корневые файлы — сгенерированные копии с пометкой, ссылки не ломаются (D36).
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPIES = {"AI_USE.md": "docs/ai_use.md", "CONTRIBUTIONS.md": "docs/contributions.md", "DECLARATION.md": "docs/declaration.md"}


def render(source: str) -> str:
    text = (ROOT / source).read_text(encoding="utf-8")
    return f"<!-- Сгенерированная копия {source} (`python run.py update`); править {source}. -->\n" + text


def main() -> int:
    for target, source in COPIES.items():
        (ROOT / target).write_text(render(source), encoding="utf-8", newline="\n")
    print("Wrote " + ", ".join(COPIES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
