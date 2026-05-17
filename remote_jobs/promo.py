from __future__ import annotations

from dataclasses import dataclass

SITE_URL = "https://vadzim.by"
CHANNEL_URL = "https://t.me/vadzimby_live"


@dataclass(frozen=True)
class PromoPost:
    text: str
    site_url: str
    channel_url: str
    site_button: str = "Услуги на vadzim.by"
    channel_button: str = "Канал: ИИ · Маркетинг · Дизайн"


def build_daily_promo(
    *,
    site_url: str = SITE_URL,
    channel_url: str = CHANNEL_URL,
) -> PromoPost:
    """Рекламный пост: vadzim.by + канал @vadzimby_live."""
    text = """<b>Сайты и digital под ключ</b>
<i>Vadzim.by · Минск · Беларусь</i>

Нужен сайт, который приносит заявки и лиды? Собираю решения под ключ — от лендинга до интернет-магазина.

<b>Услуги</b>
• Веб-разработка — WordPress, Tilda, чистый код, CRM
• Дизайн — понятная структура, акценты, сильные CTA
• Маркетинг — реклама, аналитика, рост конверсии
• SEO — аудит, продвижение, регулярные отчёты

<b>Подход</b>
• Сначала цель и аудитория, затем макет и вёрстка
• Прозрачные этапы — от идеи до запуска и поддержки
• Адаптив, скорость загрузки, удобная админка

<b>Стоимость</b>
Готовые решения — от <b>1 500 BYN</b>. Индивидуальные проекты — по брифу.

<b>Канал для практики в digital</b>
<b>ИИ × Маркетинг × Дизайн</b> — тренды, инструменты и рабочие приёмы без лишней теории. Если вы в IT, маркетинге или дизайне — загляните.

Подробности и подписка — кнопки ниже."""

    return PromoPost(
        text=text,
        site_url=site_url.rstrip("/"),
        channel_url=channel_url,
    )
