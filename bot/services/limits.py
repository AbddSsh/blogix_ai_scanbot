"""Лимит обращений к ИИ: защита открытого бота от перерасхода и дублей."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass

HOUR = 3600.0


@dataclass(frozen=True)
class Rejection:
    """Причина отказа: либо запрос уже выполняется, либо исчерпан лимит."""

    busy: bool
    minutes: int = 0


class RateLimiter:
    """Счётчик обращений к API, по пользователю. Хранится в памяти процесса."""

    def __init__(self, per_hour: int) -> None:
        self._per_hour = max(1, per_hour)
        self._calls: dict[int, deque[float]] = defaultdict(deque)
        self._in_flight: set[int] = set()

    @property
    def per_hour(self) -> int:
        return self._per_hour

    def try_acquire(self, user_id: int) -> Rejection | None:
        if user_id in self._in_flight:
            return Rejection(busy=True)

        now = time.monotonic()
        calls = self._calls[user_id]
        while calls and now - calls[0] > HOUR:
            calls.popleft()

        if len(calls) >= self._per_hour:
            wait_seconds = HOUR - (now - calls[0])
            return Rejection(busy=False, minutes=max(1, int(wait_seconds // 60) + 1))

        calls.append(now)
        self._in_flight.add(user_id)
        return None

    def release(self, user_id: int) -> None:
        self._in_flight.discard(user_id)
