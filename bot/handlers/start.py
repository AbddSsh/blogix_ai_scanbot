"""Команды, меню и навигация между режимами."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import keyboards, texts
from bot.handlers.flows import start_create, start_scan
from bot.services.collector import MessageCollector

router = Router(name="start")


@router.message(CommandStart())
async def on_start(
    message: Message, state: FSMContext, collector: MessageCollector
) -> None:
    collector.cancel(message.chat.id)
    await state.clear()
    await message.answer(texts.START, reply_markup=keyboards.main_menu())


@router.message(Command("help"))
async def on_help(message: Message) -> None:
    await message.answer(texts.HELP, reply_markup=keyboards.main_menu())


@router.message(Command("cancel"))
async def on_cancel(
    message: Message, state: FSMContext, collector: MessageCollector
) -> None:
    collector.cancel(message.chat.id)
    had_state = await state.get_state() is not None
    await state.clear()
    await message.answer(
        texts.CANCELLED if had_state else texts.NOTHING_TO_CANCEL,
        reply_markup=keyboards.main_menu(),
    )


@router.callback_query(F.data == "cancel")
async def on_cancel_button(
    callback: CallbackQuery, state: FSMContext, collector: MessageCollector
) -> None:
    await callback.answer()
    if callback.message:
        collector.cancel(callback.message.chat.id)
        await state.clear()
        await callback.message.answer(
            texts.CANCELLED, reply_markup=keyboards.main_menu()
        )


@router.message(F.text == texts.BTN_SCAN)
async def on_scan_button(
    message: Message, state: FSMContext, collector: MessageCollector
) -> None:
    collector.cancel(message.chat.id)
    await start_scan(message, state)


@router.message(F.text == texts.BTN_CREATE)
async def on_create_button(
    message: Message, state: FSMContext, collector: MessageCollector
) -> None:
    collector.cancel(message.chat.id)
    await start_create(message, state)


@router.callback_query(F.data == "go:scan")
async def on_go_scan(
    callback: CallbackQuery, state: FSMContext, collector: MessageCollector
) -> None:
    await callback.answer()
    if callback.message:
        collector.cancel(callback.message.chat.id)
        await start_scan(callback.message, state)


@router.callback_query(F.data == "go:create")
async def on_go_create(
    callback: CallbackQuery, state: FSMContext, collector: MessageCollector
) -> None:
    await callback.answer()
    if callback.message:
        collector.cancel(callback.message.chat.id)
        await start_create(callback.message, state)
