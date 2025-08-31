import logging
from fastapi import APIRouter
from app.routers import search_router, transcription_router, chat_router, ingestion_router
from app.routers import fusion_router

# Create a new router
router = APIRouter()

# Include the routers from the other files
router.include_router(search_router.router, tags=["Search"])
router.include_router(transcription_router.router, tags=["Transcription"])
router.include_router(chat_router.router, tags=["Chat"])
router.include_router(ingestion_router.router, tags=["Ingestion"])
router.include_router(fusion_router.router, tags=["Fusion"])