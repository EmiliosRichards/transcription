import chromadb
from typing import List, Dict, Any
from app.config import settings
from chromadb.utils import embedding_functions

class IngestionService:
    """
    A service to handle the ingestion of documents into the ChromaDB collection.
    It generates embeddings on the fly and stores the documents.
    """

    def __init__(self):
        """Initializes the ChromaDB client and the embedding function."""
        self.client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
        self.openai_ef = embedding_functions.OpenAIEmbeddingFunction(
            api_key=settings.OPENAI_API_KEY,
            model_name=settings.EMBEDDING_MODEL
        )
        self.collection = self._get_or_create_collection()

    def _get_or_create_collection(self):
        """
        Retrieves the collection from ChromaDB or creates it if it doesn't exist.
        """
        try:
            collection = self.client.get_collection(
                name=settings.CHROMA_COLLECTION_NAME,
                embedding_function=self.openai_ef # type: ignore
            )
            print(f"Collection '{settings.CHROMA_COLLECTION_NAME}' loaded.")
        except Exception:
            print(f"Collection '{settings.CHROMA_COLLECTION_NAME}' not found. Creating a new one.")
            collection = self.client.create_collection(
                name=settings.CHROMA_COLLECTION_NAME,
                embedding_function=self.openai_ef # type: ignore
            )
        return collection

    def ingest_documents(self, documents: List[Dict[str, Any]]):
        """
        Processes and ingests a list of documents into the collection.

        Args:
            documents: A list of dictionaries, where each dictionary represents
                       a document to be ingested. Expected to have 'document_text'
                       and 'metadata' keys.
        """
        if not documents:
            print("No documents provided for ingestion.")
            return

        docs_to_embed = [doc['document_text'] for doc in documents]
        embeddings = [doc['embedding'] for doc in documents]
        metadatas = [doc['metadata'] for doc in documents]
        ids = [str(meta.get('id', i)) for i, meta in enumerate(metadatas)]

        # The embedding function is not used here, as we are providing pre-computed embeddings.
        print(f"Ingesting {len(docs_to_embed)} documents with pre-computed embeddings...")
        self.collection.add(
            embeddings=embeddings,
            documents=docs_to_embed,
            metadatas=metadatas,
            ids=ids
        )
        print(f"Successfully ingested {len(docs_to_embed)} documents.")
        print(f"Total items in collection: {self.collection.count()}")

# Singleton instance
ingestion_service = IngestionService()