#!/usr/bin/env bash
# Установка на VPS (Ubuntu/Debian): venv + cron, часовой пояс Europe/Minsk.
# Запуск из корня проекта: bash deploy/setup_linux.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"
LOG_DIR="$ROOT/logs"
MARKER="# remote_belarus_vacancy_bot"

echo "Проект: $ROOT"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Нужен python3. Ubuntu: sudo apt update && sudo apt install -y python3 python3-venv"
    exit 1
fi

if [ ! -f "$ROOT/.env" ]; then
    echo "Создайте .env (скопируйте .env.example и укажите TELEGRAM_BOT_TOKEN)."
    exit 1
fi

"$PYTHON" -m venv "$VENV"
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -r requirements.txt
mkdir -p "$LOG_DIR" "$ROOT/data"

# Тест импортов и часового пояса
"$PY" -c "from remote_jobs.schedule import now_minsk; print('Минск:', now_minsk().strftime('%Y-%m-%d %H:%M'))"

CRON_BLOCK=$(cat <<EOF
$MARKER
CRON_TZ=Europe/Minsk
0 9 * * * cd $ROOT && $PY main.py --promo >> $LOG_DIR/cron.log 2>&1
*/5 9-20 * * * cd $ROOT && $PY main.py >> $LOG_DIR/cron.log 2>&1
EOF
)

(crontab -l 2>/dev/null | grep -vF "$ROOT" | grep -v "$MARKER" || true
 echo "$CRON_BLOCK") | crontab -

echo ""
echo "Готово. Cron для пользователя $(whoami):"
crontab -l | grep -A3 "$MARKER" || true
echo ""
echo "Проверка:  $PY main.py --show-schedule"
echo "Логи:     tail -f $LOG_DIR/cron.log"
echo ""
echo "Если переносите с Windows — скопируйте data/seen.db на сервер в $ROOT/data/"
