"""Режим «Создать пост»: фото → описание → категория → язык → готовый пост."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from bot import keyboards, texts
from bot.keyboards import CATEGORIES, LANGUAGES
from bot.services.claude import ClaudeError, ClaudeService
from bot.services.images import (
    download_image,
    image_reference,
    is_unsupported_media,
)
from bot.services.limits import RateLimiter
from bot.services.progress import CREATE_STAGES, Progress
from bot.states import CreateStates
from bot.utils.formatting import (
    TELEGRAM_CAPTION_LIMIT,
    Section,
    parse_sections,
    plain_messages,
    pop_disclaimer,
    render_sections,
    to_plain,
)
from bot.utils.sending import send_html, send_plain

logger = logging.getLogger(__name__)

router = Router(name="create")

DESCRIPTION_MIN = 10
DESCRIPTION_MAX = 1500
POST_TITLES = ("Пост",)


# --- Шаг 1: фото ----------------------------------------------------------


@router.message(CreateStates.waiting_photo)
async def on_photo(message: Message, state: FSMContext) -> None:
    reference = image_reference(message)
    if reference is None:
        await message.answer(
            texts.CREATE_ASK_PHOTO_AGAIN, reply_markup=keyboards.ask_photo()
        )
        return
    await state.update_data(photo_file_id=reference[0], photo_media_type=reference[1])
    await state.set_state(CreateStates.waiting_description)
    await message.answer(
        texts.CREATE_ASK_DESCRIPTION, reply_markup=keyboards.cancel_only()
    )


@router.callback_query(CreateStates.waiting_photo, F.data == "create:nophoto")
async def on_no_photo(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.message:
        return
    await state.update_data(photo_file_id=None, photo_media_type=None)
    await state.set_state(CreateStates.waiting_description)
    await callback.message.answer(
        texts.CREATE_ASK_DESCRIPTION, reply_markup=keyboards.cancel_only()
    )


# --- Шаг 2: описание ------------------------------------------------------


@router.message(CreateStates.waiting_description)
async def on_description(message: Message, state: FSMContext) -> None:
    if is_unsupported_media(message) or image_reference(message):
        await message.answer(
            texts.CREATE_ASK_DESCRIPTION, reply_markup=keyboards.cancel_only()
        )
        return
    description = (message.text or message.caption or "").strip()
    if len(description) < DESCRIPTION_MIN:
        await message.answer(
            texts.CREATE_DESCRIPTION_TOO_SHORT, reply_markup=keyboards.cancel_only()
        )
        return
    if len(description) > DESCRIPTION_MAX:
        await message.answer(
            texts.CREATE_DESCRIPTION_TOO_LONG, reply_markup=keyboards.cancel_only()
        )
        return
    await state.update_data(description=description)
    await state.set_state(CreateStates.waiting_category)
    await message.answer(texts.CREATE_ASK_CATEGORY, reply_markup=keyboards.categories())


# --- Шаг 3: категория -----------------------------------------------------


@router.callback_query(CreateStates.waiting_category, F.data.startswith("cat:"))
async def on_category(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.message or not callback.data:
        return
    code = callback.data.split(":", 1)[1]
    if code not in CATEGORIES:
        return
    await state.update_data(category=code)
    await state.set_state(CreateStates.waiting_language)
    if code == "rx":
        await callback.message.answer(texts.CREATE_RX_WARNING)
    await callback.message.answer(
        texts.CREATE_ASK_LANGUAGE, reply_markup=keyboards.languages()
    )


# --- Шаг 4: язык и генерация ---------------------------------------------


@router.callback_query(CreateStates.waiting_language, F.data.startswith("lang:"))
async def on_language(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    claude: ClaudeService,
    limiter: RateLimiter,
) -> None:
    await callback.answer()
    message = callback.message
    if not message or not callback.data or not callback.from_user:
        return
    code = callback.data.split(":", 1)[1]
    if code not in LANGUAGES:
        return

    data = await state.get_data()
    description = (data.get("description") or "").strip()
    category = data.get("category") or "unknown"
    file_id = data.get("photo_file_id")
    media_type = data.get("photo_media_type") or "image/jpeg"
    if not description:
        await state.clear()
        await message.answer(texts.ERR_UNKNOWN, reply_markup=keyboards.main_menu())
        return

    user_id = callback.from_user.id
    rejection = limiter.try_acquire(user_id)
    if rejection:
        await message.answer(
            texts.BUSY
            if rejection.busy
            else texts.RATE_LIMITED.format(
                limit=limiter.per_hour, minutes=rejection.minutes
            )
        )
        return

    try:
        images = []
        if file_id:
            image = await download_image(bot, file_id, media_type)
            if image:
                images.append(image)

        logger.info(
            "Создание поста: user=%s категория=%s язык=%s фото=%s",
            user_id,
            category,
            code,
            bool(images),
        )
        async with Progress(message, CREATE_STAGES):
            answer = await claude.create_post(description, category, code, images)

        await state.clear()
        await send_create_result(message, answer, file_id if images else None)
    except ClaudeError as error:
        await message.answer(error.user_message)
    except Exception:
        logger.exception("Непредвиденная ошибка при создании поста")
        await message.answer(texts.ERR_UNKNOWN)
    finally:
        limiter.release(user_id)


async def send_create_result(
    message: Message, answer: str, photo_file_id: str | None
) -> None:
    """Готовый пост — подписью к фото; разбор и примечания — отдельным сообщением."""
    sections = parse_sections(answer)
    disclaimer = pop_disclaimer(sections)

    post_sections = [s for s in sections if s.title_matches(*POST_TITLES)]
    info_sections = [s for s in sections if not s.title_matches(*POST_TITLES)]

    if post_sections:
        await _send_main_post(message, post_sections[0], photo_file_id)
        for extra in post_sections[1:]:
            if extra.title:
                await message.answer(f"👇 <b>{extra.title}</b>")
            await send_plain(message, extra.body)
    elif photo_file_id:
        await message.answer_photo(photo_file_id)

    info_markdown = render_sections(info_sections)
    parts = [info_markdown] if info_markdown.strip() else []
    parts.append(f"*{disclaimer or texts.DISCLAIMER}*")
    await send_html(
        message, "\n\n".join(parts), reply_markup=keyboards.after_create()
    )


async def _send_main_post(
    message: Message, section: Section, photo_file_id: str | None
) -> None:
    post_text = to_plain(section.body)
    if photo_file_id and len(post_text) <= TELEGRAM_CAPTION_LIMIT:
        await message.answer_photo(
            photo_file_id, caption=post_text, parse_mode=None
        )
        await message.answer(texts.CREATE_READY_CAPTION_NOTE)
        return

    if photo_file_id:
        await message.answer_photo(photo_file_id)
    for part in plain_messages(section.body):
        await message.answer(part, parse_mode=None)
    await message.answer(texts.CREATE_READY_TEXT_NOTE)
