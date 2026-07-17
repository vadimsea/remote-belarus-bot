from __future__ import annotations

import json
import sqlite3
from datetime import date, time
from pathlib import Path
from typing import Iterable, List, Optional, Set

from .models import Vacancy
from .schedule import LATEST_FIRST_SLOT, SLOTS_PER_DAY, generate_random_slot_times, today_minsk


def _day_key(day: Optional[str] = None) -> str:
    return day or today_minsk().isoformat()


class VacancyStorage:
    def __init__(self, db_path: Path, *, seen_ttl_days: int = 21) -> None:
        self.seen_ttl_days = seen_ttl_days
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_vacancies (
                uid TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                category TEXT,
                quality_score REAL,
                slot_index INTEGER,
                posted_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_slots (
                day TEXT NOT NULL,
                slot_index INTEGER NOT NULL,
                vacancy_uid TEXT,
                posted_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (day, slot_index)
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS published_messages (
                message_id INTEGER PRIMARY KEY,
                vacancy_uid TEXT,
                posted_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_promo (
                day TEXT PRIMARY KEY,
                message_id INTEGER,
                posted_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS promo_posts (
                day TEXT NOT NULL,
                promo_key TEXT NOT NULL,
                message_id INTEGER,
                posted_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (day, promo_key)
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS candidate_queue (
                uid TEXT PRIMARY KEY,
                score REAL NOT NULL,
                payload TEXT NOT NULL,
                category TEXT NOT NULL,
                added_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_slot_schedule (
                day TEXT NOT NULL,
                slot_index INTEGER NOT NULL,
                slot_time TEXT NOT NULL,
                PRIMARY KEY (day, slot_index)
            )
            """
        )
        self._migrate_schema()
        self._conn.commit()

    def _migrate_schema(self) -> None:
        columns = {
            row[1] for row in self._conn.execute("PRAGMA table_info(seen_vacancies)")
        }
        if columns and "quality_score" not in columns:
            self._conn.execute("ALTER TABLE seen_vacancies ADD COLUMN quality_score REAL")
        if columns and "slot_index" not in columns:
            self._conn.execute("ALTER TABLE seen_vacancies ADD COLUMN slot_index INTEGER")
        if columns and "category" not in columns:
            self._conn.execute("ALTER TABLE seen_vacancies ADD COLUMN category TEXT")

    def filter_new(self, uids: Iterable[str]) -> set[str]:
        ids = list(uids)
        if not ids:
            return set()
        placeholders = ",".join("?" * len(ids))
        if self.seen_ttl_days > 0:
            rows = self._conn.execute(
                f"""
                SELECT uid FROM seen_vacancies
                WHERE uid IN ({placeholders})
                  AND posted_at >= datetime('now', ?)
                """,
                (*ids, f"-{self.seen_ttl_days} days"),
            ).fetchall()
        else:
            rows = self._conn.execute(
                f"SELECT uid FROM seen_vacancies WHERE uid IN ({placeholders})",
                ids,
            ).fetchall()
        seen = {row[0] for row in rows}
        return {uid for uid in ids if uid not in seen}

    def posts_today_count(self, day: Optional[str] = None) -> int:
        day = _day_key(day)
        row = self._conn.execute(
            "SELECT COUNT(*) FROM daily_slots WHERE day = ?",
            (day,),
        ).fetchone()
        return int(row[0]) if row else 0

    def get_daily_schedule(self, day: Optional[str] = None) -> List[time]:
        day = _day_key(day)
        rows = self._conn.execute(
            """
            SELECT slot_time FROM daily_slot_schedule
            WHERE day = ?
            ORDER BY slot_index
            """,
            (day,),
        ).fetchall()
        return [_parse_slot_time(str(row[0])) for row in rows]

    def ensure_daily_schedule(
        self,
        count: int = SLOTS_PER_DAY,
        day: Optional[str] = None,
    ) -> List[time]:
        day = _day_key(day)
        existing = self.get_daily_schedule(day)
        if len(existing) >= count and existing[0] <= LATEST_FIRST_SLOT:
            return existing[:count]

        times = generate_random_slot_times(date.fromisoformat(day), count)
        self._conn.execute(
            "DELETE FROM daily_slot_schedule WHERE day = ?",
            (day,),
        )
        for index, slot_time in enumerate(times):
            self._conn.execute(
                """
                INSERT INTO daily_slot_schedule (day, slot_index, slot_time)
                VALUES (?, ?, ?)
                """,
                (day, index, slot_time.strftime("%H:%M")),
            )
        self._conn.commit()
        return times

    def filled_slots_today(self, day: Optional[str] = None) -> Set[int]:
        day = _day_key(day)
        rows = self._conn.execute(
            "SELECT slot_index FROM daily_slots WHERE day = ?",
            (day,),
        ).fetchall()
        return {int(row[0]) for row in rows}

    def is_slot_filled(self, slot_index: int, day: Optional[str] = None) -> bool:
        day = _day_key(day)
        row = self._conn.execute(
            "SELECT 1 FROM daily_slots WHERE day = ? AND slot_index = ?",
            (day, slot_index),
        ).fetchone()
        return row is not None

    def is_vacancy_seen(self, uid: str) -> bool:
        return uid not in self.filter_new([uid])

    def try_reserve_publish(
        self,
        slot_index: int,
        vacancy: Vacancy,
        category: Optional[str],
        quality_score: float,
        day: Optional[str] = None,
    ) -> bool:
        """Атомарно занять слот и вакансию до отправки в Telegram (защита от гонки)."""
        day = _day_key(day)
        if self.is_slot_filled(slot_index, day):
            return False
        if self.is_vacancy_seen(vacancy.uid):
            return False

        slot_cursor = self._conn.execute(
            """
            INSERT OR IGNORE INTO daily_slots (day, slot_index, vacancy_uid)
            VALUES (?, ?, ?)
            """,
            (day, slot_index, vacancy.uid),
        )
        if slot_cursor.rowcount == 0:
            return False

        seen_cursor = self._conn.execute(
            """
            INSERT OR IGNORE INTO seen_vacancies
                (uid, source, external_id, title, url, category, quality_score, slot_index)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                vacancy.uid,
                vacancy.source,
                vacancy.external_id,
                vacancy.title,
                vacancy.url,
                category,
                quality_score,
                slot_index,
            ),
        )
        if seen_cursor.rowcount == 0:
            self._conn.execute(
                "DELETE FROM daily_slots WHERE day = ? AND slot_index = ?",
                (day, slot_index),
            )
            self._conn.commit()
            return False

        self._conn.commit()
        return True

    def release_publish_reservation(
        self,
        slot_index: int,
        vacancy_uid: str,
        day: Optional[str] = None,
    ) -> None:
        day = _day_key(day)
        self._conn.execute(
            """
            DELETE FROM daily_slots
            WHERE day = ? AND slot_index = ? AND vacancy_uid = ?
            """,
            (day, slot_index, vacancy_uid),
        )
        self._conn.execute(
            "DELETE FROM seen_vacancies WHERE uid = ? AND slot_index = ?",
            (vacancy_uid, slot_index),
        )
        self._conn.commit()

    def remaining_daily_quota(self, daily_limit: int, day: Optional[str] = None) -> int:
        return max(0, daily_limit - self.posts_today_count(day))

    def mark_slot_published(
        self,
        slot_index: int,
        vacancy: Vacancy,
        category: Optional[str],
        quality_score: float,
        day: Optional[str] = None,
    ) -> None:
        day = _day_key(day)
        self._conn.execute(
            """
            INSERT OR REPLACE INTO daily_slots (day, slot_index, vacancy_uid)
            VALUES (?, ?, ?)
            """,
            (day, slot_index, vacancy.uid),
        )
        self._conn.execute(
            """
            INSERT OR IGNORE INTO seen_vacancies
                (uid, source, external_id, title, url, category, quality_score, slot_index)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                vacancy.uid,
                vacancy.source,
                vacancy.external_id,
                vacancy.title,
                vacancy.url,
                category,
                quality_score,
                slot_index,
            ),
        )
        self._conn.commit()

    def save_message_id(self, message_id: int, vacancy_uid: str) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO published_messages (message_id, vacancy_uid)
            VALUES (?, ?)
            """,
            (message_id, vacancy_uid),
        )
        self._conn.commit()

    def list_message_ids(self) -> List[int]:
        rows = self._conn.execute(
            "SELECT message_id FROM published_messages ORDER BY message_id"
        ).fetchall()
        return [int(row[0]) for row in rows]

    def clear_queue(self) -> None:
        self._conn.execute("DELETE FROM candidate_queue")
        self._conn.commit()

    def queue_size(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM candidate_queue").fetchone()
        return int(row[0]) if row else 0

    def queue_uids(self) -> set[str]:
        rows = self._conn.execute("SELECT uid FROM candidate_queue").fetchall()
        return {str(row[0]) for row in rows}

    def enqueue_candidates(
        self,
        ranked: list[tuple[Vacancy, float, str]],
    ) -> int:
        added = 0
        for vacancy, score, category in ranked:
            payload = json.dumps(
                {
                    "source": vacancy.source,
                    "external_id": vacancy.external_id,
                    "title": vacancy.title,
                    "company": vacancy.company,
                    "url": vacancy.url,
                    "salary": vacancy.salary,
                    "location": vacancy.location,
                    "description": vacancy.description,
                },
                ensure_ascii=False,
            )
            cursor = self._conn.execute(
                """
                INSERT OR IGNORE INTO candidate_queue (uid, score, payload, category)
                VALUES (?, ?, ?, ?)
                """,
                (vacancy.uid, score, payload, category),
            )
            if cursor.rowcount:
                added += 1
        self._conn.commit()
        return added

    def last_published_source(self) -> Optional[str]:
        row = self._conn.execute(
            """
            SELECT source FROM seen_vacancies
            ORDER BY posted_at DESC
            LIMIT 1
            """
        ).fetchone()
        return str(row[0]) if row else None

    def pop_best_candidate(
        self,
        *,
        allowed_uids: Optional[set[str]] = None,
        prefer_source: Optional[str] = None,
    ) -> Optional[tuple[Vacancy, float, str]]:
        rows = self._conn.execute(
            """
            SELECT uid, score, payload, category
            FROM candidate_queue
            ORDER BY score DESC, added_at ASC
            """
        ).fetchall()

        def try_pick(source_filter: Optional[str]):
            for uid, score, payload, category in rows:
                if allowed_uids is not None and uid not in allowed_uids:
                    continue
                vacancy = _vacancy_from_payload(uid, payload)
                if source_filter and vacancy.source != source_filter:
                    continue
                self._conn.execute("DELETE FROM candidate_queue WHERE uid = ?", (uid,))
                self._conn.commit()
                return vacancy, float(score), str(category)
            return None

        if prefer_source:
            picked = try_pick(prefer_source)
            if picked:
                return picked

        return try_pick(None)

    def promo_keys_posted_today(self, day: Optional[str] = None) -> set[str]:
        day = _day_key(day)
        rows = self._conn.execute(
            "SELECT promo_key FROM promo_posts WHERE day = ?",
            (day,),
        ).fetchall()
        return {str(row[0]) for row in rows}

    def promo_posted_today(
        self,
        promo_key: str = "legacy_daily_promo",
        day: Optional[str] = None,
    ) -> bool:
        day = _day_key(day)
        if promo_key != "legacy_daily_promo":
            row = self._conn.execute(
                "SELECT 1 FROM promo_posts WHERE day = ? AND promo_key = ?",
                (day, promo_key),
            ).fetchone()
            return row is not None
        row = self._conn.execute(
            "SELECT 1 FROM daily_promo WHERE day = ?",
            (day,),
        ).fetchone()
        return row is not None

    def mark_promo_posted(
        self,
        message_id: int,
        promo_key: str = "legacy_daily_promo",
        day: Optional[str] = None,
    ) -> None:
        day = _day_key(day)
        if promo_key == "legacy_daily_promo":
            self._conn.execute(
                """
                INSERT OR REPLACE INTO daily_promo (day, message_id)
                VALUES (?, ?)
                """,
                (day, message_id),
            )
        self._conn.execute(
            """
            INSERT OR REPLACE INTO promo_posts (day, promo_key, message_id)
            VALUES (?, ?, ?)
            """,
            (day, promo_key, message_id),
        )
        self._conn.commit()

    def reset_all(self) -> None:
        self._conn.execute("DELETE FROM seen_vacancies")
        self._conn.execute("DELETE FROM daily_slots")
        self._conn.execute("DELETE FROM published_messages")
        self._conn.execute("DELETE FROM candidate_queue")
        self._conn.execute("DELETE FROM daily_promo")
        self._conn.execute("DELETE FROM promo_posts")
        self._conn.execute("DELETE FROM daily_slot_schedule")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def _parse_slot_time(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))


def _vacancy_from_payload(uid: str, payload: str) -> Vacancy:
    data = json.loads(payload)
    return Vacancy(
        source=data["source"],
        external_id=data["external_id"],
        title=data["title"],
        company=data["company"],
        url=data["url"],
        salary=data.get("salary"),
        location=data.get("location"),
        description=data.get("description"),
    )
