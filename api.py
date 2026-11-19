from fastapi import FastAPI, HTTPException
from db import get_connection
import mysql.connector

# Создаем приложение FastAPI
app = FastAPI(title="Parser API", description="Сервис для работы с базой источников")


@app.get("/sources")
def get_all_sources():
    """Возвращает список ВСЕХ сайтов из sources_db."""
    db = get_connection('sources')
    if db is None:
        raise HTTPException(status_code=500, detail="DB connection failed")

    cursor = None
    try:
        # dictionary=True возвращает данные в виде словарей, а не кортежей (важно для JSON!)
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT id, name, url, domain, enabled, rss_url FROM sources")
        result = cursor.fetchall()
        return result
    except mysql.connector.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor is not None:
            cursor.close()
        if db.is_connected():
            db.close()


@app.get("/sources/{domain}")
def get_source_by_domain(domain: str):
    """Ищет ОДИН сайт по его домену (например, nur.kz)."""
    db = get_connection('sources')
    if db is None:
        raise HTTPException(status_code=500, detail="DB connection failed")

    cursor = None
    try:
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, name, url, domain, enabled, rss_url FROM sources WHERE domain = %s",
            (domain,)
        )
        result = cursor.fetchone()

        if not result:
            raise HTTPException(status_code=404, detail=f"Сайт '{domain}' не найден")

        return result
    except mysql.connector.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor is not None:
            cursor.close()
        if db.is_connected():
            db.close()