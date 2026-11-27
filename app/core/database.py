from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import get_db_config, get_db_password

def create_db_engine(db_type):
    host, port, database = get_db_config(db_type)
    password = get_db_password()
    db_url = f"mysql+pymysql://root:{password}@{host}:{port}/{database}"
    return create_engine(db_url, echo=False, pool_pre_ping=True)

sources_engine = create_db_engine('sources')
news_engine = create_db_engine('news')

SourcesSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sources_engine)
NewsSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=news_engine)

def get_sources_db():
    db = SourcesSessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_news_db():
    db = NewsSessionLocal()
    try:
        yield db
    finally:
        db.close()