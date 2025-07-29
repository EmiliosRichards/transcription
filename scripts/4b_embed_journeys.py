import os
import glob
import json
import pandas as pd
import openai
from tqdm import tqdm
import argparse
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- 1. Setup ---
if "OPENAI_API_KEY" not in os.environ:
    print("OPENAI_API_KEY environment variable not found.")
    os.environ["OPENAI_API_KEY"] = input("Please enter your OpenAI API key: ")

openai.api_key = os.environ["OPENAI_API_KEY"]

def get_embedding(text):
    try:
        response = openai.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"An error occurred during embedding: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Generate embeddings for customer journeys.")
    parser.add_argument(
        "--input_dir", 
        default='output/customer_journey_poc', 
        help="Directory containing the processed JSON transcript files, organized in subdirectories by customer."
    )
    parser.add_argument(
        "--output_file", 
        default='output/journeys_with_embeddings.csv', 
        help="Path to save the final CSV file with journey embeddings."
    )
    args = parser.parse_args()

    # --- 2. Load and Aggregate Transcripts by Journey ---
    journey_dirs = [d for d in glob.glob(os.path.join(args.input_dir, '*')) if os.path.isdir(d)]

    if not journey_dirs:
        print(f"No customer journey subdirectories found in '{args.input_dir}'.")
        exit()

    journeys = []
    for journey_dir in journey_dirs:
        customer_id = os.path.basename(journey_dir)
        json_files = glob.glob(os.path.join(journey_dir, '*.json'))
        
        # Sort files to maintain chronological order if filenames have timestamps/sequence
        json_files.sort()

        full_journey_transcript = ""
        call_ids = []
        for file_path in json_files:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                full_journey_transcript += data.get("full_transcript", "") + "\n\n"
                call_ids.append(os.path.splitext(os.path.basename(file_path))[0])

        if full_journey_transcript:
            journeys.append({
                "customer_id": customer_id,
                "full_journey": full_journey_transcript.strip(),
                "call_ids": ", ".join(call_ids)
            })

    df = pd.DataFrame(journeys)

    # --- 3. Generate Embeddings for Journeys ---
    print(f"Found {len(df)} customer journeys to embed.")

    tqdm.pandas(desc="Generating journey embeddings")
    df['embedding'] = df['full_journey'].progress_apply(get_embedding)

    # --- 4. Save Results ---
    df.to_csv(args.output_file, index=False)
    print(f"\nSuccessfully generated journey embeddings and saved to '{args.output_file}'.")

if __name__ == "__main__":
    main()