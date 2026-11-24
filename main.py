import os
import re
import time
import hashlib
from datetime import datetime
from urllib.parse import urljoin, urlparse
import requests
import mysql.connector
import trafilatura
import feedparser
from parsel import Selector
from courlan import normalize_url

from config import get_parse_interval, get_db_password
from db import get_connection, url_exists, save_news_one

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
API_URL = os.getenv('API_URL', 'http://localhost:8077')


def fetch_html(url, use_browser=False):
    """Единая функция скачивания. Либо через requests, либо через наш API /render."""
    try:
        if use_browser:
            print(f'  🌐 Запрос через браузер (API): {url[:60]}')
            # Делаем запрос к нашему FastAPI
            response = requests.get(f"{API_URL}/render", params={"url": url}, timeout=90)
        else:
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
    try:
        metadata = trafilatura.extract_metadata(html)
        published_date = parse_date(metadata.date) if metadata and metadata.date else None
        content = trafilatura.extract(html, include_comments=False, include_tables=False, favor_recall=True)
        return content, published_date
    except Exception as e:
        return None, None


def parse_date(date_str):
    if not date_str: return None
    for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%d.%m.%Y', '%Y/%m/%d']:
        try:
            return datetime.strptime(date_str[:19], fmt).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
    return None


def load_sources():
    db = get_connection('sources')
    if db is None: return []
    cursor = None
    try:
        cursor = db.cursor()
        # Добавили use_browser
        cursor.execute("SELECT id, name, url, domain, rss_url, use_browser FROM sources WHERE enabled = TRUE")
        return cursor.fetchall()
    finally:
        if cursor is not None: cursor.close()
        if db.is_connected(): db.close()


def get_news_xpath(domain):
    if 'kaztag' in domain: return '//div[@class="top-inner"]//a[@href]'
    if 'nur.kz' in domain: return '//article//a[@href]'
    if 'zakon.kz' in domain: return '//a[contains(@href, ".html")]'
    return '//a[@href]'


def parse_rss(source_id, rss_url, cursor, db, use_browser, max_news=30):
    print(f'--- Начинаем парсинг RSS: {rss_url} ---')
    # Скачиваем саму RSS-ленту тоже через нашу единую функцию!
    rss_xml = fetch_html(rss_url, use_browser)
    if not rss_xml:
        return 0, 0

    feed = feedparser.parse(rss_xml)  # Передаем текст, а не URL

    if not feed.entries:
        print(f'  ⚠️ RSS пустой: {rss_url}')
        return 0, 0

    inserted, skipped = 0, 0
    for entry in feed.entries[:max_news]:
        title = (entry.get('title', '') or '').strip()
        link = (entry.get('link', '') or '').strip()
        published = entry.get('published', '')
        if not title or not link: continue

        normalized = normalize_url(link.split('#')[0])
        if not normalized: continue
        url_hash = hashlib.sha256(normalized.encode('utf-8')).hexdigest()

        if url_exists(cursor, url_hash):
            skipped += 1
            continue

        print(f'  [{inserted + 1}] Скачиваем: {title[:50]}...')
        article_html = fetch_html(normalized, use_browser)  # Используем use_browser
        if not article_html: continue

        content, published_date = extract_article(article_html)
        if not published_date and published:
            published_date = parse_date(published)

        if save_news_one(cursor, db, source_id, title, normalized, url_hash, content, published_date):
            inserted += 1
        if inserted >= max_news: break

    return inserted, skipped


def process_website(source_id, target_url, source_domain, cursor, db, use_browser, max_news=15):
    print(f'--- Начинаем парсинг HTML: {target_url} ---')
    html = fetch_html(target_url, use_browser)  # Используем use_browser
    if not html: return 0, 0

    selector = Selector(text=html)
    news_elements = selector.xpath(get_news_xpath(source_domain))
    if not news_elements: news_elements = selector.xpath('//a[@href]')

    seen_urls, inserted, skipped = set(), 0, 0
    for link in news_elements:
        if inserted >= max_news: break
        title = (link.xpath('normalize-space(string(.))').get() or '').strip()
        href = link.attrib.get('href', '')
        if not href or not title: continue

        full_url = urljoin(target_url, href)
        if not full_url.startswith(('http://', 'https://')): continue
        if not urlparse(full_url).netloc.endswith(source_domain): continue
        if not re.search(r'(/\d{5,})|(/news/[a-z0-9\-]{10,})|(/\d{6,}-)', full_url): continue

        normalized = normalize_url(full_url.split('#')[0])
        if not normalized or normalized in seen_urls: continue
        seen_urls.add(normalized)

        url_hash = hashlib.sha256(normalized.encode('utf-8')).hexdigest()
        if url_exists(cursor, url_hash):
            skipped += 1
            continue

        print(f'  [{inserted + 1}] Скачиваем: {title[:50]}...')
        article_html = fetch_html(normalized, use_browser)  # Используем use_browser
        if not article_html: continue

        content, published_date = extract_article(article_html)
        if save_news_one(cursor, db, source_id, title, normalized, url_hash, content, published_date):
            inserted += 1
    return inserted, skipped


def run_parser():
    sources = load_sources()
    if not sources:
        print('❌ Нет источников.')
        return

    db = get_connection('news')
    if db is None: return
    cursor = db.cursor()

    total_ins, total_skip = 0, 0
    try:
        for source_id, name, url, domain, rss_url, use_browser in sources:
            if rss_url:
                ins, skip = parse_rss(source_id, rss_url, cursor, db, use_browser)
            else:
                ins, skip = process_website(source_id, url, domain, cursor, db, use_browser)
            total_ins += ins
            total_skip += skip
        print(f'✅ Итого: вставлено {total_ins}, пропущено {total_skip}')
    finally:
        cursor.close()
        db.close()


if __name__ == '__main__':
    interval = get_parse_interval()
    print(f'🚀 Парсер запущен. Интервал: {interval} сек.')
    while True:
        try:
            print(f'\n=== Цикл: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} ===')
            run_parser()
            print(f'=== Ждем {interval / 60:.0f} минут ===\n')
        except Exception as e:
            print(f'❌ Ошибка: {e}')
        time.sleep(interval)