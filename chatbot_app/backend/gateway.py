from fastapi import FastAPI
from app.routers.transcription_router import router as transcription_router
from app.routers.media_router import router as media_router

app = FastAPI(title="Transcription Gateway")
app.include_router(transcription_router, prefix="/api", tags=["Transcription"])
app.include_router(media_router, prefix="/api", tags=["Media"])


