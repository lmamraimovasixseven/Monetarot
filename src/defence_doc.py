"""docs/DEFENCE_QA.md из шаблона: `python run.py defence`. Числа {{id}} берутся из журнала доказательств."""

from __future__ import annotations

import re
from pathlib import Path

from src.site_build import Ledger

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docs" / "templates" / "defence_qa.template.md"
OUTPUT = ROOT / "docs" / "DEFENCE_QA.md"


def _format(value: str) -> str:
    try:
        number = float(value)
    except ValueError:
        return value
    return value if "." not in value or len(value.split(".")[1]) <= 3 else f"{number:.3f}"


def render() -> str:
    ledger = Ledger()
    body = re.sub(r"\{\{([^}]+)\}\}", lambda m: _format(ledger.raw(m.group(1))), TEMPLATE.read_text(encoding="utf-8"))
    return "<!-- Сгенерировано `python run.py defence` из docs/templates/defence_qa.template.md; не править руками. -->\n" + body


def main() -> int:
    OUTPUT.write_text(render(), encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
