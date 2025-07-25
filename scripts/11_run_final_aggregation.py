import os
import glob
import openai
from dotenv import load_dotenv
import argparse

# --- 1. Setup ---
load_dotenv()
if "OPENAI_API_KEY" not in os.environ:
    raise EnvironmentError("OPENAI_API_KEY environment variable not found.")
openai.api_key = os.environ["OPENAI_API_KEY"]

def aggregate_summaries(batch_summaries: str, prompt_template: str, model: str) -> str:
    """Aggregates batch summaries into a final report using the OpenAI API."""
    prompt = prompt_template.format(batch_summaries=batch_summaries)
    try:
        response = openai.chat.completions.create(
            model="gpt-4.1",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        content = response.choices[0].message.content
        return content.strip() if content else "Error: No content returned from API."
    except Exception as e:
        print(f"An error occurred during final aggregation: {e}")
        return f"Error aggregating summaries: {e}"

def main():
    parser = argparse.ArgumentParser(description="Run Level 2 aggregation on batch summaries.")
    parser.add_argument(
        "--input_dir",
        default='output/customer_journey_poc/batch_summaries',
        help="Directory containing the summary text files."
    )
    parser.add_argument(
        "--output_file",
        default='output/customer_journey_poc/Final_Qualitative_Report.md',
        help="Path to save the final aggregated markdown report."
    )
    parser.add_argument(
        "--prompt_file",
        default='prompts/aggregate_summaries_qualitative.txt',
        help="Path to the prompt file for final aggregation."
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

    summary_files = sorted(glob.glob(os.path.join(args.input_dir, 'summary_*.txt')))
    if not summary_files:
        print(f"No summary files found in {args.input_dir}. Please run the batch analysis script first.")
        return

    print(f"Found {len(summary_files)} summaries to aggregate.")
    
    # Concatenate all summaries
    all_summaries = []
    for summary_file in summary_files:
        with open(summary_file, 'r', encoding='utf-8') as f:
            all_summaries.append(f.read())
    
    concatenated_summaries = "\n\n--- BATCH SUMMARY ---\n\n".join(all_summaries)
    
    # Get the final report from the AI
    final_report = aggregate_summaries(concatenated_summaries, prompt_template, args.model)
    
    # Save the final report
    with open(args.output_file, 'w', encoding='utf-8') as f:
        f.write(final_report)
    
    print(f"\nSuccessfully generated final report and saved to '{args.output_file}'.")

if __name__ == "__main__":
    main()