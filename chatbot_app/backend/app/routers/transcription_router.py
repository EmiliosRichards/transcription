import logging
import os
import tempfile
import datetime
import shutil
import json
from fastapi import APIRouter, HTTPException, File, UploadFile, Form, Depends, BackgroundTasks, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
import mimetypes
from pydantic import BaseModel, Field
from typing import Optional, List, AsyncGenerator, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app import database
from app.services import llm_handler, transcription, prompt_engine, task_manager
from app.services.storage import get_storage_service

# --- Logging Setup ---
logger = logging.getLogger(__name__)

# --- Router Setup ---
router = APIRouter()

# --- DB Dependency ---
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with database.AsyncSessionLocal() as session:
        yield session

# --- Pydantic Models ---
class CompanyNameCorrectionRequest(BaseModel):
    transcription_id: int
    full_transcript: str
    correct_company_name: str

class CorrectedTranscription(BaseModel):
    corrected_transcript: str = Field(..., description="The final transcript with the company name corrected.")

class TranscriptionInfo(BaseModel):
    id: int
    audio_source: Optional[str] = None
    created_at: datetime.datetime
    audio_file_path: Optional[str] = None
    
    class Config:
        from_attributes = True

# --- Background Tasks ---

async def run_pipeline_task(temp_path: str, audio_source: str, task_id: str):
    """
    Wrapper function to run the TranscriptionPipeline in the background.
    """
    async with database.AsyncSessionLocal() as db:
        pipeline = transcription.TranscriptionPipeline(
            db=db,
            task_id=task_id,
            temp_path=temp_path,
            audio_source=audio_source
        )
        await pipeline.run()

# --- API Endpoints ---
class TaskStatus(BaseModel):
    status: str
    progress: int
    message: str
    result: Optional[Dict[str, Any]] = None

@router.get("/tasks/{task_id}", response_model=TaskStatus, tags=["Transcription"])
async def get_task_status(task_id: str):
    """Retrieves the status of a specific transcription task."""
    status = task_manager.get_task_status(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return status

@router.post("/transcribe", tags=["Transcription"], status_code=202)
async def transcribe(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None)
):
    """Transcribes an audio file from a file upload or a URL."""
    if not file and not url:
        raise HTTPException(status_code=400, detail="Either a file or a URL must be provided.")

    task_id = task_manager.create_task()
    try:
        temp_dir = tempfile.mkdtemp()
        audio_source = file.filename if file and file.filename else url or ""
        
        if file and file.filename:
            temp_path = os.path.join(temp_dir, file.filename)
            with open(temp_path, "wb") as buffer:
                buffer.write(await file.read())
        elif url:
            temp_path = transcription.download_file(url, temp_dir, task_id)
        else:
            shutil.rmtree(temp_dir)
            raise HTTPException(status_code=400, detail="No valid audio source provided.")

        background_tasks.add_task(run_pipeline_task, temp_path, audio_source, task_id)
        return {"task_id": task_id, "message": "Transcription task started."}

    except Exception as e:
        logger.error(f"Failed to start transcription task {task_id}: {e}", exc_info=True)
        task_manager.set_task_error(task_id, f"Failed to start task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start transcription task: {e}")


