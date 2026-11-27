from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, TIMESTAMP, text
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Source(Base):
    __tablename__ = 'sources'
    __table_args__ = {'schema': 'sources_db'}

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    url = Column(String(2048), nullable=False)
    domain = Column(String(255), unique=True, nullable=False)
    enabled = Column(Boolean, default=True)
    rss_url = Column(String(2048), nullable=True)
    use_browser = Column(Boolean, default=False)

class News(Base):
    __tablename__ = 'news'
    __table_args__ = {'schema': 'news_db'}

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, nullable=False)
    title = Column(String(500))
    url = Column(String(2048), nullable=False)
    url_hash = Column(String(64), unique=True, nullable=False)
    content = Column(Text)
    published_date = Column(DateTime, nullable=True)
    parsed_date = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'))