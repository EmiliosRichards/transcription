import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, Text, DateTime
import datetime
from app.config import settings

# Ensure the URL uses the asyncpg driver for asyncio compatibility
db_url = settings.DATABASE_URL
connect_args = {}

if db_url and db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if "sslmode" in db_url:
        # Extract sslmode from the URL and add it to connect_args
        # This is necessary because asyncpg doesn't support sslmode in the URL
        import re
        match = re.search(r"[?&]sslmode=([^&]+)", db_url)
        if match:
            sslmode = match.group(1)
            connect_args["ssl"] = sslmode
            db_url = re.sub(r"[?&]sslmode=([^&]+)", "", db_url)
            # Also remove channel_binding if it exists
            db_url = re.sub(r"[?&]channel_binding=([^&]+)", "", db_url)

engine = create_async_engine(db_url, connect_args=connect_args)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()

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
