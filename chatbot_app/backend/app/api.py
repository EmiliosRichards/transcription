import logging
from fastapi import APIRouter
from app.routers import search_router, transcription_router, chat_router, ingestion_router

# Create a new router
router = APIRouter()

# Include the routers from the other files
router.include_router(search_router.router)
router.include_router(transcription_router.router)
router.include_router(chat_router.router)
router.include_router(ingestion_router.router)