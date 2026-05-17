from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Vacancy:
    source: str
    external_id: str
    title: str
    company: str
    url: str
    salary: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    published_at: Optional[datetime] = None

    @property
    def uid(self) -> str:
        return f"{self.source}:{self.external_id}"
