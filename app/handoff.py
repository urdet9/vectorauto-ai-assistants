"""Передача обращений между отделами.

Ассистент добавляет в конец ответа технический блок:

    <<HANDOFF>>
    {"to": "service", "type": "complaint", "priority": "high", ...}
    <<END>>

Этот модуль:
1) находит такие блоки в ответе модели;
2) убирает их из текста, который увидит клиент;
3) проверяет, что в заявке есть обязательные поля;
4) сохраняет заявки в файл JSONL (одна строка — одна заявка).
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

HANDOFF_START = "<<HANDOFF>>"
HANDOFF_RE = re.compile(r"<<HANDOFF>>\s*(.*?)\s*<<END>>", re.DOTALL)

VALID_TARGETS = ("sales", "service", "hr")
VALID_PRIORITIES = ("normal", "high")
REQUIRED_FIELDS = ("to", "type", "summary")

# Фразы, которыми ассистент сообщает, что обращение уже передано (прошедшее время).
# «Передам», «могу передать» сюда не попадают.
HANDOFF_CLAIM_RE = re.compile(r"\b(передал|передала|передали|передан|передано|передана|переданы)\b", re.IGNORECASE)


@dataclass
class ParseResult:
    clean_text: str
    handoffs: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def _strip_code_fence(raw: str) -> str:
    """Модели иногда оборачивают JSON в ```json ... ``` — убираем обёртку."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def validate_handoff(data: Any) -> List[str]:
    """Возвращает список проблем. Пустой список — заявка корректна."""
    if not isinstance(data, dict):
        return ["заявка должна быть JSON-объектом"]
    problems = []
    for name in REQUIRED_FIELDS:
        if not str(data.get(name, "")).strip():
            problems.append(f"нет поля {name!r}")
    target = data.get("to")
    if target and target not in VALID_TARGETS:
        problems.append(f"неизвестный отдел {target!r}")
    priority = data.get("priority", "normal")
    if priority not in VALID_PRIORITIES:
        problems.append(f"неизвестный приоритет {priority!r}")
    return problems


def parse_reply(text: str) -> ParseResult:
    """Разделяет ответ модели на текст для клиента и заявки."""
    result = ParseResult(clean_text="")
    for match in HANDOFF_RE.finditer(text):
        raw = _strip_code_fence(match.group(1))
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            result.errors.append(f"Не удалось разобрать JSON заявки: {exc.msg}")
            continue
        problems = validate_handoff(data)
        if problems:
            result.errors.append("Заявка не сохранена: " + "; ".join(problems))
            continue
        data.setdefault("priority", "normal")
        result.handoffs.append(data)

    clean = HANDOFF_RE.sub("", text)
    if HANDOFF_START in clean:
        # Блок начат, но не закрыт (например, ответ модели оборвался).
        clean = clean.split(HANDOFF_START)[0]
        result.errors.append("Блок заявки не закрыт маркером <<END>> — заявка не сохранена")
    result.clean_text = clean.strip()
    return result


SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]?")


def claims_handoff(text: str) -> bool:
    """True, если ассистент утверждает, что обращение уже передано.

    Вопросы и условные фразы не считаются: «Хотите, чтобы я передал заявку?»
    """
    for sentence in SENTENCE_RE.findall(text):
        sentence = sentence.strip()
        if not HANDOFF_CLAIM_RE.search(sentence):
            continue
        if sentence.endswith("?") or "чтобы" in sentence.lower():
            continue
        return True
    return False


def save_handoff(data: Dict[str, Any], source: str, path: Path) -> Dict[str, Any]:
    """Добавляет служебные поля и дописывает заявку в файл. Возвращает сохранённую запись."""
    record: Dict[str, Any] = {
        "id": "H-" + uuid.uuid4().hex[:6].upper(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "from": source,
    }
    record.update({k: v for k, v in data.items() if k not in record})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def load_handoffs(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records
