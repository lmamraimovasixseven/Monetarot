"""Добавление блоков продукта в model/artifact.json без переоценки модели.

`python run.py model` пишет артефакт оценки; последующие шаги (`decision`, прогнозы, коридор, журнал)
добавляют свои блоки отдельными ключами верхнего уровня. Оценённые поля не трогаются: функция отказывается
перезаписывать ключ, который создаёт модель. `python run.py update` выполняет все шаги по порядку, поэтому
после переоценки блоки появляются снова.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = ROOT / "model" / "artifact.json"
EXTENSION_KEYS = {"decision", "evidence_ledger", "forecast_desk", "patterns", "carry_corridor", "prereg",
                  "reality_check", "site"}


def merge(key: str, value: Any, path: Path = ARTIFACT_PATH) -> None:
    if key not in EXTENSION_KEYS:
        raise KeyError(f"{key!r} is not an extension key; estimated fields are written only by src/model.py")
    artifact = json.loads(Path(path).read_text(encoding="utf-8"))
    artifact[key] = value
    Path(path).write_text(json.dumps(artifact, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                          encoding="utf-8", newline="\n")
