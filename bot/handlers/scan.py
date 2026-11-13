"""Режим «Проверить пост»."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import keyboards, texts
from bot.config import Config
from bot.services.claude import ClaudeError, ClaudeService
from bot.services.collector import MessageCollector
from bot.services.images import collect_images, has_image, is_unsupported_media
from bot.services.limits import RateLimiter
from bot.services.progress import SCAN_STAGES, Progress
from bot.states import ScanStates
from bot.utils.formatting import Section, parse_sections, pop_disclaimer, render_sections
from bot.utils.sending import send_html, send_plain

logger = logging.getLogger(__name__)

router = Router(name="scan")

VARIANT_TITLES = ("Вариант",)


def build_collector(
    config: Config, claude: ClaudeService, limiter: RateLimiter
) -> MessageCollector:
    """Собирает коллектор с замыканием на сервисы — создаётся один раз в main."""

    async def flush(messages: list[Message], state: FSMContext) -> None:
        await run_scan(messages, state, claude, limiter, config)

    return MessageCollector(config.collect_delay, flush)


@router.message(StateFilter(ScanStates.waiting_for_post, None))
async def on_post(
    message: Message, state: FSMContext, collector: MessageCollector
) -> None:
    """Любой пост (текст и/или картинка) попадает в окно сбора.

    Известные команды перехватывает роутер меню, который подключён раньше.
    """
    raw = message.text or message.caption or ""
    if raw.startswith("/"):
        await message.answer(texts.UNKNOWN_COMMAND, reply_markup=keyboards.main_menu())
        return
    if is_unsupported_media(message):
        await message.answer(texts.SCAN_UNSUPPORTED)
        return
    text = message.text or message.caption or ""
    if not text.strip() and not has_image(message):
        await message.answer(texts.SCAN_EMPTY)
        return
    await collector.add(message, state)


async def run_scan(
    messages: list[Message],
    state: FSMContext,
    claude: ClaudeService,
    limiter: RateLimiter,
    config: Config,
) -> None:
    first = messages[0]
    user = first.from_user
    if user is None:
        return

    texts_parts = [
        (m.text or m.caption or "").strip()
        for m in messages
        if (m.text or m.caption or "").strip()
    ]
    post_text = "\n\n".join(texts_parts)
    image_expected = any(has_image(m) for m in messages)

    if not post_text and not image_expected:
        await first.answer(texts.SCAN_EMPTY)
        return

    rejection = limiter.try_acquire(user.id)
    if rejection:
        await first.answer(
            texts.BUSY
            if rejection.busy
            else texts.RATE_LIMITED.format(
                limit=limiter.per_hour, minutes=rejection.minutes
            )
        )
        return

    try:
        bot = first.bot
        if bot is None:
            return
        images = await collect_images(bot, messages, config.max_images)
        if not post_text and not images:
            await first.answer(texts.SCAN_EMPTY)
            return

        logger.info(
            "Проверка поста: user=%s символов=%s изображений=%s",
            user.id,
            len(post_text),
            len(images),
        )
        async with Progress(first, SCAN_STAGES):
            answer = await claude.scan_post(post_text, images)

        await state.clear()
        await send_scan_result(first, answer)
    except ClaudeError as error:
        await first.answer(error.user_message)
    except Exception:
        logger.exception("Непредвиденная ошибка при проверке поста")
        await first.answer(texts.ERR_UNKNOWN)
    finally:
        limiter.release(user.id)


async def send_scan_result(message: Message, answer: str) -> None:
    """Вердикт и правки — одним сообщением, варианты — отдельными, для копирования."""
    sections = parse_sections(answer)
    disclaimer = pop_disclaimer(sections)

    variant_indexes = [
        index
        for index, section in enumerate(sections)
        if section.title_matches(*VARIANT_TITLES)
    ]

    if variant_indexes:
        lead = sections[: variant_indexes[0]]
        variants = [sections[index] for index in variant_indexes]
        tail = sections[variant_indexes[-1] + 1 :]
    else:
        lead, variants, tail = sections, [], []

    lead_markdown = render_sections(lead)
    if variants:
        lead_markdown = f"{lead_markdown}\n\n{texts.VARIANT_HINT}".strip()
    if lead_markdown:
        await send_html(message, lead_markdown)

    for section in variants:
        if section.title:
            await message.answer(f"👇 <b>{section.title}</b>")
        await send_plain(message, section.body)

    await _send_tail(message, tail, disclaimer, keyboards.after_scan())


async def _send_tail(
    message: Message,
    tail: list[Section],
    disclaimer: str | None,
    markup,
) -> None:
    parts = [render_sections(tail)] if tail else []
    if disclaimer:
        parts.append(f"*{disclaimer}*")
    else:
        parts.append(f"*{texts.DISCLAIMER}*")
    await send_html(message, "\n\n".join(part for part in parts if part), markup)
