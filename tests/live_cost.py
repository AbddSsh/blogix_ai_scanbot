"""Замер расхода токенов на реальном запросе. python -m tests.live_cost"""

import asyncio
import anthropic

from bot.config import PROMPTS_DIR, Config

POST = (
    "Друзья, хочу рассказать про комплекс ВитаФорте! 💊\n"
    "Он снижает давление, помогает при диабете и защищает печень. "
    "Мне помог буквально за неделю — давление как у космонавта.\n"
    "Одобрено Минздравом, гарантия результата без побочных эффектов!\n"
    "Заказывайте по ссылке, первым 10 покупателям — подарок 🎁"
)

PRICE_IN = 4.00 / 1_000_000       # claude-opus-5-5
PRICE_CACHE_WRITE = 5.00 / 1_000_000
PRICE_CACHE_READ = 0.40 / 1_000_000
PRICE_OUT = 20.00 / 1_000_000


async def main() -> None:
    config = Config.load()
    client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
    legal = (PROMPTS_DIR / "legal_base.md").read_text(encoding="utf-8").strip()
    scan = (PROMPTS_DIR / "scan_task.md").read_text(encoding="utf-8").strip()
    create = (PROMPTS_DIR / "create_task.md").read_text(encoding="utf-8").strip()

    # 1. Бесплатный подсчёт входа
    for name, task in (("проверка", scan), ("создание", create)):
        counted = await client.messages.count_tokens(
            model=config.model,
            system=[
                {"type": "text", "text": legal},
                {"type": "text", "text": task},
            ],
            messages=[{"role": "user", "content": "Проверь этот пост:\n\n" + POST}],
        )
        print(f"вход ({name}): {counted.input_tokens} токенов")

    # 2. Реальный запрос — смотрим выход и кеш
    async with client.messages.stream(
        model=config.model,
        max_tokens=config.max_tokens,
        output_config={"effort": config.effort},
        system=[
            {"type": "text", "text": legal, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": scan, "cache_control": {"type": "ephemeral"}},
        ],
        messages=[{"role": "user", "content": "Проверь этот пост:\n\n" + POST}],
    ) as stream:
        response = await stream.get_final_message()

    u = response.usage
    cw = getattr(u, "cache_creation_input_tokens", 0) or 0
    cr = getattr(u, "cache_read_input_tokens", 0) or 0
    cost = u.input_tokens * PRICE_IN + cw * PRICE_CACHE_WRITE + cr * PRICE_CACHE_READ + u.output_tokens * PRICE_OUT

    print(f"\nвход некешированный: {u.input_tokens}")
    print(f"запись в кеш:        {cw}")
    print(f"чтение из кеша:      {cr}")
    print(f"выход (с мышлением): {u.output_tokens}")
    print(f"стоимость запроса:   ${cost:.4f}")
    print(f"запросов на $10:     {int(10 / cost) if cost else '-'}")
    print(f"\nдлина ответа: {sum(len(b.text) for b in response.content if b.type == 'text')} символов")
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
