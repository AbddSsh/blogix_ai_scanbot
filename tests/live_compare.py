"""Сравнение режимов по цене и качеству. python -m tests.live_compare"""

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

PRICES = {  # (вход, запись в кеш, чтение кеша, выход) за 1М токенов
    "claude-opus-5-5": (4.0, 5.0, 0.4, 20.0),
    "claude-sonnet-5-5": (2.0, 2.5, 0.2, 10.0),
}

# Нормы, которые обязаны быть найдены в этом посте
EXPECTED = {
    "ст. 35 (БАД/лечебные обещания)": ["35"],
    "ст. 18 (пометка «Реклама»)": ["18"],
    "ст. 16 (одобрено государством)": ["16"],
    "запрет акций/подарков": ["подар", "акци", "21"],
    "отзыв «мне помогло»": ["мне помог", "отзыв", "выздоров"],
}


async def run(client, model, effort, legal, task):
    async with client.messages.stream(
        model=model,
        max_tokens=8000,
        output_config={"effort": effort},
        system=[
            {"type": "text", "text": legal, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": task, "cache_control": {"type": "ephemeral"}},
        ],
        messages=[{"role": "user", "content": "Проверь этот пост:\n\n" + POST}],
    ) as stream:
        response = await stream.get_final_message()

    u = response.usage
    pin, pcw, pcr, pout = PRICES[model]
    cw = getattr(u, "cache_creation_input_tokens", 0) or 0
    cr = getattr(u, "cache_read_input_tokens", 0) or 0
    cost = (
        u.input_tokens * pin + cw * pcw + cr * pcr + u.output_tokens * pout
    ) / 1_000_000
    text = "\n".join(b.text for b in response.content if b.type == "text")
    return cost, u.output_tokens, text


async def main() -> None:
    config = Config.load()
    client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
    legal = (PROMPTS_DIR / "legal_base.md").read_text(encoding="utf-8").strip()
    task = (PROMPTS_DIR / "scan_task.md").read_text(encoding="utf-8").strip()

    for model, effort in (
        ("claude-opus-5-5", "medium"),
        ("claude-sonnet-5-5", "high"),
    ):
        cost, out_tokens, text = await run(client, model, effort, legal, task)
        low = text.lower()
        found = [
            name
            for name, keys in EXPECTED.items()
            if any(k.lower() in low for k in keys)
        ]
        verdict = next(
            (ln for ln in text.split("\n") if "ердикт" in ln), "(вердикт не найден)"
        )
        print(f"\n=== {model} / effort={effort} ===")
        print(f"выход: {out_tokens} токенов | цена: ${cost:.4f} | на $10: {int(10/cost)}")
        print(f"{verdict.strip()}")
        print(f"найдено норм: {len(found)}/{len(EXPECTED)} -> {', '.join(found)}")
        print(f"длина ответа: {len(text)} символов")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
