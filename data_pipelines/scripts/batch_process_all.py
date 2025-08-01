import os
from data_pipelines import config
import sys
from .post_process import post_process
from .review_interface import create_review_interface

def main():
    """
    Runs the full post-processing and review interface generation pipeline
    for all transcripts.
    """
    transcription_dir = str(config.TRANSCRIPTIONS_DIR)
    processed_dir = str(config.PROCESSED_DIR)
    
    # Ensure output directory exists
    os.makedirs(processed_dir, exist_ok=True)

    # Get all transcript files
    try:
        all_files = [f for f in os.listdir(transcription_dir) if f.endswith(".txt")]
    except FileNotFoundError:
        print(f"Error: The directory '{transcription_dir}' was not found.")
        return

    print(f"Found {len(all_files)} transcripts to process.")

    # --- Step 1: Run post-processing on all transcripts ---
    print("\\n--- Starting Post-Processing Batch ---")
    for filename in all_files:
        input_path = os.path.join(transcription_dir, filename)
        output_path = os.path.join(processed_dir, os.path.splitext(filename)[0] + ".json")
        
        post_process(input_path, output_path)

    print("\\n--- Post-Processing Batch Complete ---")

    # --- Step 2: Generate HTML review interfaces for all processed files ---
    print("\\n--- Starting HTML Generation Batch ---")
    processed_json_files = [f for f in os.listdir(processed_dir) if f.endswith(".json")]

    for filename in processed_json_files:
        json_path = os.path.join(processed_dir, filename)
        html_path = os.path.join(processed_dir, os.path.splitext(filename)[0] + ".html")

        create_review_interface(json_path, html_path)

    print("\\n--- HTML Generation Batch Complete ---")
    print(f"\\nAll tasks finished. Processed files and review interfaces are in the '{processed_dir}' directory.")

if __name__ == "__main__":
    main()