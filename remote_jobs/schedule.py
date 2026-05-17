from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional, Sequence

try:
    from zoneinfo import ZoneInfo

    MINSK = ZoneInfo("Europe/Minsk")
except Exception:
    MINSK = timezone(timedelta(hours=3))

# Реклама vadzim.by — только в этом окне (Минск), раз в день
PROMO_TIME = time(9, 0)
PROMO_WINDOW_END = time(9, 35)

# 5 публикаций вакансий в случайное время в окне (Минск)
SLOTS_PER_DAY = 5
DAY_WINDOW_START = time(10, 0)
DAY_WINDOW_END = time(19, 0)
MIN_SLOT_GAP = timedelta(minutes=50)
GRACE_AFTER_LAST = timedelta(minutes=45)
SCHEDULE_SEED_SUFFIX = "v1"


@dataclass(frozen=True)
class PostSlot:
    index: int
    at: time
    label: str


def _time_to_minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _minutes_to_time(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


def generate_random_slot_times(
    day: date,
    count: int = SLOTS_PER_DAY,
    *,
    day_start: time = DAY_WINDOW_START,
    day_end: time = DAY_WINDOW_END,
    min_gap: timedelta = MIN_SLOT_GAP,
) -> List[time]:
    """Стабильное на день случайное расписание (одинаковое при перезапусках)."""
    rng = random.Random(f"{day.isoformat()}-{SCHEDULE_SEED_SUFFIX}")
    start_min = _time_to_minutes(day_start)
    end_min = _time_to_minutes(day_end)
    gap_min = int(min_gap.total_seconds() // 60)
    span = end_min - start_min
    required = (count - 1) * gap_min
    if span < required:
        raise ValueError("Слишком узкое окно для заданного числа слотов и минимального интервала")

    points: List[int] = []
    low = start_min
    for remaining in range(count, 0, -1):
        high = end_min - (remaining - 1) * gap_min
        minute = rng.randint(low, high)
        points.append(minute)
        low = minute + gap_min

    return [_minutes_to_time(m) for m in points]


def slots_from_times(slot_times: Sequence[time]) -> List[PostSlot]:
    return [
        PostSlot(index=i, at=slot_time, label=slot_time.strftime("%H:%M"))
        for i, slot_time in enumerate(slot_times)
    ]


def now_minsk() -> datetime:
    return datetime.now(MINSK)


def today_minsk() -> date:
    return now_minsk().date()


def slot_datetime(day: date, slot: PostSlot) -> datetime:
    return datetime.combine(day, slot.at, tzinfo=MINSK)


def get_due_slots_to_publish(
    filled_slots: set[int],
    slot_times: Sequence[time],
    *,
    now: Optional[datetime] = None,
) -> List[PostSlot]:
    """Все просроченные незаполненные слоты (догон, если GitHub опоздал)."""
    slots = slots_from_times(slot_times)
    if not slots:
        return []

    current = now or now_minsk()
    today = current.date()

    if current.time() < slot_times[0]:
        return []

    last_slot = slots[-1]
    grace_end = slot_datetime(today, last_slot) + GRACE_AFTER_LAST
    if current > grace_end:
        return []

    due: List[PostSlot] = []
    for slot in slots:
        if slot.index in filled_slots:
            continue
        if current >= slot_datetime(today, slot):
            due.append(slot)
    return due


def get_slot_to_publish(
    filled_slots: set[int],
    slot_times: Sequence[time],
    *,
    now: Optional[datetime] = None,
    force_slot: Optional[int] = None,
) -> Optional[PostSlot]:
    """Первый слот из очереди на публикацию."""
    if force_slot is not None:
        slots = slots_from_times(slot_times)
        if 0 <= force_slot < len(slots):
            return slots[force_slot]
        return None

    due = get_due_slots_to_publish(filled_slots, slot_times, now=now)
    return due[0] if due else None


def is_promo_in_window(now: Optional[datetime] = None) -> bool:
    """Реклама только 09:00–09:35 Минск — не в слоты вакансий."""
    current = now or now_minsk()
    t = current.time()
    return PROMO_TIME <= t <= PROMO_WINDOW_END


def is_promo_due(
    *,
    promo_posted_today: bool,
    now: Optional[datetime] = None,
    force: bool = False,
) -> bool:
    if promo_posted_today and not force:
        return False
    if force:
        return True
    current = now or now_minsk()
    if not is_promo_in_window(current):
        return False
    promo_at = datetime.combine(current.date(), PROMO_TIME, tzinfo=MINSK)
    return current >= promo_at


def next_slot_hint(
    filled_slots: set[int],
    slot_times: Sequence[time],
    *,
    now: Optional[datetime] = None,
) -> Optional[str]:
    current = now or now_minsk()
    today = current.date()
    for slot in slots_from_times(slot_times):
        if slot.index in filled_slots:
            continue
        target = slot_datetime(today, slot)
        if target > current:
            return target.strftime("%H:%M")
    return None


def format_schedule(slot_times: Sequence[time]) -> str:
    return ", ".join(t.strftime("%H:%M") for t in slot_times)
