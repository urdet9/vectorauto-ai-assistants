"""Проверка логики диалога без настоящего API: вместо OpenAI — «фейковый» клиент.
Запускается без API-ключа: pytest
"""
from types import SimpleNamespace

from app.chat import START_EVENT, ChatSession


class FakeCompletions:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.replies.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class FakeClient:
    def __init__(self, replies):
        self.chat = SimpleNamespace(completions=FakeCompletions(replies))


def test_dialog_flow_with_handoff():
    client = FakeClient([
        "Здравствуйте! Чем помочь?",
        'Передал заявку.\n<<HANDOFF>>\n{"to": "sales", "type": "test_drive", "summary": "S5"}\n<<END>>',
    ])
    session = ChatSession(client, "sales", model="test-model")

    greeting = session.start()
    assert greeting.text == "Здравствуйте! Чем помочь?"

    reply = session.ask("Запишите на тест-драйв")
    assert reply.text == "Передал заявку."
    assert reply.handoffs[0]["type"] == "test_drive"

    second_call = client.chat.completions.calls[1]
    messages = second_call["messages"]
    assert second_call["model"] == "test-model"
    assert messages[0]["role"] == "system"
    assert messages[1]["content"] == START_EVENT
    assert messages[-1] == {"role": "user", "content": "Запишите на тест-драйв"}
    # В истории хранится полный ответ с блоком, чтобы модель не дублировала заявку.
    assert "<<HANDOFF>>" in session.history[-1]["content"]


def test_history_is_trimmed():
    client = FakeClient(["1", "2", "3"])
    session = ChatSession(client, "hr", model="m", max_history_messages=2)
    session.ask("a")
    session.ask("b")
    session.ask("c")
    last_messages = client.chat.completions.calls[-1]["messages"]
    # system + 2 последних сообщения истории + новое сообщение
    assert len(last_messages) == 4
    assert last_messages[1]["content"] == "b"


def test_reset_clears_history():
    session = ChatSession(FakeClient(["ok"]), "service", model="m")
    session.ask("привет")
    session.reset()
    assert session.history == []


def test_warning_when_claimed_but_no_block():
    session = ChatSession(FakeClient(["Передал анкету HR-специалисту."]), "hr", model="m")
    reply = session.ask("Да, всё верно")
    assert reply.handoffs == []
    assert any("НЕ сохранена" in e for e in reply.errors)


def test_no_warning_after_block_already_created():
    client = FakeClient([
        'Передал.\n<<HANDOFF>>{"to": "service", "type": "complaint", "summary": "x"}<<END>>',
        "Ваше обращение передано, руководитель свяжется с вами.",
    ])
    session = ChatSession(client, "service", model="m")
    assert session.ask("Да").handoffs
    assert session.ask("Спасибо").errors == []


def test_nocode_variant_has_no_handoff_block_and_no_warning():
    session = ChatSession(FakeClient(["Передал обращение в сервис."]), "sales", model="m", variant="nocode")
    assert "<<HANDOFF>>" not in session.system_prompt
    assert session.ask("Да").errors == []
