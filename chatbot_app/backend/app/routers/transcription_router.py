import logging
import os
import tempfile
import datetime
import shutil
from fastapi import APIRouter, HTTPException, File, UploadFile, Form, Depends, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional, List, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app import database
from app.services import llm_handler, transcription, prompt_engine, task_manager

# --- Logging Setup ---
logger = logging.getLogger(__name__)

# --- Router Setup ---
router = APIRouter()

# --- DB Dependency ---
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with database.AsyncSessionLocal() as session:
        yield session

# --- Pydantic Models ---
class TranscriptionProcessRequest(BaseModel):
    transcription_id: int
    transcription: str

class CompanyNameCorrectionRequest(BaseModel):
    transcription_id: int
    full_transcript: str
    correct_company_name: str

class ProcessedTranscription(BaseModel):
    full_transcript: str = Field(..., description="The full, corrected, and diarized transcript.")

class CorrectedTranscription(BaseModel):
    corrected_transcript: str = Field(..., description="The final transcript with the company name corrected.")

class TranscriptionInfo(BaseModel):
    id: int
    audio_source: Optional[str] = None
    created_at: datetime.datetime
    
    class Config:
        from_attributes = True

# --- API Endpoints ---
async def run_transcription_task(
    temp_path: str,
    audio_source: str,
    task_id: str,
    db: AsyncSession
):
    """Helper function to run the transcription process in the background."""
    async with database.AsyncSessionLocal() as db:
        try:
            logger.info(f"[Task {task_id}] Starting transcription...")
            
            # 1. Save the audio file permanently
            audio_storage_path = "audio_files"
            os.makedirs(audio_storage_path, exist_ok=True)
            permanent_path = os.path.join(audio_storage_path, os.path.basename(temp_path))
            shutil.move(temp_path, permanent_path)
            logger.info(f"[Task {task_id}] Moved audio file to {permanent_path}")

            # 2. Transcribe the audio
            segments = transcription.transcribe_audio(permanent_path, task_id)
            
            # 3. Format the transcription
            full_transcription = " ".join(seg['text'] for seg in segments)
            
            # 4. Save to database
            logger.info(f"[Task {task_id}] Saving transcription to DB with audio path: {permanent_path}")
            new_transcription = database.Transcription(
                audio_source=audio_source,
                raw_transcription=full_transcription,
                audio_file_path=permanent_path
            )
            db.add(new_transcription)
            await db.commit()
            await db.refresh(new_transcription)
            logger.info(f"[Task {task_id}] Saved transcription with ID: {new_transcription.id}")
            
            # 5. Mark task as successful
            result = {
                "transcription_id": new_transcription.id,
                "transcription_segments": segments,
            }
            task_manager.set_task_success(task_id, result)
            logger.info(f"[Task {task_id}] Transcription successful.")

        except Exception as e:
            logger.error(f"An error occurred during transcription task {task_id}: {e}", exc_info=True)
            task_manager.set_task_error(task_id, f"Internal Server Error: {e}")
        finally:
            # Clean up the temporary directory
            temp_dir = os.path.dirname(temp_path)
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)


