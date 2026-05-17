# Бесплатно: GitHub Actions (без VPS и без карты)

Подходит, если не хотите платить за сервер. GitHub запускает скрипт по расписанию в облаке.

**Ограничения:** запуск может опаздывать на 5–15 минут; на **приватном** репозитории лимит ~2000 минут Actions в месяц (этого проекту обычно хватает). На **публичном** — минуты не ограничены.

## 1. Репозиторий на GitHub

1. Зарегистрируйтесь на [github.com](https://github.com).
2. Репозиторий: [github.com/vadimsea/remote-belarus-bot](https://github.com/vadimsea/remote-belarus-bot)

На ПК в папке проекта:

```powershell
cd "d:\Work\Vadzim.by\Парсер удалёнки"
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/vadimsea/remote-belarus-bot.git
git push -u origin main
```

Файл `.env` в git **не попадёт** (он в `.gitignore`) — это правильно.

## 2. Секрет с токеном бота

1. Репозиторий → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
2. Имя: `TELEGRAM_BOT_TOKEN`, значение — токен от [@BotFather](https://t.me/BotFather).
3. По желанию второй секрет: `TELEGRAM_CHANNEL_ID` = `@remote_belarus` (если не задавать — подставится из кода).

## 3. Включить Actions

**Actions** → если спросит — **I understand my workflows, go ahead and enable them**.

Workflow уже в репозитории: `.github/workflows/publish.yml`.

Проверка вручную: **Actions** → **Publish to Telegram** → **Run workflow** → включить **dry_run** для теста без постов.

## 4. Отключить публикацию с ПК

Удалите задачи `RemoteBelarusVacancy_*` в Планировщике Windows, иначе посты могут дублироваться.

## 5. База вакансий (не публиковать повторно)

На GitHub база `data/seen.db` хранится в **кэше** между запусками.

Чтобы перенести уже опубликованное с ПК:

1. Один раз положите `data/seen.db` в репозиторий **временно** или запустите workflow после локальной работы — проще: скопируйте файл через отдельный коммит в ветку и удалите (не рекомендуется для публичного repo).

**Проще:** при первом запуске в облаке база пустая — бот начнёт с новых вакансий; старые в канале не тронет.

## Расписание на сегодня

**Actions** → последний успешный run → шаг **Publish vacancy slot** → в логе строка с расписанием.

Или локально: `python main.py --show-schedule`.

---

## Альтернатива: Oracle Cloud (бесплатно, нужна карта)

Полноценный VPS 24/7 без задержек GitHub: [Oracle Cloud Free](https://www.oracle.com/cloud/free/) → Ubuntu → `bash deploy/setup_linux.sh` (см. README).
