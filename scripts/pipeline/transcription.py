import importlib

from typing import Union

def transcribe_audio(audio_path: str, provider: str) -> Union[dict, str]:
    """
    Transcribes an audio file using the specified provider.

    Args:
        audio_path: The path to the audio file.
        provider: The name of the transcription provider 
                  (e.g., 'openai_api', 'mistral_api').

    Returns:
        The transcribed text.
    """
    try:
        # Dynamically import the provider module
        provider_module = importlib.import_module(f"scripts.pipeline.providers.{provider}")
        
        # Call the 'transcribe' function from the provider module
        transcript = provider_module.transcribe(audio_path)
        return transcript
        
    except ImportError:
        print(f"Error: The transcription provider '{provider}' was not found.")
        return ""
    except Exception as e:
        print(f"An error occurred in the transcription module: {e}")
        return ""