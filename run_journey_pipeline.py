import os
import glob
import argparse
from tqdm import tqdm
import json
import pandas as pd

from scripts.pipeline.transcription import transcribe_audio
from scripts.pipeline.diarization import get_speaker_timeline
from scripts.pipeline.postprocessing import combine_transcript_and_diarization

def main():
    parser = argparse.ArgumentParser(description="Run the full customer journey transcription pipeline.")
    parser.add_argument(
        "provider", 
        choices=['openai_api', 'mistral_api', 'local_whisper'], 
        help="The transcription provider to use."
    )
    parser.add_argument(
        "--audio_dir", 
        default='data/audio/selected_for_poc', 
        help="Directory containing the audio files to process."
    )
    parser.add_argument(
        "--details_file",
        default='output/customer_journey_poc/all_selected_recordings_details.csv',
        help="CSV file with details of the selected recordings."
    )
    parser.add_argument(
        "--output_dir",
        default='output/customer_journey_poc',
        help="Directory to save the final processed transcripts."
    )
    parser.add_argument(
        "--diarize", 
        action="store_true", 
        help="Enable speaker diarization."
    )
    parser.add_argument(
        "--no_post_processing", 
        action="store_true", 
        help="Skip the post-processing step."
    )
    args = parser.parse_args()

    # --- Load Recording Details ---
    try:
        df_details = pd.read_csv(args.details_file)
    except FileNotFoundError:
        print(f"Error: Details file not found at {args.details_file}")
        print("Please run the customer selection script (1_select_customers.py) first.")
        return

    # --- Group Recordings by Phone Number ---
    customer_journeys = df_details.groupby('phone')

    print(f"Found {len(customer_journeys)} customer journeys to process.")

    # --- Run Pipeline ---
    for phone_number, group in tqdm(customer_journeys, desc="Processing customer journeys"):
        customer_output_dir = os.path.join(args.output_dir, str(phone_number))
        os.makedirs(customer_output_dir, exist_ok=True)

        for _, row in group.iterrows():
            base_filename = os.path.splitext(os.path.basename(row['recording_url']))[0]
            audio_path = os.path.join(args.audio_dir, f"{base_filename}.mp3")

            if not os.path.exists(audio_path):
                print(f"Warning: Audio file not found for {base_filename}. Skipping.")
                continue

            # --- Run Individual File Pipeline ---
            # (This is the same logic as our previous run_pipeline.py)
            
            # 1. Transcription
            transcript = transcribe_audio(audio_path, args.provider)
            if not transcript:
                continue

            # 2. Diarization
            diarization_result = None
            if args.diarize:
                hf_token = os.environ.get("HF_TOKEN")
                if hf_token:
                    if isinstance(transcript, dict):
                        diarization_result = get_speaker_timeline(audio_path, hf_token, transcript)
                    else:
                        diarization_result = get_speaker_timeline(audio_path, hf_token, {"segments": [{"text": transcript}], "language": "de"})

            # 3. Post-processing
            if not args.no_post_processing:
                if diarization_result:
                    transcript_for_processing = ""
                    for segment in diarization_result["segments"]:
                        speaker = segment.get('speaker', 'UNKNOWN')
                        text = segment['text'].strip()
                        transcript_for_processing += f"[{speaker}]: {text}\n"
                else:
                    transcript_for_processing = transcript if isinstance(transcript, str) else json.dumps(transcript)
                
                processed_data = combine_transcript_and_diarization(transcript_for_processing, diarization_result, base_filename, diarized=bool(diarization_result))
                
                if processed_data:
                    output_path = os.path.join(customer_output_dir, f"{base_filename}.json")
                    with open(output_path, "w", encoding="utf-8") as f:
                        json.dump(processed_data, f, ensure_ascii=False, indent=4)
                else:
                    # If post-processing fails, save the raw transcript
                    output_path = os.path.join(customer_output_dir, f"{base_filename}_raw.json")
                    with open(output_path, "w", encoding="utf-8") as f:
                        json.dump({"full_transcript": transcript if isinstance(transcript, str) else json.dumps(transcript)}, f, ensure_ascii=False, indent=4)
            else:
                # If post-processing is skipped, save the raw transcript
                output_path = os.path.join(customer_output_dir, f"{base_filename}.json")
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump({"full_transcript": transcript if isinstance(transcript, str) else json.dumps(transcript)}, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    main()