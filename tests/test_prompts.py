"""Проверка, что промпты и база знаний содержат все разделы, которые требует ТЗ.
Запускается без API-ключа: pytest
"""
import pytest

from app.assistants import ASSISTANTS, build_system_prompt, load_knowledge, load_prompt

# Разделы системного промпта из ТЗ (п. 1) + раздел передачи обращений между отделами.
REQUIRED_PROMPT_SECTIONS = [
    "# Название",
    "# Цель и задачи",
    "# Роль, стиль и тон",
    "# Приветствие и начало диалога",
    "# Пошаговые сценарии",
    "# Ограничения",
    "# Типовые вопросы и ответы",
    "# Передача обращений в другие отделы",
]

# Разделы базы знаний из ТЗ (п. 3).
REQUIRED_KB_SECTIONS = ["## FAQ", "## Типовые обращения", "## Скрипты общения (по ролям)"]


@pytest.mark.parametrize("key", list(ASSISTANTS))
def test_prompt_has_required_sections(key):
    prompt = load_prompt(key)
    missing = [s for s in REQUIRED_PROMPT_SECTIONS if s not in prompt]
    assert not missing, f"{key}: в промпте нет разделов {missing}"


@pytest.mark.parametrize("key", list(ASSISTANTS))
def test_prompt_describes_handoff_format(key):
    prompt = load_prompt(key)
    assert "<<HANDOFF>>" in prompt and "<<END>>" in prompt


@pytest.mark.parametrize("key", list(ASSISTANTS))
def test_knowledge_has_required_sections(key):
    kb = load_knowledge(key)
    missing = [s for s in REQUIRED_KB_SECTIONS if s not in kb]
    assert not missing, f"{key}: в базе знаний нет разделов {missing}"


@pytest.mark.parametrize("key", list(ASSISTANTS))
def test_system_prompt_contains_prompt_and_kb(key):
    system_prompt = build_system_prompt(key)
    assert "# БАЗА ЗНАНИЙ" in system_prompt
    assert "Общая информация об автоцентре" in system_prompt
    assert load_prompt(key) in system_prompt


def test_unknown_assistant_raises():
    with pytest.raises(KeyError):
        load_prompt("unknown")


@pytest.mark.parametrize("key", list(ASSISTANTS))
def test_prompt_requires_block_when_claiming_handoff(key):
    prompt = load_prompt(key)
    assert "«Всё верно?»" in prompt
    assert "только в сообщении, в котором есть блок" in prompt


GPT_INSTRUCTIONS_LIMIT = 8000  # лимит поля Instructions в конструкторе GPT


@pytest.mark.parametrize("key", list(ASSISTANTS))
def test_nocode_prompt_fits_limit_and_has_sections(key):
    from config import BASE_DIR
    text = (BASE_DIR / "prompts_nocode" / f"{key}.md").read_text(encoding="utf-8")
    assert len(text) <= GPT_INSTRUCTIONS_LIMIT, f"{key}: {len(text)} символов"
    assert "<<HANDOFF>>" not in text
    assert "«Всё верно?»" in text, f"{key}: нет правила подтверждения данных"
    missing = [s for s in REQUIRED_PROMPT_SECTIONS if s not in text]
    assert not missing, f"{key}: нет разделов {missing}"
