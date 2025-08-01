import os
import pandas as pd
import chromadb
from chromadb.utils import embedding_functions
import ast
import argparse
from app.config import settings
from chromadb.utils import embedding_functions

def setup_embedding_function():
    """Sets up the OpenAI embedding function."""
    return embedding_functions.OpenAIEmbeddingFunction(
        api_key=settings.OPENAI_API_KEY,
        model_name=settings.EMBEDDING_MODEL
    )

def ingest_data(force_recreate: bool = False):
    """
    Connects to ChromaDB, creates a collection if it doesn't exist,
    and populates it with data from the embeddings CSV.
    """
    print("--- Starting Data Ingestion ---")
    
    # 1. Setup ChromaDB client and embedding function
    client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
    openai_ef = setup_embedding_function()

    # 2. Handle existing collection
    if force_recreate:
        print(f"Force recreating collection '{settings.CHROMA_COLLECTION_NAME}'...")
        client.delete_collection(name=settings.CHROMA_COLLECTION_NAME)
    
    try:
        collection = client.get_collection(name=settings.CHROMA_COLLECTION_NAME, embedding_function=openai_ef) # type: ignore
        print(f"Collection '{settings.CHROMA_COLLECTION_NAME}' already exists and is populated. Ingestion skipped.")
        print(f"Current item count: {collection.count()}")
        if not force_recreate:
            return
    except Exception:
        print(f"Collection '{settings.CHROMA_COLLECTION_NAME}' not found. Creating a new one.")
        collection = client.create_collection(name=settings.CHROMA_COLLECTION_NAME, embedding_function=openai_ef) # type: ignore

    # 3. Load and process data from CSV
    if not os.path.exists(settings.EMBEDDINGS_CSV_PATH):
        print(f"ERROR: Embeddings CSV file not found at: {settings.EMBEDDINGS_CSV_PATH}.")
        return

    print(f"Loading data from {settings.EMBEDDINGS_CSV_PATH}...")
    df = pd.read_csv(settings.EMBEDDINGS_CSV_PATH)
    
    def safe_literal_eval(embedding_str):
        try:
            return ast.literal_eval(embedding_str)
        except (ValueError, SyntaxError):
            return None
    
    df['embedding'] = df['embedding'].apply(safe_literal_eval)
    df.dropna(subset=['embedding'], inplace=True)

    if df.empty:
        print("ERROR: No valid embeddings found after parsing the CSV.")
        return

    # 4. Prepare data for ChromaDB
    documents = df["full_journey"].tolist()
    embeddings = df["embedding"].tolist()
    metadata_cols = [col for col in df.columns if col not in ["full_journey", "embedding"]]
    metadatas = df[metadata_cols].fillna("").to_dict('records')
    ids = [str(i) for i in range(len(documents))]
    
    # 5. Add data to the collection in batches
    batch_size = 500
    print(f"Ingesting {len(documents)} documents in batches of {batch_size}...")
    for i in range(0, len(documents), batch_size):
        batch_end = i + batch_size
        print(f"  - Ingesting batch {i // batch_size + 1}...")
        collection.add(
            embeddings=embeddings[i:batch_end],
            documents=documents[i:batch_end],
            metadatas=metadatas[i:batch_end], # type: ignore
            ids=ids[i:batch_end]
        )
    
    print("\n--- Data Ingestion Complete ---")
    print(f"Successfully populated the collection '{settings.CHROMA_COLLECTION_NAME}'.")
    print(f"Total items in collection: {collection.count()}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Data ingestion script for ChromaDB.")
    parser.add_argument(
        '--force',
        action='store_true',
        help='If set, the existing collection will be deleted and recreated.'
    )
    args = parser.parse_args()
    
    ingest_data(force_recreate=args.force)