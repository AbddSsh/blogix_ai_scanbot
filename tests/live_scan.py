"""Живой вызов Claude на реальном примере. Запуск: python -m tests.live_scan"""

import asyncio

from bot.config import Config
from bot.services.claude import ClaudeService

POST = (
    "Друзья, хочу рассказать про комплекс ВитаФорте! 💊\n"
    "Он снижает давление, помогает при диабете и защищает печень. "
    "Мне помог буквально за неделю — давление как у космонавта.\n"
    "Одобрено Минздравом, гарантия результата без побочных эффектов!\n"
    "Заказывайте по ссылке, первым 10 покупателям — подарок 🎁"
)


async def main() -> None:
    config = Config.load()
    claude = ClaudeService(config)
    try:
        answer = await claude.scan_post(POST, [])
    finally:
        await claude.close()
    print("=" * 70)
    print(answer)
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
