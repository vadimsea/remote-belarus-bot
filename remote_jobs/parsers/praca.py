from __future__ import annotations

import html as html_module
import logging
import re
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..filters import is_full_description
from ..models import Vacancy
from .details import PracaDetailFetcher

logger = logging.getLogger(__name__)

BASE_URL = "https://praca.by"
SEARCH_PATH = "/rabota-na-domu/"


class PracaParser:
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
        self.detail_fetcher = PracaDetailFetcher(session, request_delay=request_delay)

    def fetch_vacancies(self) -> List[Vacancy]:
        stubs = self._collect_listing_stubs()
        vacancies: List[Vacancy] = []

        for stub in stubs:
            detail = self.detail_fetcher.fetch(stub["external_id"], stub["url"])
            if not detail:
                continue

            description = detail["description"]
            if not is_full_description(description, self.min_description_length):
                logger.debug("Praca %s: описание слишком короткое", stub["external_id"])
                continue
            vacancies.append(
                Vacancy(
                    source="praca",
                    external_id=stub["external_id"],
                    title=stub["title"],
                    company=stub["company"],
                    url=stub["url"],
                    salary=stub.get("salary"),
                    location=stub.get("location"),
                    description=description,
                )
            )

        logger.info("Praca.by: %s удалённых вакансий с полным описанием", len(vacancies))
        return vacancies

    def _collect_listing_stubs(self) -> List[dict]:
        stubs: List[dict] = []
        page = 1

        while True:
            if self.max_pages and page > self.max_pages:
                break

            url = self._page_url(page)
            logger.info("Praca.by: страница %s — %s", page, url)
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            page_stubs = self._parse_listing(response.text)
            if not page_stubs:
                break

            stubs.extend(page_stubs)
            if not self._has_next_page(response.text, page):
                break
            page += 1

        unique = {stub["external_id"]: stub for stub in stubs}
        logger.info("Praca.by: в листинге %s вакансий", len(unique))
        return list(unique.values())

    def _page_url(self, page: int) -> str:
        if page <= 1:
            return urljoin(BASE_URL, SEARCH_PATH)
        return urljoin(
            BASE_URL,
            f"{SEARCH_PATH}?page={page}&search%5Bnature%5D%5Bremote%5D=1",
        )

    def _parse_listing(self, page_html: str) -> List[dict]:
        soup = BeautifulSoup(page_html, "html.parser")
        items = soup.select("li.vac-small")
        stubs: List[dict] = []

        for item in items:
            link = item.select_one("a.vac-small__title-link")
            if not link or not link.get("href"):
                continue

            href = link["href"]
            match = re.search(r"/vacancy/(\d+)/", href)
            if not match:
                continue

            remote_el = item.select_one(".vacancy-list__is-location")
            if not remote_el:
                continue

            title_el = link.select_one("h2") or link
            title = html_module.unescape(title_el.get_text(" ", strip=True))
            if not title:
                continue

            company_el = item.select_one("a.vac-small__organization")
            company = (
                company_el.get_text(" ", strip=True) if company_el else "Компания не указана"
            )

            salary_el = item.select_one(".vac-small__salary")
            salary = salary_el.get_text(" ", strip=True) if salary_el else None

            location_el = item.select_one(".vac-small__city")
            location = location_el.get_text(" ", strip=True) if location_el else None
            remote_text = remote_el.get_text(" ", strip=True)
            location = f"{location}, {remote_text}" if location else remote_text

            stubs.append(
                {
                    "external_id": match.group(1),
                    "title": title,
                    "company": company,
                    "url": urljoin(BASE_URL, href),
                    "salary": salary,
                    "location": location,
                }
            )

        return stubs

    @staticmethod
    def _has_next_page(html: str, current_page: int) -> bool:
        soup = BeautifulSoup(html, "html.parser")
        rel_next = soup.select_one('link[rel="next"]')
        if rel_next and rel_next.get("href"):
            match = re.search(r"page=(\d+)", rel_next["href"])
            if match:
                return int(match.group(1)) > current_page
        return False
