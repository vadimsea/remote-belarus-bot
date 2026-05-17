from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_CHANNEL = "@remote_belarus"


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_channel_id: str
    daily_post_limit: int
    max_pages_praca: int
    max_pages_rabota: int
    queue_size: int
    telegram_post_delay: float
    telegram_part_delay: float
    request_delay: float
    min_description_length: int
    http_user_agent: str
    db_path: Path
    promo_site_url: str
    promo_channel_url: str

    @classmethod
    def from_env(cls, *, require_telegram: bool = True) -> "Settings":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        channel = os.getenv("TELEGRAM_CHANNEL_ID", DEFAULT_CHANNEL).strip() or DEFAULT_CHANNEL
        if require_telegram:
            if not token:
                raise ValueError("Укажите TELEGRAM_BOT_TOKEN в .env")
            if not channel:
                raise ValueError("Укажите TELEGRAM_CHANNEL_ID в .env")

        return cls(
            telegram_bot_token=token,
            telegram_channel_id=channel,
            daily_post_limit=int(os.getenv("DAILY_POST_LIMIT", "5")),
            max_pages_praca=int(os.getenv("MAX_PAGES_PRACA", "4")),
            max_pages_rabota=int(os.getenv("MAX_PAGES_RABOTA", "4")),
            queue_size=int(os.getenv("QUEUE_SIZE", "25")),
            telegram_post_delay=float(os.getenv("TELEGRAM_POST_DELAY", "3")),
            telegram_part_delay=float(os.getenv("TELEGRAM_PART_DELAY", "4")),
            request_delay=float(os.getenv("REQUEST_DELAY", "0.8")),
            min_description_length=int(os.getenv("MIN_DESCRIPTION_LENGTH", "200")),
            http_user_agent=os.getenv(
                "HTTP_USER_AGENT",
                "Mozilla/5.0 (compatible; RemoteJobsBY/1.0; +https://t.me/remote_belarus)",
            ),
            db_path=Path(os.getenv("DB_PATH", "data/seen.db")),
            promo_site_url=os.getenv("PROMO_SITE_URL", "https://vadzim.by").strip(),
            promo_channel_url=os.getenv(
                "PROMO_CHANNEL_URL", "https://t.me/vadzimby_live"
            ).strip(),
        )
