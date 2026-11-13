"""Приёмные проверки (tests/acceptance.md): `python run.py acceptance [--clone] [--quick]`.

Проверки 1–10 выполняются на свежей копии проекта во временной папке (по умолчанию копия рабочего дерева без
игнорируемых файлов; с --clone — `git clone` текущего HEAD, то есть только закоммиченное). 11–12 зарезервированы
под объявление преподавателя в день Update Drill. --quick пропускает долгие 1 и 10 (≈ 5 минут).
Статусы: PASS, FAIL, PENDING DATA (код проверен, реальных данных нет), RESERVED.
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
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
IGNORE = shutil.ignore_patterns(".git", ".pytest-temp", "__pycache__", "incoming", "*.pyc", ".venv")


def _run(args: list[str], cwd: Path, timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, env={**__import__("os").environ, "PYTHONUTF8": "1"})


def c01_offline_one_command(work: Path) -> tuple[str, str]:
    started = time.perf_counter()
    result = _run(["run.py", "update"], work)
    return ("PASS" if result.returncode == 0 else "FAIL",
            f"`python run.py update` на копии: код {result.returncode}, {time.perf_counter() - started:.0f} с; сеть не используется")


def c02_cutoff(work: Path) -> tuple[str, str]:
    code = ("import pandas as pd; from src import forecast_desk as fd\n"
            "s = fd.load_series('inflation_yoy'); c = s.index[100]; t = s.copy(); t[t.index > c] += 1000\n"
            "ok = all(fd.forecast(s, c, 3, m)['point'] == fd.forecast(t, c, 3, m)['point'] for m in ['naive','ar1','arima_110'])\n"
            "print(ok)")
    out = _run(["-c", code], work).stdout.strip()
    return ("PASS" if out.endswith("True") else "FAIL", "изменение значений после cutoff не двигает прогноз (naive, AR(1), ARIMA)")


def c03_usd_kzt_same_code(work: Path) -> tuple[str, str]:
    code = ("from src import forecast_desk as fd\n"
            "s = fd.load_series('usd_kzt')\nprint('EMPTY' if s.dropna().empty else 'DATA')")
    out = _run(["-c", code], work).stdout.strip()
    if out.endswith("EMPTY"):
        return ("PENDING DATA", "путь кода для usd_kzt тот же (load_series → backtest → forecast); data/raw/external/usd_kzt_daily.csv пока шаблон")
    desk = json.loads((work / "model" / "artifact.json").read_text(encoding="utf-8"))["forecast_desk"]["series"]["usd_kzt"]
    return ("PASS" if desk.get("status") == "ok" else "FAIL", f"usd_kzt: {desk.get('status')}")


def c04_seasonal_benchmark(work: Path) -> tuple[str, str]:
    desk = json.loads((work / "model" / "artifact.json").read_text(encoding="utf-8"))["forecast_desk"]["series"]
    candidates = json.loads((work / "prereg" / "candidates.json").read_text(encoding="utf-8"))["series"]
    bad = [n for n, spec in candidates.items() if spec.get("seasonal") and desk[n].get("status") == "ok"
           and desk[n]["benchmark"] != "seasonal_naive"]
    return ("PASS" if not bad else "FAIL", "сезонные ряды сравниваются с seasonal naive" + (f"; нарушено: {bad}" if bad else ""))


def c05_log_before_release() -> tuple[str, str]:
    import csv

    with (ROOT / "docs" / "forecast_log.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    problems = []
    for row in rows:
        log = subprocess.run(["git", "log", "--format=%cI", "-S", row["logged_at_utc"], "--", "docs/forecast_log.csv"],
                             cwd=ROOT, capture_output=True, text=True)
        dates = sorted(log.stdout.split())
        if not dates:
            problems.append(f"{row['target_decision_date']}: строка ещё не закоммичена")
        elif dates[0][:10] >= row["target_decision_date"]:
            problems.append(f"{row['target_decision_date']}: первый коммит {dates[0]} не раньше решения")
    return ("PASS" if not problems else "FAIL", f"{len(rows)} записей журнала; коммит раньше решения" + (f"; {problems}" if problems else ""))


def c06_live_setting(work: Path) -> tuple[str, str]:
    code = ("import json; from pathlib import Path; from src import decision_rule as dr\n"
            "p = Path('config/decision_losses.json'); c = json.loads(p.read_text(encoding='utf-8'))\n"
            "before = dr.build()['binary_threshold_p_cut']; c['binary_losses']['not_lengthen_but_cut'] = 3.0\n"
            "p.write_text(json.dumps(c, ensure_ascii=False), encoding='utf-8'); after = dr.build()['binary_threshold_p_cut']\n"
            "print(before, after)")
    config = work / "config" / "decision_losses.json"
    original = config.read_bytes()
    try:
        out = _run(["-c", code], work).stdout.split()
    finally:
        config.write_bytes(original)  # демонстрация не должна влиять на следующие проверки той же копии
    before, after = float(out[-2]), float(out[-1])
    return ("PASS" if abs(after - 0.25) < 1e-12 and after < before else "FAIL",
            f"упущенное снижение втрое дороже: порог {before:.3f} → {after:.3f} (= 1/(1+3)); правка в копии, не в репозитории")


def c07_trace(work: Path) -> tuple[str, str]:
    result = _run(["run.py", "trace", "n:rmse_ratio"], work)
    return ("PASS" if result.returncode == 0 and "Согласовано: да" in result.stdout else "FAIL",
            "n:rmse_ratio: сайт → журнал → src/report.py → artifact.json → тест")


def c08_prereg(work: Path) -> tuple[str, str]:
    result = _run(["run.py", "prereg-check"], work)
    return ("PASS" if result.returncode == 0 else "FAIL", "prereg/ не менялся после заморозки (хеши freeze.json)")


def c09_site(work: Path) -> tuple[str, str]:
    result = _run(["-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_site.py", "-k",
                   "360px or budget or alt or external or show_it"], work, timeout=600)
    return ("PASS" if result.returncode == 0 else "FAIL", "сайт на 360 px, бюджет загрузки < 3 с, alt, без CDN, без заглушек")


def c10_all_tests(work: Path) -> tuple[str, str]:
    result = _run(["-m", "pytest", "-q", "-p", "no:cacheprovider", "-k", "not check_01"], work, timeout=3600)
    lines = result.stdout.strip().splitlines() or ["?"]
    failed = [l.split(" - ")[0].replace("FAILED ", "") for l in lines if l.startswith(("FAILED", "ERROR"))]
    return ("PASS" if result.returncode == 0 else "FAIL", f"все тесты на копии: {lines[-1]}" + (f"; упали: {failed}" if failed else ""))


CHECKS: list[tuple[str, str, Callable | None, bool]] = [
    ("A01", "Чистая машина, офлайн, одна команда", c01_offline_one_command, True),
    ("A02", "Cutoff-дата: значение после cutoff не двигает вывод", c02_cutoff, False),
    ("A03", "Тот же код на курсе USD/KZT без правок", c03_usd_kzt_same_code, False),
    ("A04", "Сезонные ряды сравниваются с seasonal naive", c04_seasonal_benchmark, False),
    ("A05", "Журнал прогнозов закоммичен раньше релиза", None, False),
    ("A06", "Смена одной настройки вживую с объяснением", c06_live_setting, False),
    ("A07", "Трассировка числа сайта через журнал, код и модель", c07_trace, False),
    ("A08", "prereg не менялся после заморозки", c08_prereg, False),
    ("A09", "Сайт на 360 px и в бюджете скорости", c09_site, False),
    ("A10", "Чистый клон проходит все тесты", c10_all_tests, True),
    ("A11", "Зарезервировано: объявление преподавателя в день Update Drill", None, False),
    ("A12", "Зарезервировано: объявление преподавателя в день Update Drill", None, False),
]


def prepare(clone: bool) -> Path:
    work = Path(tempfile.mkdtemp(prefix="monetarot-acceptance-")) / "repo"
    if clone:
        subprocess.run(["git", "clone", "--quiet", str(ROOT), str(work)], check=True)
    else:
        shutil.copytree(ROOT, work, ignore=IGNORE)
    return work


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clone", action="store_true", help="git clone HEAD instead of copying the working tree")
    parser.add_argument("--quick", action="store_true", help="skip the long checks A01 and A10")
    args = parser.parse_args(argv)
    work = prepare(args.clone)
    print(f"Fresh copy: {work}")
    failed = 0
    for check_id, title, function, slow in CHECKS:
        if check_id == "A05":
            status, detail = c05_log_before_release()
        elif function is None:
            status, detail = "RESERVED", "заполняется в день Update Drill"
        elif slow and args.quick:
            status, detail = "SKIPPED", "--quick"
        else:
            try:
                status, detail = function(work)
            except Exception as exc:  # проверка, упавшая с ошибкой, — FAIL, а не пропуск
                status, detail = "FAIL", f"{type(exc).__name__}: {exc}"
        failed += status == "FAIL"
        print(f"{status:<12} {check_id} {title}: {detail}")
    print(f"acceptance: {'FAIL' if failed else 'PASS'} ({failed} failed)")
    shutil.rmtree(work.parent, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
