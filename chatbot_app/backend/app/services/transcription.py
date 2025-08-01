import os
import httpx
from openai import AsyncOpenAI
import aiofiles
from app.config import settings

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def download_file(url: str, temp_dir: str) -> str:
    """Downloads a file from a URL asynchronously and saves it to a temporary directory."""
    file_name = url.split("/")[-1]
    temp_path = os.path.join(temp_dir, file_name)
    
    async with httpx.AsyncClient() as http_client:
        async with http_client.stream("GET", url) as response:
            response.raise_for_status()
            async with aiofiles.open(temp_path, "wb") as f:
                async for chunk in response.aiter_bytes():
                    await f.write(chunk)
                    
    return temp_path

async def transcribe_audio(audio_path: str) -> str:
    """Transcribes an audio file asynchronously using the OpenAI Whisper API."""
    async with aiofiles.open(audio_path, "rb") as audio_file:
        # The OpenAI client handles async file reading internally if the object supports it
        transcription = await client.audio.transcriptions.create(
            model=settings.TRANSCRIPTION_MODEL,
            file=await audio_file.read()
        )
    return transcription.text