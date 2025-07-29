import os
import glob
import json
import pandas as pd
import openai
from tqdm import tqdm
import argparse
from dotenv import load_dotenv
from datetime import datetime

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
        default='output/customer_journey_poc',
        help="Directory containing the processed JSON transcript files."
    )
    parser.add_argument(
        "--output_file",
        default='output/transcripts_with_embeddings.csv',
        help="Path to save the final CSV file with embeddings."
    )
    parser.add_argument(
        "--aggregate_journeys",
        action="store_true",
        help="Aggregate transcripts into customer journeys before embedding."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of customer journeys to process."
    )
    args = parser.parse_args()

    # --- 2. Load Transcripts ---
    all_json_files = glob.glob(os.path.join(args.input_dir, '**/*.json'), recursive=True)

    if not all_json_files:
        print(f"No .json files found in '{args.input_dir}'.")
        exit()

    if args.aggregate_journeys:
        # First, group files by customer_id
        customer_files = {}
        for file_path in all_json_files:
            customer_id = os.path.basename(os.path.dirname(file_path))
            if customer_id not in customer_files:
                customer_files[customer_id] = []
            customer_files[customer_id].append(file_path)
        
        # Apply the limit if provided
        customer_ids_to_process = list(customer_files.keys())
        if args.limit:
            customer_ids_to_process = customer_ids_to_process[:args.limit]
            print(f"Limiting processing to {len(customer_ids_to_process)} customers.")

        journeys = {}
        for customer_id in customer_ids_to_process:
            journeys[customer_id] = {
                "full_journey": "", "call_ids": [], "dates": [],
                "outcomes": [], "tags": [], "sentiments": []
            }
            for file_path in customer_files[customer_id]:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    journeys[customer_id]["full_journey"] += data.get("full_transcript", "") + "\n\n"
                    journeys[customer_id]["call_ids"].append(os.path.splitext(os.path.basename(file_path))[0])
                    journeys[customer_id]["dates"].append(os.path.getmtime(file_path))
                    
                    if "analysis" in data and isinstance(data["analysis"], dict):
                        analysis = data["analysis"]
                        if analysis.get("outcome"):
                            journeys[customer_id]["outcomes"].append(analysis["outcome"])
                        if analysis.get("tags"):
                            journeys[customer_id]["tags"].extend(analysis["tags"])
                        if analysis.get("sentiment"):
                            journeys[customer_id]["sentiments"].append(analysis["sentiment"])

        journey_list = []
        for customer_id, data in journeys.items():
            # Calculate average sentiment, avoiding division by zero
            avg_sentiment = round(sum(data["sentiments"]) / len(data["sentiments"]), 2) if data["sentiments"] else 0
            
            # Create a unique list of tags
            unique_tags = sorted(list(set(data["tags"])))

            journey_list.append({
                "customer_id": customer_id,
                "full_journey": data["full_journey"].strip(),
                "call_ids": ", ".join(data["call_ids"]),
                "last_call_date": int(max(data["dates"])),
                "journey_outcomes": data["outcomes"],
                "journey_tags": unique_tags,
                "average_sentiment": avg_sentiment
            })
        df = pd.DataFrame(journey_list)
        embedding_column = 'full_journey'
    else:
        # Apply limit for non-aggregated transcripts as well
        files_to_process = all_json_files
        if args.limit:
            files_to_process = files_to_process[:args.limit]
            print(f"Limiting processing to {len(files_to_process)} transcripts.")

        transcripts = []
        for file_path in files_to_process:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Also include analysis data for individual transcript processing
                analysis_data = data.get("analysis", {})
                transcripts.append({
                    "call_id": os.path.splitext(os.path.basename(file_path))[0],
                    "transcript": data.get("full_transcript", ""),
                    "call_date": int(os.path.getmtime(file_path)),
                    "summary": analysis_data.get("summary"),
                    "outcome": analysis_data.get("outcome"),
                    "sentiment": analysis_data.get("sentiment"),
                    "tags": ", ".join(analysis_data.get("tags", []))
                })
        df = pd.DataFrame(transcripts)
        embedding_column = 'transcript'


    # --- 3. Generate Embeddings ---
    print(f"Found {len(df)} items to embed.")

    tqdm.pandas(desc="Generating embeddings")
    df['embedding'] = df[embedding_column].progress_apply(get_embedding)

    # --- 4. Save Results ---
    df.to_csv(args.output_file, index=False)
    print(f"\nSuccessfully generated embeddings and saved to '{args.output_file}'.")

if __name__ == "__main__":
    main()