"""Отправка заявок в Telegram — в чат отдела, куда смотрят сотрудники.

Настройки в .env:
  TELEGRAM_BOT_TOKEN      — токен бота от @BotFather
  TELEGRAM_CHAT_SALES     — id чата отдела продаж
  TELEGRAM_CHAT_SERVICE   — id чата сервиса
  TELEGRAM_CHAT_HR        — id чата отдела персонала
  TELEGRAM_CHAT_DEFAULT   — чат для отделов без своего чата (необязательно)

Если токен не задан, уведомления отключены и заявки только сохраняются в файл.
Используется стандартная библиотека Python — дополнительные пакеты не нужны.
"""
from __future__ import annotations

import html
import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

DEPARTMENT_TITLES = {"sales": "Отдел продаж", "service": "Сервис", "hr": "Отдел персонала"}

TYPE_TITLES = {
    "test_drive": "Тест-драйв", "trade_in": "Трейд-ин", "credit": "Кредит", "callback": "Обратный звонок",
    "service_request": "Обращение в сервис", "service_booking": "Запись в сервис", "warranty": "Гарантия",
    "recall_check": "Проверка отзывной кампании", "roadside": "Помощь на дорогах", "complaint": "Жалоба",
    "purchase_interest": "Интерес к покупке", "job_application": "Отклик на вакансию",
    "interview": "Интервью", "talent_pool": "Кадровый резерв", "employee_request": "Запрос сотрудника",
    "other": "Другое",
}


class TelegramError(Exception):
    """Ошибка отправки, которую можно понятно показать пользователю."""


def format_message(record: Dict[str, Any]) -> str:
    """Текст сообщения для чата отдела (HTML-разметка Telegram)."""
    e = lambda v: html.escape(str(v or "—"))  # noqa: E731
    urgent = record.get("priority") == "high"
    lines = [
        ("🔴 <b>СРОЧНО</b> · " if urgent else "🆕 ") + f"<b>{e(TYPE_TITLES.get(record.get('type'), record.get('type')))}</b>",
        f"Клиент: {e(record.get('client_name'))}",
        f"Контакт: {e(record.get('contact'))}",
        f"Суть: {e(record.get('summary'))}",
        f"Источник: ассистент «{e(DEPARTMENT_TITLES.get(record.get('from'), record.get('from')))}» · "
        f"заявка {e(record.get('id'))}",
    ]
    return "\n".join(lines)


class TelegramNotifier:
    API = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self, token: str, chats: Dict[str, str], default_chat: Optional[str] = None, timeout: float = 10):
        self.token = token
        self.chats = {k: v for k, v in chats.items() if v}
        self.default_chat = default_chat or None
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> Optional["TelegramNotifier"]:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            return None
        chats = {dep: os.getenv(f"TELEGRAM_CHAT_{dep.upper()}", "").strip() for dep in DEPARTMENT_TITLES}
        return cls(token, chats, os.getenv("TELEGRAM_CHAT_DEFAULT", "").strip())

    def chat_for(self, department: str) -> Optional[str]:
        return self.chats.get(department) or self.default_chat

    def call(self, method: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        url = self.API.format(token=self.token, method=method)
        data = json.dumps(payload or {}).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                description = json.loads(exc.read().decode("utf-8")).get("description", "")
            except Exception:  # noqa: BLE001
                description = ""
            if exc.code == 401:
                raise TelegramError("Telegram не принял токен бота. Проверьте TELEGRAM_BOT_TOKEN в .env.") from None
            raise TelegramError(f"Telegram вернул ошибку {exc.code}: {description}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise TelegramError(f"Нет соединения с Telegram: {exc}") from None
        if not body.get("ok"):
            raise TelegramError(f"Telegram вернул ошибку: {body.get('description')}")
        return body.get("result")

    def send(self, record: Dict[str, Any]) -> str:
        """Отправляет заявку в чат отдела из поля to. Возвращает id чата."""
        chat_id = self.chat_for(record.get("to", ""))
        if not chat_id:
            raise TelegramError(f"Не задан чат для отдела {record.get('to')!r} (TELEGRAM_CHAT_{str(record.get('to')).upper()})")
        self.call("sendMessage", {"chat_id": chat_id, "text": format_message(record), "parse_mode": "HTML"})
        return chat_id
