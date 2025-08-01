import os
import glob
import pandas as pd
import openai
from dotenv import load_dotenv
import argparse
from data_pipelines import config

# --- 1. Setup ---
load_dotenv()
if "OPENAI_API_KEY" not in os.environ:
    raise EnvironmentError("OPENAI_API_KEY environment variable not found.")
openai.api_key = os.environ["OPENAI_API_KEY"]

def analyze_batch(batch_transcripts: str, prompt_template: str, model: str) -> str:
    """Analyzes a batch of transcripts using the OpenAI API."""
    prompt = prompt_template.format(batch_transcripts=batch_transcripts)
    try:
        response = openai.chat.completions.create(
            model="gpt-4.1",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        content = response.choices[0].message.content
        return content.strip() if content else "Error: No content returned from API."
    except Exception as e:
        print(f"An error occurred during batch analysis: {e}")
        return f"Error analyzing batch: {e}"

def main():
    parser = argparse.ArgumentParser(description="Run Level 1 batch analysis on journey batches.")
    parser.add_argument(
        "--input_dir",
        default=str(config.BATCHES_DIR),
        help="Directory containing the batch CSV files."
    )
    parser.add_argument(
        "--output_dir",
        default=str(config.BATCH_SUMMARIES_DIR),
        help="Directory to save the summary text files."
    )
    parser.add_argument(
        "--prompt_file",
        default=str(config.PROMPTS_DIR / 'analyze_batch_qualitative.txt'),
        help="Path to the prompt file for batch analysis."
    )
    parser.add_argument(
        "--model",
        default='gpt-4.1-turbo',
        help="The OpenAI model to use for analysis."
    )
    args = parser.parse_args()

    # --- 2. Load and Process ---
    os.makedirs(args.output_dir, exist_ok=True)
    try:
        with open(args.prompt_file, 'r', encoding='utf-8') as f:
            prompt_template = f.read()
    except FileNotFoundError:
        print(f"Error: Prompt file not found at {args.prompt_file}")
        return

    batch_files = sorted(glob.glob(os.path.join(args.input_dir, 'batch_*.csv')))
    if not batch_files:
        print(f"No batch files found in {args.input_dir}. Please run the batch creation script first.")
        return

    print(f"Found {len(batch_files)} batches to analyze.")

    for batch_file in batch_files:
        print(f"Analyzing {batch_file}...")
        df = pd.read_csv(batch_file)
        
        # Concatenate all transcripts in the batch
        concatenated_transcripts = "\n\n--- JOURNEY SEPARATOR ---\n\n".join(df['tagged_journey_transcript'])
        
        # Get the summary from the AI
        summary = analyze_batch(concatenated_transcripts, prompt_template, args.model)
        
        # Save the summary
        batch_num = os.path.basename(batch_file).split('_')[1].split('.')[0]
        summary_path = os.path.join(args.output_dir, f'summary_{batch_num}.txt')
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(summary)
        
        print(f"Saved summary for batch {batch_num} to {summary_path}")

    print("\nSuccessfully completed Level 1 batch analysis.")

if __name__ == "__main__":
    main()