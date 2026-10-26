"""Консольный чат с нейроассистентами автоцентра «ВекторАвто».

Запуск: python main.py  (или кнопка Run в PyCharm)
"""
from __future__ import annotations

import sys
from typing import Optional

from app.assistants import ASSISTANTS, DEPARTMENTS
from app.chat import AssistantError, ChatSession, Reply, create_client
from app.handoff import load_handoffs, save_handoff
from app.notify import TelegramError, TelegramNotifier
from app.transcript import Transcript
from config import DATA_DIR, Settings, get_settings

HANDOFFS_FILE = DATA_DIR / "handoffs.jsonl"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"

MENU = {"1": "sales", "2": "service", "3": "hr"}

# Отправка заявок в Telegram-чат отдела. None — Telegram не настроен в .env.
NOTIFIER: Optional[TelegramNotifier] = None

HELP = """Команды:
  /menu      — выбрать другого ассистента
  /reset     — начать диалог заново
  /handoffs  — показать последние переданные заявки
  /help      — список команд
  /exit      — выход"""


def choose_assistant() -> Optional[str]:
    print("\nВыберите ассистента:")
    for number, key in MENU.items():
        print(f"  {number} — {ASSISTANTS[key].title}")
    print("  0 — выход")
    while True:
        try:
            choice = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if choice == "0":
            return None
        if choice in MENU:
            return MENU[choice]
        print("Введите 1, 2, 3 или 0.")


def show_reply(reply: Reply, session: ChatSession, transcript: Transcript) -> None:
    print(f"\n{session.spec.title}:\n{reply.text}\n")
    transcript.write("Ассистент", reply.text)

    for data in reply.handoffs:
        record = save_handoff(data, source=session.key, path=HANDOFFS_FILE)
        department = DEPARTMENTS.get(record["to"], record["to"])
        message = (
            f"[ЗАЯВКА {record['id']}] → {department} | тип: {record['type']} | "
            f"приоритет: {record['priority']} | {record['summary']}"
        )
        print(message)
        transcript.write("Система", message)
        delivery = deliver(record)
        print(delivery + "\n")
        transcript.write("Система", delivery)

    for error in reply.errors:
        message = f"[ВНИМАНИЕ] {error}"
        print(message + "\n")
        transcript.write("Система", message)


def deliver(record: dict) -> str:
    """Отправляет заявку в чат отдела и возвращает строку о результате."""
    if NOTIFIER is None:
        return "  Telegram не настроен — заявка сохранена только в data/handoffs.jsonl."
    try:
        NOTIFIER.send(record)
        return f"  ✓ Отправлено в Telegram-чат отдела ({DEPARTMENTS.get(record['to'], record['to'])})."
    except TelegramError as exc:
        return f"[ВНИМАНИЕ] Заявка сохранена в файл, но в Telegram не отправлена: {exc}"


def show_handoffs(limit: int = 10) -> None:
    records = load_handoffs(HANDOFFS_FILE)
    if not records:
        print("Заявок пока нет.")
        return
    print(f"Последние заявки (всего: {len(records)}):")
    for r in records[-limit:]:
        print(
            f"  {r.get('created_at', '')} | {r.get('id', '')} | {r.get('from', '')} → {r.get('to', '')} | "
            f"{r.get('type', '')} | {r.get('priority', '')} | {r.get('summary', '')}"
        )


def greet(session: ChatSession, transcript: Transcript) -> bool:
    try:
        show_reply(session.start(), session, transcript)
        return True
    except AssistantError as exc:
        print(f"[ОШИБКА] {exc}")
        return False


def run_chat(client, settings: Settings, key: str) -> bool:
    """Диалог с одним ассистентом. True — вернуться в меню, False — выйти из программы."""
    session = ChatSession(
        client,
        key,
        model=settings.model,
        temperature=settings.temperature,
        max_history_messages=settings.max_history_messages,
    )
    transcript = Transcript(TRANSCRIPTS_DIR, key, session.spec.title)
    print(f"\n=== {session.spec.title} ===   (/help — команды)")
    if not greet(session, transcript):
        return False

    while True:
        try:
            text = input("Вы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if not text:
            continue

        command = text.lower()
        if command == "/exit":
            return False
        if command == "/menu":
            return True
        if command == "/help":
            print(HELP)
            continue
        if command == "/handoffs":
            show_handoffs()
            continue
        if command == "/reset":
            session.reset()
            transcript = Transcript(TRANSCRIPTS_DIR, key, session.spec.title)
            print("Диалог начат заново.")
            greet(session, transcript)
            continue

        transcript.write("Пользователь", text)
        try:
            reply = session.ask(text)
        except AssistantError as exc:
            print(f"[ОШИБКА] {exc}")
            continue
        show_reply(reply, session, transcript)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        settings = get_settings()
    except RuntimeError as exc:
        print(f"[ОШИБКА] {exc}")
        return 1

    global NOTIFIER
    NOTIFIER = TelegramNotifier.from_env()

    client = create_client(settings)
    print("Автоцентр «ВекторАвто» — демо нейроассистентов (учебный проект, данные вымышленные)")
    print(f"Модель: {settings.model}")
    print("Заявки в Telegram: " + ("включены" if NOTIFIER else "выключены (нет TELEGRAM_BOT_TOKEN в .env)"))

    while True:
        key = choose_assistant()
        if key is None:
            break
        if not run_chat(client, settings, key):
            break

    print("До свидания!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
