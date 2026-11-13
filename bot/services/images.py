"""Получение изображений из Telegram и подготовка их для Claude API."""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import Message

logger = logging.getLogger(__name__)

# Лимит одного изображения в Claude API — 5 МБ в base64; берём с запасом.
MAX_IMAGE_BYTES = 4_000_000
SUPPORTED_MEDIA_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})


@dataclass(frozen=True)
class InputImage:
    """Изображение, готовое к отправке в API."""

    media_type: str
    data_b64: str
    file_id: str

    def to_block(self) -> dict:
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": self.media_type,
                "data": self.data_b64,
            },
        }


def has_image(message: Message) -> bool:
    if message.photo:
        return True
    document = message.document
    return bool(document and (document.mime_type or "") in SUPPORTED_MEDIA_TYPES)


def is_unsupported_media(message: Message) -> bool:
    """Сообщение с вложением, которое бот не умеет разбирать."""
    if has_image(message):
        return False
    return bool(
        message.video
        or message.animation
        or message.voice
        or message.audio
        or message.video_note
        or message.sticker
        or message.document
    )


def _pick_photo(message: Message) -> tuple[str, str] | None:
    """Самый крупный размер фото, укладывающийся в лимит. -> (file_id, media_type)"""
    sizes = sorted(
        message.photo or [],
        key=lambda size: (size.width or 0) * (size.height or 0),
        reverse=True,
    )
    for size in sizes:
        if (size.file_size or 0) <= MAX_IMAGE_BYTES:
            return size.file_id, "image/jpeg"
    return None


def image_reference(message: Message) -> tuple[str, str] | None:
    """file_id и media_type изображения из сообщения, без скачивания."""
    if message.photo:
        return _pick_photo(message)
    document = message.document
    if document and (document.mime_type or "") in SUPPORTED_MEDIA_TYPES:
        if (document.file_size or 0) > MAX_IMAGE_BYTES:
            return None
        return document.file_id, document.mime_type or "image/jpeg"
    return None


async def download_image(bot: Bot, file_id: str, media_type: str) -> InputImage | None:
    """Скачивает файл из Telegram и кодирует в base64."""
    try:
        buffer = await bot.download(file_id)
    except Exception:  # сеть, истёкший file_id, слишком большой файл
        logger.exception("Не удалось скачать изображение %s", file_id)
        return None
    if buffer is None:
        return None
    raw = buffer.read()
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        logger.warning("Изображение %s пропущено: размер %s байт", file_id, len(raw))
        return None
    return InputImage(
        media_type=media_type,
        data_b64=base64.standard_b64encode(raw).decode("ascii"),
        file_id=file_id,
    )


async def collect_images(
    bot: Bot, messages: list[Message], limit: int
) -> list[InputImage]:
    """Собирает до `limit` изображений из списка сообщений."""
    images: list[InputImage] = []
    for message in messages:
        if len(images) >= limit:
            break
        reference = image_reference(message)
        if not reference:
            continue
        image = await download_image(bot, reference[0], reference[1])
        if image:
            images.append(image)
    return images
