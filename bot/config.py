"""Конфигурация бота: читается из переменных окружения (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = BASE_DIR / "prompts"


def _load_dotenv(path: Path) -> None:
    """Минимальный загрузчик .env без внешних зависимостей.

    Уже выставленные переменные окружения не перезаписываются — так на сервере
    (Docker, systemd) окружение всегда важнее файла.
    """
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    bot_token: str
    anthropic_api_key: str
    model: str
    max_tokens: int
    effort: str
    # Лимиты
    rate_limit_per_hour: int
    max_concurrent_requests: int
    # Поведение
    collect_delay: float
    max_images: int
    log_level: str

    @classmethod
    def load(cls) -> "Config":
        _load_dotenv(BASE_DIR.parent / ".env")

        bot_token = os.environ.get("BOT_TOKEN", "").strip()
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()

        missing = [
            name
            for name, value in (("BOT_TOKEN", bot_token), ("ANTHROPIC_API_KEY", api_key))
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Не заданы переменные окружения: "
                + ", ".join(missing)
                + ". Скопируйте .env.example в .env и заполните значения."
            )

        return cls(
            bot_token=bot_token,
            anthropic_api_key=api_key,
            model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5").strip(),
            max_tokens=_int_env("MAX_TOKENS", 8000),
            effort=os.environ.get("EFFORT", "high").strip(),
            rate_limit_per_hour=_int_env("RATE_LIMIT_PER_HOUR", 10),
            max_concurrent_requests=_int_env("MAX_CONCURRENT_REQUESTS", 5),
            collect_delay=float(os.environ.get("COLLECT_DELAY", "2.5")),
            max_images=_int_env("MAX_IMAGES", 4),
            log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper(),
        )
