import os
import openai

def transcribe(audio_path: str) -> str:
    """
    Transcribes the given audio file using the OpenAI Whisper API.

    Args:
        audio_path: The path to the audio file.

    Returns:
        The transcribed text.
    """
    if "OPENAI_API_KEY" not in os.environ:
        raise ValueError("OPENAI_API_KEY environment variable not found.")

    openai.api_key = os.environ["OPENAI_API_KEY"]

    try:
        with open(audio_path, "rb") as audio_file:
            transcription = openai.audio.transcriptions.create(
              model="whisper-1", 
              file=audio_file
            )
        return transcription.text
    except Exception as e:
        print(f"An error occurred during OpenAI transcription: {e}")
        return ""