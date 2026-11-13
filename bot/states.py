"""Состояния FSM."""

from aiogram.fsm.state import State, StatesGroup


class ScanStates(StatesGroup):
    waiting_for_post = State()


class CreateStates(StatesGroup):
    waiting_photo = State()
    waiting_description = State()
    waiting_category = State()
    waiting_language = State()
