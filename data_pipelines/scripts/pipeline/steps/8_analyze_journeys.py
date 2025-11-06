import os
import pandas as pd
import openai
from dotenv import load_dotenv
import argparse

# Load environment variables from .env file
load_dotenv()

# --- 1. Setup ---
if "OPENAI_API_KEY" not in os.environ:
    print("OPENAI_API_KEY environment variable not found.")
    os.environ["OPENAI_API_KEY"] = input("Please enter your OpenAI API key: ")

openai.api_key = os.environ["OPENAI_API_KEY"]

def load_prompt(prompt_name: str) -> str:
    """Loads a prompt template from the prompts directory."""
    prompt_path = os.path.join("prompts", f"{prompt_name}.txt")
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise ValueError(f"Prompt file not found: {prompt_path}")

def analyze_journey(journey_text: str):
    """
    Sends the aggregated journey transcript to the LLM for analysis.
    """
    prompt_template = load_prompt("analyze_journey")
    prompt = prompt_template.format(transcription_text=journey_text)

    try:
        response = openai.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return response.choices[0].message.content.strip() if response.choices[0].message.content else "No insights generated."
    except Exception as e:
        print(f"An error occurred during analysis: {e}")
        return f"Error: {e}"

def main():
    parser = argparse.ArgumentParser(description="Analyze aggregated customer journeys.")
    parser.add_argument(
        "--input_file",
        default='output/customer_journey_poc/aggregated_journeys.csv',
        help="Path to the aggregated customer journeys CSV file."
    )
    parser.add_argument(
        "--output_file",
        default='output/customer_journey_poc/final_analysis.csv',
        help="Path to save the final analysis."
    )
    args = parser.parse_args()

    # --- Load Journeys ---
    try:
        df = pd.read_csv(args.input_file)
    except FileNotFoundError:
        print(f"Error: The file {args.input_file} was not found.")
        print("Please run the aggregation script (7_aggregate_transcripts.py) first.")
        exit()

    # --- Perform Analysis ---
    print(f"Analyzing {len(df)} customer journeys...")
    
    analyses = []
    for _, row in tqdm(df.iterrows(), total=df.shape[0], desc="Analyzing journeys"):
        analysis = analyze_journey(row['full_journey'])
        analyses.append(analysis)
    
    df['analysis'] = analyses
    
    # --- Save Results ---
    df.to_csv(args.output_file, index=False)
    print(f"\nSuccessfully analyzed journeys and saved to '{args.output_file}'.")

if __name__ == "__main__":
    from tqdm import tqdm
    main()