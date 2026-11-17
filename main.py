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
import trafilatura


def get_db_password():
    return os.getenv('MYSQL_ROOT_PASSWORD', 'mysecretpassword')


def load_sources():
    """Читает список сайтов из sources_db."""
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
    """XPath для новостных ссылок на конкретном сайте."""
    if 'kaztag' in domain:
        return '//div[@class="top-inner"]//a[@href]'
    if 'nur.kz' in domain:
        return '//article//a[@href]'
    if 'zakon.kz' in domain:
        return '//a[contains(@href, ".html")]'
    return '//a[@href]'


def fetch_article_text(url):
    """Скачивает статью и извлекает чистый текст через trafilatura."""
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=False,
            favor_recall=True
        )
        return text
    except Exception as e:
        print(f'  ⚠️ Ошибка при извлечении текста из {url[:60]}: {e}')
        return None


def parse_website(target_url, source_domain):
    """Парсит сайт, оставляет только новости, тянет текст каждой статьи."""
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

        news_elements = selector.xpath(get_news_xpath(source_domain))
        if not news_elements:
            news_elements = selector.xpath('//a[@href]')

        print(f'Найдено <a> элементов: {len(news_elements)}')

        seen_urls = set()  # локальный дедуп в рамках одного сайта

        for link in news_elements:
            title = (link.xpath('normalize-space(string(.))').get() or '').strip()
            href = link.attrib.get('href', '')

            if not href:
                continue

            full_url = urljoin(target_url, href)

            if not full_url.startswith(('http://', 'https://')):
                continue

            link_domain = urlparse(full_url).netloc
            if not link_domain.endswith(source_domain):
                continue

            # Паттерн новости для каждого сайта
            if not re.search(
                r'(/\d{5,})|(/news/[a-z0-9\-]{10,})|(/\d{6,}-)',
                full_url
            ):
                continue

            url_without_fragment = full_url.split('#')[0]
            normalized = normalize_url(url_without_fragment)
            if not normalized:
                continue

            if normalized in seen_urls:
                continue
            seen_urls.add(normalized)

            # Заголовок не должен быть пустым
            if not title:
                continue

            # Скачиваем текст статьи
            print(f'  [{len(collected_links) + 1}] Тянем текст: {title[:50]}...')
            content = fetch_article_text(normalized)

            collected_links.append([source_domain, title, normalized, content])

            if len(collected_links) >= 15:
                break

        print(f'--- Завершен парсинг: {target_url}. Собрано: {len(collected_links)} ---\n')

    except Exception as e:
        print(f'Ошибка при запросе к {target_url}: {e}')

    return collected_links


def save_news(all_data):
    """Сохраняет новости (с текстом) в news_db. Возвращает число вставленных строк."""
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
            source_domain, title, url, content = row
            url_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()
            cursor.execute(
                "INSERT IGNORE INTO news (source_domain, title, url, url_hash, content) "
                "VALUES (%s, %s, %s, %s, %s)",
                (source_domain, title, url, url_hash, content)
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
    """Один цикл: читает источники, парсит, сохраняет новости с текстом."""
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

    print(f'💾 Сохраняем {len(all_data)} новостей в news_db...')
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