import os
import asyncio
import requests
import logging
import json
from openai import OpenAI
from pydub import AudioSegment
from math import ceil
import shutil
from sqlalchemy.ext.asyncio import AsyncSession
from app import database
from app.services import task_manager
from app.services.storage import get_storage_service

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
logger = logging.getLogger(__name__)

# Whisper API has a 25MB file size limit
CHUNK_SIZE_MB = 20
MAX_FILE_SIZE = CHUNK_SIZE_MB * 1024 * 1024

class TranscriptionPipeline:
    """
    Encapsulates the entire transcription process, ensuring consistent state
    and database session management.
    """
    def __init__(self, db: AsyncSession, task_id: str, temp_path: str, audio_source: str):
        self.db = db
        self.task_id = task_id
        self.temp_path = temp_path
        self.audio_source = audio_source
        self.transcription_record = None

    async def run(self):
        """Executes the full transcription and post-processing pipeline."""
        try:
            logger.info(f"[Pipeline Task {self.task_id}] Starting...")
            storage_service = get_storage_service()
            audio_file_path = ""

            if storage_service.check_connection():
                logger.info(f"[Pipeline Task {self.task_id}] B2 connection is active. Uploading to cloud.")
                object_key = os.path.basename(self.temp_path)
                if storage_service.upload_file(self.temp_path, object_key):
                    audio_file_path = object_key
                else:
                    logger.warning(f"[Pipeline Task {self.task_id}] B2 upload failed. Falling back to local storage.")
            
            if not audio_file_path:
                local_audio_dir = os.path.join(os.path.dirname(__file__), '..', 'audio_files')
                os.makedirs(local_audio_dir, exist_ok=True)
                local_path = os.path.join(local_audio_dir, os.path.basename(self.temp_path))
                shutil.copy(self.temp_path, local_path)
                audio_file_path = local_path
                logger.info(f"[Pipeline Task {self.task_id}] Saved file locally to {audio_file_path}")

            task_manager.update_task_status(
                self.task_id,
                "PROCESSING",
                "Uploading and preparing audio...",
                result=None,
                progress=5,
            )
            # Yield to event loop so clients can read the update
            await asyncio.sleep(0)

            # Indicate Whisper is running to provide an intermediate message
            task_manager.update_task_status(
                self.task_id,
                "PROCESSING",
                "Transcribing with Whisper API...",
                result=None,
                progress=20,
            )
            await asyncio.sleep(0)

            # Run Whisper transcription in a background thread to avoid blocking the event loop
            raw_segments = await asyncio.to_thread(transcribe_audio, self.temp_path, self.task_id)

            # Emit raw transcript to the client immediately after Whisper returns
            task_manager.update_task_status(
                self.task_id,
                "PROCESSING",
                "Transcription received from Whisper.",
                result={
                    "transcription_id": None,
                    "raw_segments": raw_segments,
                    "status": "RAW_TRANSCRIPT_READY",
                },
                progress=55,
            )
            await asyncio.sleep(0)

            # Persist to DB to obtain a transcription ID and audio path
            await self._save_initial_transcription(raw_segments, audio_file_path)

            # Update with the new transcription ID while preserving the same result structure
            task_manager.update_task_status(
                self.task_id,
                "PROCESSING",
                "Raw transcript ready.",
                result={
                    "transcription_id": self.transcription_record.id,  # type: ignore
                    "raw_segments": raw_segments,
                    "status": "RAW_TRANSCRIPT_READY",
                },
                progress=60,
            )
            await asyncio.sleep(0)

            # Brief intermediate step to remain visible before post-processing starts
            task_manager.update_task_status(
                self.task_id,
                "PROCESSING",
                "Preparing data for AI analysis...",
                result=None,
                progress=65,
            )
            await asyncio.sleep(0)
            
            task_manager.update_task_status(
                self.task_id,
                "PROCESSING",
                "Structuring transcript for AI analysis...",
                result=None,
                progress=70,
            )

            # Run LLM post-processing in a background thread as it uses blocking I/O
            processed_text, processed_segments = await asyncio.to_thread(
                post_process_transcription_with_timestamps, raw_segments, self.task_id
            )
            
            await self._update_with_processed_data(processed_text, processed_segments)

            # --- Final Event: Processed Data is Ready ---
            final_result = {
                "transcription_id": self.transcription_record.id, # type: ignore
                "raw_segments": raw_segments,
                "processed_segments": processed_segments,
            }
            task_manager.set_task_success(self.task_id, final_result)
            logger.info(f"[Pipeline Task {self.task_id}] Pipeline completed successfully.")

        except Exception as e:
            logger.error(f"An error occurred during transcription pipeline for task {self.task_id}: {e}", exc_info=True)
            task_manager.set_task_error(self.task_id, f"Internal Server Error: {e}")
        finally:
            self._cleanup_temp_files()

    async def _save_initial_transcription(self, raw_segments: list, object_key: str):
        """Saves the initial raw transcription to the database."""
        # This step is now part of the main flow and doesn't need its own progress update
        # to avoid the large jump.
        # task_manager.update_task_status(self.task_id, "PROCESSING", 75, "Saving initial transcript...")
        full_transcription = " ".join(seg['text'] for seg in raw_segments)
        
        self.transcription_record = database.Transcription(
            audio_source=self.audio_source,
            raw_transcription=full_transcription,
            raw_segments=raw_segments,
            audio_file_path=object_key, # Store the B2 object key, not a local path
        )
        self.db.add(self.transcription_record)
        await self.db.commit()
        await self.db.refresh(self.transcription_record)
        logger.info(f"[Pipeline Task {self.task_id}] Saved initial transcription with ID: {self.transcription_record.id}")

    async def _update_with_processed_data(self, processed_text: str, processed_segments: list):
        """Updates the database record with the post-processed data."""
        if not self.transcription_record:
            raise ValueError("Transcription record not found. Cannot update.")
            
        pass
        self.transcription_record.processed_transcription = processed_text  # type: ignore
        self.transcription_record.processed_segments = processed_segments  # type: ignore
        await self.db.commit()
        await self.db.refresh(self.transcription_record)
        logger.info(f"[Pipeline Task {self.task_id}] Updated transcription with processed data.")

    def _cleanup_temp_files(self):
        """Removes the temporary directory and its contents."""
        temp_dir = os.path.dirname(self.temp_path)
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

