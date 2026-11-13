"""Отправка длинных ответов в Telegram с учётом лимитов."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, Message

from bot.utils.formatting import html_messages, plain_messages


async def send_html(
    message: Message,
    markdown: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Отправляет Markdown-текст модели как Telegram HTML, разбив по лимиту."""
    parts = html_messages(markdown)
    if not parts:
        return
    for part in parts[:-1]:
        await message.answer(part)
    await message.answer(parts[-1], reply_markup=reply_markup)


async def send_plain(
    message: Message,
    markdown: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Отправляет текст без разметки — чтобы его было удобно скопировать."""
    parts = plain_messages(markdown)
    if not parts:
        return
    for part in parts[:-1]:
        await message.answer(part, parse_mode=None)
    await message.answer(parts[-1], parse_mode=None, reply_markup=reply_markup)
