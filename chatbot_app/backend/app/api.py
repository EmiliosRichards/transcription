import logging
from fastapi import APIRouter
from app.routers import search_router, transcription_router, chat_router, ingestion_router

# Create a new router
router = APIRouter()

# Include the routers from the other files
router.include_router(search_router.router, prefix="/v1/search", tags=["Search"])
router.include_router(transcription_router.router, prefix="/v1/transcribe", tags=["Transcription"])
router.include_router(chat_router.router, prefix="/v1/chat", tags=["Chat"])
router.include_router(ingestion_router.router, prefix="/v1/ingestion", tags=["Ingestion"])