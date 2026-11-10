import csv
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import requests
import os
from datetime import datetime

def parse_website(target_url):

  collected_links = []

  try:
    response = requests.get(target_url, timeout=10, verify=False)

    if response.status_code == 200:
      soup = BeautifulSoup(response.text, 'html.parser')
      links = soup.find_all('a')
      print(response.status_code)

      for link in links:
        title = link.get_text(strip=True)
        href = link.get('href')

        if href:
          full_url = urljoin(target_url, href)
          collected_links.append([target_url, title, full_url])
    else:
      print(f'Сайт ответил со статусом: {response.status_code}')

  except Exception as e:
    print(f'Ошибка при запросе к {target_url}: {e}')

  return collected_links

if __name__ == '__main__':
  urls = ['https://nur.kz', 'https://inform.kz', 'https://kaztag.kz']
  all_data = []

  for site_url in urls:
    site_data = parse_website(site_url)
    all_data.extend(site_data)

  # Папка для сохранения: по умолчанию "data" (локально), в Docker будет "/data"
  data_dir = os.environ.get('DATA_DIR', 'data')
  os.makedirs(data_dir, exist_ok=True)

  # Имя файла с датой и временем: parsed_links_2026-11-10_14-30.csv
  timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
  filename = os.path.join(data_dir, f'parsed_links_{timestamp}.csv')

  with open(filename, mode='w', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    writer.writerow(['Source_Website', 'Link_Text', 'Full_URL'])
    writer.writerows(all_data)

  print(f'Данные сохранены в {filename}')
