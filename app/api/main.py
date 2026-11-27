from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from app.core.db import get_connection
import mysql.connector
import hashlib
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from pydantic import HttpUrl
from contextlib import asynccontextmanager
import re

# --- БРАУЗЕР ---
playwright_instance = None
browser_instance = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global playwright_instance, browser_instance
    print("Запуск браузера Playwright...")
    playwright_instance = await async_playwright().start()
    browser_instance = await playwright_instance.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-setuid-sandbox"]
    )
    yield
    print("Закрытие браузера Playwright...")
    await browser_instance.close()
    await playwright_instance.stop()


app = FastAPI(title="Parser API", lifespan=lifespan)


# --- ЭНДПОИНТ 1: УМНЫЙ ПОИСК ПО ДОМЕНУ/ID ---
@app.get("/domain")
def search_by_domain(query: str = Query(..., description="ID (1), домен (nur.kz) или ссылка (https://nur.kz)")):
    # 1. Очищаем запрос: убираем http://, https:// и слеши на конце
    clean_query = query.replace('https://', '').replace('http://', '').strip('/')

    db_sources = get_connection('sources')
    if db_sources is None: raise HTTPException(status_code=500, detail="DB sources failed")

    source_info = None
    cursor_s = None
    try:
        cursor_s = db_sources.cursor(dictionary=True)

        # 2. Определяем: это ID (число) или домен?
        if clean_query.isdigit():
            cursor_s.execute("SELECT * FROM sources WHERE id = %s", (int(clean_query),))
        else:
            # Ищем по домену (например, nur.kz)
            cursor_s.execute("SELECT * FROM sources WHERE domain = %s", (clean_query,))

        source_info = cursor_s.fetchone()

        if not source_info:
            raise HTTPException(status_code=404, detail=f"Источник '{query}' не найден")

    finally:
        if cursor_s is not None: cursor_s.close()
        if db_sources.is_connected(): db_sources.close()

    # 3. Если сайт найден, ищем его новости
    db_news = get_connection('news')
    if db_news is None: raise HTTPException(status_code=500, detail="DB news failed")

    cursor_n = None
    try:
        cursor_n = db_news.cursor(dictionary=True)
        # Ищем новости по ID источника
        cursor_n.execute(
            "SELECT id, title, url, published_date, parsed_date FROM news WHERE source_id = %s ORDER BY published_date DESC",
            (source_info['id'],)
        )
        news_list = cursor_n.fetchall()

        return {
            "source": source_info,
            "news_count": len(news_list),
            "news": news_list
        }
    finally:
        if cursor_n is not None: cursor_n.close()
        if db_news.is_connected(): db_news.close()


# --- ЭНДПОИНТ 2: ПОИСК КОНКРЕТНОЙ НОВОСТИ ПО ССЫЛКЕ ---
@app.get("/news")
def search_by_link(url: str = Query(..., description="Точная ссылка на новость")):
    # Генерируем хэш ссылки (как в парсере), чтобы найти новость
    url_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()

    db = get_connection('news')
    if db is None: raise HTTPException(status_code=500, detail="DB failed")

    cursor = None
    try:
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM news WHERE url_hash = %s", (url_hash,))
        result = cursor.fetchone()

        if not result:
            raise HTTPException(status_code=404, detail=f"Новость с такой ссылкой не найдена")

        return result
    finally:
        if cursor is not None: cursor.close()
        if db.is_connected(): db.close()


# --- ЭНДПОИНТ 3: БРАУЗЕР (RENDER) ---
@app.get("/render", response_class=HTMLResponse)
async def render_page(url: HttpUrl):
    global browser_instance
    context = await browser_instance.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080}
    )
    page = await context.new_page()
    try:
        await Stealth().apply_stealth_async(page)
        await page.goto(str(url), timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(8000)
        html_content = await page.content()
        return html_content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка рендеринга: {str(e)}")
    finally:
        await context.close()