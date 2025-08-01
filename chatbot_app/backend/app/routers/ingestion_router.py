from fastapi import APIRouter, Depends, HTTPException, status, Security
from fastapi.security.api_key import APIKeyHeader
from typing import List, Dict, Any
from app.services.ingestion import ingestion_service
from app.config import settings

router = APIRouter()

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

async def get_api_key(api_key: str = Security(api_key_header)):
    """Dependency to verify the API key."""
    if api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    return api_key

@router.post(
    "/",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest documents into the knowledge base",
    dependencies=[Depends(get_api_key)]
)
async def ingest_documents(documents: List[Dict[str, Any]]):
    """
    Receives a list of documents, generates embeddings, and ingests them
    into the vector database.

    - **documents**: A list of dictionaries, each containing:
        - `document_text`: The string content of the document.
        - `embedding`: The pre-computed embedding vector for the document.
        - `metadata`: A dictionary of metadata associated with the document.
                      Must contain a unique `id` for each document.
    """
    try:
        ingestion_service.ingest_documents(documents)
        return {"status": "success", "message": f"Accepted {len(documents)} documents for ingestion."}
    except Exception as e:
        # It's better to catch specific exceptions, but this is a safeguard.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during ingestion: {e}"
        )