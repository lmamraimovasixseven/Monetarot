"""Блок I: список приёмных проверок в tests/acceptance.md совпадает с кодом; trace согласован."""

import re
from pathlib import Path

from src import acceptance, trace

ROOT = Path(__file__).resolve().parents[1]


def test_acceptance_doc_lists_exactly_the_implemented_checks():
    text = (ROOT / "tests" / "acceptance.md").read_text(encoding="utf-8")
    documented = re.findall(r"(?m)^\| (A\d\d) \| ([^|]+) \|", text)
    assert [(i, t.strip()) for i, t in documented] == [(i, t) for i, t, _, _ in acceptance.CHECKS]
    assert sum("Зарезервировано" in t for _, t, _, _ in acceptance.CHECKS) == 2 and len(acceptance.CHECKS) == 12


def test_trace_is_consistent_for_numbers_shown_on_the_site():
    for key in ("n:rmse_ratio", "reality_check:expected_rate", "decision:binary_threshold_p_cut"):
        result = trace.trace(key)
        assert result["consistent"] and result["site_pages"], key
