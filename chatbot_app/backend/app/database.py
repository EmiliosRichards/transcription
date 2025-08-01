import os
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import datetime

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("No DATABASE_URL set for the project. Please set it in the .env file.")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
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

def create_db_and_tables():
    Base.metadata.create_all(bind=engine)
