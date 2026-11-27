#!/bin/sh
set -e

echo "[entrypoint] Запуск парсера..."
exec python -u -m app.parser.main