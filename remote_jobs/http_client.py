from __future__ import annotations

import requests


def make_session(user_agent: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": user_agent,
            "Accept-Language": "ru-RU,ru;q=0.9",
        }
    )
    return session
