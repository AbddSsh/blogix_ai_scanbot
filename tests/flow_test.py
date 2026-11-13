"""Офлайн-прогон сценариев бота: апдейты идут через настоящий диспетчер,
Telegram и Claude подменены. Запуск: python -m tests.flow_test
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os

os.environ.setdefault("BOT_TOKEN", "1:test")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("COLLECT_DELAY", "0.2")

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import (
    CallbackQuery,
    Message,
    MessageEntity,
    PhotoSize,
    Update,
    User,
    Voice,
)

from bot.config import Config
from bot.handlers import scan
from bot.main import build_dispatcher
from bot.services.limits import RateLimiter
from tests.fake_telegram import CHAT, USER, FakeSession

SCAN_ANSWER = """**Вердикт:** 🟡 Можно после правок (БАД)

**Правки**
❌ «снижает давление» → убрать лечебное обещание (ст. 35)
❌ Нет пометки «Реклама» → добавить первой строкой (ст. 18)

**Вариант 1**
Реклама / Reklama
Комплекс витаминов [Название].
Не является лекарственным средством. Ushbu mahsulot dori vositasi hisoblanmaydi.

**Вариант 2**
Reklama
Другой заход к тому же продукту.

**Нужно от клиента**
Свидетельство о госрегистрации БАД (ст. 12–13).

*Справочное заключение, не заменяет юридической консультации.*
"""

CREATE_ANSWER = """**Пост**
Реклама / Reklama
Осенью иммунитету нужна поддержка 🍂 [Название] — витаминный комплекс для взрослых.
Не является лекарственным средством. Ushbu mahsulot dori vositasi hisoblanmaydi.

**Картинка**
🖼 Уберите надпись «№1» с упаковки (ст. 16).

**Что учтено**
Пометка «Реклама» → (ст. 18)
Предупреждение «не лекарство» → (ст. 35)

**Нужно от клиента**
Свидетельство о госрегистрации (ст. 12–13).

