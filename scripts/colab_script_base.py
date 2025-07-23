import os
import subprocess
import time
import dataclasses
import whisperx
from faster_whisper import WhisperModel
from whisperx.diarize import DiarizationPipeline
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Parameters ---
MODEL_NAME = "base" # Using the smaller 'base' model to conserve RAM
LANGUAGE = "de"
RANGE_SLICE = "0:1"
DIARISE = True
HF_TOKEN = os.environ.get("HF_TOKEN") # Your Hugging Face Token

# ... (rest of the script is the same) ...
def parse_range(range_str):
    """Parses a range string and returns a slice object."""
    if not range_str:
        return slice(None)
    if ':' in range_str:
        start, end = map(int, range_str.split(':'))
        return slice(start, end)
    elif '-' in range_str:
        if range_str.startswith('-'):
            return slice(abs(int(range_str)))
        elif range_str.endswith('-'):
            return slice(int(range_str[:-1]), None)
        else:
            start, end = map(int, range_str.split('-'))
            return slice(start, end)
    else:
        return slice(int(range_str))

def preprocess_audio(input_path, output_path):
    """Denoises and normalizes an audio file using FFmpeg."""
    print(f"Preprocessing {input_path}...")
    command = ['ffmpeg', '-i', input_path, '-af', 'anlmdn,dynaudnorm', '-y', output_path]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        print(f"Preprocessing complete: {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"Error during preprocessing: {e.stderr}")
        return None

def transcribe_and_diarise(audio_path, model_name, language, hf_token, diarise):
    """Transcribes and optionally diarises an audio file."""
    print(f"Loading model '{model_name}'...")
    model = WhisperModel(model_name, device="cuda", compute_type="float16")
    
    print(f"Loading audio from {audio_path}...")
    audio = whisperx.load_audio(audio_path)

    print("Transcribing...")
    segments, _ = model.transcribe(audio, language=language)
    result = {"segments": [dataclasses.asdict(segment) for segment in segments], "language": language}

    if diarise:
        print("Aligning transcription...")
        model_a, metadata = whisperx.load_align_model(language_code=result["language"], device="cuda")
        result = whisperx.align(result["segments"], model_a, metadata, audio, device="cuda", return_char_alignments=False)

        print("Diarising speakers...")
        diarize_model = DiarizationPipeline(use_auth_token=hf_token, device="cuda")
        diarize_segments = diarize_model(audio)
        result = whisperx.assign_word_speakers(diarize_segments, result)

    return result

def format_output(result, output_path):
    """Formats and saves the transcription result."""
    print(f"Saving transcription to {output_path}...")
    with open(output_path, "w", encoding="utf-8") as f:
        if 'speaker' in result['segments'][0]:
            for segment in result["segments"]:
                if 'speaker' in segment:
                    f.write(f"[{segment['speaker']}]: {segment['text'].strip()}\\n")
                else:
                    f.write(f"[UNKNOWN]: {segment['text'].strip()}\\n")
        else:
            plain_text = " ".join([segment['text'].strip() for segment in result["segments"]])
            f.write(plain_text)

# --- Main Logic ---
start_time = time.time()
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

audio_dir = "data/audio/unprocessed"
output_dir = "output/transcriptions"
temp_dir = "temp"

all_files = sorted([f for f in os.listdir(audio_dir) if f.endswith(".mp3")])
file_slice = parse_range(RANGE_SLICE)
files_to_process = all_files[file_slice]

for filename in files_to_process:
    input_path = os.path.join(audio_dir, filename)
    processed_path = input_path

    # We are not using preprocess for this test
    
    result = transcribe_and_diarise(processed_path, MODEL_NAME, LANGUAGE, HF_TOKEN, DIARISE)

    output_filename = os.path.splitext(filename)[0] + ".txt"
    output_path = os.path.join(output_dir, output_filename)
    format_output(result, output_path)

end_time = time.time()
elapsed_time = end_time - start_time
print(f"\\nProcessed {len(files_to_process)} file(s) in {elapsed_time:.2f} seconds.")