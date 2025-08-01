import os
import random
import pandas as pd
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
import ast

# Load environment variables
load_dotenv()

# --- Constants ---
EMBEDDINGS_CSV_PATH = os.path.join(os.path.dirname(__file__), "../../../../output/journeys_with_embeddings.csv")
CHROMA_DB_PATH = os.path.join(os.path.dirname(__file__), "../../../../output/chroma_db")
COLLECTION_NAME = "journeys_prod"

# --- OpenAI Embedding Function ---
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise ValueError("The OPENAI_API_KEY environment variable is not set.")

openai_ef = embedding_functions.OpenAIEmbeddingFunction(
    api_key=openai_api_key,
    model_name="text-embedding-3-small"
)

# --- ChromaDB Client ---
client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

def get_or_create_collection():
    """
    Retrieves or creates the ChromaDB collection, populating it with data if it's the first time.
    """
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"Deleted old collection '{COLLECTION_NAME}'.")
    except Exception:
        pass

    try:
        collection = client.get_collection(name=COLLECTION_NAME, embedding_function=openai_ef) # type: ignore
        print(f"Successfully retrieved existing collection '{COLLECTION_NAME}'.")
        return collection
    except Exception:
        print(f"Collection '{COLLECTION_NAME}' not found. Creating and populating a new one...")
        collection = client.create_collection(name=COLLECTION_NAME, embedding_function=openai_ef) # type: ignore
        
        print("Skipping collection population because embeddings file is missing.")
        # if not os.path.exists(EMBEDDINGS_CSV_PATH):
        #     raise FileNotFoundError(f"Embeddings CSV file not found at: {EMBEDDINGS_CSV_PATH}")
        
        # df = pd.read_csv(EMBEDDINGS_CSV_PATH)
        
        # def safe_literal_eval(embedding_str):
        #     try:
        #         return ast.literal_eval(embedding_str)
        #     except (ValueError, SyntaxError):
        #         return None
        
        # df['embedding'] = df['embedding'].apply(safe_literal_eval)
        # df.dropna(subset=['embedding'], inplace=True)

        # if df.empty:
        #     print("ERROR: No valid embeddings found after parsing.")
        #     return collection

        # documents = df["full_journey"].tolist()
        # embeddings = df["embedding"].tolist()
        # metadata_cols = [col for col in df.columns if col not in ["full_journey", "embedding"]]
        # metadatas = df[metadata_cols].fillna("").to_dict('records')
        # ids = [str(i) for i in range(len(documents))]
        
        # collection.add(
        #     embeddings=embeddings,
        #     documents=documents,
        #     metadatas=metadatas, # type: ignore
        #     ids=ids
        # )
        # print("Successfully populated the collection.")
        return collection

def search_journeys(query_text, n_results=3, where_filter=None):
    """
    Searches the collection for journeys with an optional metadata filter.
    """
    collection = get_or_create_collection()
    
    if where_filter and not isinstance(where_filter, dict):
        print("Warning: Invalid where_filter provided. Must be a dict. Ignoring filter.")
        where_filter = None

    print(f"DEBUG: ChromaDB 'where' filter: {where_filter}") # Debugging print statement

    return collection.query(
        query_texts=[query_text],
        n_results=n_results,
        where=where_filter
    )

def get_random_journeys(n_results=5):
    """
    Retrieves a random sample of journeys from the collection.
    """
    collection = get_or_create_collection()
    
    # Get all document IDs from the collection
    all_ids = collection.get(include=[])['ids']
    
    if not all_ids:
        return None
        
    # Randomly select n_results IDs
    # Ensure we don't request more samples than available
    sample_size = min(n_results, len(all_ids))
    random_ids = random.sample(all_ids, sample_size)
    
    # Retrieve the full documents for the selected IDs
    return collection.get(ids=random_ids)

def get_collection_count():
    """
    Returns the number of documents in the collection.
    """
    collection = get_or_create_collection()
    return collection.count()

# --- Main Execution for Testing ---
if __name__ == '__main__':
    print("Testing vector_db.py...")
    
    test_collection = get_or_create_collection()
    print(f"Collection count: {test_collection.count()}")

    test_query = "salesperson went off-topic"
    print(f"\nPerforming a test search for: '{test_query}'")
    search_results = search_journeys(test_query, n_results=2)

    if search_results:
        documents = search_results.get('documents', [[]])
        metadatas = search_results.get('metadatas', [[]])
        distances = search_results.get('distances', [[]])

        # The query returns a list containing one list of results
        if documents and len(documents[0]) > 0:
            print(f"Found {len(documents[0])} results.")
            for i, doc in enumerate(documents[0]):
                metadata = metadatas[0][i] if metadatas and len(metadatas[0]) > i else {}
                distance = distances[0][i] if distances and len(distances[0]) > i else 'N/A'
                
                print(f"\nResult {i+1}:")
                print(f"  - Customer ID: {metadata.get('customer_id', 'N/A')}")
                print(f"  - Last Call Date: {metadata.get('last_call_date', 'N/A')}")
                print(f"  - Transcript Snippet: {doc[:150]}...")
                print(f"  - Distance: {distance}")
        else:
            print("Test search returned no documents.")
    else:
        print("No results found for the test query.")

    print("\nPerforming a test for random sampling...")
    random_results = get_random_journeys(n_results=3)

    if random_results:
        documents = random_results.get('documents', [])
        metadatas = random_results.get('metadatas', [])
        
        if documents:
            print(f"Found {len(documents)} random results.")
            for i, doc in enumerate(documents):
                metadata = metadatas[i] if metadatas and len(metadatas) > i else {}
                print(f"\nRandom Result {i+1}:")
                print(f"  - Customer ID: {metadata.get('customer_id', 'N/A')}")
                print(f"  - Last Call Date: {metadata.get('last_call_date', 'N/A')}")
                print(f"  - Transcript Snippet: {doc[:150]}...")
        else:
            print("Random sampling returned no documents.")
    else:
        print("No results found for random sampling.")
