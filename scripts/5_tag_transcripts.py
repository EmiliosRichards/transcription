import os
import pandas as pd
import openai
from tqdm import tqdm
from dotenv import load_dotenv
import argparse

# Load environment variables from .env file
load_dotenv()

# --- 1. Setup ---
if "OPENAI_API_KEY" not in os.environ:
    print("OPENAI_API_KEY environment variable not found.")
    os.environ["OPENAI_API_KEY"] = input("Please enter your OpenAI API key: ")

openai.api_key = os.environ["OPENAI_API_KEY"]

def tag_call(transcript):
    prompt = f"""
    Categorize the following sales call transcript into exactly one of these categories:
    1. Relevant - Success
    2. Relevant - Failed but interested
    3. Relevant - Failed not interested
    4. Relevant - Failed saturated with customers
    5. Not Relevant (no useful conversation)

    Transcript:
    {transcript}

    Only reply with the exact category name.
    """
    try:
        response = openai.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        content = response.choices[0].message.content
        category = content.strip() if content else "Error: No content"
        return category
    except Exception as e:
        print(f"An error occurred during tagging: {e}")
        return "Error"

def main():
    parser = argparse.ArgumentParser(description="Tag transcripts with categories.")
    parser.add_argument(
        "--input_file", 
        default='output/transcripts_with_embeddings.csv', 
        help="Path to the CSV file with transcripts and embeddings."
    )
    parser.add_argument(
        "--output_file", 
        default='output/transcripts_with_tags.csv', 
        help="Path to save the final CSV file with tags."
    )
    args = parser.parse_args()

    # --- 2. Load Transcripts ---
    try:
        df = pd.read_csv(args.input_file)
    except FileNotFoundError:
        print(f"Error: The file {args.input_file} was not found.")
        print("Please run the embedding script (4_embed_transcripts.py) first.")
        exit()

    # --- 3. Tag Transcripts ---
    print(f"Found {len(df)} transcripts to tag.")

    tqdm.pandas(desc="Tagging transcripts")
    df['category'] = df['transcript'].progress_apply(tag_call)

    # --- 4. Save Results ---
    df.to_csv(args.output_file, index=False)
    print(f"\nSuccessfully tagged transcripts and saved to '{args.output_file}'.")

if __name__ == "__main__":
    main()