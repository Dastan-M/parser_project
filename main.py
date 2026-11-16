import os
import time
import hashlib
from datetime import datetime
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import requests
import mysql.connector
from courlan import normalize_url


def get_db_password():
    return os.getenv('MYSQL_ROOT_PASSWORD', 'mysecretpassword')


def load_sources():
    """Читает список сайтов из sources_db. Возвращает список (name, url, domain)."""
    db = None
    cursor = None
    try:
        db = mysql.connector.connect(
            host=os.getenv('DB_SOURCES_HOST', '127.0.0.1'),
            port=int(os.getenv('DB_SOURCES_PORT', 3306)),
            user='root',
            password=get_db_password(),
            database='sources_db',
            charset='utf8mb4'
        )
        cursor = db.cursor()
        cursor.execute("SELECT name, url, domain FROM sources")
        return cursor.fetchall()
    except mysql.connector.Error as e:
        print(f'❌ Ошибка при чтении sources_db: {e}')
        return []
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None and db.is_connected():
            db.close()


def parse_website(target_url, source_domain):
    """Парсит сайт, оставляет только ссылки с того же домена, нормализует URL."""
    collected_links = []
    print(f'--- Начинаем парсинг: {target_url} ---')

    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(target_url, timeout=10, headers=headers)
        response.encoding = 'utf-8'

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            links = soup.find_all('a')

            for link in links:
                title = link.get_text(strip=True)
                href = link.get('href')

                if not href:
                    continue

                full_url = urljoin(target_url, href)

                # Фильтр 1: только http/https
                if not full_url.startswith(('http://', 'https://')):
                    continue

                # Фильтр 2: только тот же домен (или поддомены)
                link_domain = urlparse(full_url).netloc
                if not link_domain.endswith(source_domain):
                    continue

                # Нормализуем URL: обрезаем якорь, убираем UTM-метки и т.д.
                url_without_fragment = full_url.split('#')[0]
                normalized = normalize_url(url_without_fragment)
                if not normalized:
                    continue  # если URL невалидный — пропускаем

                collected_links.append([source_domain, title, normalized])

                if len(collected_links) >= 15:
                    break

            print(f'--- Завершен парсинг: {target_url}. Собрано: {len(collected_links)} ---\n')
        else:
            print(f'Сайт {target_url} ответил со статусом: {response.status_code}')

    except Exception as e:
        print(f'Ошибка при запросе к {target_url}: {e}')

    return collected_links


def save_news(all_data):
    """Сохраняет новости в news_db. Возвращает число вставленных строк."""
    if not all_data:
        return 0

    db = None
    cursor = None
    inserted = 0
    try:
        db = mysql.connector.connect(
            host=os.getenv('DB_NEWS_HOST', '127.0.0.1'),
            port=int(os.getenv('DB_NEWS_PORT', 3306)),
            user='root',
            password=get_db_password(),
            database='news_db',
            charset='utf8mb4'
        )
        cursor = db.cursor()

        for row in all_data:
            source_domain, title, url = row
            url_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()
            cursor.execute(
                "INSERT IGNORE INTO news (source_domain, title, url, url_hash) "
                "VALUES (%s, %s, %s, %s)",
                (source_domain, title, url, url_hash)
            )
            inserted += cursor.rowcount

        db.commit()
        return inserted

    except mysql.connector.Error as e:
        print(f'❌ Ошибка при записи в news_db: {e}')
        return 0
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None and db.is_connected():
            db.close()


def run_parser():
    """Один цикл: читает источники, парсит, сохраняет новости."""
    sources = load_sources()

    if not sources:
        print('❌ Нет источников в sources_db. Пропускаем цикл.')
        return

    print(f'📋 Загружено источников: {len(sources)}')

    all_data = []
    for name, url, domain in sources:
        site_data = parse_website(url, domain)
        all_data.extend(site_data)

    if not all_data:
        print('Нет данных для записи. Пропускаем этот цикл.')
        return

    print(f'💾 Сохраняем {len(all_data)} ссылок в news_db...')
    inserted = save_news(all_data)
    print(f'✅ Вставлено новых строк: {inserted} (из {len(all_data)} собранных)')


if __name__ == '__main__':
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