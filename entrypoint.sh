#!/bin/sh
set -e

echo "[entrypoint] Запуск cron..."
cron

echo "[entrypoint] Cron запущен. Первый парсинг — в начале следующего часа."
echo "[entrypoint] Логи парсера будут появляться здесь же (docker logs)."

# Держим контейнер живым и показываем вывод cron-задач в docker logs
exec tail -f /proc/1/fd/1