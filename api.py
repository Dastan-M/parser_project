from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from typing import Optional
from db import get_connection
import mysql.connector
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

app = FastAPI(title="Parser API", description="Сервис для работы с базой данных парсера")


# --- ЭНДПОИНТЫ ДЛЯ SOURCES (уже были) ---

@app.get("/sources")
def get_all_sources():
    db = get_connection('sources')
    if db is None:
        raise HTTPException(status_code=500, detail="DB connection failed")
    cursor = None
    try:
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT id, name, url, domain, enabled, rss_url FROM sources")
        return cursor.fetchall()
    finally:
        if cursor is not None: cursor.close()
        if db.is_connected(): db.close()


@app.get("/sources/{domain}")
def get_source_by_domain(domain: str):
    db = get_connection('sources')
    if db is None:
        raise HTTPException(status_code=500, detail="DB connection failed")
    cursor = None
    try:
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT id, name, url, domain, enabled, rss_url FROM sources WHERE domain = %s", (domain,))
        result = cursor.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail=f"Сайт '{domain}' не найден")
        return result
    finally:
        if cursor is not None: cursor.close()
        if db.is_connected(): db.close()


# --- НОВЫЕ ЭНДПОИНТЫ ДЛЯ NEWS ---

@app.get("/news")
def get_news(
        limit: int = Query(10, ge=1, le=100, description="Сколько новостей вернуть"),
        offset: int = Query(0, ge=0, description="Сколько новостей пропустить (для пагинации)"),
        source_id: Optional[int] = Query(None, description="Фильтр по ID источника"),
        date_from: Optional[str] = Query(None, description="Начало периода (ГГГГ-ММ-ДД)"),
        date_to: Optional[str] = Query(None, description="Конец периода (ГГГГ-ММ-ДД)")
):
    """Возвращает список новостей с фильтрами и пагинацией."""
    db = get_connection('news')
    if db is None:
        raise HTTPException(status_code=500, detail="DB connection failed")

    cursor = None
    try:
        cursor = db.cursor(dictionary=True)

        # Базовый запрос (без поля content, чтобы не передавать лишние мегабайты)
        query = "SELECT id, source_id, title, url, published_date, parsed_date FROM news WHERE 1=1"
        params = []

        # Динамически добавляем фильтры, если они переданы
        if source_id is not None:
            query += " AND source_id = %s"
            params.append(source_id)

        if date_from:
            query += " AND published_date >= %s"
            params.append(date_from)

        if date_to:
            query += " AND published_date <= %s"
            params.append(date_to)

        # Сортировка и пагинация
        query += " ORDER BY published_date DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, tuple(params))
        return cursor.fetchall()
    finally:
        if cursor is not None: cursor.close()
        if db.is_connected(): db.close()


@app.get("/news/{news_id}")
def get_news_by_id(news_id: int):
    """Возвращает ОДНУ новость по её ID со всем текстом."""
    db = get_connection('news')
    if db is None:
        raise HTTPException(status_code=500, detail="DB connection failed")

    cursor = None
    try:
        cursor = db.cursor(dictionary=True)
        # Здесь берем ВСЕ поля, включая content
        cursor.execute("SELECT * FROM news WHERE id = %s", (news_id,))
        result = cursor.fetchone()

        if not result:
            raise HTTPException(status_code=404, detail=f"Новость с ID {news_id} не найдена")

        return result
    finally:
        if cursor is not None: cursor.close()
        if db.is_connected(): db.close()


@app.get("/render", response_class=HTMLResponse)
async def render_page(url: str):
    """Открывает ссылку в браузере (со скрытием от Cloudflare) и возвращает HTML."""
    async with async_playwright() as p:
        # Запускаем браузер
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )

        # Создаем контекст с реалистичным разрешением и User-Agent
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        try:
            # Применяем маскировку
            await Stealth().apply_stealth_async(page)

            # Переходим и ждем
            await page.goto(url, timeout=60000, wait_until="domcontentloaded")

            # Ждем 10 секунд, чтобы Cloudflare успел пропустить
            await page.wait_for_timeout(10000)

            html_content = await page.content()
            return html_content

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ошибка рендеринга: {str(e)}")
        finally:
            await browser.close()