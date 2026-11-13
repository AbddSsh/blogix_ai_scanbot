"""Обращение к Claude API: проверка поста и создание поста с нуля."""

from __future__ import annotations

import asyncio
import logging

import anthropic

from bot import texts
from bot.config import PROMPTS_DIR, Config
from bot.keyboards import CATEGORIES, LANGUAGES
from bot.services.images import InputImage

logger = logging.getLogger(__name__)


class ClaudeError(Exception):
    """Ошибка обращения к API с готовым текстом для пользователя."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


def _read_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


class ClaudeService:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
        self._legal_base = _read_prompt("legal_base.md")
        self._scan_task = _read_prompt("scan_task.md")
        self._create_task = _read_prompt("create_task.md")
        self._semaphore = asyncio.Semaphore(config.max_concurrent_requests)

    async def close(self) -> None:
        await self._client.close()

    # --- публичные методы ------------------------------------------------

    async def scan_post(self, text: str, images: list[InputImage]) -> str:
        if text.strip():
            user_text = "Проверь этот рекламный пост:\n\n" + text.strip()
        else:
            user_text = (
                "Проверь этот рекламный пост. Текста нет, пост — только изображение."
            )
        if not images:
            user_text += "\n\n(Изображение не прислано.)"
        return await self._ask(self._scan_task, user_text, images)

    async def create_post(
        self,
        description: str,
        category_code: str,
        language_code: str,
        images: list[InputImage],
    ) -> str:
        category = CATEGORIES.get(category_code, CATEGORIES["unknown"])[1]
        language = LANGUAGES.get(language_code, LANGUAGES["ru"])[1]
        lines = [
            "Напиши готовый рекламный пост по этим данным.",
            "",
            f"Категория продукта: {category}",
            f"Язык поста: {language}",
            f"Описание от клиента: {description.strip()}",
        ]
        if images:
            lines.append(
                "Фото препарата приложено — проверь его по чек-листу изображения."
            )
        else:
            lines.append("Фото не приложено.")
        return await self._ask(self._create_task, "\n".join(lines), images)

    # --- внутреннее ------------------------------------------------------

    async def _ask(
        self, task_prompt: str, user_text: str, images: list[InputImage]
    ) -> str:
        content: list[dict] = [image.to_block() for image in images]
        content.append({"type": "text", "text": user_text})

        system = [
            {
                "type": "text",
                "text": self._legal_base,
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": task_prompt,
                "cache_control": {"type": "ephemeral"},
            },
        ]

        async with self._semaphore:
            try:
                async with self._client.messages.stream(
                    model=self._config.model,
                    max_tokens=self._config.max_tokens,
                    output_config={"effort": self._config.effort},
                    system=system,
                    messages=[{"role": "user", "content": content}],
                ) as stream:
                    response = await stream.get_final_message()
            except anthropic.AuthenticationError:
                logger.exception("Claude API: ключ отклонён")
                raise ClaudeError(texts.ERR_AUTH) from None
            except anthropic.PermissionDeniedError:
                logger.exception("Claude API: нет прав у ключа")
                raise ClaudeError(texts.ERR_AUTH) from None
            except anthropic.RateLimitError:
                logger.warning("Claude API: превышен лимит запросов")
                raise ClaudeError(texts.ERR_RATE) from None
            except anthropic.BadRequestError as error:
                # Нулевой баланс приходит как 400, но лечится не кодом, а
                # пополнением счёта — отделяем его от настоящих ошибок запроса.
                if "credit balance" in str(error).lower():
                    logger.error(
                        "Claude API: нулевой баланс аккаунта — пополните счёт "
                        "в console.anthropic.com → Plans & Billing"
                    )
                    raise ClaudeError(texts.ERR_BILLING) from None
                logger.exception("Claude API: некорректный запрос")
                raise ClaudeError(texts.ERR_UNKNOWN) from None
            except anthropic.APIStatusError as error:
                logger.exception("Claude API: статус %s", error.status_code)
                raise ClaudeError(texts.ERR_NETWORK) from None
            except anthropic.APIConnectionError:
                logger.exception("Claude API: сетевая ошибка")
                raise ClaudeError(texts.ERR_NETWORK) from None

        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            logger.warning(
                "Claude отказался отвечать: %s",
                getattr(details, "category", None),
            )
            raise ClaudeError(texts.ERR_REFUSAL)

        answer = "\n".join(
            block.text for block in response.content if block.type == "text"
        ).strip()

        if response.stop_reason == "max_tokens" and not answer:
            raise ClaudeError(texts.ERR_TRUNCATED)
        if not answer:
            logger.error("Claude вернул пустой ответ, stop_reason=%s", response.stop_reason)
            raise ClaudeError(texts.ERR_UNKNOWN)
        if response.stop_reason == "max_tokens":
            answer += "\n\n⚠️ Ответ оборвался из-за длины — сократите пост и попробуйте снова."

        usage = response.usage
        logger.info(
            "Claude ok: in=%s cache_read=%s cache_write=%s out=%s",
            usage.input_tokens,
            getattr(usage, "cache_read_input_tokens", None),
            getattr(usage, "cache_creation_input_tokens", None),
            usage.output_tokens,
        )
        return answer
