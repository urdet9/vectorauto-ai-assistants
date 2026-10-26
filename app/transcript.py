"""Запись диалогов в markdown-файлы (для проверки и скриншотов в портфолио)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path


class Transcript:
    def __init__(self, directory: Path, assistant_key: str, title: str):
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.path = directory / f"{stamp}_{assistant_key}.md"
        self.path.write_text(f"# Диалог: {title}\n\nНачало: {stamp}\n\n", encoding="utf-8")

    def write(self, role: str, text: str) -> None:
        with self.path.open("a", encoding="utf-8") as file:
            file.write(f"**{role}:** {text}\n\n")
