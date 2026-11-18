import mysql.connector
from config import get_db_config, get_db_password


def get_connection(db_type):
    """Универсальное подключение к БД.

    db_type: 'sources' или 'news'
    Возвращает mysql.connector.connection или None при ошибке.
    """
    host, port, database = get_db_config(db_type)
    try:
        return mysql.connector.connect(
            host=host,
            port=port,
            user='root',
            password=get_db_password(),
            database=database,
            charset='utf8mb4'
        )
    except mysql.connector.Error as e:
        print(f'❌ Не удалось подключиться к {database} ({host}:{port}): {e}')
        return None


def url_exists(cursor, url_hash):
    """Проверяет, есть ли уже новость с таким url_hash в news_db."""
    cursor.execute("SELECT 1 FROM news WHERE url_hash = %s LIMIT 1", (url_hash,))
    return cursor.fetchone() is not None


def save_news_one(cursor, db, source_id, title, url, url_hash, content, published_date):
    """Вставляет ОДНУ новость и сразу коммитит.

    Возвращает True, если вставлено, False — если уже была (или ошибка).
    """
    try:
        cursor.execute(
            "INSERT INTO news "
            "(source_id, title, url, url_hash, content, published_date) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (source_id, title, url, url_hash, content, published_date)
        )
        db.commit()
        return cursor.rowcount > 0
    except mysql.connector.Error as e:
        print(f'❌ Ошибка при вставке {url[:60]}: {e}')
        db.rollback()
        return False