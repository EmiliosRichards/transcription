import os
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.config import settings
import datetime

# --- Async/Sync DB Setup with conditional SSL ---
db_url = settings.DATABASE_URL
need_ssl = not ("sslmode=disable" in db_url or "localhost" in db_url or "127.0.0.1" in db_url)

async_engine = create_async_engine(
    db_url,
    pool_pre_ping=True,
    connect_args={'ssl': 'require'} if need_ssl else {}
)
AsyncSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=async_engine)

sync_engine = create_engine(
    db_url.replace("postgresql+asyncpg", "postgresql+psycopg2"),
    pool_pre_ping=True
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)


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
    processed_segments = Column(JSON, nullable=True)
    raw_segments = Column(JSON, nullable=True)
    audio_file_path = Column(String, nullable=False, server_default="")

class ChatLog(Base):
    __tablename__ = "chat_logs"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    role = Column(String) # "user" or "assistant"
    content = Column(Text)

# --- Utility to create tables ---

async def create_db_and_tables():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
