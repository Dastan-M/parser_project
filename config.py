import os


def get_db_config(db_type):
    """Возвращает (host, port, database) для нужной БД.

    db_type: 'sources' или 'news'
    """
    if db_type == 'sources':
        return (
            os.getenv('DB_SOURCES_HOST', '127.0.0.1'),
            int(os.getenv('DB_SOURCES_PORT', 3306)),
            'sources_db'
        )
    elif db_type == 'news':
        return (
            os.getenv('DB_NEWS_HOST', '127.0.0.1'),
            int(os.getenv('DB_NEWS_PORT', 3306)),
            'news_db'
        )
    else:
        raise ValueError(f'Unknown db_type: {db_type}')


def get_db_password():
    return os.getenv('MYSQL_ROOT_PASSWORD')


def get_parse_interval():
    return int(os.getenv('PARSE_INTERVAL', 3600))