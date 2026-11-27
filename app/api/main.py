from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import hashlib
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from pydantic import HttpUrl
from contextlib import asynccontextmanager

# Импортируем наши модели и зависимости для БД
from app.core.models import Source, News
from app.core.database import get_sources_db, get_news_db

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


# --- ЭНДПОИНТ 1: УМНЫЙ ПОИСК ПО ДОМЕНУ/ID (ЧЕРЕЗ ORM) ---
@app.get("/domain")
def search_by_domain(
        query: str = Query(..., description="ID (1), домен (nur.kz) или ссылка (https://nur.kz)"),
        sources_db: Session = Depends(get_sources_db),
        news_db: Session = Depends(get_news_db)
):
    clean_query = query.replace('https://', '').replace('http://', '').strip('/')

    # Ищем источник через ORM
    if clean_query.isdigit():
        source_info = sources_db.query(Source).filter(Source.id == int(clean_query)).first()
    else:
        source_info = sources_db.query(Source).filter(Source.domain == clean_query).first()

    if not source_info:
        raise HTTPException(status_code=404, detail=f"Источник '{query}' не найден")

    # Ищем новости через ORM (сортируем по дате)
    news_list = news_db.query(News).filter(News.source_id == source_info.id).order_by(News.published_date.desc()).all()

    # Превращаем объекты SQLAlchemy в обычные словари для JSON-ответа
    source_dict = {
        "id": source_info.id,
        "name": source_info.name,
        "domain": source_info.domain,
        "enabled": source_info.enabled,
        "rss_url": source_info.rss_url,
        "use_browser": source_info.use_browser
    }

    news_dicts = [
        {
            "id": n.id,
            "title": n.title,
            "url": n.url,
            "published_date": n.published_date,
            "parsed_date": n.parsed_date
        } for n in news_list
    ]

    return {
        "source": source_dict,
        "news_count": len(news_dicts),
        "news": news_dicts
    }


# --- ЭНДПОИНТ 2: ПОИСК КОНКРЕТНОЙ НОВОСТИ ПО ССЫЛКЕ (ЧЕРЕЗ ORM) ---
@app.get("/news")
def search_by_link(
        url: str = Query(..., description="Точная ссылка на новость"),
        news_db: Session = Depends(get_news_db)
):
    url_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()

    # Ищем новость по хэшу через ORM
    result = news_db.query(News).filter(News.url_hash == url_hash).first()

    if not result:
        raise HTTPException(status_code=404, detail="Новость с такой ссылкой не найдена")

    return {
        "id": result.id,
        "source_id": result.source_id,
        "title": result.title,
        "url": result.url,
        "content": result.content,
        "published_date": result.published_date,
        "parsed_date": result.parsed_date
    }


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