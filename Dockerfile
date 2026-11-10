# Базовый образ: Python 3.12 на минимальном Debian
FROM python:3.12-slim

# Устанавливаем cron (планировщик) и чистим кэш пакетов
RUN apt-get update && apt-get install -y --no-install-recommends cron \
    && rm -rf /var/lib/apt/lists/*

# Рабочая папка внутри контейнера
WORKDIR /app

# Куда складывать результаты (в контейнере это /data, куда подключён volume)
ENV DATA_DIR=/data

# Сначала копируем только requirements.txt — так Docker закэширует установку библиотек
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальной код (main.py, crontab, entrypoint.sh — см. следующие шаги)
COPY . .

# Убираем CRLF-окончания строк в entrypoint и даём права
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

# Копируем crontab в системную папку и ЧИСТИМ УЖЕ ТАМ (после COPY!)
COPY crontab /etc/cron.d/parser-cron
RUN sed -i 's/\r$//' /etc/cron.d/parser-cron \
    && printf '\n' >> /etc/cron.d/parser-cron \
    && chmod 0644 /etc/cron.d/parser-cron

# Запускаем контейнер через наш entrypoint
ENTRYPOINT ["./entrypoint.sh"]