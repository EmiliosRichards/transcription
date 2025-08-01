import os
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings
import datetime

# The asyncpg driver expects SSL settings in connect_args, not the URL query.
db_url_without_query = settings.DATABASE_URL.split('?')[0]
engine = create_async_engine(
    db_url_without_query,
    pool_pre_ping=True,
    connect_args={'ssl': 'require'}
)
AsyncSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

# --- Database Models ---

class Transcription(Base):
    __tablename__ = "transcriptions"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    audio_source = Column(String, index=True)
    raw_transcription = Column(Text)
    processed_transcription = Column(Text)
    corrected_transcription = Column(Text, nullable=True)

class ChatLog(Base):
    __tablename__ = "chat_logs"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    role = Column(String) # "user" or "assistant"
    content = Column(Text)

# --- Utility to create tables ---

async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
