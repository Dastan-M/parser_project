import os
import re
import time
import hashlib
from datetime import datetime
from urllib.parse import urljoin, urlparse
from parsel import Selector
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

def get_news_xpath(domain):
    """Возвращает XPath для новостных ссылок на конкретном сайте."""
    if 'kaztag' in domain:
        # Новости kaztag.kz — <a class="title"> внутри <div class="top-inner">
        return '//div[@class="top-inner"]//a[@href]'
    if 'nur.kz' in domain:
        # Новости nur.kz — <a> внутри <article>
        return '//article//a[@href]'
    if 'zakon.kz' in domain:
        # Новости zakon.kz — ссылки на .html
        return '//a[contains(@href, ".html")]'
    # Fallback для других сайтов
    return '//a[@href]'

def parse_website(target_url, source_domain):
    """Парсит сайт через parsel+XPath, оставляет только новости."""
    collected_links = []
    print(f'--- Начинаем парсинг: {target_url} ---')

    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(target_url, timeout=10, headers=headers)
        response.encoding = 'utf-8'

        if response.status_code != 200:
            print(f'Сайт {target_url} ответил со статусом: {response.status_code}')
            return collected_links

        selector = Selector(text=response.text)

        # XPath: для каждого сайта — свой, в зависимости от структуры
        news_elements = selector.xpath(get_news_xpath(source_domain))
        if not news_elements:
            news_elements = selector.xpath('//a[@href]')

        print(f'Найдено <a> элементов: {len(news_elements)}')

        for link in news_elements:
            # XPath: normalize-space(string(.)) — берёт весь текст внутри <a>, убирает лишние пробелы
            title = (link.xpath('normalize-space(string(.))').get() or '').strip()
            href = link.attrib.get('href', '')

            if not href:
                continue

            full_url = urljoin(target_url, href)

            # Фильтр 1: только http/https
            if not full_url.startswith(('http://', 'https://')):
                continue

            # Фильтр 2: только тот же домен
            link_domain = urlparse(full_url).netloc
            if not link_domain.endswith(source_domain):
                continue

            # Фильтр 3: паттерн новости для каждого сайта
            # nur.kz:      /2457843-slug        — 5+ цифр подряд
            # zakon.kz:    /6538895-slug.html   — 6+ цифр + дефис
            # kaztag.kz:   /ru/news/{slug}      — /news/ + 10+ символов slug
            if not re.search(
                r'(/\d{5,})|(/news/[a-z0-9\-]{10,})|(/\d{6,}-)',
                full_url
            ):
                continue

            # Нормализация: обрезаем якорь, UTM
            url_without_fragment = full_url.split('#')[0]
            normalized = normalize_url(url_without_fragment)
            if not normalized:
                continue

            collected_links.append([source_domain, title, normalized])

            if len(collected_links) >= 15:
                break

        print(f'--- Завершен парсинг: {target_url}. Собрано: {len(collected_links)} ---\n')

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