#!/usr/bin/env bash
# Убрать cron-задачи бота с сервера
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MARKER="# remote_belarus_vacancy_bot"
(crontab -l 2>/dev/null | grep -vF "$ROOT" | grep -v "$MARKER" || true) | crontab -
echo "Cron-задачи бота удалены."
