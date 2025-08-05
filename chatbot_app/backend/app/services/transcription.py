import os
import requests
import logging
from openai import OpenAI
from pydub import AudioSegment
from math import ceil
import shutil


from app.services import task_manager

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
logger = logging.getLogger(__name__)

# Whisper API has a 25MB file size limit
CHUNK_SIZE_MB = 20
MAX_FILE_SIZE = CHUNK_SIZE_MB * 1024 * 1024

def download_file(url: str, temp_dir: str, task_id: str) -> str:
    """Downloads a file from a URL and saves it to a temporary directory."""
    task_manager.update_task_status(task_id, "PROCESSING", 5, f"Downloading file from {url}")
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
    The API handles large files directly, so no manual chunking is needed.
    Returns a list of segment dictionaries, each with 'start', 'end', and 'text'.
    """
    logger.info(f"[transcribe_audio] Starting transcription for: {audio_path} (Task ID: {task_id})")
    try:
        # Estimate time based on file size. A rough estimate is fine.
        file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        estimated_time_seconds = file_size_mb * 60  # Rough estimate: 60 seconds per MB
        
        task_manager.update_task_status(
            task_id,
            "PROCESSING",
            10,
            "Uploading and transcribing audio file...",
            estimated_time=int(estimated_time_seconds)
        )

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
        task_manager.update_task_status(task_id, "PROCESSING", 98, "Finalizing transcription...")
        return all_segments
        
    except Exception as e:
        logger.error(f"[transcribe_audio] An error occurred in the transcription function: {e}", exc_info=True)
        task_manager.set_task_error(task_id, "A critical error occurred during transcription.")
        raise