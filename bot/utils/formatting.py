"""Разбор ответа модели и подготовка его к отправке в Telegram.

Модель отвечает ограниченным подмножеством Markdown (см. legal_base.md):
`**жирный**`, `*курсив*`, строки-цитаты `> `. Здесь это подмножество
превращается в Telegram HTML, а ответ режется на блоки по заголовкам.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

TELEGRAM_TEXT_LIMIT = 4096
TELEGRAM_CAPTION_LIMIT = 1024

# Строка, целиком состоящая из жирного заголовка: «**Вариант 1**», «**Правки**»,
# «**Нужно от клиента**». Двоеточие после заголовка допускается.
_SECTION_RE = re.compile(r"^[ \t]*\*\*(?P<title>[^*\n]+?)\*\*[ \t]*:?[ \t]*$")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
# Строка-дисклеймер целиком курсивом.
_DISCLAIMER_RE = re.compile(r"^[ \t]*\*(?P<body>[^*\n]+)\*[ \t]*$")


@dataclass
class Section:
    """Блок ответа: заголовок (без звёздочек) и его содержимое."""

    title: str | None
    body: str

    def title_matches(self, *prefixes: str) -> bool:
        if not self.title:
            return False
        low = self.title.casefold()
        return any(low.startswith(p.casefold()) for p in prefixes)


def parse_sections(text: str) -> list[Section]:
    """Режет ответ модели на блоки по строкам-заголовкам, сохраняя их порядок."""
    sections: list[Section] = []
    current_title: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip("\n")
        if current_title is not None or body.strip():
            sections.append(Section(title=current_title, body=body))
        buffer.clear()

    for line in text.split("\n"):
        match = _SECTION_RE.match(line)
        if match:
            flush()
            current_title = match.group("title").strip()
        else:
            buffer.append(line)
    flush()
    return sections


def pop_disclaimer(sections: list[Section]) -> str | None:
    """Вынимает финальную строку курсивом из последнего блока."""
    for section in reversed(sections):
        lines = section.body.rstrip().split("\n")
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            continue
        match = _DISCLAIMER_RE.match(lines[-1])
        if match:
            section.body = "\n".join(lines[:-1]).rstrip()
            return match.group("body").strip()
        return None
    return None


def render_sections(sections: list[Section]) -> str:
    """Собирает блоки обратно в Markdown (заголовки — жирным)."""
    parts: list[str] = []
    for section in sections:
        chunk = f"**{section.title}**\n{section.body}" if section.title else section.body
        chunk = chunk.strip("\n")
        if chunk:
            parts.append(chunk)
    return "\n\n".join(parts)


def _inline_html(line: str) -> str:
    escaped = html.escape(line, quote=False)
    escaped = _BOLD_RE.sub(r"<b>\1</b>", escaped)
    return _ITALIC_RE.sub(r"<i>\1</i>", escaped)


def md_to_html(text: str) -> str:
    """Переводит разрешённое подмножество Markdown в Telegram HTML."""
    out: list[str] = []
    quote: list[str] = []

    def flush_quote() -> None:
        if quote:
            out.append("<blockquote>" + "\n".join(quote) + "</blockquote>")
            quote.clear()

    for line in text.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith(">"):
            quote.append(_inline_html(stripped[1:].lstrip()))
        else:
            flush_quote()
            out.append(_inline_html(line))
    flush_quote()
    return "\n".join(out).strip()


def to_plain(text: str) -> str:
    """Убирает разметку — для готовых текстов постов, которые пользователь копирует.

    Такие сообщения отправляются с parse_mode=None, поэтому экранировать нечего.
    """
    lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith(">"):
            line = stripped[1:].lstrip()
        line = line.replace("**", "")
        line = _ITALIC_RE.sub(r"\1", line)
        lines.append(line.rstrip())
    return "\n".join(lines).strip()


def split_markdown(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> list[str]:
    """Режет текст на части под лимит Telegram — по абзацам, затем по строкам.

    Разрез проходит только по границам абзацев и строк, поэтому разметка
    (в т.ч. группы строк-цитат) не рвётся посередине.
    """
    text = text.strip()
    if not text:
        return []
    # Запас на расширение разметки в HTML-теги.
    budget = max(512, int(limit * 0.75))
    if len(text) <= budget:
        return [text]

    chunks: list[str] = []
    buffer = ""

    def push(piece: str, separator: str) -> None:
        nonlocal buffer
        if not piece:
            return
        candidate = f"{buffer}{separator}{piece}" if buffer else piece
        if len(candidate) <= budget:
            buffer = candidate
            return
        if buffer:
            chunks.append(buffer)
            buffer = ""
        if len(piece) <= budget:
            buffer = piece
            return
        if separator == "\n\n":
            for line in piece.split("\n"):
                push(line, "\n")
            return
        for start in range(0, len(piece), budget):
            hard = piece[start : start + budget]
            if len(hard) == budget:
                chunks.append(hard)
            else:
                buffer = hard

    for paragraph in text.split("\n\n"):
        push(paragraph.strip("\n"), "\n\n")
    if buffer:
        chunks.append(buffer)
    return [chunk for chunk in (c.strip() for c in chunks) if chunk]


def html_messages(markdown: str, limit: int = TELEGRAM_TEXT_LIMIT) -> list[str]:
    """Готовые HTML-сообщения из Markdown-текста."""
    return [md_to_html(chunk) for chunk in split_markdown(markdown, limit)]


def plain_messages(markdown: str, limit: int = TELEGRAM_TEXT_LIMIT) -> list[str]:
    """Готовые сообщения без разметки (для текстов, которые копируют)."""
    plain = to_plain(markdown)
    return [chunk for chunk in split_markdown(plain, limit)]
