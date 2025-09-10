import os
from urllib.parse import urlparse, parse_qsl, urlencode
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.config import settings
import datetime

# --- Async/Sync DB Setup with conditional SSL ---
raw_db_url = settings.DATABASE_URL

def _normalize_async_db_url(url: str) -> str:
    # Ensure async driver scheme
    if url.startswith("postgresql+psycopg2://"):
        url = "postgresql+asyncpg://" + url.split("://", 1)[1]
    elif url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url.split("://", 1)[1]
    elif url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
        url = "postgresql+asyncpg://" + url.split("://", 1)[1]

    # Drop ALL query parameters to avoid passing libpq-only args (e.g., channel_binding) to asyncpg
    parsed = urlparse(url)
    sanitized = parsed._replace(query="").geturl()
    return sanitized

async_db_url = _normalize_async_db_url(raw_db_url)

# Decide if SSL is needed (remote DBs typically require SSL)
parsed = urlparse(async_db_url)
host = (parsed.hostname or "").lower()
orig_has_sslmode_disable = "sslmode=disable" in raw_db_url.lower()
need_ssl = not (orig_has_sslmode_disable or host in ("localhost", "127.0.0.1"))

async_engine = create_async_engine(
    async_db_url,
    pool_pre_ping=True,
    # asyncpg expects a boolean or SSLContext for "ssl"; never "sslmode"
    connect_args={"ssl": True} if need_ssl else {}
)
AsyncSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=async_engine)

# For sync operations/tools, use psycopg2
sync_db_url = raw_db_url.replace("postgresql+asyncpg", "postgresql+psycopg2")
sync_engine = create_engine(
    sync_db_url,
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
