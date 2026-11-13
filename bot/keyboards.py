"""Клавиатуры и справочники категорий/языков."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot import texts

# Категории продукта: код -> (подпись на кнопке, формулировка для промпта)
CATEGORIES: dict[str, tuple[str, str]] = {
    "bad": ("БАД / пищевая добавка", "БАД (пищевая добавка)"),
    "otc": ("Лекарство без рецепта (OTC)", "безрецептурное лекарственное средство (OTC)"),
    "rx": ("Лекарство по рецепту (Rx)", "рецептурное лекарственное средство (Rx)"),
    "device": ("Медизделие", "медицинское изделие"),
    "cosmetics": ("Косметика", "косметическое средство"),
    "service": ("Медуслуга / клиника", "медицинская услуга"),
    "folk": ("Народная медицина", "средство народной медицины"),
    "unknown": ("Не знаю", "категория не указана — определи сам по фото и описанию"),
}

# Языки: код -> (подпись на кнопке, формулировка для промпта)
LANGUAGES: dict[str, tuple[str, str]] = {
    "ru": (
        "Русский",
        "русский (основной текст по-русски, обязательные пометки и предупреждения "
        "дополнительно на узбекском)",
    ),
    "uz": ("Узбекский", "узбекский (латиница), весь пост на узбекском"),
    "both": ("Оба языка", "обе полные версии: сначала русская, затем узбекская"),
}


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_SCAN)],
            [KeyboardButton(text=texts.BTN_CREATE)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие или пришлите пост",
    )


def cancel_only() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✖️ Отмена", callback_data="cancel")]]
    )


def ask_photo() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Без фото", callback_data="create:nophoto")],
            [InlineKeyboardButton(text="✖️ Отмена", callback_data="cancel")],
        ]
    )


def categories() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"cat:{code}")]
        for code, (label, _) in CATEGORIES.items()
    ]
    rows.append([InlineKeyboardButton(text="✖️ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def languages() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"lang:{code}")]
        for code, (label, _) in LANGUAGES.items()
    ]
    rows.append([InlineKeyboardButton(text="✖️ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def after_scan() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Проверить ещё один", callback_data="go:scan")],
            [InlineKeyboardButton(text="✍️ Создать пост", callback_data="go:create")],
        ]
    )


def after_create() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Создать ещё один", callback_data="go:create")],
            [InlineKeyboardButton(text="🔍 Проверить пост", callback_data="go:scan")],
        ]
    )
