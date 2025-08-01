import logging
import os
import tempfile
import datetime
from fastapi import APIRouter, HTTPException, File, UploadFile, Form, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app import database
from app.services import llm_handler, transcription, prompt_engine

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
@router.post("/transcribe", tags=["Transcription"])
async def transcribe(file: Optional[UploadFile] = File(None), url: Optional[str] = Form(None), db: AsyncSession = Depends(get_db)):
    """
    Transcribes an audio file from a file upload or a URL and saves the raw
    transcription to the database.
    """
    logger.info("Received request to /transcribe")
    if not file and not url:
        logger.error("No file or URL provided.")
        raise HTTPException(status_code=400, detail="Either a file or a URL must be provided.")

    audio_source = file.filename if file and file.filename else url

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            logger.info(f"Created temporary directory: {temp_dir}")
            if file and file.filename:
                temp_path = os.path.join(temp_dir, file.filename)
                with open(temp_path, "wb") as buffer:
                    buffer.write(await file.read())
                audio_path = temp_path
            elif url:
                audio_path = await transcription.download_file(url, temp_dir)
            else:
                raise HTTPException(status_code=400, detail="No file or URL provided")

            logger.info("Starting transcription...")
            transcript_text = await transcription.transcribe_audio(audio_path)
            logger.info("Transcription successful.")

            # Save to database
            new_transcription = database.Transcription(
                audio_source=audio_source,
                raw_transcription=transcript_text
            )
            db.add(new_transcription)
            await db.commit()
            await db.refresh(new_transcription)
            
            return {"transcription": transcript_text, "transcription_id": new_transcription.id}

    except Exception as e:
        logger.error(f"An error occurred during transcription: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

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