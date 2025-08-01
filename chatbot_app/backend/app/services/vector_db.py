import os
import random
import chromadb
from chromadb.utils import embedding_functions
import random
from app.config import settings

# --- Embedding Function ---
openai_ef = embedding_functions.OpenAIEmbeddingFunction(
    api_key=settings.OPENAI_API_KEY,
    model_name=settings.EMBEDDING_MODEL
)

# --- ChromaDB Client ---
# This service now assumes the DB and collection are created and populated
# by the offline `ingest_data.py` script.
client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
_collection = None

def get_collection():
    """
    Returns the ChromaDB collection, initializing it if necessary.
    """
    global _collection
    if _collection is None:
        _collection = client.get_collection(name=settings.CHROMA_COLLECTION_NAME, embedding_function=openai_ef) # type: ignore
    return _collection

def get_or_create_collection():
    """
    Gets or creates the ChromaDB collection.
    """
    global _collection
    _collection = client.get_or_create_collection(name=settings.CHROMA_COLLECTION_NAME, embedding_function=openai_ef) # type: ignore
    return _collection

def search_journeys(query_text, n_results=3, where_filter=None):
    """
    Searches the collection for journeys with an optional metadata filter.
    """
    collection = get_collection()
    if where_filter and not isinstance(where_filter, dict):
        print("Warning: Invalid where_filter provided. Must be a dict. Ignoring filter.")
        where_filter = None

    print(f"DEBUG: ChromaDB 'where' filter: {where_filter}")
    return collection.query(
        query_texts=[query_text],
        n_results=n_results,
        where=where_filter
    )

def get_random_journeys(n_results=5):
    """
    Retrieves a random sample of journeys from the collection.
    """
    collection = get_collection()
    all_ids = collection.get(include=[])['ids']
    if not all_ids:
        return None
        
    sample_size = min(n_results, len(all_ids))
    random_ids = random.sample(all_ids, sample_size)
    
    return collection.get(ids=random_ids)

def get_collection_count():
    """
    Returns the number of documents in the collection.
    """
    collection = get_collection()
    return collection.count()
