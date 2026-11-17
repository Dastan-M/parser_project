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
    """Читает только ВКЛЮЧЁННЫЕ сайты из sources_db. Возвращает (id, name, url, domain)."""
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
        cursor.execute("SELECT id, name, url, domain FROM sources WHERE enabled = TRUE")
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
    if 'kaztag' in domain:
        return '//div[@class="top-inner"]//a[@href]'
    if 'nur.kz' in domain:
        return '//article//a[@href]'
    if 'zakon.kz' in domain:
        return '//a[contains(@href, ".html")]'
    return '//a[@href]'


def parse_date(date_str):
    """Парсит дату из разных форматов в MySQL DATETIME. Если не получилось — None."""
    if not date_str:
        return None
    for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%d.%m.%Y', '%Y/%m/%d']:
        try:
            return datetime.strptime(date_str[:19], fmt).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
    return None


def fetch_article(url):
    """Скачивает статью, возвращает (текст, дата_публикации)."""
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None, None

        # Метаданные (дата публикации)
        metadata = trafilatura.extract_metadata(downloaded)
        published_date = parse_date(metadata.date) if metadata and metadata.date else None

        # Текст статьи
        content = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=False,
            favor_recall=True
        )
        return content, published_date
    except Exception as e:
        print(f'  ⚠️ Ошибка при извлечении статьи {url[:60]}: {e}')
        return None, None


def parse_website(source_id, target_url, source_domain):
    """Парсит сайт, возвращает список [source_id, title, url, content, published_date]."""
    collected_links = []
    print(f'--- Начинаем парсинг: {target_url} (source_id={source_id}) ---')

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

        seen_urls = set()

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

            if not re.search(r'(/\d{5,})|(/news/[a-z0-9\-]{10,})|(/\d{6,}-)', full_url):
                continue

            normalized = normalize_url(full_url.split('#')[0])
            if not normalized or normalized in seen_urls:
                continue
            seen_urls.add(normalized)

            if not title:
                continue

            print(f'  [{len(collected_links) + 1}] Тянем текст: {title[:50]}...')
            content, published_date = fetch_article(normalized)

            collected_links.append([source_id, title, normalized, content, published_date])

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
            source_id, title, url, content, published_date = row
            url_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()
            cursor.execute(
                "INSERT IGNORE INTO news "
                "(source_id, title, url, url_hash, content, published_date) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (source_id, title, url, url_hash, content, published_date)
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
    sources = load_sources()

    if not sources:
        print('❌ Нет включённых источников в sources_db. Пропускаем цикл.')
        return

    print(f'📋 Загружено включённых источников: {len(sources)}')

    all_data = []
    for source_id, name, url, domain in sources:
        site_data = parse_website(source_id, url, domain)
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