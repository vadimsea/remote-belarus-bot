from __future__ import annotations

import json
import html
import logging
import re
import time
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..filters import is_genuine_remote_work, is_strictly_remote_praca_text
from ..text_utils import html_to_plain_text, normalize_whitespace

logger = logging.getLogger(__name__)

PRACA_BASE = "https://praca.by"
RABOTA_BASE = "https://rabota.by"


class PracaDetailFetcher:
    def __init__(self, session: requests.Session, request_delay: float = 0.5) -> None:
        self.session = session
        self.request_delay = request_delay

    def fetch(self, vacancy_id: str, url: str) -> Optional[dict]:
        time.sleep(self.request_delay)
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        remote_parts = []
        remote_el = soup.select_one(".vacancy__is-location")
        if remote_el:
            remote_parts.append(remote_el.get_text(" ", strip=True))

        for item in soup.select(".vacancy-required .vacancy__item"):
            text = item.get_text(" ", strip=True)
            if "Характер работы" in text:
                remote_parts.append(text)

        desc_block = soup.select_one(".vacancy__description .description")
        if not desc_block:
            logger.debug("Praca %s: нет блока описания", vacancy_id)
            return None

        description = normalize_whitespace(html_to_plain_text(str(desc_block)))
        if not description:
            return None

        title_el = soup.select_one("h1") or soup.select_one(".vacancy__title h1")
        title = title_el.get_text(" ", strip=True) if title_el else ""

        if not is_strictly_remote_praca_text(*remote_parts, description=description):
            logger.debug("Praca %s: не удалённая (только «из дома» или офис/цех)", vacancy_id)
            return None

        if not is_genuine_remote_work(title, description):
            logger.debug("Praca %s: описание — не удалённая работа", vacancy_id)
            return None

        return {
            "description": description,
            "is_remote": True,
        }


class RabotaDetailFetcher:
    def __init__(self, session: requests.Session, request_delay: float = 0.5) -> None:
        self.session = session
        self.request_delay = request_delay

    def fetch(self, vacancy_id: str, url: str) -> Optional[dict]:
        time.sleep(self.request_delay)
        page_url = url if url.startswith("http") else urljoin(RABOTA_BASE, url)
        response = self.session.get(page_url, timeout=30)
        response.raise_for_status()

        match = re.search(
            r'id="HH-Lux-InitialState"[^>]*>(\{.*?\})</template>',
            response.text,
            re.DOTALL,
        )
        if not match:
            logger.debug("Rabota %s: JSON состояния не найден", vacancy_id)
            return None

        state = json.loads(html.unescape(match.group(1)))
        vacancy = state.get("vacancyView") or state.get("vacancy")
        if not vacancy or str(vacancy.get("vacancyId")) != str(vacancy_id):
            vacancy = self._find_vacancy(state, vacancy_id)
        if not vacancy:
            return None

        from ..filters import extract_work_formats, is_strictly_remote_rabota

        if not is_strictly_remote_rabota(vacancy):
            formats = extract_work_formats(vacancy)
            logger.debug("Rabota %s: форматы %s — не только удалёнка", vacancy_id, formats)
            return None

        raw_description = vacancy.get("description") or ""
        description = normalize_whitespace(html_to_plain_text(raw_description))
        if not description:
            return None

        title = (vacancy.get("name") or "").strip()
        if not is_genuine_remote_work(title, description):
            logger.debug("Rabota %s: описание — не удалённая работа", vacancy_id)
            return None

        return {
            "description": description,
            "is_remote": True,
        }

    @staticmethod
    def _find_vacancy(state: dict, vacancy_id: str) -> Optional[dict]:
        found = None

        def walk(obj):
            nonlocal found
            if found or not isinstance(obj, dict):
                return
            if str(obj.get("vacancyId")) == str(vacancy_id) and obj.get("description"):
                found = obj
                return
            for value in obj.values():
                if isinstance(value, (dict, list)):
                    walk(value)

        walk(state)
        return found
