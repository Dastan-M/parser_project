# Базовый образ
FROM python:3.12-slim

# Устанавливаем системные зависимости для Playwright (Chromium)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем переменную окружения для Playwright
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/lib/playwright

WORKDIR /app

# Сначала копируем requirements.txt для кэширования
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем Chromium и его зависимости для Playwright
RUN python -m playwright install --with-deps chromium

# Копируем остальной код
COPY . .

# Делаем entrypoint.sh исполняемым
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

# Переменные окружения (для парсера)
ENV DATA_DIR=/data

# По умолчанию запускаем парсер (API переопределит это через docker-compose)
ENTRYPOINT ["./entrypoint.sh"]