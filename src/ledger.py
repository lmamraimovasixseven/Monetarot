"""Журнал доказательств: `python run.py ledger` собирает ledger/evidence_ledger.csv.

Одна строка на каждое число, которое может попасть в README, отчёт или на сайт:
* каждый ключ outputs/numbers_for_note.json (источник — путь в артефакте или правило вывода);
* каждое скалярное значение блоков продукта в model/artifact.json (decision, forecast_desk, patterns,
  carry_corridor, prereg, reality_check);
* каждый сырой ряд data/raw/*.csv и data/external/*.csv (источник, URL, даты, преобразование);
* хеши файлов преререгистрации (prereg/).
Колонки: id, value, source, series, url, retrieved, release_or_vintage, transformation, script, artifact_field,
used_in, test. Неизвестное — UNKNOWN. Ничего не оценивает.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Iterator

from src.artifact_extensions import EXTENSION_KEYS
from src.hashing import normalized_sha256

ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "ledger" / "evidence_ledger.csv"
NUMBERS_PATH = ROOT / "outputs" / "numbers_for_note.json"
ARTIFACT_PATH = ROOT / "model" / "artifact.json"
FACTS_CSV = ROOT / "docs" / "facts_to_fill.csv"
EXTERNAL_SOURCES = ROOT / "config" / "external_sources.json"
COLUMNS = ["id", "value", "source", "series", "url", "retrieved", "release_or_vintage", "transformation", "script",
           "artifact_field", "used_in", "test"]
UNKNOWN = "UNKNOWN"
BLOCK_SCRIPTS = {"decision": "src/decision_rule.py", "forecast_desk": "src/forecast_desk.py", "patterns": "src/patterns.py",
                 "carry_corridor": "src/carry_corridor.py", "prereg": "src/prereg.py", "reality_check": "src/prereg.py",
                 "site": "src/site_build.py", "evidence_ledger": "src/ledger.py"}
SKIP_BLOCKS = {"evidence_ledger", "site"}  # описывают сам журнал и сборку сайта, не числа результата


def _leaves(value: Any, path: str) -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _leaves(item, f"{path}/{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _leaves(item, f"{path}/{index}")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield path, value


def _row(**fields: Any) -> dict[str, str]:
    return {column: str(fields.get(column, UNKNOWN)) for column in COLUMNS}


def number_rows(numbers_path: Path = NUMBERS_PATH) -> list[dict[str, str]]:
    numbers = json.loads(Path(numbers_path).read_text(encoding="utf-8"))["numbers"]
    rows = []
    for key, entry in numbers.items():
        source = entry.get("source")
        field = source if isinstance(source, str) else json.dumps(source, ensure_ascii=False)
        rows.append(_row(id=f"n:{key}", value=entry.get("display", entry.get("value")), source="outputs/numbers_for_note.json",
                         series="model results", url="not applicable (computed)", retrieved="not applicable",
                         release_or_vintage="current data (no vintages)", transformation=entry.get("kind", UNKNOWN),
                         script="src/report.py", artifact_field=field, used_in="README.md; docs/*; site/",
                         test="tests/test_ledger.py; python run.py check"))
    return rows


def artifact_rows(artifact_path: Path = ARTIFACT_PATH) -> list[dict[str, str]]:
    artifact = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    rows = []
    for block in sorted(EXTENSION_KEYS - SKIP_BLOCKS):
        if block not in artifact:
            continue
        for path, value in _leaves(artifact[block], ""):
            rows.append(_row(id=f"{block}:{path.lstrip('/')}", value=repr(value) if isinstance(value, float) else value,
                             source="model/artifact.json", series=block, url="not applicable (computed)",
                             retrieved="not applicable", release_or_vintage="current data (no vintages)",
                             transformation="see script", script=BLOCK_SCRIPTS[block],
                             artifact_field=f"model/artifact.json#/{block}{path}", used_in="site/",
                             test="tests/test_ledger.py"))
    return rows


def series_rows(root: Path = ROOT) -> list[dict[str, str]]:
    rows = []
    with Path(FACTS_CSV).open(encoding="utf-8", newline="") as handle:
        for fact in csv.DictReader(handle):
            path = root / "data" / "raw" / fact["series_file"]
            rows.append(_row(id=f"raw:{fact['series_file']}", value=normalized_sha256(path), source=fact["publisher"],
                             series=fact["source_title"], url=fact["url_or_api_query"], retrieved=fact["retrieval_date"],
                             release_or_vintage=fact["publication_date"], transformation="src/ingest.py (FEATURE_RULES)",
                             script="src/ingest.py", artifact_field="model/artifact.json#/data_sha256_normalized_crlf_to_lf",
                             used_in="data/processed/*; model", test="tests/test_data_contract.py"))
    if Path(EXTERNAL_SOURCES).is_file():
        for name, spec in json.loads(Path(EXTERNAL_SOURCES).read_text(encoding="utf-8"))["series"].items():
            path = root / "data" / "external" / spec["file"]
            rows.append(_row(id=f"external:{spec['file']}", value=normalized_sha256(path) if path.is_file() else UNKNOWN,
                             source=spec["publisher"], series=spec["title"], url=spec["url"],
                             retrieved=spec.get("retrieved", UNKNOWN), release_or_vintage=spec.get("release", UNKNOWN),
                             transformation=spec.get("transformation", UNKNOWN), script="src/external_data.py",
                             artifact_field="model/artifact.json#/carry_corridor", used_in="carry corridor",
                             test="tests/test_external_data.py"))
    return rows


def prereg_rows(root: Path = ROOT) -> list[dict[str, str]]:
    rows = []
    for path in sorted((root / "prereg").glob("*")) if (root / "prereg").is_dir() else []:
        if path.is_file() and path.name != "freeze.json":
            rows.append(_row(id=f"prereg:{path.name}", value=normalized_sha256(path), source="prereg/", series="preregistration",
                             url="not applicable", retrieved="not applicable", release_or_vintage="frozen file",
                             transformation="SHA-256 (CRLF normalized)", script="src/prereg.py",
                             artifact_field="model/artifact.json#/prereg", used_in="site/; prereg-check",
                             test="tests/test_prereg.py"))
    return rows


LOG_FILES = {"forecast_log": ROOT / "docs" / "forecast_log.csv", "forecast_ledger": ROOT / "ledger" / "forecast_ledger.csv"}
CHART_SOURCES = {"chart:holdout": ROOT / "outputs" / "annex_predictions.csv", "chart:base_rate": ROOT / "data" / "raw" / "base_rate_history.csv"}


def log_rows() -> list[dict[str, str]]:
    """Числа журналов прогнозов (показываются на странице «Журнал прогнозов») и источники графиков."""
    rows = []
    for name, path in LOG_FILES.items():
        if not Path(path).is_file():
            continue
        with Path(path).open(encoding="utf-8", newline="") as handle:
            for i, record in enumerate(csv.DictReader(handle)):
                for column, value in record.items():
                    try:
                        float(value)
                    except (TypeError, ValueError):
                        continue
                    rows.append(_row(id=f"{name}:{i}:{column}", value=value, source=str(Path(path).relative_to(ROOT)).replace("\\", "/"),
                                     series=name, url="not applicable", retrieved="not applicable", release_or_vintage="append-only log",
                                     transformation="as logged", script="src/forecast_log.py" if name == "forecast_log" else "src/forecast_desk.py",
                                     artifact_field="not applicable", used_in="site/forecasts.html", test="tests/test_ledger.py"))
    for key, path in CHART_SOURCES.items():
        rows.append(_row(id=key, value=normalized_sha256(path), source=str(Path(path).relative_to(ROOT)).replace("\\", "/"),
                         series="chart data", url="not applicable", retrieved="not applicable", release_or_vintage="current",
                         transformation="plotted as is", script="src/site_build.py", artifact_field="not applicable",
                         used_in="site/index.html", test="tests/test_site.py"))
    return rows


def build() -> list[dict[str, str]]:
    return number_rows() + artifact_rows() + series_rows() + prereg_rows() + log_rows()


def render(rows: list[dict[str, str]]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def main() -> int:
    rows = build()
    text = render(rows)
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(text, encoding="utf-8", newline="\n")
    from src.artifact_extensions import merge

    merge("evidence_ledger", {"path": "ledger/evidence_ledger.csv", "rows": len(rows),
                              "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})
    print(f"Wrote {LEDGER_PATH.relative_to(ROOT)}: {len(rows)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
