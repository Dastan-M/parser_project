# Базовый образ: Python 3.12 на минимальном Debian
FROM python:3.12-slim

# Рабочая папка внутри контейнера
WORKDIR /app

# Сначала копируем только requirements.txt — так Docker закэширует установку библиотек
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальной код
COPY . .

# Убираем CRLF-окончания строк (Windows → Linux) и даём права
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

# Куда складывать результаты (для локальной разработки)
ENV DATA_DIR=/data

# Запускаем контейнер через наш entrypoint
ENTRYPOINT ["./entrypoint.sh"]