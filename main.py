#!/usr/bin/env python3
"""Одна качественная IT/маркетинг вакансия за запуск в случайный слот 10:00–19:00 (Минск)."""

from __future__ import annotations

import argparse
import logging
import sys

from remote_jobs.config import Settings
from remote_jobs.http_client import make_session
from remote_jobs.parsers import PracaParser, RabotaParser
from remote_jobs.professions import ProfessionCategory
from remote_jobs.quality import pick_best_vacancies
from remote_jobs.promo import build_daily_promo
from remote_jobs.schedule import (
    format_schedule,
    get_due_slots_to_publish,
    get_slot_to_publish,
    is_promo_due,
    is_promo_in_window,
    next_slot_hint,
    now_minsk,
    slots_from_times,
)
from remote_jobs.storage import VacancyStorage
from remote_jobs.telegram_publisher import TelegramPublisher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("remote_jobs")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Публикует 1 удалённую IT/маркетинг вакансию в слот @remote_belarus.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source", choices=("all", "praca", "rabota"), default="all")
    parser.add_argument("--reset-db", action="store_true")
    parser.add_argument("--clear-channel", action="store_true")
    parser.add_argument(
        "--force-slot",
        type=int,
        choices=range(5),
        help="Принудительный слот 0–4 (сегодняшнее расписание)",
    )
    parser.add_argument(
        "--show-schedule",
        action="store_true",
        help="Показать случайное расписание на сегодня и выйти",
    )
    parser.add_argument(
        "--ignore-schedule",
        action="store_true",
        help="Не проверять время Минска (для теста)",
    )
    parser.add_argument(
        "--refresh-queue",
        action="store_true",
        help="Пересобрать очередь лучших вакансий",
    )
    parser.add_argument(
        "--promo",
        action="store_true",
        help="Опубликовать рекламу vadzim.by + @vadzimby_live (раз в день)",
    )
    parser.add_argument(
        "--force-promo",
        action="store_true",
        help="Реклама даже если уже была сегодня или раньше 09:00",
    )
    return parser.parse_args()


def collect_vacancies(settings: Settings, session, source: str):
    parser_kwargs = {
        "min_description_length": settings.min_description_length,
        "request_delay": settings.request_delay,
    }
    all_vacancies = []
    if source in ("all", "praca"):
        all_vacancies.extend(
            PracaParser(session, max_pages=settings.max_pages_praca, **parser_kwargs).fetch_vacancies()
        )
    if source in ("all", "rabota"):
        all_vacancies.extend(
            RabotaParser(session, max_pages=settings.max_pages_rabota, **parser_kwargs).fetch_vacancies()
        )
    return all_vacancies


def refresh_queue(
    storage: VacancyStorage,
    settings: Settings,
    session,
    source: str,
    *,
    replace: bool = False,
) -> tuple[int, list]:
    vacancies = collect_vacancies(settings, session, source)
    unique = {v.uid: v for v in vacancies}
    new_uids = storage.filter_new(unique.keys())
    candidates = [unique[uid] for uid in unique if uid in new_uids]
    praca_n = sum(1 for v in candidates if v.source == "praca")
    rabota_n = sum(1 for v in candidates if v.source == "rabota")
    logger.info("Кандидаты: praca=%s, rabota=%s", praca_n, rabota_n)
    ranked = pick_best_vacancies(candidates, limit=settings.queue_size)
    if replace and ranked:
        storage.clear_queue()
    added = storage.enqueue_candidates(ranked) if ranked else 0
    logger.info(
        "В очередь: praca=%s, rabota=%s",
        sum(1 for v, _, _ in ranked if v.source == "praca"),
        sum(1 for v, _, _ in ranked if v.source == "rabota"),
    )
    if candidates and not ranked:
        logger.warning(
            "Из %s новых вакансий ни одна не IT/маркетинг — очередь не трогаем (%s в очереди)",
            len(candidates),
            storage.queue_size(),
        )
    return added, ranked


