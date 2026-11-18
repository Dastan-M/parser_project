import hashlib
import re
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
import mysql.connector
import trafilatura
from parsel import Selector
from courlan import normalize_url

from config import get_parse_interval
from db import get_connection, url_exists, save_news_one

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}


def fetch_html(url):
    """Единая функция скачивания HTML. Возвращает текст или None."""
    try:
        response = requests.get(url, timeout=10, headers=HEADERS)
        if response.status_code != 200:
            print(f'  ⚠️ {url[:60]} ответил {response.status_code}')
            return None
        response.encoding = 'utf-8'
        return response.text
    except Exception as e:
        print(f'  ⚠️ Ошибка скачивания {url[:60]}: {e}')
        return None


def extract_article(html):
    """Извлекает текст статьи и дату публикации из готового HTML."""
    try:
        metadata = trafilatura.extract_metadata(html)
        published_date = parse_date(metadata.date) if metadata and metadata.date else None
        content = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            favor_recall=True
        )
        return content, published_date
    except Exception as e:
        print(f'  ⚠️ Ошибка извлечения текста: {e}')
        return None, None


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%d.%m.%Y', '%Y/%m/%d']:
        try:
            return datetime.strptime(date_str[:19], fmt).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
    return None


def load_sources():
    """Читает только ВКЛЮЧЁННЫЕ сайты из sources_db."""
    db = get_connection('sources')
    if db is None:
        return []
    cursor = None
    try:
        cursor = db.cursor()
        cursor.execute("SELECT id, name, url, domain, rss_url FROM sources WHERE enabled = TRUE")
        return cursor.fetchall()
    except mysql.connector.Error as e:
        print(f'❌ Ошибка при чтении sources_db: {e}')
        return []
    finally:
        if cursor is not None:
            cursor.close()
        if db.is_connected():
            db.close()


def get_news_xpath(domain):
    if 'kaztag' in domain:
        return '//div[@class="top-inner"]//a[@href]'
    if 'nur.kz' in domain:
        return '//article//a[@href]'
    if 'zakon.kz' in domain:
        return '//a[contains(@href, ".html")]'
    return '//a[@href]'

def parse_rss_date(date_str):
    """Парсит дату из RSS (RFC 822: 'Wed, 18 Nov 2026 16:04:58 +0500')."""
    if not date_str:
        return None
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return None


def parse_rss(source_id, rss_url, cursor, db, max_news=30):
    """Парсит RSS-ленту, сохраняет новости в БД."""
    import feedparser

    print(f'--- Начинаем парсинг RSS: {rss_url} (source_id={source_id}) ---')
    feed = feedparser.parse(rss_url)

    if not feed.entries:
        print(f'  ⚠️ RSS пустой или недоступен: {rss_url}')
        return 0, 0

    print(f'Найдено новостей в RSS: {len(feed.entries)}')

    inserted = 0
    skipped = 0

    for entry in feed.entries[:max_news]:
        title = (entry.get('title', '') or '').strip()
        link = (entry.get('link', '') or '').strip()
        published = entry.get('published', '')

        if not title or not link:
            continue

        normalized = normalize_url(link.split('#')[0])
        if not normalized:
            continue

        url_hash = hashlib.sha256(normalized.encode('utf-8')).hexdigest()

        if url_exists(cursor, url_hash):
            skipped += 1
            continue

        print(f'  [{inserted + 1}] Скачиваем: {title[:60]}...')
        article_html = fetch_html(normalized)
        if not article_html:
            continue

        content, published_date = extract_article(article_html)

        # Если из статьи дата не извлеклась — берём из RSS
        if not published_date and published:
            published_date = parse_rss_date(published)

        if save_news_one(cursor, db, source_id, title, normalized, url_hash, content, published_date):
            inserted += 1

        if inserted >= max_news:
            break

    print(f'--- Завершен RSS: {rss_url}. Вставлено: {inserted}, пропущено: {skipped} ---\n')
    return inserted, skipped

def process_website(source_id, target_url, source_domain, cursor, db, max_news=15):
    """Парсит сайт и СОХРАНЯЕТ новости в БД в процессе.

    Порядок для каждой ссылки:
    1. Нормализация
    2. Проверка в БД по url_hash (самое быстрое)
    3. Если нет — скачивание, извлечение, вставка (самое дорогое)
    """
    print(f'--- Начинаем парсинг: {target_url} (source_id={source_id}) ---')

    html = fetch_html(target_url)
    if not html:
        return 0, 0  # вставлено, пропущено

    selector = Selector(text=html)
    news_elements = selector.xpath(get_news_xpath(source_domain))
    if not news_elements:
        news_elements = selector.xpath('//a[@href]')

    print(f'Найдено <a> элементов: {len(news_elements)}')

    seen_urls = set()
    inserted = 0
    skipped = 0

    for link in news_elements:
        if inserted >= max_news:
            break

        title = (link.xpath('normalize-space(string(.))').get() or '').strip()
        href = link.attrib.get('href', '')
        if not href or not title:
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

        # === ПРОВЕРКА В БД ДО СКАЧИВАНИЯ ===
        url_hash = hashlib.sha256(normalized.encode('utf-8')).hexdigest()
        if url_exists(cursor, url_hash):
            skipped += 1
            print(f'  ⏭️  Уже в базе: {title[:50]}')
            continue

        # === СКАЧИВАНИЕ (только если в БД нет) ===
        print(f'  [{inserted + 1}] Скачиваем: {title[:50]}...')
        article_html = fetch_html(normalized)
        if not article_html:
            continue

        content, published_date = extract_article(article_html)

        # === ВСТАВКА ВНУТРИ ЦИКЛА (с commit внутри save_news_one) ===
        if save_news_one(cursor, db, source_id, title, normalized, url_hash, content, published_date):
            inserted += 1

    print(f'--- Завершен: {target_url}. Вставлено: {inserted}, пропущено: {skipped} ---\n')
    return inserted, skipped


def run_parser():
    sources = load_sources()
    if not sources:
        print('❌ Нет включённых источников в sources_db. Пропускаем цикл.')
        return

    print(f'📋 Загружено включённых источников: {len(sources)}')

    db = get_connection('news')
    if db is None:
        return

    cursor = None
    total_inserted = 0
    total_skipped = 0
    try:
        cursor = db.cursor()

        # === ЦИКЛ ПО САЙТАМ (запись в БД происходит ВНУТРИ process_website) ===
        for source_id, name, url, domain, rss_url in sources:
            if rss_url:
                ins, skip = parse_rss(source_id, rss_url, cursor, db)
            else:
                ins, skip = process_website(source_id, url, domain, cursor, db)
            total_inserted += ins
            total_skipped += skip

        print(f'✅ Итого: вставлено {total_inserted}, пропущено {total_skipped}')
    except mysql.connector.Error as e:
        print(f'❌ Ошибка при работе с news_db: {e}')
    finally:
        if cursor is not None:
            cursor.close()
        if db.is_connected():
            db.close()


if __name__ == '__main__':
    interval = get_parse_interval()
    print(f'🚀 Парсер запущен. Интервал: {interval} секунд ({interval / 60:.0f} минут).')

    while True:
        try:
            print(f'\n=== Цикл парсинга начат: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} ===')
            run_parser()
            print(f'=== Цикл завершён. Следующий через {interval / 60:.0f} минут ===\n')
        except Exception as e:
            print(f'❌ Критическая ошибка в цикле: {e}')

        time.sleep(interval)