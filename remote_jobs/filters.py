from __future__ import annotations

import re
from typing import Any, Dict, Set

# Реально не удалёнка (производство, цех, командировки)
NOT_REMOTE_WORK_MARKERS = (
    "командировк",
    "станок",
    "станков",
    "чпу",
    "cnc",
    "фрезер",
    "токар",
    "производствен",
    "массовое производство",
    "цех",
    "наладк",
    "спецодежда",
    "доставка к месту работы",
    "к месту работы",
    "металлообработк",
    "режущего инструмента",
    "механической обработки",
    "оператор станк",
    "инженер-технолог",
    "solid cam",
    "solid works",
    "уп )",
    "уп на станк",
    "на территории работодателя",
    "в офисе работодателя",
    "работа в офисе",
)

PRACA_REMOTE_TYPE_MARKERS = (
    "удаленная работа",
    "удалённая работа",
)

PRACA_REMOTE_WEAK_MARKERS = (
    "можно из дома",
    "удаленно",
    "удалённо",
    "дистанционно",
    "remote",
)


def extract_work_formats(item: Dict[str, Any]) -> Set[str]:
    formats: Set[str] = set()
    raw = item.get("workFormats")
    if not raw:
        return formats
    for block in raw:
        if isinstance(block, str):
            formats.add(block.upper())
        elif isinstance(block, dict):
            for value in block.get("workFormatsElement") or []:
                formats.add(str(value).upper())
    return formats


def is_strictly_remote_rabota(item: Dict[str, Any]) -> bool:
    formats = extract_work_formats(item)
    if not formats:
        schedule = item.get("@workSchedule") or item.get("workSchedule")
        if schedule != "REMOTE":
            return False
    elif not ("REMOTE" in formats and "ON_SITE" not in formats and "HYBRID" not in formats):
        return False

    name = (item.get("name") or "").lower()
    desc = (item.get("description") or "").lower()
    return is_genuine_remote_work(name, desc)


def is_strictly_remote_praca_text(*texts: str | None, description: str | None = None) -> bool:
    """Praca: только если в характере работы указана удалённая работа, не просто «можно из дома»."""
    combined = " ".join(t for t in texts if t).lower()
    desc = (description or "").lower()
    full = f"{combined} {desc}"

    if _has_onsite_work_signals(full):
        return False

    if any(marker in combined for marker in PRACA_REMOTE_TYPE_MARKERS):
        return True

    # Только «можно из дома» без типа «удалённая работа» — отсекаем
    if "можно из дома" in combined and not any(
        m in combined for m in PRACA_REMOTE_TYPE_MARKERS
    ):
        return False

    return False


def is_genuine_remote_work(title: str, description: str) -> bool:
    text = f"{title}\n{description}".lower()
    if _has_onsite_work_signals(text):
        return False

    remote_signals = (
        "удален",
        "удалён",
        "из дома",
        "дистанцион",
        "remote",
        "home office",
        "работа в интернете",
    )
    return any(signal in text for signal in remote_signals)


def _has_onsite_work_signals(text: str) -> bool:
    lower = text.lower()

    for marker in NOT_REMOTE_WORK_MARKERS:
        if marker in lower:
            return True

    if re.search(
        r"\bгибрид\w*\b|\bhybrid\b|частичн\w+ удал|"
        r"\d[\s/\-–—]*\d?\s*дн\w*\s+в офис|"
        r"посещени\w+ офис|приезж\w+ в офис|обязательн\w+ в офис|"
        r"в нашем офисе|в офисе компании|в офисе работодателя|"
        r"работа в офисе|очный формат|очно[\s\-]|"
        r"на месте работы|fix\s*desk|open\s*space|"
        r"только\s+минск|только\s+беларусь.{0,40}офис",
        lower,
    ):
        return True

    if re.search(r"чпу|cnc|станок", lower) and re.search(
        r"программист|fanuc|siemens|cam|фрезер", lower
    ):
        return True

    if "командировк" in lower and re.search(
        r"предел|производств|заграниц", lower
    ):
        return True

    if re.search(
        r"массовое производство|доставка к месту работы|карт наладки|уп \)",
        lower,
    ):
        return True

    if re.search(r"спецодежда", lower) and re.search(
        r"проживание предоставляется|цех|производств", lower
    ):
        return True

    if re.search(r"инженер-технолог|оператор станк", lower):
        return True

    return False


def is_full_description(text: str | None, min_length: int) -> bool:
    if not text:
        return False
    cleaned = re.sub(r"\s+", " ", text).strip()
    return len(cleaned) >= min_length
