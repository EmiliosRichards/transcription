import os
import glob
import argparse
from tqdm import tqdm
import json

from scripts.pipeline.transcription import transcribe_audio
from scripts.pipeline.diarization import get_speaker_timeline
from scripts.pipeline.postprocessing import combine_transcript_and_diarization

def main():
    parser = argparse.ArgumentParser(description="Run the full transcription and diarization pipeline.")
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
        "--output_dir",
        default='output/processed',
        help="Directory to save the final processed transcripts."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of files to process for testing."
    )
    parser.add_argument(
        "--test_run",
        action="store_true",
        help="Run in test mode, saving snapshots of each step."
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

    # --- Setup ---
    output_dir = "output/test_run" if args.test_run else args.output_dir
    os.makedirs(output_dir, exist_ok=True)
    
    audio_files = glob.glob(os.path.join(args.audio_dir, '*.mp3'))

    if args.limit:
        audio_files = audio_files[:args.limit]

    if not audio_files:
        print(f"No .mp3 files found in '{args.audio_dir}'.")
        return

    print(f"Found {len(audio_files)} audio files to process.")

    # --- Run Pipeline ---
    for audio_path in tqdm(audio_files, desc="Processing audio files"):
        base_filename = os.path.splitext(os.path.basename(audio_path))[0]
        processed_data = None
        
        # Create a dedicated subdirectory for each test run
        run_output_dir = os.path.join(output_dir, base_filename)
        if args.test_run:
            os.makedirs(run_output_dir, exist_ok=True)

        # 1. Transcription
        print(f"\nTranscribing {base_filename} with {args.provider}...")
        transcript = transcribe_audio(audio_path, args.provider)
        if not transcript:
            print(f"Skipping {base_filename} due to transcription error.")
            continue
        if args.test_run:
            # Convert transcript to a consistent string format for logging
            transcript_text_for_log = json.dumps(transcript, indent=2) if isinstance(transcript, dict) else transcript
            with open(os.path.join(run_output_dir, "1_transcript.txt"), "w", encoding="utf-8") as f:
                f.write(transcript_text_for_log)

        # 2. Diarization
        diarization_result = None
        if args.diarize:
            print(f"Diarizing {base_filename}...")
            hf_token = os.environ.get("HF_TOKEN")
            if not hf_token:
                print("Warning: HF_TOKEN environment variable not set. Diarization will be skipped.")
            else:
                if isinstance(transcript, dict):
                    diarization_result = get_speaker_timeline(audio_path, hf_token=hf_token, transcript_result=transcript)
                else:
                    diarization_result = get_speaker_timeline(audio_path, hf_token=hf_token, transcript_result={"segments": [{"text": transcript}], "language": "de"})
                
                if not diarization_result:
                    print(f"Skipping {base_filename} due to diarization error.")
                    continue
                if args.test_run:
                    with open(os.path.join(run_output_dir, "2_diarization.txt"), "w", encoding="utf-8") as f:
                        f.write(str(diarization_result))

        # 3. Post-processing
        if not args.no_post_processing:
            print(f"Post-processing {base_filename}...")
            
            if diarization_result and isinstance(diarization_result, dict) and "segments" in diarization_result:
                # If we have a valid diarization result, format it for the prompt
                transcript_for_processing = ""
                for segment in diarization_result["segments"]:
                    speaker = segment.get('speaker', 'UNKNOWN')
                    text = segment['text'].strip()
                    transcript_for_processing += f"[{speaker}]: {text}\n"
            else:
                # If diarization was skipped or failed, use the raw transcript
                transcript_for_processing = transcript if isinstance(transcript, str) else json.dumps(transcript)
                
            processed_data = combine_transcript_and_diarization(transcript_for_processing, diarization_result, base_filename, diarized=bool(diarization_result))
            
            if processed_data:
                output_path = os.path.join(run_output_dir if args.test_run else output_dir, f"{base_filename}.json")
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(processed_data, f, ensure_ascii=False, indent=4)
                print(f"Successfully processed and saved to {output_path}")
            else:
                print(f"Skipping {base_filename} due to post-processing error.")
        
        if processed_data:
            output_path = os.path.join(run_output_dir if args.test_run else output_dir, f"{base_filename}.json")
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(processed_data, f, ensure_ascii=False, indent=4)
            print(f"Successfully processed and saved to {output_path}")
        else:
            print(f"Skipping {base_filename} due to post-processing error.")

if __name__ == "__main__":
    main()