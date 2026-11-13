"""Склейка нескольких сообщений в одну заявку.

Telegram присылает альбом отдельными апдейтами, а пользователь часто отправляет
текст и картинку двумя сообщениями подряд. Поэтому первое сообщение запускает
короткое окно ожидания, в которое попадают все следующие.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

logger = logging.getLogger(__name__)

FlushCallback = Callable[[list[Message], FSMContext], Awaitable[None]]


@dataclass
class _Batch:
    state: FSMContext
    messages: list[Message] = field(default_factory=list)
    task: asyncio.Task | None = None


class MessageCollector:
    def __init__(self, delay: float, flush: FlushCallback) -> None:
        self._delay = delay
        self._flush = flush
        self._batches: dict[int, _Batch] = {}

    async def add(self, message: Message, state: FSMContext) -> None:
        chat_id = message.chat.id
        batch = self._batches.get(chat_id)
        if batch is None:
            batch = _Batch(state=state)
            self._batches[chat_id] = batch
        batch.state = state
        batch.messages.append(message)

        if batch.task:
            batch.task.cancel()
        batch.task = asyncio.create_task(self._wait_and_flush(chat_id))

    def cancel(self, chat_id: int) -> None:
        batch = self._batches.pop(chat_id, None)
        if batch and batch.task:
            batch.task.cancel()

    async def _wait_and_flush(self, chat_id: int) -> None:
        try:
            await asyncio.sleep(self._delay)
        except asyncio.CancelledError:
            return
        batch = self._batches.pop(chat_id, None)
        if not batch or not batch.messages:
            return
        try:
            await self._flush(batch.messages, batch.state)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Ошибка обработки заявки в чате %s", chat_id)

    async def shutdown(self) -> None:
        tasks = [b.task for b in self._batches.values() if b.task]
        self._batches.clear()
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
