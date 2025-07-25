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
    parser = argparse.ArgumentParser(description="Generate embeddings for processed transcripts.")
    parser.add_argument(
        "--input_dir", 
        default='output/processed', 
        help="Directory containing the processed JSON transcript files."
    )
    parser.add_argument(
        "--output_file", 
        default='output/transcripts_with_embeddings.csv', 
        help="Path to save the final CSV file with embeddings."
    )
    args = parser.parse_args()

    # --- 2. Load Transcripts ---
    json_files = glob.glob(os.path.join(args.input_dir, '**/*.json'), recursive=True)

    if not json_files:
        print(f"No .json files found in '{args.input_dir}'.")
        exit()

    transcripts = []
    for file_path in json_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            transcripts.append({
                "call_id": os.path.splitext(os.path.basename(file_path))[0],
                "transcript": data.get("full_transcript", "")
            })

    df = pd.DataFrame(transcripts)

    # --- 3. Generate Embeddings ---
    print(f"Found {len(df)} transcripts to embed.")

    tqdm.pandas(desc="Generating embeddings")
    df['embedding'] = df['transcript'].progress_apply(get_embedding)

    # --- 4. Save Results ---
    df.to_csv(args.output_file, index=False)
    print(f"\nSuccessfully generated embeddings and saved to '{args.output_file}'.")

if __name__ == "__main__":
    main()