def run_promo(
    settings: Settings,
    storage: VacancyStorage,
    session,
    *,
    dry_run: bool,
    force: bool,
) -> int:
    current = now_minsk()
    already = storage.promo_posted_today()
    if not is_promo_due(promo_posted_today=already, now=current, force=force):
        if already:
            logger.info("Реклама vadzim.by уже опубликована сегодня")
        else:
            logger.info(
                "Реклама с 09:00 (Минск). Сейчас %s — рано.",
                current.strftime("%H:%M"),
            )
        return 0

    promo = build_daily_promo(
        site_url=settings.promo_site_url,
        channel_url=settings.promo_channel_url,
    )
    if dry_run:
        logger.info("Реклама (dry-run):\n%s", promo.text.replace("<b>", "").replace("</b>", ""))
        return 0

    publisher = TelegramPublisher(
        bot_token=settings.telegram_bot_token,
        channel_id=settings.telegram_channel_id,
        post_delay=settings.telegram_post_delay,
        session=session,
    )
    message_id = publisher.publish_promo(promo)
    if not message_id:
        logger.error("Не удалось опубликовать рекламу")
        return 1
    storage.mark_promo_posted(message_id)
    logger.info("Реклама опубликована, message_id=%s", message_id)
    return 0


def main() -> int:
    args = parse_args()

    try:
        settings = Settings.from_env(require_telegram=not args.dry_run)
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    storage = VacancyStorage(settings.db_path, seen_ttl_days=settings.seen_ttl_days)

    if args.reset_db:
        storage.reset_all()
        logger.info("База очищена")

    session = make_session(settings.http_user_agent)

    if args.clear_channel:
        if args.dry_run:
            logger.error("--clear-channel нельзя с --dry-run")
            storage.close()
            return 1
        publisher = TelegramPublisher(
            bot_token=settings.telegram_bot_token,
            channel_id=settings.telegram_channel_id,
            session=session,
        )
        ids = storage.list_message_ids()
        if ids:
            logger.info("Удалено сообщений: %s", publisher.delete_messages(ids))
        else:
            logger.warning("Нет сохранённых ID. Старые посты удалите вручную в канале.")
        storage.close()
        return 0

    if args.promo:
        code = run_promo(
            settings,
            storage,
            session,
            dry_run=args.dry_run,
            force=args.force_promo,
        )
        storage.close()
        return code

    # Реклама только 09:00–09:35 Минск (не при каждом cron-запуске)
    if not args.dry_run and not args.reset_db and not args.clear_channel:
        current = now_minsk()
        if args.force_promo or (
            not storage.promo_posted_today()
            and is_promo_in_window(current)
        ):
            promo_code = run_promo(
                settings,
                storage,
                session,
                dry_run=False,
                force=args.force_promo,
            )
            if promo_code != 0:
                storage.close()
                return promo_code

    if args.reset_db and not args.dry_run and not args.force_slot:
        storage.close()
        return 0

    slot_times = storage.ensure_daily_schedule(settings.daily_post_limit)
    if args.show_schedule:
        logger.info("Расписание на сегодня (Минск): %s", format_schedule(slot_times))
        storage.close()
        return 0

    current = now_minsk()
    filled = storage.filled_slots_today()

    if args.force_slot is not None:
        forced = get_slot_to_publish(
            filled, slot_times, now=current, force_slot=args.force_slot
        )
        due_slots = [forced] if forced else []
    elif args.ignore_schedule:
        due_slots = [
            s
            for s in slots_from_times(slot_times)
            if s.index not in filled
        ][:1]
    else:
        due_slots = get_due_slots_to_publish(filled, slot_times, now=current)
        # Один пост за запуск GitHub Actions; пропущенные слоты догоняются по очереди
        due_slots = due_slots[:1]

    if not due_slots:
        if not args.ignore_schedule and not args.force_slot:
            hint = next_slot_hint(filled, slot_times, now=current)
            logger.info(
                "Сейчас %s (Минск). Не время публикации.%s",
                current.strftime("%H:%M"),
                f" Следующий слот: {hint}" if hint else " На сегодня слоты закрыты.",
            )
        else:
            logger.info("Нет слотов для публикации")
        storage.close()
        return 0

    if storage.remaining_daily_quota(settings.daily_post_limit) <= 0:
        logger.info("Лимит %s вакансий на сегодня исчерпан", settings.daily_post_limit)
        storage.close()
        return 0

    logger.info(
        "Канал: %s | К публикации слотов: %s | Заполнено: %s/%s | Расписание: %s",
        settings.telegram_channel_id,
        len(due_slots),
        len(filled),
        settings.daily_post_limit,
        format_schedule(slot_times),
    )

    ranked_from_refresh: list = []
    if args.refresh_queue or storage.queue_size() < 3:
        added, ranked_from_refresh = refresh_queue(
            storage,
            settings,
            session,
            args.source,
            replace=args.refresh_queue,
        )
        logger.info("Очередь обновлена: +%s вакансий (в очереди %s)", added, storage.queue_size())

    publisher = TelegramPublisher(
        bot_token=settings.telegram_bot_token,
        channel_id=settings.telegram_channel_id,
        post_delay=settings.telegram_post_delay,
        part_delay=settings.telegram_part_delay,
        daily_limit=settings.daily_post_limit,
        session=session,
    )

    published_count = 0
    for slot in due_slots:
        if storage.remaining_daily_quota(settings.daily_post_limit) <= 0:
            break
        if storage.is_slot_filled(slot.index) and not args.force_slot:
            logger.info("Слот %s уже опубликован", slot.label)
            continue

        last_source = storage.last_published_source()
        prefer = (
            "rabota"
            if last_source == "praca"
            else "praca"
            if last_source == "rabota"
            else None
        )

        allowed = storage.filter_new(storage.queue_uids())
        picked = storage.pop_best_candidate(allowed_uids=allowed, prefer_source=prefer)

        if not picked and not args.dry_run:
            added, ranked_from_refresh = refresh_queue(
                storage,
                settings,
                session,
                args.source,
                replace=False,
            )
            logger.info("Очередь пуста, повторный сбор: +%s", added)
            allowed = storage.filter_new(storage.queue_uids())
            picked = storage.pop_best_candidate(allowed_uids=allowed, prefer_source=prefer)

        if not picked and ranked_from_refresh:
            vacancy, score, category_raw = ranked_from_refresh.pop(0)
            category: ProfessionCategory = category_raw  # type: ignore[assignment]
            picked = (vacancy, score, category)

        if not picked:
            logger.warning("Нет вакансий для слота %s — остановка", slot.label)
            break

        vacancy, score, category_raw = picked
        category: ProfessionCategory = category_raw  # type: ignore[assignment]

        logger.info(
            "Слот %s: [%s/%s] score=%.1f — %s",
            slot.label,
            vacancy.source,
            category,
            score,
            vacancy.title,
        )

        if args.dry_run:
            logger.info("URL: %s | описание: %s симв.", vacancy.url, len(vacancy.description or ""))
            published_count += 1
            continue

        if not storage.try_reserve_publish(slot.index, vacancy, category, score):
            if storage.is_slot_filled(slot.index):
                logger.info("Слот %s уже занят другим процессом", slot.label)
                break
            logger.warning(
                "Вакансия уже в канале, берём следующую: %s — %s",
                vacancy.uid,
                vacancy.title,
            )
            continue

        try:
            _, published = publisher.publish_one(
                vacancy,
                category,
                slot_index=slot.index,
                slot_label=slot.label,
            )
        except Exception:
            logger.exception("Ошибка публикации слота %s", slot.label)
            storage.release_publish_reservation(slot.index, vacancy.uid)
            storage.enqueue_candidates([(vacancy, score, category)])
            storage.close()
            return 1

        storage.mark_slot_published(slot.index, vacancy, category, score)
        for _, message_id in published:
            storage.save_message_id(message_id, vacancy.uid)
        published_count += 1
        filled.add(slot.index)
        logger.info("Опубликовано в слот %s", slot.label)

    if published_count:
        logger.info("Готово: опубликовано вакансий за запуск: %s", published_count)
    storage.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
