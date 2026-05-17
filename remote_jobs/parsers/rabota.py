from __future__ import annotations

import html
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urljoin

import requests

from ..filters import (
    is_full_description,
    is_strictly_remote_rabota,
)
from ..models import Vacancy
from .details import RabotaDetailFetcher

logger = logging.getLogger(__name__)

BASE_URL = "https://rabota.by"
SEARCH_URL = f"{BASE_URL}/search/vacancy"
BELARUS_COUNTRY_ID = 4


class RabotaParser:
    def __init__(
        self,
        session: requests.Session,
        max_pages: int = 3,
        min_description_length: int = 150,
        request_delay: float = 0.5,
    ) -> None:
        self.session = session
        self.max_pages = max_pages
        self.min_description_length = min_description_length
        self.detail_fetcher = RabotaDetailFetcher(session, request_delay=request_delay)

    def fetch_vacancies(self) -> List[Vacancy]:
        stubs = self._collect_listing_stubs()
        vacancies: List[Vacancy] = []

        for stub in stubs:
            detail = self.detail_fetcher.fetch(stub["external_id"], stub["url"])
            if not detail:
                continue

            description = detail["description"]
            if not is_full_description(description, self.min_description_length):
                logger.debug("Rabota %s: описание слишком короткое", stub["external_id"])
                continue
            vacancies.append(
                Vacancy(
                    source="rabota",
                    external_id=stub["external_id"],
                    title=stub["title"],
                    company=stub["company"],
                    url=stub["url"],
                    salary=stub.get("salary"),
                    location=stub.get("location"),
                    description=description,
                    published_at=stub.get("published_at"),
                )
            )

        logger.info("Rabota.by: %s удалённых вакансий с полным описанием", len(vacancies))
        return vacancies

    def _collect_listing_stubs(self) -> List[dict]:
        stubs: List[dict] = []
        page = 0

        while True:
            if self.max_pages and page >= self.max_pages:
                break

            params = {
                "schedule": "remote",
                "area": "16",
                "page": str(page),
            }
            url = f"{SEARCH_URL}?{urlencode(params)}"
            logger.info("Rabota.by: страница %s — %s", page, url)
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            raw_items = self._extract_items(response.text)
            if not raw_items:
                break

            for raw in raw_items:
                stub = self._to_stub(raw)
                if stub:
                    stubs.append(stub)

            page += 1

        unique = {stub["external_id"]: stub for stub in stubs}
        logger.info("Rabota.by: в листинге %s кандидатов (только REMOTE)", len(unique))
        return list(unique.values())

    def _extract_items(self, html: str) -> List[Dict[str, Any]]:
        match = re.search(
            r'id="HH-Lux-InitialState"[^>]*>(\{.*?\})</template>',
            html,
            re.DOTALL,
        )
        if not match:
            logger.warning("Rabota.by: не найден JSON состояния на странице")
            return []

        state = json.loads(match.group(1))
        items: List[Dict[str, Any]] = []

        def walk(obj: Any) -> None:
            if isinstance(obj, dict):
                if (
                    "vacancyId" in obj
                    and "name" in obj
                    and "company" in obj
                    and is_strictly_remote_rabota(obj)
                    and self._is_belarus(obj)
                ):
                    items.append(obj)
                for value in obj.values():
                    walk(value)
            elif isinstance(obj, list):
                for value in obj:
                    walk(value)

        walk(state)
        return items

    @staticmethod
    def _is_belarus(item: Dict[str, Any]) -> bool:
        company = item.get("company") or {}
        country_id = company.get("@countryId")
        if country_id == BELARUS_COUNTRY_ID:
            return True
        host = item.get("displayHost") or ""
        links = item.get("links") or {}
        desktop = links.get("desktop", "")
        return host == "rabota.by" or "rabota.by" in desktop

    def _to_stub(self, item: Dict[str, Any]) -> Optional[dict]:
        vacancy_id = str(item.get("vacancyId", "")).strip()
        title = html.unescape((item.get("name") or "").strip())
        if not vacancy_id or not title:
            return None

        company_data = item.get("company") or {}
        company = (company_data.get("visibleName") or company_data.get("name") or "").strip()
        if not company:
            company = "Компания не указана"

        area = item.get("area") or {}
        location = area.get("name")

        published_at = None
        pub_raw = item.get("publicationTime") or item.get("creationTime")
        if pub_raw:
            published_at = self._parse_datetime(pub_raw)

        return {
            "external_id": vacancy_id,
            "title": title,
            "company": company,
            "url": self._vacancy_url(item, vacancy_id),
            "salary": self._format_salary(item.get("compensation")),
            "location": location,
            "published_at": published_at,
        }

    def _vacancy_url(self, item: Dict[str, Any], vacancy_id: str) -> str:
        links = item.get("links") or {}
        desktop = links.get("desktop")
        if desktop and "rabota.by" in desktop:
            return desktop
        return urljoin(BASE_URL, f"/vacancy/{vacancy_id}")

    @staticmethod
    def _format_salary(compensation: Optional[Dict[str, Any]]) -> Optional[str]:
        if not compensation:
            return None

        currency = compensation.get("currencyCode") or ""
        gross = compensation.get("gross")
        gross_suffix = " до вычета налогов" if gross else " на руки" if gross is False else ""

        amount_from = compensation.get("from")
        amount_to = compensation.get("to")
        if amount_from is None and amount_to is None:
            return None

        def fmt_amount(value: Optional[int]) -> Optional[str]:
            if value is None:
                return None
            if currency in {"BYN", "RUB", "USD", "EUR", "KZT"}:
                value = value / 100
            return f"{value:,.0f}".replace(",", " ").replace(".0", "")

        left = fmt_amount(amount_from)
        right = fmt_amount(amount_to)
        body = f"{left} – {right}" if left and right else (left or right)
        if not body:
            return None
        return f"{body} {currency}{gross_suffix}".strip()

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        if isinstance(value, str):
            normalized = value.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(normalized)
            except ValueError:
                return None
        return None
