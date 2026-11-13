"""Блок J: ответы защиты из журнала, их выводы соответствуют данным; шпаргалка Quiz 2."""

import json
from pathlib import Path

from src import defence_doc

ROOT = Path(__file__).resolve().parents[1]


def test_defence_doc_is_a_fresh_render_with_40_questions():
    text = (ROOT / "docs" / "DEFENCE_QA.md").read_text(encoding="utf-8")
    assert text == defence_doc.render()
    import re

    assert len(re.findall(r"(?m)^\d+\. \*\*", text)) == 40
    assert "## Про часть, которую не писала" in text and "{{" not in text


def test_conclusions_written_in_the_answers_still_hold():
    """Если данные изменят вывод, этот тест упадёт и подскажет обновить текст шаблона."""
    numbers = json.loads((ROOT / "outputs" / "numbers_for_note.json").read_text(encoding="utf-8"))["numbers"]
    artifact = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))
    value = lambda key: float(numbers[key]["value"])  # noqa: E731
    assert value("rmse_ratio_ci_low") <= 1 <= value("rmse_ratio_ci_high") and value("dm_squared_error_p") >= 0.05  # Q5
    assert value("stability_lr_p") < 0.05  # Q10
    assert artifact["forecast_desk"]["series"]["real_rate"]["horizons"]["1"]["verdict"].startswith("нет выигрыша")  # Q26
    assert artifact["carry_corridor"]["credit_constraint"]["slope"] >= 0  # Q32
    assert artifact["patterns"]["seasonality"]["inflation"]["verdict"] == "нет"  # Q27


def test_quiz_sheet_starts_with_the_individual_work_rule_and_has_no_project_numbers():
    text = (ROOT / "docs" / "quiz2_sheet.md").read_text(encoding="utf-8")
    assert "Quiz 2 пишется индивидуально и без ИИ; этот лист нужно понять самой" in text.split("\n## ")[0]
    for topic in ("Стационарность", "ARIMA", "Оценка прогнозов", "Дизайн оценки", "чужого бэктеста"):
        assert topic in text
    assert "0.995" not in text and "15.75" not in text