@router.post("/transcribe", tags=["Transcription"], status_code=202)
async def transcribe(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Transcribes an audio file from a file upload or a URL.
    """
    logger.info("Received request to /transcribe")
    if not file and not url:
        logger.error("No file or URL provided.")
        raise HTTPException(status_code=400, detail="Either a file or a URL must be provided.")

    task_id = task_manager.create_task()
    audio_source = file.filename if file and file.filename else url

    try:
        # Create a temporary directory to store the uploaded file
        temp_dir = tempfile.mkdtemp()
        
        if file and file.filename:
            temp_path = os.path.join(temp_dir, file.filename)
            with open(temp_path, "wb") as buffer:
                buffer.write(await file.read())
        elif url:
            temp_path = transcription.download_file(url, temp_dir, task_id)
        else:
            raise HTTPException(status_code=400, detail="No file or URL provided")

        source = audio_source or url
        if not source:
            raise HTTPException(status_code=400, detail="Could not determine audio source.")
        
        await run_transcription_task(temp_path, source, task_id, db)

        return {"task_id": task_id, "message": "Transcription task started."}

    except Exception as e:
        logger.error(f"Failed to start transcription task: {e}", exc_info=True)
        task_manager.set_task_error(task_id, f"Failed to start task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start transcription task: {e}")

@router.post("/post-process-transcription", tags=["Transcription"])
async def post_process_transcription(request: TranscriptionProcessRequest, db: AsyncSession = Depends(get_db)):
    """
    Receives a raw transcription and its ID, post-processes it, and saves
    the processed version to the database.
    """
    logger.info(f"Received request to /post-process-transcription for ID: {request.transcription_id}")
    try:
        # 1. Create the prompt using the new template
        prompt = prompt_engine.create_prompt_from_template(
            "post_process_advanced_diarization.txt",
            {"transcription_text": request.transcription}
        )
        logger.info("Generated advanced diarization prompt.")

        # 2. Get the structured response from the LLM
        response_data = await llm_handler.get_structured_response(prompt, response_model=ProcessedTranscription)
        logger.info("Received structured response from LLM.")

        # 3. Return the processed transcript
        processed_transcript = response_data.full_transcript

        # Update database
        result = await db.execute(select(database.Transcription).filter(database.Transcription.id == request.transcription_id))
        db_transcription = result.scalars().first()
        if not db_transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")
        
        db_transcription.processed_transcription = processed_transcript
        await db.commit()

        return {"processed_transcription": processed_transcript}

    except Exception as e:
        logger.error(f"An error occurred during transcription post-processing: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@router.post("/correct-company-name", tags=["Transcription"])
async def correct_company_name(request: CompanyNameCorrectionRequest, db: AsyncSession = Depends(get_db)):
    """
    Receives a processed transcript and its ID, and a correct company name,
    and uses an LLM to replace the incorrect company name.
    """
    logger.info(f"Received request to /correct-company-name for ID: {request.transcription_id}")
    try:
        prompt = prompt_engine.create_prompt_from_template(
            "correct_company_name.txt",
            {
                "full_transcript": request.full_transcript,
                "correct_company_name": request.correct_company_name
            }
        )
        logger.info("Generated company name correction prompt.")

        response_data = await llm_handler.get_structured_response(prompt, response_model=CorrectedTranscription)
        logger.info("Received structured response from LLM for company name correction.")

        corrected_transcript = response_data.corrected_transcript

        # Update database
        result = await db.execute(select(database.Transcription).filter(database.Transcription.id == request.transcription_id))
        db_transcription = result.scalars().first()
        if not db_transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")

        db_transcription.corrected_transcription = corrected_transcript
        await db.commit()

        return {"corrected_transcript": corrected_transcript}

    except Exception as e:
        logger.error(f"An error occurred during company name correction: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@router.get("/transcriptions", tags=["Transcription"], response_model=List[TranscriptionInfo])
async def get_transcriptions(db: AsyncSession = Depends(get_db)):
    """
    Retrieves a list of all past transcriptions from the database.
    """
    logger.info("Received request to /transcriptions")
    try:
        result = await db.execute(select(database.Transcription).order_by(database.Transcription.created_at.desc()))
        transcriptions = result.scalars().all()
        
        return [TranscriptionInfo.from_orm(t) for t in transcriptions]
    except Exception as e:
        logger.error(f"An error occurred while fetching transcriptions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@router.get("/transcriptions/{transcription_id}", tags=["Transcription"])
async def get_transcription(transcription_id: int, db: AsyncSession = Depends(get_db)):
    """
    Retrieves a single transcription by its ID.
    """
    logger.info(f"Received request for transcription ID: {transcription_id}")
    try:
        result = await db.execute(select(database.Transcription).filter(database.Transcription.id == transcription_id))
        db_transcription = result.scalars().first()
        if not db_transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")
        
        return {
            "raw_transcription": db_transcription.raw_transcription,
            "processed_transcription": db_transcription.processed_transcription,
            "corrected_transcription": db_transcription.corrected_transcription,
        }

    except Exception as e:
        logger.error(f"An error occurred while fetching transcription {transcription_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@router.delete("/transcriptions/{transcription_id}", tags=["Transcription"], status_code=204)
async def delete_transcription(transcription_id: int, db: AsyncSession = Depends(get_db)):
    """
    Deletes a transcription by its ID.
    """
    logger.info(f"Received request to delete transcription ID: {transcription_id}")
    try:
        result = await db.execute(select(database.Transcription).filter(database.Transcription.id == transcription_id))
        db_transcription = result.scalars().first()
        if not db_transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")
        
        await db.delete(db_transcription)
        await db.commit()
        return
    except Exception as e:
        logger.error(f"An error occurred while deleting transcription {transcription_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")
@router.get("/audio/{transcription_id}", tags=["Transcription"])
async def get_audio_file(transcription_id: int, db: AsyncSession = Depends(get_db)):
    """
    Retrieves the audio file for a given transcription ID.
    """
    logger.info(f"Received request for audio file for transcription ID: {transcription_id}")
    try:
        result = await db.execute(
            select(database.Transcription.audio_file_path)
            .filter(database.Transcription.id == transcription_id)
        )
        file_path = result.scalars().first()

        if not file_path:
            raise HTTPException(status_code=404, detail="Audio file not found in database")

        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Audio file not found on disk")

        return FileResponse(path=file_path)

    except Exception as e:
        logger.error(f"An error occurred while fetching audio file for transcription {transcription_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")