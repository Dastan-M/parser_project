import os
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


if __name__ == '__main__':
    urls = ['https://nur.kz', 'https://inform.kz', 'https://kaztag.kz']
    all_data = []

    for site_url in urls:
        site_data = parse_website(site_url)
        all_data.extend(site_data)

    # Подключение к MySQL (порт 3307!)
    print('Подключаемся к базе данных...')
    db = mysql.connector.connect(
        host='127.0.0.1',
        port=3307,
        user='root',
        password='mysecretpassword',
        database='parser_db',
        charset='utf8mb4'  # <--- ДОБАВЛЯЕМ КОДИРОВКУ
    )
    cursor = db.cursor()

    # Вставляем каждую ссылку в таблицу
    print(f'Вставляем {len(all_data)} ссылок в базу...')
    for row in all_data:
        cursor.execute(
            "INSERT INTO links (site, title, url) VALUES (%s, %s, %s)",
            (row[0], row[1], row[2])
        )
    db.commit()

    # Исправляем вывод количества строк
    print(f'✅ Вставлено {len(all_data)} строк в таблицу links')

    cursor.close()
    db.close()
    print('Соединение с базой закрыто.')