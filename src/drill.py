"""Update Drill: `python run.py drill --card {revision|release|shock|broken_source|question} [--light]`.

Каждая карточка имитируется на временной копии проекта (репозиторий не меняется): изменение данных или вопроса,
прогон обновления (по умолчанию `python run.py update`; с --light только нужные шаги), сравнение до и после
(версии файлов, прогнозы, вердикты, флаги), черновик заметки на 100 слов с подставленными числами и пустыми
местами для человеческой оценки, засечённое время. Значения карточек release и shock — ИМИТАЦИЯ ДЛЯ УЧЕНИЯ
(повтор последнего значения и последнее значение × 1.5), не данные.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IGNORE = shutil.ignore_patterns(".git", ".pytest-temp", "__pycache__", "incoming", "*.pyc", ".venv", "site")
CARDS = ["revision", "release", "shock", "broken_source", "question"]
LIGHT_STEPS = {"revision": ["data"], "release": ["data"], "shock": ["data"], "broken_source": ["data"], "question": ["decision"]}
TARGET = "data/raw/export_history.csv"


def _snapshot(work: Path) -> dict[str, Any]:
    artifact = json.loads((work / "model" / "artifact.json").read_text(encoding="utf-8"))
    screen_path = work / "data" / "processed" / "data_anomalies.json"
    screen = json.loads(screen_path.read_text(encoding="utf-8")) if screen_path.is_file() else {}
    panel = pd.read_csv(work / "data" / "processed" / "nbk_decisions_clean.csv")
    desk = artifact.get("forecast_desk", {}).get("series", {})
    return {"rmse_ratio": artifact["benchmark_comparison"]["rmse_ratio_model_to_hold"],
            "p_cut": artifact["latest_prediction"]["class_probabilities"]["Decrease"],
            "threshold": artifact.get("decision", {}).get("binary_threshold_p_cut"),
            "flags": len(screen.get("flags", [])), "flags_latest": len(screen.get("affecting_latest_score", [])),
            "panel_rows": len(panel), "exports_last": str(pd.read_csv(work / TARGET)["year_month"].iloc[-1]),
            "desk_verdicts": {f"{n}:h{h}": b["verdict"] for n, s in desk.items() if s.get("status") == "ok"
                              for h, b in s["horizons"].items()}}


def apply_card(card: str, work: Path) -> str:
    path = work / TARGET
    frame = pd.read_csv(path)
    last_month, last_value = frame["year_month"].iloc[-1], float(frame.iloc[-1, 1])
    if card == "revision":
        frame.iloc[-1, 1] = round(last_value * 1.01, 2)
        frame.to_csv(path, index=False, lineterminator="\n")
        return f"ИМИТАЦИЯ: пересмотр {TARGET} {last_month} на +1% (новый винтаж)"
    if card in ("release", "shock"):
        month = str(pd.Period(last_month, "M") + 1)
        value = last_value if card == "release" else round(last_value * 1.5, 2)
        text = path.read_text(encoding="utf-8")
        separator = "" if text.endswith("\n") else "\n"  # как при реальном добавлении (D22): строка с новой строки
        with path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(f"{separator}{month},{value}\n")
        return f"ИМИТАЦИЯ: {'новый релиз' if card == 'release' else 'структурный шок'} {TARGET} {month} = {value} (не данные)"
    if card == "broken_source":
        path.write_text("year_month,exports_thousand_usd\n2015-01,not-a-number\n", encoding="utf-8")
        return f"ИМИТАЦИЯ: сломанный источник {TARGET} (нечисловое значение)"
    if card == "question":
        config_path = work / "config" / "decision_losses.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["binary_losses"]["not_lengthen_but_cut"] *= 2
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        return "Вопрос: «а если упущенное снижение вдвое дороже ложного удлинения?» (потери изменены в копии)"
    raise KeyError(card)


def note(card: str, change: str, before: dict, after: dict, seconds: float, ok: bool, error: str) -> str:
    if not ok:
        return (f"Карточка {card}: {change}. Обновление остановилось с ошибкой: {error}. Откат: временная копия удалена, "
                f"репозиторий не изменён. Время {seconds:.0f} с. Что сломалось у источника: [ВАША ОЦЕНКА]. "
                f"Как восстановить и кому сообщить: [ВАША ОЦЕНКА].")
    changed = [k for k in after["desk_verdicts"] if after["desk_verdicts"][k] != before["desk_verdicts"].get(k)]
    return (f"Карточка {card}: {change}. После обновления ({seconds:.0f} с): отношение RMSE {before['rmse_ratio']:.3f} → "
            f"{after['rmse_ratio']:.3f}; P(снижение) {before['p_cut']:.3f} → {after['p_cut']:.3f}; порог "
            f"{before['threshold']:.3f} → {after['threshold']:.3f}; флагов экрана {before['flags']} → {after['flags']} (в последней "
            f"оценке {before['flags_latest']} → {after['flags_latest']}); вердикты прогноза изменились: {len(changed)}. "
            f"Меняет ли это действие с дюрацией: [ВАША ОЦЕНКА]. Насколько доверять новым данным: [ВАША ОЦЕНКА].")


def drill(card: str, light: bool = False, keep: bool = False) -> dict[str, Any]:
    work = Path(tempfile.mkdtemp(prefix=f"monetarot-drill-{card}-")) / "repo"
    shutil.copytree(ROOT, work, ignore=IGNORE)
    before = _snapshot(work)
    change = apply_card(card, work)
    started = time.perf_counter()
    steps = LIGHT_STEPS[card] if light else ["update"]
    ok, error = True, ""
    for step in steps:
        result = subprocess.run([sys.executable, "run.py", step], cwd=work, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", env={**__import__("os").environ, "PYTHONUTF8": "1"})
        if result.returncode != 0:
            ok = False
            lines = [l for l in (result.stderr + result.stdout).splitlines() if "Error" in l or "error" in l]
            error = (lines[-1] if lines else f"код {result.returncode}").strip()
            break
    seconds = time.perf_counter() - started
    after = _snapshot(work) if ok else before
    output = {"card": card, "change": change, "steps": steps, "ok": ok, "error": error, "seconds": round(seconds, 1),
              "before": before, "after": after, "note": note(card, change, before, after, seconds, ok, error),
              "repository_untouched": True}
    if not keep:
        shutil.rmtree(work.parent, ignore_errors=True)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--card", choices=CARDS, required=True)
    parser.add_argument("--light", action="store_true", help="run only the steps the card needs (fast)")
    args = parser.parse_args(argv)
    result = drill(args.card, light=args.light)
    for key in ("rmse_ratio", "p_cut", "threshold", "flags", "flags_latest", "panel_rows", "exports_last"):
        print(f"{key:<14} до: {result['before'][key]!s:<22} после: {result['after'][key]!s}")
    print(f"\nСтатус: {'обновление прошло' if result['ok'] else 'ОШИБКА, откат: ' + result['error']}; время {result['seconds']} с")
    print(f"\nЧерновик заметки ({len(result['note'].split())} слов):\n{result['note']}")
    return 0 if result["ok"] or args.card == "broken_source" else 1


if __name__ == "__main__":
    raise SystemExit(main())
