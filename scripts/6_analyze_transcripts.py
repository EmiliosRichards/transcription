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

def main():
    parser = argparse.ArgumentParser(description="Perform exploratory analysis on tagged transcripts.")
    parser.add_argument(
        "--input_file", 
        default='output/transcripts_with_tags.csv', 
        help="Path to the CSV file with tagged transcripts."
    )
    args = parser.parse_args()

    # --- 2. Load Transcripts ---
    try:
        df = pd.read_csv(args.input_file)
    except FileNotFoundError:
        print(f"Error: The file {args.input_file} was not found.")
        print("Please run the tagging script (5_tag_transcripts.py) first.")
        exit()

    # --- 3. Perform Analysis ---
    print("Performing exploratory analysis on the transcripts...")

    # Sample (if dataset large)
    sample_transcripts = "\n\n".join(df['transcript'].head(100))

    prompt = f"""
    You're an expert sales analyst. Review these sales call transcripts and identify:
    1. The most common reasons calls fail.
    2. Common customer objections.
    3. Any notable patterns or unusual interactions between agents and customers.

    Transcripts:
    {sample_transcripts}

    Provide your analysis clearly as bullet points.
    """

    try:
        response = openai.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        insights = response.choices[0].message.content.strip() if response.choices[0].message.content else "No insights generated."

        # --- 4. Output Insights ---
        print("\n--- Exploratory Analysis Insights ---")
        print(insights)
        print("-------------------------------------\n")

    except Exception as e:
        print(f"An error occurred during analysis: {e}")

if __name__ == "__main__":
    main()