from fastapi import APIRouter, Form, HTTPException, Depends, status
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
import hashlib, os, uuid
import urllib.request
import urllib.parse

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
    url: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    campaign: Optional[str] = Form(None),
    campaign_id: Optional[str] = Form(None),
    recording_id: Optional[str] = Form(None),
    b2_prefix: Optional[str] = Form(None),
):
    if not recording_id and not url:
        raise HTTPException(status_code=400, detail="Provide recording_id or url")

    b2_key = None
    source_url = url

    def _derive_ext(filename_or_url: str) -> str:
        try:
            path = urllib.parse.urlparse(filename_or_url).path
            base = os.path.basename(path)
        except Exception:
            base = filename_or_url
        ext = os.path.splitext(base)[1]
        return ext if ext else ".mp3"

    # 1) Look up metadata from source DB (public.recordings + contacts + campaign_map)
    # Source of truth: DB. Provided phone/campaign are only fallback/cross-check.
    row = None
    try:
        if recording_id:
            # 1) Try exact match by recordings.id (cast to text to support non-numeric ids)
            stmt = text(
                """
                SELECT r.id AS rec_id,
                       r.location AS url,
                       c."$phone" AS phone_raw,
                       c."$campaign_id" AS campaign_id,
                       COALESCE(cm.campaign, c."$campaign_id") AS campaign_name,
                       r.started::timestamptz AS started,
                       r.stopped::timestamptz AS stopped
                FROM public.recordings r
                JOIN public.contacts c ON r.contact_id = c."$id"
                LEFT JOIN public.campaign_map cm ON cm.campaign_id = c."$campaign_id"
                WHERE r.id::text = :rid
                LIMIT 1
                """
            )
            res = await db.execute(stmt, {"rid": recording_id})
            row = res.first()
            # 2) Fallback: try to find the token inside the URL
            if row is None:
                stmt = text(
                    """
                    SELECT r.id AS rec_id,
                           r.location AS url,
                           c."$phone" AS phone_raw,
                           c."$campaign_id" AS campaign_id,
                           COALESCE(cm.campaign, c."$campaign_id") AS campaign_name,
                           r.started::timestamptz AS started,
                           r.stopped::timestamptz AS stopped
                    FROM public.recordings r
                    JOIN public.contacts c ON r.contact_id = c."$id"
                    LEFT JOIN public.campaign_map cm ON cm.campaign_id = c."$campaign_id"
                    WHERE r.location LIKE ('%' || :rid || '%')
                    LIMIT 1
                    """
                )
                res = await db.execute(stmt, {"rid": recording_id})
                row = res.first()
        if row is None and url:
            stmt = text(
                """
                SELECT r.id AS rec_id,
                       r.location AS url,
                       c."$phone" AS phone_raw,
                       c."$campaign_id" AS campaign_id,
                       COALESCE(cm.campaign, c."$campaign_id") AS campaign_name,
                       r.started::timestamptz AS started,
                       r.stopped::timestamptz AS stopped
                FROM public.recordings r
                JOIN public.contacts c ON r.contact_id = c."$id"
                LEFT JOIN public.campaign_map cm ON cm.campaign_id = c."$campaign_id"
                WHERE r.location = :url
                LIMIT 1
                """
            )
            res = await db.execute(stmt, {"url": url})
            row = res.first()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB lookup failed: {e}")

    if row is None:
        raise HTTPException(status_code=404, detail="Recording not found in DB by id or url")

    rec_id = int(row.rec_id)
    source_url = str(row.url)
    # Normalize phone from DB; fallback to provided phone
    def _norm_phone(v: Optional[str]) -> str:
        if not v:
            return (phone or "unknown")
        return ''.join(ch for ch in v.strip() if ch.isdigit() or ch == '+') or (phone or "unknown")
    phone_norm = _norm_phone(row.phone_raw if hasattr(row, 'phone_raw') else None)
    campaign_label = (campaign or campaign_id or (row.campaign_name if hasattr(row,'campaign_name') else None) or 'unspecified').replace('/', '_')

    safe_phone = phone_norm.replace("/", "_")
    safe_campaign = campaign_label
    # Conventional layout: <campaign>/audio/<phone>/<uuid>.<ext> with optional leading override prefix
    base_prefix_default = f"{safe_campaign}/audio"
    base_prefix = f"{b2_prefix.rstrip('/')}/{base_prefix_default}" if b2_prefix else base_prefix_default

    # Upload to B2 from the source URL
    storage = get_storage_service()
    ext = _derive_ext(source_url)
    object_key = f"{base_prefix}/{safe_phone}/{uuid.uuid4().hex}{ext}"
    tmp_path = f"/tmp/{uuid.uuid4().hex}{ext}"
    try:
        with urllib.request.urlopen(source_url) as resp, open(tmp_path, "wb") as out:
            out.write(resp.read())
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to download url: {e}")
    ok = storage.upload_file(tmp_path, object_key)
    try:
        os.remove(tmp_path)
    except Exception:
        pass
    if not ok:
        raise HTTPException(status_code=500, detail="Upload to B2 failed")
    b2_key = object_key
    b2_url = f"b2://{object_key}"

    url_sha1 = hashlib.sha1((source_url or uuid.uuid4().hex).encode("utf-8")).hexdigest()
    stmt = text(
        """
        INSERT INTO media_pipeline.audio_files (
            phone, campaign_name, recording_id,
            url, url_sha1,
            started, stopped,
            b2_object_key, file_size_bytes,
            source_table, source_row_id
        ) VALUES (
            :phone, :campaign_name, :recording_id,
            :url, :url_sha1,
            :started, :stopped,
            :b2_key, :size_bytes,
            :source_table, :source_row_id
        )
        ON CONFLICT (url_sha1) DO UPDATE SET url = EXCLUDED.url
        RETURNING id
        """
    )
    res = await db.execute(
        stmt,
        {
            "phone": phone_norm,
            "campaign_name": safe_campaign,
            "recording_id": recording_id,
            "url": source_url,
            "url_sha1": url_sha1,
            "b2_key": b2_key,
            "size_bytes": None,
            "started": row.started if hasattr(row, 'started') else None,
            "stopped": row.stopped if hasattr(row, 'stopped') else None,
            "source_table": "public.recordings",
            "source_row_id": rec_id,
        },
    )
    row = res.first()
    await db.commit()
    audio_file_id = row[0] if row else None
    return {"audio_file_id": audio_file_id, "status": "QUEUED", "b2_key": b2_key, "b2_url": b2_url}

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


