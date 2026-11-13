"""Трассировка числа: `python run.py trace <id>`.

Печатает цепочку «число на сайте → журнал доказательств → скрипт → поле model/artifact.json → тест» и
проверяет, что значение в журнале совпадает со значением в артефакте (код 1, если нет).
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def resolve_pointer(document: Any, pointer: str) -> Any:
    for part in [p for p in pointer.split("/") if p]:
        document = document[int(part)] if isinstance(document, list) else document[part]
    return document


def trace(key: str, root: Path = ROOT) -> dict[str, Any]:
    with (root / "ledger" / "evidence_ledger.csv").open(encoding="utf-8", newline="") as handle:
        rows = {row["id"]: row for row in csv.DictReader(handle)}
    if key not in rows:
        raise KeyError(f"{key!r} is not in ledger/evidence_ledger.csv")
    row = rows[key]
    pages = sorted(p.name for p in (root / "site").glob("*.html") if f'data-ledger="{key}"' in p.read_text(encoding="utf-8"))
    result: dict[str, Any] = {"id": key, "ledger_value": row["value"], "script": row["script"], "artifact_field": row["artifact_field"],
                              "test": row["test"], "site_pages": pages, "source": row["source"]}
    field = row["artifact_field"]
    match = re.match(r"^model/artifact\.json#(/.*)$", field)
    if match:
        artifact = json.loads((root / "model" / "artifact.json").read_text(encoding="utf-8"))
        value = resolve_pointer(artifact, match.group(1))
        result["artifact_value"] = value
        try:
            result["consistent"] = abs(float(value) - float(row["value"])) <= 1e-9 * max(1.0, abs(float(value))) or \
                (key.startswith("n:") and f"{float(value):.3f}".rstrip("0") in row["value"])
        except (TypeError, ValueError):
            result["consistent"] = str(value) == row["value"]
    if key.startswith("n:"):
        numbers = json.loads((root / "outputs" / "numbers_for_note.json").read_text(encoding="utf-8"))["numbers"]
        result["numbers_for_note_display"] = numbers[key[2:]]["display"]
        result["consistent"] = result.get("consistent", True) and numbers[key[2:]]["display"] == row["value"]
    return result


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: python run.py trace <ledger id>, e.g. n:rmse_ratio or reality_check:expected_rate")
        return 2
    result = trace(args[0])
    print(f"1. Число на сайте: {', '.join(result['site_pages']) or 'не показано на сайте'} (атрибут data-ledger=\"{result['id']}\")")
    print(f"2. Журнал: ledger/evidence_ledger.csv, id {result['id']}, значение {result['ledger_value']}, источник {result['source']}")
    print(f"3. Скрипт: {result['script']}")
    print(f"4. Поле артефакта: {result['artifact_field']}" + (f" = {result['artifact_value']!r}" if "artifact_value" in result else ""))
    print(f"5. Тест: {result['test']}")
    consistent = result.get("consistent", True)
    print("Согласовано: " + ("да" if consistent else "НЕТ"))
    return 0 if consistent else 1


if __name__ == "__main__":
    raise SystemExit(main())
