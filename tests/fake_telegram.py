"""Подменная сессия Telegram: ловит исходящие вызовы вместо сети."""

from __future__ import annotations

import datetime as dt
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import Chat, Message, User

BOT_USER = User(id=1, is_bot=True, first_name="TestBot", username="test_bot")
CHAT = Chat(id=1000, type="private")
USER = User(id=777, is_bot=False, first_name="Тестовый")


class FakeSession(BaseSession):
    """Записывает каждый вызов API и возвращает правдоподобный ответ."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._message_id = 0

    async def close(self) -> None:  # pragma: no cover
        return None

    async def stream_content(self, *args: Any, **kwargs: Any):  # pragma: no cover
        # Минимальный PNG 1x1 — для bot.download()
        yield bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000a49444154789c6300010000050001" "0d0a2db40000000049454e44ae426082"
        )

    def _next_message(self, **kwargs: Any) -> Message:
        self._message_id += 1
        return Message(
            message_id=self._message_id,
            date=dt.datetime.now(dt.timezone.utc),
            chat=CHAT,
            from_user=BOT_USER,
            **kwargs,
        )

    async def make_request(
        self, bot: Bot, method: TelegramMethod, timeout: int | None = None
    ) -> Any:
        name = type(method).__name__
        payload = method.model_dump(exclude_none=True)
        self.calls.append((name, payload))

        if name == "GetMe":
            return BOT_USER
        if name in {"SendMessage", "EditMessageText"}:
            # Настоящая сессия привязывает ответы к боту — повторяем это.
            return self._next_message(text=payload.get("text", "")).as_(bot)
        if name == "SendPhoto":
            return self._next_message(caption=payload.get("caption")).as_(bot)
        if name == "GetFile":
            from aiogram.types import File

            return File(
                file_id=payload.get("file_id", "f"),
                file_unique_id="u",
                file_size=10,
                file_path="photos/test.png",
            )
        return True

    # --- помощники для тестов -------------------------------------------

    def texts(self) -> list[str]:
        out = []
        for name, payload in self.calls:
            if name == "SendMessage":
                out.append(payload.get("text", ""))
            elif name == "SendPhoto":
                out.append("[ФОТО] " + (payload.get("caption") or ""))
        return out

    def method_names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def reset(self) -> None:
        self.calls.clear()
