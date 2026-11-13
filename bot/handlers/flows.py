"""Запуск режимов — общий код для кнопок меню и inline-кнопок."""

from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import keyboards, texts
from bot.states import CreateStates, ScanStates


async def start_scan(target: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ScanStates.waiting_for_post)
    await target.answer(texts.SCAN_PROMPT, reply_markup=keyboards.cancel_only())


async def start_create(target: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(CreateStates.waiting_photo)
    await target.answer(texts.CREATE_ASK_PHOTO, reply_markup=keyboards.ask_photo())
