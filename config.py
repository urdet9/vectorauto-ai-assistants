"""Настройки проекта: пути к папкам и параметры из файла .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = BASE_DIR / "prompts"
PROMPTS_NOCODE_DIR = BASE_DIR / "prompts_nocode"  # версии для GPTs и no-code
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
SCENARIOS_FILE = BASE_DIR / "tests" / "scenarios.json"

load_dotenv(BASE_DIR / ".env")

PLACEHOLDER_KEY = "sk-your-key-here"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


@dataclass(frozen=True)
class Settings:
    api_key: str
    model: str
    base_url: str
    temperature: float
    max_history_messages: int


def _read_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        raise RuntimeError(f"Параметр {name} в .env должен быть числом, сейчас: {raw!r}") from None


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"Параметр {name} в .env должен быть целым числом, сейчас: {raw!r}") from None


def get_settings() -> Settings:
    """Читает настройки из .env. Без ключа API работать нельзя — сообщаем об этом понятно."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or api_key == PLACEHOLDER_KEY:
        raise RuntimeError(
            "Не найден OPENAI_API_KEY. Скопируйте файл .env.example в .env и впишите свой ключ."
        )
    return Settings(
        api_key=api_key,
        model=os.getenv("OPENAI_MODEL", "").strip() or "gpt-4o-mini",
        # Пустое значение заменяем официальным адресом: иначе библиотека openai
        # возьмёт пустую строку из окружения и не сможет отправить запрос.
        base_url=os.getenv("OPENAI_BASE_URL", "").strip() or DEFAULT_BASE_URL,
        temperature=_read_float("TEMPERATURE", 0.4),
        max_history_messages=_read_int("MAX_HISTORY_MESSAGES", 20),
    )
