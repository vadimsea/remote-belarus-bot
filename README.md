# @remote_belarus — удалёнка IT и маркетинг

Канал: [**@remote_belarus**](https://t.me/remote_belarus)

## Как работает

- **5 вакансий в сутки**, по **одной** в **случайное** время в окне **10:00–19:00** (**Минск**); расписание фиксируется в БД на весь день
- Реклама по расписанию: **vadzim.by** каждый день в **09:00**, **ATEN** каждый день в **12:30** и **18:30**, недвижимость Минска по воскресеньям в **11:30**, канал про ИИ/маркетинг/дизайн по вторникам и пятницам в **16:30**, бот-помощник программиста раз в 2 дня в **14:30**
- Только **IT** и **маркетинг**, только **удалёнка**, с **полным описанием**
- Отбор **качественных** вакансий (зарплата, структура текста, без спама)
- Аккуратное оформление поста + кнопка **«Получить работу»** со ссылкой на вакансию

## Установка

```powershell
cd "d:\Work\Vadzim.by\Парсер удалёнки"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# вставьте TELEGRAM_BOT_TOKEN
```

## Автозапуск 24/7 (рекомендуется)

**Планировщик Windows работает только при включённом ПК.**

### Бесплатно: GitHub Actions (без карты)

Код в репозитории на GitHub, токен бота — в **Secrets**, запуск по cron в облаке.

Подробная инструкция: **[deploy/GITHUB_ACTIONS.md](deploy/GITHUB_ACTIONS.md)**

Кратко: `git push` → Settings → Secrets → `TELEGRAM_BOT_TOKEN` → Actions включены → отключить задачи Windows.

### VPS (точнее по времени, Oracle — бесплатно с картой)

### Сервер (Ubuntu)

1. Арендуйте VPS (Hetzner, Timeweb, Oracle Free Tier и т.п.).
2. Залейте проект на сервер (`git clone`, `scp` или SFTP).
3. На сервере:

```bash
cd /opt/remote-jobs   # путь к проекту
cp .env.example .env  # вставьте TELEGRAM_BOT_TOKEN
bash deploy/setup_linux.sh
.venv/bin/python main.py --show-schedule
```

Скрипт ставит **cron** с часовым поясом **Europe/Minsk**: реклама в **09:00**, проверка вакансий **каждые 5 минут** с 09:00 до 20:55.

Логи: `tail -f logs/cron.log`

**Перенос с ПК:** скопируйте `data/seen.db` на сервер — чтобы не публиковать уже вышедшие вакансии. После переноса на сервер **отключите** задачи Windows (`setup_tasks.ps1` больше не запускайте или удалите задачи `RemoteBelarusVacancy_*` в Планировщике).

Убрать cron с сервера: `bash deploy/remove_cron.sh`

### Только локальный ПК (ПК должен быть включён)

От имени администратора:

```powershell
.\setup_tasks.ps1
```

Расписание на сегодня:

```powershell
python main.py --show-schedule
```

Часовой пояс Windows — **Минск (UTC+3)**.

## Ручной запуск

```powershell
python main.py --dry-run --force-slot 0   # тест без отправки
python main.py --force-slot 0             # одна публикация (тест)
python main.py                            # в рабочее время — по расписанию
```

## Очистка

```powershell
python main.py --reset-db
python main.py --clear-channel   # только посты с сохранёнными ID
```

Старые посты в канале — удалите вручную в Telegram.
