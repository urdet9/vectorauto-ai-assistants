"""Проверка автооценки сценариев. Запускается без API-ключа: pytest"""
import json

from app.evaluate import evaluate
from config import SCENARIOS_FILE

H = {"to": "sales", "type": "test_drive", "priority": "normal"}


def test_pass_when_expectations_met():
    expect = {"handoff": {"to": "sales", "types": ["test_drive"]}, "must_contain": ["верно?"]}
    assert evaluate(expect, ["Тест-драйв S5, суббота. Всё верно?", "Передал."], [H], []) == []


def test_missing_handoff_fails():
    expect = {"handoff": {"to": "hr", "types": ["interview"]}}
    problems = evaluate(expect, ["Передал анкету."], [], [])
    assert problems and "нет заявки hr/interview" in problems[0]


def test_unexpected_handoff_fails():
    assert evaluate({"handoff": None}, ["..."], [H], [])


def test_priority_is_checked():
    expect = {"handoff": {"to": "sales", "priority": "high"}}
    assert evaluate(expect, ["..."], [H], [])


def test_program_warning_is_failure():
    problems = evaluate({}, ["Передал."], [], ["заявка НЕ сохранена"])
    assert problems and "предупреждение" in problems[0]


def test_regex_and_negative_lookbehind():
    expect = {"must_not_contain": ["re:(?<!не )продолжайте движение"]}
    assert evaluate(expect, ["Не продолжайте движение."], [], []) == []
    assert evaluate(expect, ["Можете продолжайте движение потихоньку."], [], [])


def test_must_contain_any():
    expect = {"must_contain_any": ["000-00-01", "отдел продаж"]}
    assert evaluate(expect, ["Обратитесь в отдел продаж."], [], []) == []
    assert evaluate(expect, ["Не знаю."], [], [])


def test_nocode_variant_checks_confirmation_instead_of_block():
    expect = {"handoff": {"to": "sales", "types": ["test_drive"]}}
    assert evaluate(expect, ["Всё верно?", "Передал заявку."], [], [], variant="nocode") == []
    assert evaluate(expect, ["Передал заявку."], [], [], variant="nocode")


def test_every_scenario_has_expectations():
    scenarios = json.loads(SCENARIOS_FILE.read_text(encoding="utf-8"))
    assert all("expect" in s for s in scenarios)
    assert sum(1 for s in scenarios if s.get("critical")) >= 3


def test_confirmation_message_is_checked():
    expect = {"confirm_contains": ["ТО-1"], "confirm_not_contains": ["диагностик"]}
    good = ["ТО-1 стоит 14 900 ₽.", "Проверьте: ТО-1, пятница. Всё верно?"]
    bad = ["ТО-1 стоит 14 900 ₽.", "Проверьте: диагностика, пятница. Всё верно?"]
    assert evaluate(expect, good, [], []) == []
    assert len(evaluate(expect, bad, [], [])) == 2
