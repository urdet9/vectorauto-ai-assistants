"""Отправка заявок в Telegram — без реальной сети (urlopen подменяется)."""
import io
import json
import urllib.error

import pytest

from app import notify
from app.notify import TelegramError, TelegramNotifier, format_message

RECORD = {"id": "H-ABC123", "from": "service", "to": "service", "type": "complaint", "priority": "high",
          "client_name": "Ольга <Тест>", "contact": "+7 900 000-00-00", "summary": "Жалоба на сроки ремонта"}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def fake_urlopen(calls, body=None):
    def _urlopen(request, timeout=None):
        calls.append({"url": request.full_url, "payload": json.loads(request.data.decode("utf-8"))})
        return FakeResponse(json.dumps(body or {"ok": True, "result": {}}).encode("utf-8"))
    return _urlopen


def test_message_marks_urgent_and_escapes_html():
    text = format_message(RECORD)
    assert text.startswith("🔴 <b>СРОЧНО</b>")
    assert "Жалоба" in text and "H-ABC123" in text
    assert "&lt;Тест&gt;" in text  # имя клиента не ломает HTML-разметку


def test_normal_priority_is_not_urgent():
    assert "СРОЧНО" not in format_message({**RECORD, "priority": "normal", "type": "test_drive"})


def test_from_env_disabled_without_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert TelegramNotifier.from_env() is None


def test_from_env_reads_department_chats(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_SERVICE", "-100")
    monkeypatch.setenv("TELEGRAM_CHAT_SALES", "")
    monkeypatch.setenv("TELEGRAM_CHAT_HR", "")
    monkeypatch.setenv("TELEGRAM_CHAT_DEFAULT", "-999")
    n = TelegramNotifier.from_env()
    assert n.chat_for("service") == "-100"
    assert n.chat_for("sales") == "-999"  # без своего чата — в общий


def test_send_goes_to_chat_of_target_department(monkeypatch):
    calls = []
    monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen(calls))
    n = TelegramNotifier("123:abc", {"sales": "-1", "service": "-2"})
    assert n.send(RECORD) == "-2"
    assert calls[0]["url"].endswith("/bot123:abc/sendMessage")
    assert calls[0]["payload"]["chat_id"] == "-2"
    assert calls[0]["payload"]["parse_mode"] == "HTML"


def test_send_without_chat_raises():
    n = TelegramNotifier("123:abc", {"sales": "-1"})
    with pytest.raises(TelegramError):
        n.send(RECORD)


def test_telegram_error_response_raises(monkeypatch):
    calls = []
    monkeypatch.setattr(notify.urllib.request, "urlopen",
                        fake_urlopen(calls, {"ok": False, "description": "Bad Request: chat not found"}))
    with pytest.raises(TelegramError, match="chat not found"):
        TelegramNotifier("123:abc", {"service": "-2"}).send(RECORD)


def test_no_network_raises_clear_error(monkeypatch):
    def broken(request, timeout=None):
        raise urllib.error.URLError("no route")
    monkeypatch.setattr(notify.urllib.request, "urlopen", broken)
    with pytest.raises(TelegramError, match="Нет соединения"):
        TelegramNotifier("123:abc", {"service": "-2"}).send(RECORD)
