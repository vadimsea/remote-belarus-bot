from __future__ import annotations

import logging
import time
from typing import Iterable, List, Optional, Tuple

import requests

from .formatter import APPLY_BUTTON_TEXT, FormattedPost, format_vacancy_post
from .promo import PromoPost
from .models import Vacancy
from .professions import ProfessionCategory

logger = logging.getLogger(__name__)


class TelegramPublisher:
    def __init__(
        self,
        bot_token: str,
        channel_id: str,
        post_delay: float = 3.0,
        part_delay: float = 4.0,
        daily_limit: int = 5,
        session: requests.Session | None = None,
    ) -> None:
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.post_delay = post_delay
        self.part_delay = part_delay
        self.daily_limit = daily_limit
        self.session = session or requests.Session()
        self.api_base = f"https://api.telegram.org/bot{bot_token}"

    def publish_one(
        self,
        vacancy: Vacancy,
        category: ProfessionCategory,
        *,
        slot_index: int,
        slot_label: str,
    ) -> Tuple[int, List[Tuple[str, int]]]:
        post = format_vacancy_post(vacancy, category=category)
        if not post or not post.messages:
            raise ValueError("Пустое сообщение для публикации")

        published: List[Tuple[str, int]] = []
        last_index = len(post.messages) - 1

        for index, message in enumerate(post.messages):
            with_button = index == last_index
            message_id = self._send_message(
                message,
                button_url=post.apply_url if with_button else None,
                button_text=post.apply_button_text if with_button else APPLY_BUTTON_TEXT,
            )
            if message_id:
                published.append((vacancy.uid, message_id))
            if index < last_index and self.part_delay > 0:
                time.sleep(self.part_delay)

        if self.post_delay > 0:
            time.sleep(self.post_delay)

        return len(post.messages), published

    def publish(
        self,
        vacancies: Iterable[Vacancy],
        categories: Optional[dict[str, ProfessionCategory]] = None,
    ) -> Tuple[int, List[Tuple[str, int]]]:
        categories = categories or {}
        sent = 0
        published: List[Tuple[str, int]] = []
        for vacancy in vacancies:
            category = categories.get(vacancy.uid, "it")
            _, ids = self.publish_one(vacancy, category, slot_index=sent, slot_label="")
            published.extend(ids)
            sent += 1
        return sent, published

    def delete_messages(self, message_ids: Iterable[int]) -> int:
        deleted = 0
        for message_id in message_ids:
            try:
                response = self.session.post(
                    f"{self.api_base}/deleteMessage",
                    json={"chat_id": self.channel_id, "message_id": message_id},
                    timeout=30,
                )
                data = response.json()
                if data.get("ok"):
                    deleted += 1
                time.sleep(0.4)
            except Exception:
                logger.exception("Не удалось удалить message_id=%s", message_id)
        return deleted

    def publish_promo(self, promo: PromoPost) -> Optional[int]:
        keyboard = {
            "inline_keyboard": [
                [{"text": promo.site_button, "url": promo.site_url}],
                [{"text": promo.channel_button, "url": promo.channel_url}],
            ]
        }
        return self._send_message(promo.text, reply_markup=keyboard)

    def _inline_keyboard(self, url: str, text: str) -> dict:
        return {
            "inline_keyboard": [
                [{"text": text, "url": url}],
            ]
        }

    def _send_message(
        self,
        text: str,
        *,
        button_url: Optional[str] = None,
        button_text: str = APPLY_BUTTON_TEXT,
        reply_markup: Optional[dict] = None,
    ) -> Optional[int]:
        payload = {
            "chat_id": self.channel_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        elif button_url:
            payload["reply_markup"] = self._inline_keyboard(button_url, button_text)

        for attempt in range(5):
            response = self.session.post(
                f"{self.api_base}/sendMessage",
                json=payload,
                timeout=30,
            )
            data = response.json()
            if data.get("ok"):
                message_id = (data.get("result") or {}).get("message_id")
                logger.info("Опубликовано в %s (msg %s)", self.channel_id, message_id)
                return message_id

            if data.get("error_code") == 429:
                retry_after = int((data.get("parameters") or {}).get("retry_after", 30))
                logger.warning("Лимит Telegram, ждём %s сек.", retry_after)
                time.sleep(retry_after + 2)
                continue

            raise RuntimeError(f"Telegram API error: {data}")

        raise RuntimeError("Telegram API: слишком много попыток отправки")
