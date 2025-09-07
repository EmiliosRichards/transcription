from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, status
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
import hashlib, os, uuid

from app import database
from app.config import settings
from app.services.storage import get_storage_service

router = APIRouter()

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

async def get_db():
    async with database.AsyncSessionLocal() as session:
        yield session

async def get_api_key(api_key: str = Depends(api_key_header)):
    if api_key != settings.API_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    return api_key

@router.post("/media/transcribe", dependencies=[Depends(get_api_key)], status_code=202)
async def enqueue_transcription(
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(None),
    url: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    b2_prefix: str = Form("dexter/audio"),
):
    if not file and not url:
        raise HTTPException(status_code=400, detail="Provide file or url")

    b2_key = None
    source_url = url

    if file:
        storage = get_storage_service()
        ext = os.path.splitext(file.filename or "")[1] or ".wav"
        safe_phone = (phone or "unknown").replace("/", "_")
        object_key = f"{b2_prefix}/{safe_phone}/{uuid.uuid4().hex}{ext}"
        tmp_path = f"/tmp/{uuid.uuid4().hex}{ext}"
        with open(tmp_path, "wb") as f:
            f.write(await file.read())
        ok = storage.upload_file(tmp_path, object_key)
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        if not ok:
            raise HTTPException(status_code=500, detail="Upload to B2 failed")
        b2_key = object_key
        source_url = f"b2://{object_key}"

    url_sha1 = hashlib.sha1((source_url or b2_key or uuid.uuid4().hex).encode("utf-8")).hexdigest()
    stmt = text(
        """
        INSERT INTO media_pipeline.audio_files (url, url_sha1, b2_object_key, phone)
        VALUES (:url, :url_sha1, :b2_key, :phone)
        ON CONFLICT (url_sha1) DO UPDATE SET url = EXCLUDED.url
        RETURNING id
        """
    )
    res = await db.execute(stmt, {"url": source_url, "url_sha1": url_sha1, "b2_key": b2_key, "phone": phone})
    row = res.first()
    await db.commit()
    audio_file_id = row[0] if row else None
    return {"audio_file_id": audio_file_id, "status": "QUEUED", "b2_key": b2_key}

@router.get("/media/status/{audio_file_id}", dependencies=[Depends(get_api_key)])
async def get_status(audio_file_id: int, db: AsyncSession = Depends(get_db)):
    stmt = text(
        """
        SELECT status, transcript_text, metadata
        FROM media_pipeline.transcriptions
        WHERE audio_file_id = :id
        ORDER BY id DESC
        LIMIT 1
        """
    )
    res = await db.execute(stmt, {"id": audio_file_id})
    row = res.first()
    if not row:
        return {"status": "pending"}
    status_val, transcript, metadata = row
    return {"status": status_val, "transcript": transcript, "metadata": metadata}


