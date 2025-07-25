import whisperx
from faster_whisper import WhisperModel
import dataclasses

def transcribe(audio_path: str, model_name: str = "large-v3", language: str = "de", beam_size: int = 5, temperature: float = 0) -> dict:
    """
    Transcribes an audio file using a local WhisperX/faster-whisper model.

    Args:
        audio_path: The path to the audio file.
        model_name: The name of the Whisper model to use.
        language: The language of the audio.
        beam_size: The beam size for decoding.
        temperature: The temperature for sampling.

    Returns:
        A dictionary containing the transcription segments.
    """
    print(f"Loading model '{model_name}'...")
    model = WhisperModel(
        model_name,
        device="cpu",
        compute_type="int8",
    )
    
    print(f"Loading audio from {audio_path}...")
    audio = whisperx.load_audio(audio_path)

    print("Transcribing...")
    segments, _ = model.transcribe(
        audio,
        beam_size=beam_size,
        language=language,
        temperature=temperature,
    )

    # Convert segments to a list of dictionaries
    result = {"segments": [dataclasses.asdict(segment) for segment in segments], "language": language}
    return result