@router.post("/correct-company-name", tags=["Transcription"], response_model=CorrectedTranscription)
async def correct_company_name(request: CompanyNameCorrectionRequest, db: AsyncSession = Depends(get_db)):
    """Uses an LLM to replace an incorrect company name in a transcript."""
    logger.info(f"Received request to /correct-company-name for ID: {request.transcription_id}")
    try:
        stmt = select(database.Transcription).filter(database.Transcription.id == request.transcription_id)
        result = await db.execute(stmt)
        db_transcription = result.scalars().first()
        if not db_transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")

        prompt = prompt_engine.create_prompt_from_template(
            "correct_company_name.txt",
            {"full_transcript": request.full_transcript, "correct_company_name": request.correct_company_name}
        )
        response_data = await llm_handler.get_structured_response(prompt, response_model=CorrectedTranscription)
        
        db_transcription.corrected_transcription = response_data.corrected_transcript # type: ignore
        await db.commit()
        return response_data

    except Exception as e:
        logger.error(f"An error occurred during company name correction: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@router.get("/transcriptions", tags=["Transcription"], response_model=List[TranscriptionInfo])
async def get_transcriptions(db: AsyncSession = Depends(get_db)):
    """Retrieves a list of all past transcriptions."""
    logger.info("Received request to /transcriptions")
    try:
        stmt = select(database.Transcription).order_by(database.Transcription.created_at.desc())
        result = await db.execute(stmt)
        transcriptions = result.scalars().all()
        return [TranscriptionInfo.from_orm(t) for t in transcriptions]
    except Exception as e:
        logger.error(f"An error occurred while fetching transcriptions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.get("/transcriptions/{transcription_id}", tags=["Transcription"], response_model=Dict[str, Any])
async def get_transcription(transcription_id: int, db: AsyncSession = Depends(get_db)):
    """Retrieves a single transcription by its ID."""
    logger.info(f"Received request for transcription ID: {transcription_id}")
    stmt = select(database.Transcription).filter(database.Transcription.id == transcription_id)
    result = await db.execute(stmt)
    db_transcription = result.scalars().first()
    if not db_transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")
    
    response_data = {
        "id": db_transcription.id,
        "audio_source": db_transcription.audio_source,
        "created_at": db_transcription.created_at,
        "raw_transcription": db_transcription.raw_transcription,
        "processed_transcription": db_transcription.processed_transcription,
        "corrected_transcription": db_transcription.corrected_transcription,
        "processed_segments": db_transcription.processed_segments,
        "raw_segments": db_transcription.raw_segments,
        "audio_file_path": db_transcription.audio_file_path
    }

    if not response_data.get("raw_segments") and db_transcription.raw_transcription is not None:
        try:
            raw_text = str(db_transcription.raw_transcription)
            parsed_segments = json.loads(raw_text)
            if isinstance(parsed_segments, list):
                response_data["raw_segments"] = parsed_segments
                logger.info(f"Successfully parsed raw_segments from raw_transcription for ID: {transcription_id}")
        except json.JSONDecodeError:
            logger.warning(f"Could not parse raw_transcription as JSON for ID: {transcription_id}. ")
        except Exception as e:
            logger.error(f"An unexpected error occurred while parsing raw_transcription for ID: {transcription_id}: {e}", exc_info=True)

    return response_data

@router.delete("/transcriptions/{transcription_id}", tags=["Transcription"], status_code=204)
async def delete_transcription(transcription_id: int, db: AsyncSession = Depends(get_db)):
    """Deletes a transcription by its ID."""
    logger.info(f"Received request to delete transcription ID: {transcription_id}")
    stmt = select(database.Transcription).filter(database.Transcription.id == transcription_id)
    result = await db.execute(stmt)
    db_transcription = result.scalars().first()
    if not db_transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")
    
    await db.delete(db_transcription)
    await db.commit()
    return

def _iter_file_segment(path: str, start: int, end: int, chunk_size: int = 1024 * 1024):
    with open(path, "rb") as f:
        f.seek(start)
        bytes_remaining = end - start + 1
        while bytes_remaining > 0:
            read_size = min(chunk_size, bytes_remaining)
            data = f.read(read_size)
            if not data:
                break
            yield data
            bytes_remaining -= len(data)


@router.get("/audio/{transcription_id}", tags=["Transcription"])
async def get_audio_file(transcription_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Retrieves the audio file for a given transcription ID.
    - If the file is stored locally, it serves the file directly.
    - If the file is in B2, it returns a secure, temporary pre-signed URL.
    """
    logger.info(f"Received request for audio for transcription ID: {transcription_id}")
    
    stmt = select(database.Transcription.audio_file_path).filter(database.Transcription.id == transcription_id)
    audio_path = (await db.execute(stmt)).scalar_one_or_none()

    if not audio_path:
        raise HTTPException(status_code=404, detail="Audio file reference not found in database record.")

    # Check if the path points to a local file
    if os.path.exists(audio_path):
        logger.info(f"Serving local audio file: {audio_path}")
        file_size = os.path.getsize(audio_path)
        range_header = request.headers.get("range") or request.headers.get("Range")
        media_type, _ = mimetypes.guess_type(audio_path)
        if media_type is None:
            media_type = "audio/mpeg"
        if range_header:
            # Example: "bytes=0-1023"
            try:
                units, ranges = range_header.split("=", 1)
                if units != "bytes":
                    raise ValueError("Only bytes unit is supported")
                start_str, end_str = ranges.split("-", 1)
                start = int(start_str) if start_str else 0
                end = int(end_str) if end_str else file_size - 1
                start = max(0, start)
                end = min(end, file_size - 1)
                if start > end:
                    start = 0
                    end = file_size - 1
            except Exception:
                # Fallback to full content on parse error
                start, end = 0, file_size - 1

            content_length = end - start + 1
            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                # Let the browser sniff or set a generic audio type; specific type detection could be added
                "Cache-Control": "no-cache",
            }
            return StreamingResponse(
                _iter_file_segment(audio_path, start, end),
                status_code=206,
                media_type=media_type,
                headers=headers,
            )
        # No Range header; send entire file but advertise range support
        response = FileResponse(audio_path, media_type=media_type)
        response.headers["Accept-Ranges"] = "bytes"
        return response

    # If not a local file, assume it's a B2 object key and generate a pre-signed URL
    logger.info(f"Generating pre-signed URL for B2 object key: {audio_path}")
    storage_service = get_storage_service()
    
    if not storage_service.check_connection():
        logger.error(f"B2 connection is down. Cannot generate pre-signed URL for key: {audio_path}")
        raise HTTPException(status_code=503, detail="Cloud storage service is currently unavailable.")

    presigned_url = storage_service.create_presigned_url(audio_path)

    if not presigned_url:
        logger.error(f"Could not generate pre-signed URL for object key: {audio_path}")
        raise HTTPException(status_code=500, detail="Could not generate audio file URL.")

    return JSONResponse(content={"url": presigned_url})