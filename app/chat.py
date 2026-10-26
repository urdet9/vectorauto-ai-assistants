"""Диалоговая сессия с одним ассистентом через OpenAI API."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from openai import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAI,
    RateLimitError,
)

from app.assistants import build_system_prompt, get_spec
from app.handoff import claims_handoff, parse_reply

# Техническое сообщение, чтобы ассистент сам поприветствовал пользователя при открытии чата.
START_EVENT = (
    "[Системное событие: пользователь открыл чат. "
    "Поприветствуй его согласно разделу «Приветствие и начало диалога».]"
)


class AssistantError(Exception):
    """Ошибка, которую можно понятно показать пользователю."""


@dataclass
class Reply:
    text: str
    handoffs: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    raw: str = ""


def create_client(settings) -> OpenAI:
    kwargs = {"api_key": settings.api_key}
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    return OpenAI(**kwargs)


class ChatSession:
    def __init__(self, client, assistant_key: str, model: str,
                 temperature: float = 0.4, max_history_messages: int = 20, variant: str = "full"):
        self.spec = get_spec(assistant_key)
        self.client = client
        self.model = model
        self.temperature = temperature
        self.max_history_messages = max_history_messages
        self.variant = variant
        self.system_prompt = build_system_prompt(assistant_key, variant)
        self.history: List[Dict[str, str]] = []
        self.handoff_count = 0  # сколько заявок создано в этом диалоге

    @property
    def key(self) -> str:
        return self.spec.key

    def reset(self) -> None:
        self.history.clear()
        self.handoff_count = 0

    def start(self) -> Reply:
        return self.ask(START_EVENT)

    def ask(self, user_text: str) -> Reply:
        user_text = user_text.strip()
        if not user_text:
            raise ValueError("Пустое сообщение")
        raw = self._complete(self._build_messages(user_text))
        # В историю сохраняем полный ответ (с блоком заявки),
        # чтобы модель помнила, что заявка уже создана, и не дублировала её.
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": raw})
        parsed = parse_reply(raw)
        errors = list(parsed.errors)
        if parsed.handoffs:
            self.handoff_count += len(parsed.handoffs)
        elif (self.variant == "full" and not errors and self.handoff_count == 0
              and claims_handoff(parsed.clean_text)):
            # Модель сказала клиенту «передал», но заявку не создала — обращение потеряется.
            errors.append("Ассистент написал, что обращение передано, но блок заявки не создал — заявка НЕ сохранена")
        return Reply(text=parsed.clean_text, handoffs=parsed.handoffs, errors=errors, raw=raw)

    def _build_messages(self, user_text: str) -> List[Dict[str, str]]:
        history = self.history[-self.max_history_messages:] if self.max_history_messages > 0 else []
        return [
            {"role": "system", "content": self.system_prompt},
            *history,
            {"role": "user", "content": user_text},
        ]

    def _complete(self, messages: List[Dict[str, str]]) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
            )
        except AuthenticationError:
            raise AssistantError("Ключ API не принят. Проверьте OPENAI_API_KEY в файле .env.") from None
        except NotFoundError:
            raise AssistantError(
                f"Модель {self.model!r} не найдена или недоступна. Укажите другую в OPENAI_MODEL."
            ) from None
        except RateLimitError:
            raise AssistantError(
                "Превышен лимит запросов или закончился баланс. Подождите минуту или проверьте баланс."
            ) from None
        except APIConnectionError as exc:
            reason = exc.__cause__ or exc
            raise AssistantError(
                "Нет соединения с API. Проверьте интернет, VPN или адрес OPENAI_BASE_URL.\n"
                f"Подробности: {type(reason).__name__}: {reason}"
            ) from None
        except BadRequestError as exc:
            raise AssistantError(f"API отклонил запрос (проверьте модель и параметры): {exc}") from None
        except APIError as exc:
            raise AssistantError(f"Ошибка API: {exc}") from None
        content = response.choices[0].message.content
        return (content or "").strip()
