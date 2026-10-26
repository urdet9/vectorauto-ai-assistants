"""Проверка разбора и сохранения заявок. Запускается без API-ключа: pytest"""
from app.handoff import claims_handoff, load_handoffs, parse_reply, save_handoff

VALID_BLOCK = (
    "<<HANDOFF>>\n"
    '{"to": "sales", "type": "test_drive", "priority": "normal", '
    '"client_name": "Андрей", "contact": "+7 900 111-22-33", "summary": "Тест-драйв S5"}\n'
    "<<END>>"
)


def test_valid_block_is_parsed_and_removed():
    result = parse_reply("Передал заявку менеджеру.\n" + VALID_BLOCK)
    assert result.clean_text == "Передал заявку менеджеру."
    assert len(result.handoffs) == 1
    assert result.handoffs[0]["to"] == "sales"
    assert not result.errors


def test_text_without_block():
    result = parse_reply("Здравствуйте! Чем помочь?")
    assert result.clean_text == "Здравствуйте! Чем помочь?"
    assert result.handoffs == [] and result.errors == []


def test_json_in_code_fence():
    text = 'Готово.\n<<HANDOFF>>\n```json\n{"to": "hr", "type": "interview", "summary": "Интервью"}\n```\n<<END>>'
    result = parse_reply(text)
    assert result.handoffs[0]["to"] == "hr"
    assert result.handoffs[0]["priority"] == "normal"  # подставляется по умолчанию


def test_invalid_json_gives_error_and_clean_text():
    result = parse_reply("Готово.\n<<HANDOFF>>\n{to: sales}\n<<END>>")
    assert result.clean_text == "Готово."
    assert result.handoffs == []
    assert result.errors


def test_unknown_department_rejected():
    result = parse_reply('<<HANDOFF>>{"to": "finance", "type": "other", "summary": "x"}<<END>>')
    assert result.handoffs == []
    assert "неизвестный отдел" in result.errors[0]


def test_missing_required_field_rejected():
    result = parse_reply('<<HANDOFF>>{"to": "sales", "type": "callback"}<<END>>')
    assert result.handoffs == []
    assert "summary" in result.errors[0]


def test_unclosed_block_is_cut():
    result = parse_reply('Передал.\n<<HANDOFF>>\n{"to": "sales"')
    assert result.clean_text == "Передал."
    assert result.handoffs == []
    assert result.errors


def test_save_and_load(tmp_path):
    path = tmp_path / "handoffs.jsonl"
    data = parse_reply(VALID_BLOCK).handoffs[0]
    record = save_handoff(data, source="sales", path=path)
    assert record["id"].startswith("H-")
    assert record["from"] == "sales"
    loaded = load_handoffs(path)
    assert len(loaded) == 1 and loaded[0]["summary"] == "Тест-драйв S5"


def test_claims_handoff_detects_past_tense_only():
    from app.handoff import claims_handoff
    assert claims_handoff("Передал анкету HR-специалисту.")
    assert claims_handoff("Ваше обращение передано.")
    assert not claims_handoff("Я передам ваше обращение руководителю.")
    assert not claims_handoff("Могу передать вопрос менеджеру.")
    assert not claims_handoff("Хотите, чтобы я передал заявку кредитному специалисту? Оставьте имя.")
    assert claims_handoff("Спасибо! Обращение передано. Менеджер перезвонит.")


def test_claims_handoff_short_participle():
    assert claims_handoff("Ваш запрос передан в сервисный центр.")
    assert not claims_handoff("Передаю запрос мастеру. Всё верно?")
