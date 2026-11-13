"""Индикатор процесса: редактируемое сообщение + статус «печатает»."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender

logger = logging.getLogger(__name__)

BAR_FRAMES = ("▰▱▱▱▱", "▰▰▱▱▱", "▰▰▰▱▱", "▰▰▰▰▱", "▰▰▰▰▰")
# Telegram не любит частые правки одного сообщения.
EDIT_INTERVAL = 3.0
# Сколько тиков держать одну стадию.
TICKS_PER_STAGE = 2

SCAN_STAGES = (
    "Читаю пост и определяю категорию продукта…",
    "Проверяю запреты для этой категории (ст. 34–35, 45)…",
    "Проверяю изображение по чек-листу…",
    "Проверяю обязательные предупреждения и язык (ст. 6, 18)…",
    "Готовлю исправленные варианты…",
)

CREATE_STAGES = (
    "Определяю категорию и ограничения…",
    "Подбираю формулировки без лечебных обещаний…",
    "Добавляю обязательные предупреждения и пометки…",
    "Собираю готовый пост…",
)


class Progress:
    """Асинхронный контекст: пока идёт запрос, пользователь видит прогресс."""

    def __init__(
        self,
        message: Message,
        stages: tuple[str, ...],
        action: str = "typing",
    ) -> None:
        self._message = message
        self._stages = stages or ("Обрабатываю…",)
        self._action = action
        self._placeholder: Message | None = None
        self._task: asyncio.Task | None = None

    async def __aenter__(self) -> "Progress":
        text = self._render(0, 0)
        try:
            self._placeholder = await self._message.answer(text)
        except Exception:
            logger.warning("Не удалось отправить индикатор прогресса", exc_info=True)
            return self
        self._task = asyncio.create_task(self._run())
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._placeholder:
            # Индикатор — вспомогательный: любая его ошибка не должна помешать
            # отправить пользователю результат.
            try:
                await self._placeholder.delete()
            except Exception:
                logger.debug("Не удалось удалить индикатор", exc_info=True)
            self._placeholder = None

    def _render(self, stage_index: int, tick: int) -> str:
        stage = self._stages[min(stage_index, len(self._stages) - 1)]
        bar = BAR_FRAMES[tick % len(BAR_FRAMES)]
        return f"{bar}\n{stage}"

    async def _run(self) -> None:
        bot = self._message.bot
        chat_id = self._message.chat.id
        tick = 0
        try:
            async with contextlib.AsyncExitStack() as stack:
                if bot is not None:
                    await stack.enter_async_context(
                        ChatActionSender(
                            bot=bot, chat_id=chat_id, action=self._action
                        )
                    )
                while True:
                    await asyncio.sleep(EDIT_INTERVAL)
                    tick += 1
                    if not self._placeholder:
                        continue
                    text = self._render(tick // TICKS_PER_STAGE, tick)
                    try:
                        await self._placeholder.edit_text(text)
                    except Exception:
                        # «message is not modified», «message to edit not found»,
                        # флуд-контроль — индикатор не повод ломать запрос.
                        pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Индикатор прогресса остановлен ошибкой", exc_info=True)
