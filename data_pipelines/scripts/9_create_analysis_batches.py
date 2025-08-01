import os
import pandas as pd
import tiktoken
import argparse

# --- Constants ---
# Using a smaller token count for more granular batching.
MAX_TOKENS_PER_BATCH = 10000

def get_token_count(text: str, encoding) -> int:
    """Returns the number of tokens in a text string."""
    return len(encoding.encode(text))

def main():
    parser = argparse.ArgumentParser(description="Create token-based batches from aggregated journeys.")
    parser.add_argument(
        "--input_file",
        default='output/customer_journey_poc/tagged_aggregated_journeys.csv',
        help="Path to the CSV file with tagged, aggregated journey transcripts."
    )
    parser.add_argument(
        "--output_dir",
        default='output/customer_journey_poc/batches',
        help="Directory to save the batch CSV files."
    )
    parser.add_argument(
        "--max_tokens",
        type=int,
        default=MAX_TOKENS_PER_BATCH,
        help="Maximum number of tokens per batch."
    )
    args = parser.parse_args()

    # --- 1. Setup ---
    os.makedirs(args.output_dir, exist_ok=True)
    try:
        df = pd.read_csv(args.input_file)
    except FileNotFoundError:
        print(f"Error: Input file not found at {args.input_file}")
        print("Please run the modified aggregation script (7_aggregate_transcripts.py) first.")
        return

    # --- 2. Calculate Metrics for Sorting & Batching ---
    print("Calculating call and token counts for each journey...")
    # Using the cl100k_base encoding for gpt-4/3.5-turbo
    encoding = tiktoken.get_encoding("cl100k_base")
    df['token_count'] = df['tagged_journey_transcript'].apply(lambda x: get_token_count(x, encoding))
    df['call_count'] = df['tagged_journey_transcript'].str.count("--- END OF CALL ---")

    # Sort by call count to group similar journeys together
    df = df.sort_values(by='call_count', ascending=False).reset_index(drop=True)
    print("Journeys sorted by call count to improve batch consistency.")

    # --- 3. Create Batches ---
    print(f"Creating batches with a max of {args.max_tokens} tokens each...")
    batches = []
    current_batch = []
    current_batch_tokens = 0

    for _, row in df.iterrows():
        # If adding the next journey exceeds the limit, save the current batch and start a new one.
        if current_batch_tokens + row['token_count'] > args.max_tokens and current_batch:
            batches.append(pd.DataFrame(current_batch))
            current_batch = []
            current_batch_tokens = 0
        
        current_batch.append(row)
        current_batch_tokens += row['token_count']

    # Add the last batch if it's not empty
    if current_batch:
        batches.append(pd.DataFrame(current_batch))

    # --- 4. Save Batches ---
    for i, batch_df in enumerate(batches):
        batch_path = os.path.join(args.output_dir, f'batch_{i+1}.csv')
        batch_df.to_csv(batch_path, index=False)
        print(f"Saved batch {i+1} with {len(batch_df)} journeys and {batch_df['token_count'].sum()} tokens to {batch_path}")

    print(f"\nSuccessfully created {len(batches)} batches in '{args.output_dir}'.")

if __name__ == "__main__":
    main()