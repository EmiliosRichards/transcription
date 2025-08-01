import os
import pandas as pd
import httpx
import ast
from tqdm import tqdm
from dotenv import load_dotenv
import argparse

# Load environment variables from .env file
load_dotenv()

def load_embedded_data(input_file: str):
    """Loads the CSV file containing pre-computed embeddings."""
    if not os.path.exists(input_file):
        print(f"ERROR: Embeddings CSV file not found at: {input_file}.")
        return []

    print(f"Loading data from {input_file}...")
    df = pd.read_csv(input_file)

    # Safely convert the string representation of embeddings back to a list
    def safe_literal_eval(embedding_str):
        try:
            return ast.literal_eval(embedding_str)
        except (ValueError, SyntaxError):
            return None
    
    df['embedding'] = df['embedding'].apply(safe_literal_eval)
    df.dropna(subset=['embedding'], inplace=True)

    documents = []
    for _, row in tqdm(df.iterrows(), total=df.shape[0], desc="Preparing documents"):
        # Define which columns become metadata
        metadata_cols = {col: row[col] for col in df.columns if col not in ['full_journey', 'embedding']}
        metadata_cols['id'] = metadata_cols.get('call_ids', str(row.name)) # Ensure a unique ID

        documents.append({
            "document_text": row["full_journey"],
            "embedding": row["embedding"],
            "metadata": metadata_cols
        })
    return documents

def send_data_to_backend(documents: list, api_url: str, api_key: str, batch_size: int = 100):
    """Sends the documents with embeddings to the backend API in batches."""
    if not documents:
        print("No documents to send.")
        return

    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    
    with httpx.Client(timeout=30.0) as client:
        for i in tqdm(range(0, len(documents), batch_size), desc="Sending data to backend"):
            batch = documents[i:i + batch_size]
            try:
                response = client.post(api_url, json=batch, headers=headers)
                response.raise_for_status()
                print(f"Successfully sent batch {i // batch_size + 1}. Response: {response.json()}")
            except httpx.HTTPStatusError as e:
                print(f"Error sending batch {i // batch_size + 1}: {e.response.status_code} - {e.response.text}")
            except httpx.RequestError as e:
                print(f"An error occurred while requesting {e.request.url!r}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Load documents with pre-computed embeddings to the backend API.")
    parser.add_argument(
        "--input_file",
        default='output/journeys_with_embeddings.csv',
        help="Path to the CSV file containing text, metadata, and pre-computed embeddings."
    )
    parser.add_argument(
        "--api_url",
        default=os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000/api/v1/ingestion/"),
        help="URL of the backend ingestion API."
    )
    args = parser.parse_args()

    api_key = os.getenv("API_KEY")
    if not api_key:
        raise ValueError("API_KEY environment variable not set. Please set it in your .env file.")

    documents = load_embedded_data(args.input_file)
    send_data_to_backend(documents, args.api_url, api_key)

    print("\n--- Data Loading Complete ---")
    print(f"Processed and sent {len(documents)} documents to the backend.")

if __name__ == "__main__":
    main()