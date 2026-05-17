from __future__ import annotations

import re
from typing import Literal, Optional

ProfessionCategory = Literal["it", "marketing"]

IT_KEYWORDS = (
    "разработчик",
    "developer",
    "dev ",
    " dev",
    "программист",
    "программирован",
    "frontend",
    "front-end",
    "front end",
    "backend",
    "back-end",
    "back end",
    "fullstack",
    "full-stack",
    "full stack",
    "devops",
    "dev ops",
    "тестировщик",
    " qa",
    "qa ",
    "quality assurance",
    "автоматизатор",
    "data engineer",
    "data scientist",
    "data analyst",
    "аналитик данных",
    "machine learning",
    "ml engineer",
    "python",
    "java",
    "javascript",
    "typescript",
    "react",
    "vue",
    "angular",
    "node.js",
    "nodejs",
    "golang",
    "go developer",
    "php",
    "c++",
    "c#",
    ".net",
    "ios",
    "android",
    "mobile developer",
    "flutter",
    "kotlin",
    "swift",
    "sql",
    "dba",
    "database",
    "системный администратор",
    "сисадмин",
    "sysadmin",
    "сетевой инженер",
    "инженер-программист",
    "software engineer",
    "software developer",
    "web-разработ",
    "веб-разработ",
    "верстальщ",
    "ux",
    "ui",
    "ui/ux",
    "product designer",
    "продуктовый дизайнер",
    "1с-программист",
    "1c-программист",
    "bitrix",
    "wordpress",
    "wordpress",
    "it-специалист",
    "it специалист",
    "айти",
    "информационн",
    "кибербезопас",
    "cybersecurity",
    "security engineer",
    "pentest",
    "architect",
    "архитектор по",
    "solution architect",
    "team lead",
    "tech lead",
    "тимлид",
    "тим лид",
    "scrum master",
    "product owner",
    "product manager",  # often IT-adjacent
    "project manager",  # borderline - include if IT context
    "бизнес-аналитик",
    "business analyst",
    "системный аналитик",
    "embedded",
    "blockchain",
    "game developer",
    "gamedev",
    "unity",
    "unreal",
)

MARKETING_KEYWORDS = (
    "маркетолог",
    "marketing",
    "digital marketing",
    "диджитал",
    "digital-",
    "smm",
    "seo",
    "sem",
    "таргетолог",
    "таргет",
    "performance marketing",
    "growth marketing",
    "growth hacker",
    "контент-менеджер",
    "контент менеджер",
    "content manager",
    "content marketing",
    "копирайтер",
    "copywriter",
    "pr-менеджер",
    "pr менеджер",
    "public relations",
    "бренд-менеджер",
    "brand manager",
    "брендолог",
    "медиабайер",
    "media buyer",
    "community manager",
    "комьюнити",
    "influence",
    "influencer",
    "блогер",
    "email marketing",
    "crm-marketing",
    "crm marketing",
    "маркетинговый аналитик",
    "marketing analyst",
    "product marketing",
    "продакт-маркетолог",
    "продакт маркетолог",
    "ppc",
    "контекстн",
    "context ads",
    "рекламный специалист",
    "специалист по рекламе",
    "traffic manager",
    "трафик-менеджер",
    "aso",
    "affiliate",
    "партнёрск",
    "партнерск",
    "продвижен",
    "promotion manager",
    "event marketing",
    "ивент-менеджер",
)

CALL_CENTER_MARKERS = (
    "прием входящих звонков",
    "приём входящих звонков",
    "входящих звонков",
    "колл-центр",
    "колл центр",
    "call-центр",
    "100 звонков",
    "оператор call",
)

NON_IT_TECHNICAL = (
    "станок",
    "станков",
    "чпу",
    "cnc",
    "фрезер",
    "токар",
    "слесар",
    "сварщ",
    "наладчик",
    "оператор станк",
    "инженер-технолог",
    "механическ",
    "металлообработ",
    "fanuc",
    "siemens",
    "solid cam",
    "solidworks",
    "solid works",
)

EXCLUDE_KEYWORDS = (
    "бухгалтер",
    "юрист",
    "юрисконсульт",
    "врач",
    "медсестра",
    "водитель",
    "курьер",
    "уборщ",
    "охранник",
    "продавец",
    "кассир",
    "оператор call",
    "call-центр",
    "колл-центр",
    "швея",
    "сварщик",
    "токар",
    "слесар",
)


def classify_profession(title: str, description: str | None = None) -> Optional[ProfessionCategory]:
    text = _normalize(f"{title} {description or ''}")
    if any(word in text for word in NON_IT_TECHNICAL):
        return None
    if any(word in text for word in CALL_CENTER_MARKERS):
        return None
    if any(word in text for word in EXCLUDE_KEYWORDS):
        if not _has_strong_it_marketing_signal(text):
            return None

    if _matches(text, IT_KEYWORDS):
        return "it"
    if _matches(text, MARKETING_KEYWORDS):
        return "marketing"
    return None


def is_it_or_marketing(title: str, description: str | None = None) -> bool:
    return classify_profession(title, description) is not None


def _has_strong_it_marketing_signal(text: str) -> bool:
    return _matches(text, IT_KEYWORDS) or _matches(text, MARKETING_KEYWORDS)


def _matches(text: str, keywords: tuple[str, ...]) -> bool:
    for keyword in keywords:
        if " " in keyword.strip():
            if keyword in text:
                return True
        else:
            if re.search(rf"(?<![\w-]){re.escape(keyword)}(?![\w-])", text):
                return True
    return False


def _normalize(text: str) -> str:
    lowered = text.lower().replace("ё", "е")
    return re.sub(r"\s+", " ", lowered)