def download_file(url: str, temp_dir: str, task_id: str) -> str:
    """Downloads a file from a URL and saves it to a temporary directory."""
    response = requests.get(url, stream=True)
    response.raise_for_status()
    
    file_name = url.split("/")[-1]
    temp_path = os.path.join(temp_dir, file_name)
    
    with open(temp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            
    return temp_path

def transcribe_audio(audio_path: str, task_id: str) -> list[dict]:
    """
    Transcribes an audio file using the OpenAI Whisper API, returning detailed segments.
    """
    logger.info(f"[transcribe_audio] Starting transcription for: {audio_path} (Task ID: {task_id})")
    try:
        file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        estimated_time_seconds = file_size_mb * 60
        
        # No progress updates needed from here anymore
        pass

        with open(audio_path, "rb") as audio_file:
            logger.info(f"[transcribe_audio] Sending file to OpenAI API for transcription...")
            transcription_response = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json"
            )
            logger.info(f"[transcribe_audio] Received response from OpenAI.")

        all_segments = []
        if transcription_response.segments:
            for segment in transcription_response.segments:
                all_segments.append({
                    "start": round(segment.start, 3),
                    "end": round(segment.end, 3),
                    "text": segment.text
                })
        
        logger.info("[transcribe_audio] Transcription processed successfully.")
        # This is now handled by the main pipeline function
        # task_manager.update_task_status(task_id, "PROCESSING", 98, "Finalizing transcription...")
        return all_segments
        
    except Exception as e:
        logger.error(f"[transcribe_audio] An error occurred in the transcription function: {e}", exc_info=True)
        task_manager.set_task_error(task_id, "A critical error occurred during transcription.")
        raise

def _load_prompt(file_name: str) -> str:
    """Loads a prompt from the prompts directory."""
    prompt_path = os.path.join(os.path.dirname(__file__), '..', 'prompts', file_name)
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()

def post_process_transcription_with_timestamps(segments: list[dict], task_id: str) -> tuple[str, list[dict]]:
    """
    Processes raw transcription segments using an LLM to clean text,
    diarize speakers, and return structured data with timestamps preserved.
    """
    # Emit intermediate status updates to reflect LLM post-processing phases
    task_manager.update_task_status(
        task_id,
        "PROCESSING",
        "Diarizing speakers with advanced model...",
        result=None,
        progress=75,
    )
    
    transcription_text = ""
    for s in segments:
        transcription_text += f"[{s['start']:.2f} -> {s['end']:.2f}] {s['text']}\n"

    prompt_template = _load_prompt("post_process_with_timestamps.txt")
    system_prompt = prompt_template.format(transcription_text=transcription_text)
    llm_output_str = ""

    try:
        logger.info("[post_process_with_timestamps] Sending data to LLM for advanced processing.")
        response = client.chat.completions.create(
            model="gpt-4-1106-preview",
            messages=[{"role": "system", "content": system_prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        
        llm_output_str = response.choices[0].message.content
        logger.info("[post_process_with_timestamps] Received LLM response.")

        if not llm_output_str:
            raise ValueError("LLM returned an empty response.")
        
        # Indicate finalization phase after receiving LLM output
        task_manager.update_task_status(
            task_id,
            "PROCESSING",
            "Finalizing processed transcript...",
            result=None,
            progress=90,
        )

        llm_output_json = json.loads(llm_output_str)
        
        processed_segments = llm_output_json.get("processed_segments", [])
        
        full_transcript_text = "\n".join(
            f"{seg.get('speaker', '')}: {seg.get('text', '')}" for seg in processed_segments
        )

        return full_transcript_text, processed_segments

    except json.JSONDecodeError as e:
        logger.error(f"[post_process_with_timestamps] Failed to decode JSON from LLM response: {e}")
        logger.error(f"LLM Output was: {llm_output_str}")
        task_manager.set_task_error(task_id, "Failed to parse the processed transcription.")
        raise
    except Exception as e:
        logger.error(f"[post_process_with_timestamps] An error occurred: {e}", exc_info=True)
        task_manager.set_task_error(task_id, "A critical error occurred during post-processing.")
        raise