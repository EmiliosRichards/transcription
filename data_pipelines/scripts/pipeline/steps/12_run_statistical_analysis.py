import os
import pandas as pd
import openai
from dotenv import load_dotenv
import argparse
import json
from tqdm import tqdm

# --- 1. Setup ---
load_dotenv()
if "OPENAI_API_KEY" not in os.environ:
    raise EnvironmentError("OPENAI_API_KEY environment variable not found.")
openai.api_key = os.environ["OPENAI_API_KEY"]

def extract_stats(journey_transcript: str, prompt_template: str, model: str) -> dict:
    """Extracts structured stats from a journey transcript using the OpenAI API."""
    prompt = prompt_template.replace("{journey_transcript}", journey_transcript)
    try:
        response = openai.chat.completions.create(
            model="gpt-4.1",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0
        )
        content = response.choices[0].message.content
        return json.loads(content) if content else {}
    except json.JSONDecodeError:
        print("Error: Failed to decode JSON from API response.")
        return {"error": "JSONDecodeError"}
    except Exception as e:
        print(f"An error occurred during stats extraction: {e}")
        return {"error": str(e)}

def main():
    parser = argparse.ArgumentParser(description="Extract structured stats from tagged journeys.")
    parser.add_argument(
        "--input_file",
        default='output/customer_journey_poc/tagged_aggregated_journeys.csv',
        help="Path to the CSV file with tagged, aggregated journey transcripts."
    )
    parser.add_argument(
        "--output_file",
        default='output/customer_journey_poc/journey_stats.csv',
        help="Path to save the final CSV file with extracted stats."
    )
    parser.add_argument(
        "--prompt_file",
        default='prompts/extract_stats_quantitative.txt',
        help="Path to the prompt file for stats extraction."
    )
    parser.add_argument(
        "--model",
        default='gpt-4.1-turbo',
        help="The OpenAI model to use for analysis."
    )
    args = parser.parse_args()

    # --- 2. Load and Process ---
    try:
        with open(args.prompt_file, 'r', encoding='utf-8') as f:
            prompt_template = f.read()
    except FileNotFoundError:
        print(f"Error: Prompt file not found at {args.prompt_file}")
        return

    try:
        df = pd.read_csv(args.input_file)
    except FileNotFoundError:
        print(f"Error: Input file not found at {args.input_file}")
        return

    print(f"Found {len(df)} journeys to analyze for stats.")
    
    # Use tqdm for progress bar
    tqdm.pandas(desc="Extracting stats")
    
    # Apply the extraction function to each journey
    stats_df = df['tagged_journey_transcript'].progress_apply(
        lambda x: pd.Series(extract_stats(x, prompt_template, args.model))
    )
    
    # Combine the original phone number with the new stats
    result_df = pd.concat([df[['phone_number']], stats_df], axis=1)
    
    # --- 3. Save Results ---
    result_df.to_csv(args.output_file, index=False)
    print(f"\nSuccessfully extracted stats and saved to '{args.output_file}'.")

if __name__ == "__main__":
    main()