import csv
import os
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import requests


def parse_website(target_url):
    collected_links = []
    print(f'--- Начинаем парсинг: {target_url} ---')

    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(target_url, timeout=10, headers=headers)

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

    data_dir = os.environ.get('DATA_DIR', 'data')
    os.makedirs(data_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
    filename = os.path.join(data_dir, f'parsed_links_{timestamp}.csv')

    with open(filename, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Source_Website', 'Link_Text', 'Full_URL'])
        writer.writerows(all_data)

    print(f'✅ Данные сохранены в {filename}')