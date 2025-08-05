import os
import argparse
import json
from openai import OpenAI
from dotenv import load_dotenv

def transcribe_audio(file_path: str):
    """
    Transcribes an audio file using OpenAI's Whisper model and saves the
    output to both a formatted .txt file and a raw .json file.
    """
    if not os.path.exists(file_path):
        print(f"Error: File not found at '{file_path}'")
        return

    print("Loading API key from .env file...")
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not found in .env file.")
        return

    try:
        print("Initializing OpenAI client...")
        client = OpenAI(api_key=api_key)

        print(f"Opening audio file: {file_path}...")
        with open(file_path, "rb") as audio_file:
            print("Sending audio to OpenAI for transcription (this may take a moment)...")
            transcription_response = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json"
            )
        
        # Prepare output file paths
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        output_txt_path = f"{base_name}_transcript.txt"
        output_json_path = f"{base_name}_transcript_raw.json"

        # Process and save formatted transcript
        formatted_lines = []
        if transcription_response.segments:
            for segment in transcription_response.segments:
                start_time = round(segment.start, 2)
                end_time = round(segment.end, 2)
                text = segment.text
                formatted_lines.append(f"[{start_time:07.2f} -> {end_time:07.2f}] {text}")
        
        formatted_transcript = "\n".join(formatted_lines)
        with open(output_txt_path, "w", encoding="utf-8") as f:
            f.write(formatted_transcript)
        print(f"\nFormatted transcript saved to: {output_txt_path}")

        # Save raw JSON response
        # The response object is a Pydantic model, so we convert it to a dict first
        raw_json_output = {
            "text": transcription_response.text,
            "segments": [segment.model_dump() for segment in transcription_response.segments] if transcription_response.segments else [],
            "language": transcription_response.language,
            "duration": transcription_response.duration
        }
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(raw_json_output, f, indent=4, ensure_ascii=False)
        print(f"Raw API response saved to: {output_json_path}")

        print("\n--- Transcription Preview ---")
        print(formatted_transcript)
        print("---------------------------\n")

    except Exception as e:
        print(f"\nAn error occurred: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transcribe an audio file and save the output.")
    parser.add_argument("audio_file", help="The path to the audio file to transcribe.")
    args = parser.parse_args()

    transcribe_audio(args.audio_file)