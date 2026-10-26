"""Реестр ассистентов и сборка системного промпта.

Системный промпт для API = промпт ассистента + общая база знаний компании
+ база знаний отдела. Так же устроен GPTs: Instructions + файлы в Knowledge.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from config import KNOWLEDGE_DIR, PROMPTS_DIR, PROMPTS_NOCODE_DIR

COMPANY_KB_FILE = "company.md"
# full — полные промпты с передачей заявок; nocode — версии для GPTs и no-code
VARIANTS = {"full": PROMPTS_DIR, "nocode": PROMPTS_NOCODE_DIR}


@dataclass(frozen=True)
class AssistantSpec:
    key: str          # короткий код: sales / service / hr
    title: str        # название для меню и отчётов
    prompt_file: str  # файл в папке prompts/
    kb_file: str      # файл в папке knowledge/


ASSISTANTS: Dict[str, AssistantSpec] = {
    "sales": AssistantSpec("sales", "Ассистент отдела продаж", "sales.md", "sales_kb.md"),
    "service": AssistantSpec(
        "service", "Ассистент сервиса и постпродажного обслуживания", "service.md", "service_kb.md"
    ),
    "hr": AssistantSpec("hr", "HR-ассистент", "hr.md", "hr_kb.md"),
}

DEPARTMENTS: Dict[str, str] = {
    "sales": "Отдел продаж",
    "service": "Сервис и постпродажное обслуживание",
    "hr": "Отдел персонала",
}


def get_spec(key: str) -> AssistantSpec:
    try:
        return ASSISTANTS[key]
    except KeyError:
        raise KeyError(f"Неизвестный ассистент: {key!r}. Доступны: {', '.join(ASSISTANTS)}") from None


def _read(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Не найден файл: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Файл пустой: {path}")
    return text


def load_prompt(key: str, variant: str = "full") -> str:
    if variant not in VARIANTS:
        raise KeyError(f"Неизвестный вариант промпта: {variant!r}. Доступны: {', '.join(VARIANTS)}")
    return _read(VARIANTS[variant] / get_spec(key).prompt_file)


def load_knowledge(key: str) -> str:
    spec = get_spec(key)
    company = _read(KNOWLEDGE_DIR / COMPANY_KB_FILE)
    department = _read(KNOWLEDGE_DIR / spec.kb_file)
    return f"{company}\n\n{department}"


def build_system_prompt(key: str, variant: str = "full") -> str:
    return f"{load_prompt(key, variant)}\n\n---\n\n# БАЗА ЗНАНИЙ\n\n{load_knowledge(key)}"
