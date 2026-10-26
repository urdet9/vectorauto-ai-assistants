"""Помощник настройки Telegram: проверяет токен бота и показывает id чатов.

Запуск: python telegram_setup.py
1. Вписать TELEGRAM_BOT_TOKEN в .env.
2. Добавить бота в группу отдела (или написать боту в личку) и отправить туда любое сообщение.
3. Запустить этот скрипт — он покажет id чатов, которые нужно вписать в .env.
4. С флагом --test отправит тестовую заявку в каждый настроенный чат.
"""
from __future__ import annotations

import sys

from dotenv import load_dotenv

from app.notify import DEPARTMENT_TITLES, TelegramError, TelegramNotifier
from config import BASE_DIR


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(BASE_DIR / ".env")
    notifier = TelegramNotifier.from_env()
    if notifier is None:
        print("[ОШИБКА] В .env не задан TELEGRAM_BOT_TOKEN.")
        return 1
    try:
        me = notifier.call("getMe")
        print(f"Бот найден: @{me.get('username')}")
        updates = notifier.call("getUpdates")
    except TelegramError as exc:
        print(f"[ОШИБКА] {exc}")
        return 1

    chats = {}
    for upd in updates:
        msg = upd.get("message") or upd.get("my_chat_member") or upd.get("channel_post") or {}
        chat = msg.get("chat")
        if chat:
            chats[chat["id"]] = chat.get("title") or chat.get("username") or chat.get("first_name") or ""
    if chats:
        print("\nЧаты, где бот видел сообщения (впишите нужные id в .env):")
        for cid, title in chats.items():
            print(f"  {cid}  —  {title}")
    else:
        print("\nСообщений пока нет. Добавьте бота в группу, отправьте туда сообщение и запустите скрипт снова.")

    print("\nНастройки в .env:")
    for dep, title in DEPARTMENT_TITLES.items():
        print(f"  {title}: {notifier.chat_for(dep) or 'не задан'}")

    if "--test" in sys.argv:
        print()
        for dep in DEPARTMENT_TITLES:
            record = {"id": "TEST", "from": dep, "to": dep, "type": "other", "priority": "normal",
                      "client_name": "Тест", "contact": "—", "summary": "Проверка связи с чатом отдела"}
            try:
                print(f"  {DEPARTMENT_TITLES[dep]}: отправлено в чат {notifier.send(record)}")
            except TelegramError as exc:
                print(f"  {DEPARTMENT_TITLES[dep]}: [ОШИБКА] {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
