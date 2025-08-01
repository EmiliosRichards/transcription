import os
import requests
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def download_file(url: str, temp_dir: str) -> str:
    """Downloads a file from a URL and saves it to a temporary directory."""
    response = requests.get(url, stream=True)
    response.raise_for_status()
    
    file_name = url.split("/")[-1]
    temp_path = os.path.join(temp_dir, file_name)
    
    with open(temp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            
    return temp_path

def transcribe_audio(audio_path: str) -> str:
    """Transcribes an audio file using the OpenAI Whisper API."""
    with open(audio_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file
        )
    return transcription.text