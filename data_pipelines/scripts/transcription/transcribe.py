import os
import argparse
import subprocess
import whisperx
from whisperx.diarize import DiarizationPipeline
import torch
from pyannote.audio import Model
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from dotenv import load_dotenv
from data_pipelines.scripts.mistral_transcribe import transcribe_with_mistral
from data_pipelines.scripts.pipeline.providers import openai_api
from data_pipelines import config
from . import post_process

def parse_range(range_str):
    """Parses a range string (e.g., '5', '-5', '5-', '10-15') and returns a slice object."""
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
            # This case is ambiguous, but we'll treat it as a slice for now.
            start, end = map(int, range_str.split('-'))
            return slice(start, end)
    else:
        return slice(int(range_str))

def preprocess_audio(input_path, output_path):
    """Denoises and normalizes an audio file using FFmpeg."""
    print(f"Preprocessing {input_path}...")
    command = [
        'ffmpeg',
        '-i', input_path,
        '-af', 'anlmdn,dynaudnorm',
        '-y', # Overwrite output file if it exists
        output_path
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        print(f"Preprocessing complete: {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"Error during preprocessing: {e.stderr}")
        return None

from faster_whisper import WhisperModel

def load_speaker_profiles(profiles_dir=str(config.SPEAKER_PROFILES_DIR)):
    """Loads speaker profiles from the specified directory."""
    if not os.path.isdir(profiles_dir):
        return {}
    
    profiles = {}
    for filename in os.listdir(profiles_dir):
        if filename.endswith(".pt"):
            speaker_name = os.path.splitext(filename)[0]
            profile_path = os.path.join(profiles_dir, filename)
            embedding = torch.load(profile_path)
            profiles[speaker_name] = embedding
    print(f"Loaded {len(profiles)} speaker profile(s).")
    return profiles

def recognize_speakers(diarize_result, audio, speaker_profiles, hf_token, threshold=0.7):
    """Recognizes speakers based on enrolled profiles."""
    if not speaker_profiles:
        return {}

    embedding_model = Model.from_pretrained("pyannote/embedding", use_auth_token=hf_token)
    speaker_mapping = {}
    
    for _, segment in diarize_result.iterrows():
        speaker_label = segment['speaker']
        if speaker_label in speaker_mapping:
            continue

        # Extract embedding for the speaker in the new audio
        start_frame = int(segment['start'] * 16000)
        end_frame = int(segment['end'] * 16000)
        segment_waveform = torch.tensor(audio[start_frame:end_frame]).unsqueeze(0)
        
        with torch.no_grad():
            new_embedding = embedding_model(segment_waveform)

        # Compare with enrolled profiles
        max_similarity = 0
        best_match = None
        for name, enrolled_embedding in speaker_profiles.items():
            similarity = cosine_similarity(new_embedding, enrolled_embedding)[0][0]
            if similarity > max_similarity:
                max_similarity = similarity
                best_match = name
        
        if max_similarity > threshold:
            speaker_mapping[speaker_label] = best_match
        else:
            # If no good match is found, assign a generic label
            # This logic needs to be improved to handle multiple unknown speakers
            speaker_mapping[speaker_label] = "CUSTOMER"

    return speaker_mapping

def transcribe_and_diarise(audio_path, args, speaker_profiles=None):
    """Transcribes and optionally diarises an audio file using WhisperX."""
    print(f"Loading model '{args.model}'...")
    model = WhisperModel(
        args.model,
        device="cpu",
        compute_type="int8",
    )
    
    print(f"Loading audio from {audio_path}...")
    audio = whisperx.load_audio(audio_path)

    print("Transcribing...")
    segments, _ = model.transcribe(
        audio,
        beam_size=args.beam_size,
        language=args.language,
        temperature=args.temperature,
    )

    import dataclasses
    # Convert segments to a list of dictionaries
    result = {"segments": [dataclasses.asdict(segment) for segment in segments], "language": args.language}

    if args.diarise:
        print("Aligning transcription...")
        model_a, metadata = whisperx.load_align_model(language_code=result["language"], device="cpu")
        result = whisperx.align(result["segments"], model_a, metadata, audio, device="cpu", return_char_alignments=False)

        print("Diarising speakers...")
        diarize_model = DiarizationPipeline(use_auth_token=args.hf_token, device="cpu")
        diarize_segments = diarize_model(audio)
        result = whisperx.assign_word_speakers(diarize_segments, result)

        if args.recognize_speakers and speaker_profiles:
            print("Recognizing speakers...")
            speaker_mapping = recognize_speakers(diarize_segments, audio, speaker_profiles, args.hf_token, args.recognition_threshold)
            
            # Update speaker labels in the result
            for segment in result["segments"]:
                if 'speaker' in segment:
                    original_speaker = segment['speaker']
                    segment['speaker'] = speaker_mapping.get(original_speaker, original_speaker)

    return result

def format_output(result, output_path):
    """Formats and saves the transcription result to a text file."""
    print(f"Saving transcription to {output_path}...")
    with open(output_path, "w", encoding="utf-8") as f:
        if 'speaker' in result['segments'][0]:
            # Diarised output
            for segment in result["segments"]:
                start_time = f"{segment['start']:.2f}"
                end_time = f"{segment['end']:.2f}"
                speaker = segment.get('speaker', 'UNKNOWN')
                text = segment['text'].strip()
                f.write(f"[{start_time} -> {end_time}] [{speaker}]: {text}\n")
        else:
            # Plain transcription
            plain_text = " ".join([segment['text'].strip() for segment in result["segments"]])
            f.write(plain_text)

import time

def main():
    start_time = time.time()
    # Disable symlinks for huggingface_hub on Windows
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    
    parser = argparse.ArgumentParser(description="Transcribe and diarise audio files.")
    # Existing arguments
    parser.add_argument("-r", "--range", type=str, default=None, help="Range of files to process from a directory.")
    parser.add_argument("-f", "--file", type=str, default=None, help="Path to a single audio file to process.")
    parser.add_argument("-m", "--model", type=str, default="large-v3", help="Whisper model to use.")
    parser.add_argument("--language", type=str, default="de", help="Language of the audio.")
    # New arguments
    parser.add_argument("--diarise", action="store_true", help="Enable speaker diarisation.")
    parser.add_argument("--recognize_speakers", action="store_true", help="Enable speaker recognition.")
    parser.add_argument("--preprocess", action="store_true", help="Enable audio preprocessing.")
    parser.add_argument("--temperature", type=float, default=0, help="Temperature for sampling.")
    parser.add_argument("--beam_size", type=int, default=5, help="Beam size for decoding.")
    parser.add_argument("--best_of", type=int, default=5, help="Number of candidates for beam search.")
    parser.add_argument("--hf_token", type=str, default=None, help="Hugging Face token for diarisation model.")
    parser.add_argument("--recognition_threshold", type=float, default=0.7, help="Confidence threshold for speaker recognition.")
    parser.add_argument("--post_process", action="store_true", help="Enable post-processing of transcriptions.")
    parser.add_argument("--audio_source", type=str, default="unprocessed", help="Specify the audio source directory (e.g., 'unprocessed' or 'testing/duygu mp3 calls').")
    parser.add_argument("--transcription_provider", type=str, default="whisperx", help="Choose the transcription provider: 'whisperx', 'mistral', or 'openai'.")
    args = parser.parse_args()

    load_dotenv()

    output_dir = config.TRANSCRIPTIONS_DIR
    temp_dir = config.TEMP_DIR
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)

    speaker_profiles = load_speaker_profiles() if args.recognize_speakers else None

    files_to_process = []
    if args.file:
        if not os.path.exists(args.file):
            print(f"Error: File not found at {args.file}")
            return
        files_to_process.append(args.file)
    else:
        audio_dir = os.path.join(config.AUDIO_DIR, args.audio_source)
        if not os.path.isdir(audio_dir):
            print(f"Error: Audio source directory not found at {audio_dir}")
            return
        all_files = sorted([os.path.join(audio_dir, f) for f in os.listdir(audio_dir) if f.endswith(".mp3")])
        file_slice = parse_range(args.range)
        files_to_process = all_files[file_slice]

    for input_path in files_to_process:
        filename = os.path.basename(input_path)
        processed_path = input_path

        if args.preprocess:
            temp_path = os.path.join(temp_dir, filename)
            processed_path = preprocess_audio(input_path, temp_path)
            if not processed_path:
                print(f"Skipping {filename} due to preprocessing error.")
                continue # Skip to the next file
        
        if args.transcription_provider == "mistral":
            api_key = os.environ.get("MISTRAL_API_KEY")
            if not api_key:
                print("Error: MISTRAL_API_KEY not found in .env file.")
                continue
            result = transcribe_with_mistral(api_key, processed_path)
            output_filename = os.path.splitext(filename)[0] + ".txt"
            output_path = os.path.join(config.MISTRAL_TRANSCRIPTIONS_DIR, output_filename)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(result)
        elif args.transcription_provider == "openai":
            result = openai_api.transcribe(processed_path)
            output_filename = os.path.splitext(filename)[0] + ".txt"
            output_path = os.path.join(config.OPENAI_TRANSCRIPTIONS_DIR, output_filename)
            os.makedirs(config.OPENAI_TRANSCRIPTIONS_DIR, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(result)
        else:
            result = transcribe_and_diarise(processed_path, args, speaker_profiles)
            output_filename = os.path.splitext(filename)[0] + ".txt"
            output_path = os.path.join(output_dir, output_filename)
            format_output(result, output_path)

        if args.post_process:
            print(f"Post-processing {output_path}...")
            post_processed_output_path = os.path.splitext(output_path)[0] + ".json"
            try:
                post_process.post_process(output_path, post_processed_output_path)
                print(f"Post-processing complete: {post_processed_output_path}")
            except Exception as e:
                print(f"Error during post-processing: {e}")


        if args.preprocess and processed_path and os.path.exists(processed_path):
            os.remove(processed_path) # Clean up temp file

    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"\nProcessed {len(files_to_process)} file(s) in {elapsed_time:.2f} seconds.")

if __name__ == "__main__":
    main()
