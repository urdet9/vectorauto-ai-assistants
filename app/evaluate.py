"""Автоматическая оценка тестового диалога по ожиданиям из tests/scenarios.json.

Ожидания сценария (поле "expect"):
  handoff            — {"to": "sales", "types": ["test_drive"], "priority": "high"} или null,
                       если заявки быть не должно
  must_contain       — фразы, каждая из которых должна встретиться в ответах ассистента
  must_contain_any   — хотя бы одна из фраз должна встретиться
  must_not_contain   — ни одна из фраз не должна встретиться
  confirm_contains   — фразы, которые должны быть в сообщении-подтверждении («…Всё верно?»)
  confirm_not_contains — фразы, которых не должно быть в сообщении-подтверждении

Фраза с префиксом "re:" — регулярное выражение. Сравнение без учёта регистра.
Предупреждения программы (например, «передал без заявки») — всегда провал.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from app.handoff import claims_handoff


def _found(pattern: str, text: str) -> bool:
    if pattern.startswith("re:"):
        return re.search(pattern[3:], text, re.IGNORECASE) is not None
    return pattern.lower() in text.lower()


def evaluate(expect: Dict[str, Any], replies: List[str], handoffs: List[Dict[str, Any]],
             warnings: List[str], variant: str = "full") -> List[str]:
    """Возвращает список причин провала. Пустой список — сценарий пройден."""
    problems: List[str] = [f"предупреждение программы: {w}" for w in warnings]
    text = "\n".join(replies)

    if "handoff" in expect:
        exp = expect["handoff"]
        if variant == "nocode":
            # В no-code-версии блока нет: проверяем подтверждение и сообщение о передаче.
            if exp:
                if not _found("верно?", text):
                    problems.append("нет подтверждения «Всё верно?»")
                if not claims_handoff(text):
                    problems.append("ассистент не сообщил, что обращение передано")
        elif exp is None:
            if handoffs:
                problems.append(f"заявки быть не должно, создано: {len(handoffs)}")
        else:
            matched = [
                h for h in handoffs
                if h.get("to") == exp["to"]
                and (not exp.get("types") or h.get("type") in exp["types"])
                and (not exp.get("priority") or h.get("priority") == exp["priority"])
            ]
            if not matched:
                got = ", ".join(f"{h.get('to')}/{h.get('type')}/{h.get('priority')}" for h in handoffs) or "нет"
                problems.append(
                    f"нет заявки {exp['to']}/{'|'.join(exp.get('types') or ['*'])}"
                    f"{'/' + exp['priority'] if exp.get('priority') else ''} (создано: {got})"
                )

    for p in expect.get("must_contain", []):
        if not _found(p, text):
            problems.append(f"нет обязательной фразы: {p}")
    any_list = expect.get("must_contain_any", [])
    if any_list and not any(_found(p, text) for p in any_list):
        problems.append(f"нет ни одной из фраз: {' / '.join(any_list)}")
    for p in expect.get("must_not_contain", []):
        if _found(p, text):
            problems.append(f"запрещённая фраза: {p}")
    confirm_req = expect.get("confirm_contains", [])
    confirm_ban = expect.get("confirm_not_contains", [])
    if confirm_req or confirm_ban:
        confirmations = [r for r in replies if _found("верно?", r)]
        if not confirmations:
            problems.append("нет сообщения-подтверждения «Всё верно?»")
        else:
            last = confirmations[-1]
            for p in confirm_req:
                if not _found(p, last):
                    problems.append(f"в подтверждении нет: {p}")
            for p in confirm_ban:
                if _found(p, last):
                    problems.append(f"в подтверждении лишнее: {p}")
    return problems
