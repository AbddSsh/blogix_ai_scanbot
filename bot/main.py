"""Точка входа: сборка зависимостей и запуск polling."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.config import Config
from bot.handlers import create, scan, start
from bot.services.claude import ClaudeService
from bot.services.collector import MessageCollector
from bot.services.limits import RateLimiter

logger = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="help", description="Как пользоваться ботом"),
    BotCommand(command="cancel", description="Прервать текущий диалог"),
]


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def build_dispatcher(
    config: Config, claude: ClaudeService, limiter: RateLimiter
) -> tuple[Dispatcher, MessageCollector]:
    """Собирает диспетчер со всеми зависимостями. Используется и в тестах."""
    collector = scan.build_collector(config, claude, limiter)

    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher["config"] = config
    dispatcher["claude"] = claude
    dispatcher["limiter"] = limiter
    dispatcher["collector"] = collector

    # Порядок важен: меню и команды — первыми, диалог создания — раньше,
    # чем «ловушка» режима проверки.
    dispatcher.include_router(start.router)
    dispatcher.include_router(create.router)
    dispatcher.include_router(scan.router)
    return dispatcher, collector


async def run() -> None:
    config = Config.load()
    setup_logging(config.log_level)

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    claude = ClaudeService(config)
    limiter = RateLimiter(config.rate_limit_per_hour)
    dispatcher, collector = build_dispatcher(config, claude, limiter)

    try:
        await bot.set_my_commands(COMMANDS)
        await bot.delete_webhook(drop_pending_updates=True)
        me = await bot.get_me()
        logger.info("Запуск бота @%s, модель %s", me.username, config.model)
        await dispatcher.start_polling(
            bot, allowed_updates=dispatcher.resolve_used_update_types()
        )
    finally:
        await collector.shutdown()
        await claude.close()
        await bot.session.close()


def main() -> None:
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        logging.getLogger(__name__).info("Бот остановлен")


if __name__ == "__main__":
    main()
