import os
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.config import settings
import datetime

# --- Async Setup ---
# The asyncpg driver expects SSL settings in connect_args, not the URL query.
db_url_without_query = settings.DATABASE_URL.split('?')[0]
async_engine = create_async_engine(
    db_url_without_query,
    pool_pre_ping=True,
    connect_args={'ssl': 'require'}
)
AsyncSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=async_engine)

# --- Sync Setup ---
# The psycopg2 driver expects SSL settings in the URL query.
sync_engine = create_engine(
    settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2"),
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
