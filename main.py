import os
import time
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import requests
import mysql.connector


def parse_website(target_url):
    collected_links = []
    print(f'--- Начинаем парсинг: {target_url} ---')

    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(target_url, timeout=10, headers=headers)
        response.encoding = 'utf-8'

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            links = soup.find_all('a')

            for i, link in enumerate(links[:15], 1):
                title = link.get_text(strip=True)
                href = link.get('href')

                if href:
                    full_url = urljoin(target_url, href)
                    collected_links.append([target_url, title, full_url])
                    print(f'  [{i}/15] Найдена ссылка: {title[:30]} -> {full_url[:50]}...')
        else:
            print(f'Сайт {target_url} ответил со статусом: {response.status_code}')

    except Exception as e:
        print(f'Ошибка при запросе к {target_url}: {e}')

    print(f'--- Завершен парсинг: {target_url}. Собрано: {len(collected_links)} ---\n')
    return collected_links


def run_parser():
    """Один цикл парсинга: собирает данные и пишет в БД."""
    urls = ['https://nur.kz', 'https://inform.kz', 'https://kaztag.kz']
    all_data = []

    for site_url in urls:
        site_data = parse_website(site_url)
        all_data.extend(site_data)

    if not all_data:
        print('Нет данных для записи. Пропускаем этот цикл.')
        return

    print('Подключаемся к базе данных...')
    try:
        db = mysql.connector.connect(
            host=os.getenv('DB_HOST', '127.0.0.1'),
            port=int(os.getenv('DB_PORT', 3306)),
            user='root',
            password='mysecretpassword',
            database='parser_db',
            charset='utf8mb4'
        )
        cursor = db.cursor()

        print(f'Вставляем {len(all_data)} ссылок в базу...')
        for row in all_data:
            cursor.execute(
                "INSERT INTO links (site, title, url) VALUES (%s, %s, %s)",
                (row[0], row[1], row[2])
            )
        db.commit()
        print(f'✅ Вставлено {len(all_data)} строк в таблицу links')

        cursor.close()
        db.close()
        print('Соединение с базой закрыто.')

    except Exception as e:
        print(f'❌ Ошибка при работе с БД: {e}')


if __name__ == '__main__':
    # Интервал в секундах (3600 = 1 час)
    interval = int(os.getenv('PARSE_INTERVAL', 3600))

    print(f'🚀 Парсер запущен. Интервал: {interval} секунд ({interval/60:.0f} минут).')

    while True:
        try:
            print(f'\n=== Цикл парсинга начат: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} ===')
            run_parser()
            print(f'=== Цикл завершён. Следующий через {interval/60:.0f} минут ===\n')

        except Exception as e:
            print(f'❌ Критическая ошибка в цикле: {e}')

        time.sleep(interval)