from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from app.services import vector_db, prompt_engine, llm_handler, query_parser
import json

# Create a new router
router = APIRouter()

# --- Pydantic Models ---
class SearchQuery(BaseModel):
    query: str
    n_results: int = 3
    stream: bool = False
    where_filter: Optional[Dict[str, Any]] = Field(default=None, description="Optional filter for metadata")

class SourceDocument(BaseModel):
    customer_id: str
    full_journey: str
    call_ids: str
    last_call_date: str
    distance: float

class SearchResponse(BaseModel):
    llm_response: str
    source_documents: list[SourceDocument]

# --- Helper for Streaming ---
async def stream_generator(cleaned_query: str, source_documents: list[SourceDocument]):
    """
    A generator that yields Server-Sent Events for the streaming response.
    """
    # 1. Yield source documents as the first event
    source_docs_json = json.dumps([doc.dict() for doc in source_documents])
    yield f"event: sources\ndata: {source_docs_json}\n\n"

    # 2. Create prompt and stream LLM response
    prompt = prompt_engine.create_prompt(cleaned_query, [doc.dict() for doc in source_documents])
    
    # 3. Yield LLM response chunks
    async for token in llm_handler.get_llm_response_stream(prompt):
        yield f"event: llm_response_chunk\ndata: {json.dumps({'token': token})}\n\n"
        
    # 4. Signal the end of the stream
    yield "event: stream_end\ndata: {}\n\n"


# --- API Endpoints ---
@router.post("/search", tags=["Search"])
async def search(search_query: SearchQuery):
    """
    Performs a RAG-based search. Can return a normal JSON response or a stream
    of Server-Sent Events based on the `stream` parameter.
    """
    try:
        where_filter, cleaned_query = query_parser.parse_query_for_filters(search_query.query)

        search_results = vector_db.search_journeys(
            query_text=cleaned_query,
            n_results=search_query.n_results,
            where_filter=where_filter
        )
        
        if not search_results or not all(search_results.get(key) for key in ['documents', 'metadatas', 'distances']):
            return {"llm_response": "Could not find any relevant documents.", "source_documents": []}

        documents = search_results['documents'][0] if search_results['documents'] else []
        metadatas = search_results['metadatas'][0] if search_results['metadatas'] else []
        distances = search_results['distances'][0] if search_results['distances'] else []

        source_documents = [
            SourceDocument(
                customer_id=str(metadatas[i].get('customer_id', 'UNKNOWN')),
                full_journey=doc,
                call_ids=str(metadatas[i].get('call_ids', '')),
                last_call_date=str(metadatas[i].get('last_call_date', 'N/A')),
                distance=distances[i]
            ) for i, doc in enumerate(documents)
        ]

        if not cleaned_query:
            cleaned_query = " "

        if search_query.stream:
            return StreamingResponse(stream_generator(cleaned_query, source_documents), media_type="text/event-stream")
        else:
            prompt = prompt_engine.create_prompt(cleaned_query, [doc.dict() for doc in source_documents])
            llm_response = await llm_handler.get_llm_response(prompt)
            return {
                "llm_response": llm_response,
                "source_documents": source_documents
            }
            
    except Exception as e:
        print(f"An error occurred during search: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")