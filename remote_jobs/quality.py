from __future__ import annotations

import re
from typing import Optional

from .models import Vacancy
from .filters import is_genuine_remote_work
from .professions import classify_profession

SPAM_PATTERNS = (
    r"заработок без",
    r"легкие деньги",
    r"пассивный доход",
    r"пирамида",
    r"mlm",
    r"сетевой маркетинг",
    r"вложени[ея]\s+от",
    r"оплата обучения",
    r"платное обучение",
    r"купите курс",
    r"набор на обучение",
    r"18\+",
    r"без опыта.{0,30}(?:от\s*)?\d{4,}",
    r"стабильн.{0,20}от\s*\d{4,}\s*(?:byn|руб|\$|usd)",
)

WEAK_PATTERNS = (
    "стажер без оплаты",
    "без оплаты",
    "волонтер",
    "фиктивн",
    "набор в команду без",
)

POSITIVE_PATTERNS = (
    "официальное трудоустройство",
    "трудовой договор",
    "тк рб",
    "byn",
    "руб",
    "usd",
    "eur",
    "зарплат",
    "оплата",
    "удален",
    "удалён",
    "из дома",
    "remote",
)


def score_vacancy(vacancy: Vacancy) -> Optional[float]:
    category = classify_profession(vacancy.title, vacancy.description)
    if not category:
        return None

    title = (vacancy.title or "").strip()
    description = (vacancy.description or "").strip()
    text = f"{title}\n{description}".lower()

    if len(title) < 4:
        return None
    if len(description) < 280:
        return None

    for pattern in SPAM_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return None

    if not is_genuine_remote_work(title, description):
        return None

    score = 50.0

    if vacancy.salary:
        score += 18
    if category == "it":
        score += 8
    if category == "marketing":
        score += 6
    if vacancy.source == "rabota":
        score += 3

    for marker in POSITIVE_PATTERNS:
        if marker in text:
            score += 2

    for weak in WEAK_PATTERNS:
        if weak in text:
            score -= 12

    if re.search(r"(требован|обязанност|условия|предлагаем|задачи)", text):
        score += 8

    if len(description) >= 600:
        score += 6
    if len(description) >= 1200:
        score += 4

    if title.isupper() and len(title) > 20:
        score -= 10
    if text.count("!") > 8:
        score -= 5

    return max(score, 0.0)


def _rank_source(vacancies: list[Vacancy]) -> list[tuple[Vacancy, float, str]]:
    ranked: list[tuple[Vacancy, float, str]] = []
    for vacancy in vacancies:
        score = score_vacancy(vacancy)
        if score is None:
            continue
        category = classify_profession(vacancy.title, vacancy.description)
        if not category:
            continue
        ranked.append((vacancy, score, category))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked


def pick_best_vacancies(
    vacancies: list[Vacancy],
    limit: int,
) -> list[tuple[Vacancy, float, str]]:
    """Чередует praca.by и rabota.by, чтобы оба источника попадали в канал."""
    praca = _rank_source([v for v in vacancies if v.source == "praca"])
    rabota = _rank_source([v for v in vacancies if v.source == "rabota"])

    per_source = max(1, limit // 2)
    praca = praca[:per_source]
    rabota = rabota[:per_source]

    merged: list[tuple[Vacancy, float, str]] = []
    i = j = 0
    while len(merged) < limit and (i < len(praca) or j < len(rabota)):
        if i < len(praca):
            merged.append(praca[i])
            i += 1
        if len(merged) >= limit:
            break
        if j < len(rabota):
            merged.append(rabota[j])
            j += 1

    if len(merged) < limit:
        rest = _rank_source(vacancies)
        seen = {item[0].uid for item in merged}
        for item in rest:
            if item[0].uid in seen:
                continue
            merged.append(item)
            if len(merged) >= limit:
                break

    return merged[:limit]