*Справочное заключение, не заменяет юридической консультации.*
"""


class StubClaude:
    def __init__(self) -> None:
        self.scan_calls: list[tuple[str, int]] = []
        self.create_calls: list[tuple[str, str, str, int]] = []

    async def scan_post(self, text, images):
        self.scan_calls.append((text, len(images)))
        return SCAN_ANSWER

    async def create_post(self, description, category_code, language_code, images):
        self.create_calls.append(
            (description, category_code, language_code, len(images))
        )
        return CREATE_ANSWER

    async def close(self):
        return None


_update_id = 0
_message_id = 1000


def _next_ids() -> tuple[int, int]:
    global _update_id, _message_id
    _update_id += 1
    _message_id += 1
    return _update_id, _message_id


def message_update(text: str | None = None, *, photo: bool = False, command=False):
    update_id, message_id = _next_ids()
    entities = None
    if command and text:
        entities = [
            MessageEntity(type="bot_command", offset=0, length=len(text.split()[0]))
        ]
    message = Message(
        message_id=message_id,
        date=dt.datetime.now(dt.timezone.utc),
        chat=CHAT,
        from_user=USER,
        text=None if photo else text,
        caption=text if photo else None,
        entities=entities,
        photo=[
            PhotoSize(
                file_id="photo-1",
                file_unique_id="pu1",
                width=800,
                height=600,
                file_size=40000,
            )
        ]
        if photo
        else None,
    )
    return Update(update_id=update_id, message=message)


def voice_update():
    update_id, message_id = _next_ids()
    message = Message(
        message_id=message_id,
        date=dt.datetime.now(dt.timezone.utc),
        chat=CHAT,
        from_user=USER,
        voice=Voice(file_id="v1", file_unique_id="vu1", duration=5),
    )
    return Update(update_id=update_id, message=message)


def callback_update(data: str):
    update_id, message_id = _next_ids()
    message = Message(
        message_id=message_id,
        date=dt.datetime.now(dt.timezone.utc),
        chat=CHAT,
        from_user=User(id=1, is_bot=True, first_name="TestBot"),
        text="кнопка",
    )
    return Update(
        update_id=update_id,
        callback_query=CallbackQuery(
            id=str(update_id),
            from_user=USER,
            chat_instance="ci",
            message=message,
            data=data,
        ),
    )


def check(condition: bool, label: str) -> None:
    print(("  ✅ " if condition else "  ❌ ") + label)
    if not condition:
        raise AssertionError(label)


def visible(session: FakeSession) -> list[str]:
    """Тексты без служебного индикатора прогресса."""
    return [t for t in session.texts() if "▰" not in t]


async def main() -> None:
    config = Config.load()
    session = FakeSession()
    bot = Bot(
        token=config.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    claude = StubClaude()
    limiter = RateLimiter(config.rate_limit_per_hour)
    dispatcher, collector = build_dispatcher(config, claude, limiter)

    async def feed(update: Update) -> None:
        await dispatcher.feed_update(bot, update)

    print("\n[1] /start")
    await feed(message_update("/start", command=True))
    out = visible(session)
    check(any("Проверить пост" in t for t in out), "показано меню с двумя кнопками")
    check(
        any(d.get("reply_markup") for _, d in session.calls), "клавиатура прикреплена"
    )

    print("\n[2] Кнопка «Проверить пост»")
    session.reset()
    await feed(message_update("🔍 Проверить пост"))
    check(
        any("Отправьте готовый пост для проверки" in t for t in visible(session)),
        "выдан текст-приглашение из задания",
    )

    print("\n[3] Пост текстом + картинкой двумя сообщениями")
    session.reset()
    await feed(message_update("Этот комплекс снижает давление, мне помогло"))
    await feed(message_update("Фото упаковки", photo=True))
    await asyncio.sleep(config.collect_delay + 0.6)
    out = visible(session)
    check(len(claude.scan_calls) == 1, "в API ушёл ровно один запрос на оба сообщения")
    check(claude.scan_calls[0][1] == 1, "картинка дошла до API (1 изображение)")
    check(
        "снижает давление" in claude.scan_calls[0][0]
        and "Фото упаковки" in claude.scan_calls[0][0],
        "тексты обоих сообщений склеены",
    )
    check(any("<b>Вердикт:</b>" in t for t in out), "вердикт пришёл как HTML")
    check(any("Вариант 1" in t for t in out), "заголовок варианта 1")
    check(
        any(t.startswith("Реклама / Reklama") for t in out),
        "вариант 1 отправлен отдельным сообщением без разметки",
    )
    check(
        any(t.startswith("Reklama\nДругой заход") for t in out),
        "вариант 2 отправлен отдельным сообщением",
    )
    check(
        any("госрегистрации" in t and "<i>" in t for t in out),
        "хвост с «Нужно от клиента» и дисклеймером курсивом",
    )
    check(
        any("▰" in t for t in session.texts()), "индикатор прогресса показывался"
    )
    check("DeleteMessage" in session.method_names(), "индикатор удалён после ответа")

    print("\n[4] Полный диалог «Создать пост»")
    session.reset()
    await feed(callback_update("go:create"))
    check(
        any("Пришлите фото препарата" in t for t in visible(session)), "шаг 1: фото"
    )
    session.reset()
    await feed(message_update(None, photo=True))
    check(any("для чего этот препарат" in t for t in visible(session)), "шаг 2: описание")
    session.reset()
    await feed(message_update("Витамины для иммунитета, взрослым, продаются в аптеках"))
    check(any("Какая это категория" in t for t in visible(session)), "шаг 3: категория")
    session.reset()
    await feed(callback_update("cat:bad"))
    check(any("На каком языке" in t for t in visible(session)), "шаг 4: язык")
    session.reset()
    await feed(callback_update("lang:ru"))
    out = visible(session)
    check(len(claude.create_calls) == 1, "запрос на создание ушёл один раз")
    description, category, language, image_count = claude.create_calls[0]
    check(category == "bad" and language == "ru", "категория и язык переданы верно")
    check(image_count == 1, "фото препарата дошло до API")
    check(
        any(t.startswith("[ФОТО] Реклама / Reklama") for t in out),
        "готовый пост пришёл подписью к фото",
    )
    check(
        any("Уберите надпись" in t for t in out), "замечания по картинке отдельно"
    )

    print("\n[5] Рецептурный препарат — предупреждение до генерации")
    session.reset()
    await feed(callback_update("go:create"))
    await feed(callback_update("create:nophoto"))
    await feed(message_update("Препарат от давления, отпускается по рецепту"))
    session.reset()
    await feed(callback_update("cat:rx"))
    check(
        any("ст. 34" in t for t in visible(session)),
        "бот предупреждает о запрете рекламы Rx",
    )

    print("\n[6] Лимит запросов")
    # Роутеры aiogram — синглтоны, второй диспетчер собрать нельзя,
    # поэтому подменяем коллектор с «узким» лимитером в том же диспетчере.
    tight = RateLimiter(1)
    tight_collector = scan.build_collector(config, claude, tight)
    dispatcher["collector"] = tight_collector

    session.reset()
    await feed(message_update("🔍 Проверить пост"))
    await feed(message_update("Первый пост про БАД"))
    await asyncio.sleep(config.collect_delay + 0.6)
    check(
        not any("лимит запросов" in t for t in visible(session)),
        "первый запрос в пределах лимита проходит",
    )

    session.reset()
    await feed(message_update("🔍 Проверить пост"))
    await feed(message_update("Второй пост про БАД"))
    await asyncio.sleep(config.collect_delay + 0.6)
    check(
        any("лимит запросов" in t for t in visible(session)),
        "второй запрос отклонён по лимиту",
    )
    dispatcher["collector"] = collector
    await tight_collector.shutdown()

    print("\n[7] Голосовое сообщение вместо поста")
    session.reset()
    await feed(message_update("🔍 Проверить пост"))
    await feed(voice_update())
    check(
        any("текстом и изображениями" in t for t in visible(session)),
        "бот объясняет, что умеет работать с текстом и картинками",
    )

    print("\n[8] /cancel")
    session.reset()
    await feed(message_update("/cancel", command=True))
    check(any("Выберите действие" in t for t in visible(session)), "/cancel отвечает")

    await collector.shutdown()
    print("\nВСЕ СЦЕНАРИИ ПРОЙДЕНЫ ✅\n")


if __name__ == "__main__":
    asyncio.run(main())
