from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .models import Vacancy
from .professions import ProfessionCategory
from .text_utils import normalize_description_text

APPLY_BUTTON_TEXT = "Получить работу"
TELEGRAM_SAFE_LIMIT = 3600

# Вставляем переносы перед заголовками, даже если в HTML они в одном абзаце
INLINE_SECTION_MARKERS = (
    "чем предстоит заниматься",
    "что предстоит делать",
    "что предстоит заниматься",
    "ваши задачи",
    "обязанности",
    "функционал",
    "наши ожидания",
    "мы ожидаем",
    "требования к кандидату",
    "требования",
    "квалификация",
    "почему с нами",
    "мы предлагаем",
    "вам предлагаем",
    "условия работы",
    "условия",
    "о компании",
    "о проекте",
    "будет плюсом",
    "приветствуется",
    "график работы",
    "описание вакансии",
)

HEADER_STOPWORDS = frozenset(
    {
        "вам",
        "контакты",
        "контакт",
        "email",
        "e-mail",
        "телефон",
        "тел",
        "адрес",
    }
)


@dataclass(frozen=True)
class FormattedPost:
    messages: List[str]
    apply_url: str
    apply_button_text: str = APPLY_BUTTON_TEXT


def format_vacancy_post(
    vacancy: Vacancy,
    category: Optional[ProfessionCategory] = None,
    **_,
) -> Optional[FormattedPost]:
    description = _strip_recruiter_footer(
        normalize_description_text(vacancy.description or "")
    )
    if not description:
        return None

    header = _build_header(vacancy)
    body_sections = _structure_description(description)
    body = _build_body(body_sections)
    body = _fit_body_to_limit(body, TELEGRAM_SAFE_LIMIT - len(header) - 80)

    full_text = f"{header}\n\n{body}"
    return FormattedPost(messages=[full_text], apply_url=vacancy.url)


def format_vacancy_messages(
    vacancy: Vacancy,
    category: Optional[ProfessionCategory] = None,
    **kwargs,
) -> List[str]:
    post = format_vacancy_post(vacancy, category, **kwargs)
    return post.messages if post else []


def _build_header(vacancy: Vacancy) -> str:
    lines = [f"<b>{_escape(vacancy.title)}</b>"]

    meta: List[str] = []
    if vacancy.company:
        meta.append(_escape(vacancy.company))
    if vacancy.salary:
        meta.append(_escape(vacancy.salary))
    if vacancy.location:
        meta.append(_escape(_short_location(vacancy.location)))

    if meta:
        lines.append("<i>" + " · ".join(meta) + "</i>")

    return "\n".join(lines)


def _build_body(sections: List[Tuple[str, str]]) -> str:
    return "\n\n".join(
        f"<b>{_escape(title)}</b>\n{_format_block(text)}"
        for title, text in sections
        if text.strip()
    )


def _fit_body_to_limit(body: str, max_len: int) -> str:
    if len(body) <= max_len:
        return body

    trimmed = body[:max_len]
    cut = trimmed.rfind("\n\n")
    if cut > max_len // 2:
        trimmed = trimmed[:cut]

    return trimmed.rstrip() + "\n\n<i>Подробности — на сайте по кнопке ниже.</i>"


def _short_location(location: str) -> str:
    text = location.strip()
    if len(text) <= 56:
        return text
    return text[:53].rstrip() + "…"


def _strip_recruiter_footer(text: str) -> str:
    cut_markers = (
        "вакансия бесплатная",
        "лицензия мвд",
        "лицензия министерства",
        "на право осуществления деятельности",
        "трудоустройством за пределами рб",
        "ссылка на вакансию в банке",
        "gsz.gov.by",
        "планируемой к созданию",
    )
    lower = text.lower()
    earliest = len(text)
    for marker in cut_markers:
        pos = lower.find(marker)
        if pos != -1 and pos < earliest:
            earliest = pos
    if earliest < len(text):
        text = text[:earliest].rstrip()
    return text


def _inject_section_breaks(text: str) -> str:
    """Разбивает сплошной текст перед «Чем предстоит…», «Наши ожидания:» и т.д."""
    for marker in sorted(INLINE_SECTION_MARKERS, key=len, reverse=True):
        pattern = re.compile(
            rf"([^\n])\s*({re.escape(marker)})\s*:",
            re.IGNORECASE,
        )
        text = pattern.sub(r"\1\n\n\2:", text)

        pattern_line = re.compile(
            rf"^\s*({re.escape(marker)})\s*:",
            re.IGNORECASE | re.MULTILINE,
        )
        text = pattern_line.sub(r"\n\1:", text)

    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _format_block(text: str) -> str:
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        line = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", line)
        if not line or line == "•":
            continue
        line = re.sub(r"^[-–—]\s+", "• ", line)
        line = re.sub(r"^•\s+", "• ", line)
        lines.append(_escape(line))
    return "\n".join(lines)


def _is_section_header_line(line: str) -> Optional[str]:
    """Возвращает название блока для строки-заголовка."""
    raw = line.strip()
    if not raw or raw.startswith("•"):
        return None

    core = raw.rstrip(":").strip()
    normalized = core.lower()

    if normalized in HEADER_STOPWORDS or len(normalized) <= 2:
        return None

    # Явный заголовок из текста вакансии
    for marker in INLINE_SECTION_MARKERS:
        if normalized == marker or normalized.startswith(marker):
            return _display_title(core)

    # Строка вида «Наши ожидания:» / «Чем предстоит заниматься:»
    if raw.endswith(":") and len(raw) <= 72:
        words = normalized.split()
        if len(words) <= 8:
            if any(marker in normalized for marker in INLINE_SECTION_MARKERS):
                return _display_title(core)
            if len(words) <= 5 and "." not in core[:-1]:
                return _display_title(core)

    return None


def _display_title(core: str) -> str:
    if not core:
        return core
    return core[0].upper() + core[1:]


def _structure_description(description: str) -> List[Tuple[str, str]]:
    text = _inject_section_breaks(description)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return [("Описание", description)]

    sections: List[Tuple[str, List[str]]] = []
    current_title = "О компании"
    current_lines: List[str] = []
    first_section = True

    for line in lines:
        if line == "•":
            continue

        header = _is_section_header_line(line)
        if header:
            if current_lines:
                sections.append((current_title, current_lines))
            elif first_section and header != "О компании":
                # Текст до первого заголовка — вводный блок
                sections.append(("О компании", []))

            current_title = header
            current_lines = []
            first_section = False
            continue

        if first_section:
            current_title = "О компании"
            first_section = False

        current_lines.append(line)

    if current_lines:
        sections.append((current_title, current_lines))

    if not sections:
        return [("Описание", description)]

    # Убираем пустые блоки, объединяем дубли подряд
    merged: List[Tuple[str, List[str]]] = []
    for title, block in sections:
        if not block:
            continue
        if merged and merged[-1][0] == title:
            merged[-1][1].extend(block)
        else:
            merged.append((title, list(block)))

    if not merged:
        return [("Описание", description)]

    return [(title, "\n".join(block)) for title, block in merged[:12]]


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
