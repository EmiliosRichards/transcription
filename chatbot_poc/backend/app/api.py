import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, AsyncGenerator, List, Literal
from app.services import vector_db, prompt_engine, llm_handler
from app.services.query_agent import QueryAgent
from app.services.status_manager import status_manager
import json

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create a new router
router = APIRouter()
query_agent = QueryAgent()

# --- Pydantic Models ---
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class SearchQuery(BaseModel):
    query: str
    stream: bool = False
    history: Optional[List[ChatMessage]] = Field(default=None, description="A list of previous messages in the conversation.")

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
async def stream_generator(query: str, history: Optional[List[ChatMessage]]) -> AsyncGenerator[str, None]:
    """
    A generator that yields Server-Sent Events for the RAG pipeline,
    routing based on the user's detected intent.
    """
    try:
        # 1. Deconstruct Query to determine intent
        yield f"event: status_update\ndata: {json.dumps({'status': status_manager.get_message('understanding')})}\n\n"
        history_dicts = [msg.dict() for msg in history] if history else None
        deconstructed_query = await query_agent.deconstruct_query(query, history=history_dicts)
        logger.info(f"Deconstructed query: '{deconstructed_query.semantic_query}' with intent: {deconstructed_query.intent}")

        # 2. Route based on intent
        if deconstructed_query.intent == "question":
            # RAG pipeline for questions
            if deconstructed_query.hypothetical_document:
                yield f"event: status_update\ndata: {json.dumps({'status': status_manager.get_message('hyde')})}\n\n"
                logger.info(f"HyDE document generated: {deconstructed_query.hypothetical_document}")

            yield f"event: status_update\ndata: {json.dumps({'status': status_manager.get_message('searching')})}\n\n"
            
            search_text = deconstructed_query.hypothetical_document or deconstructed_query.semantic_query
            
            where_filter = {}
            if deconstructed_query.extracted_filters:
                filters = [{f.field: {f.operator: f.value}} for f in deconstructed_query.extracted_filters]
                where_filter = {"$and": filters} if len(filters) > 1 else filters[0]
            
            search_results = vector_db.search_journeys(
                query_text=search_text,
                n_results=deconstructed_query.n_results,
                where_filter=where_filter
            )

            documents_list = search_results.get('documents') if search_results else None
            metadatas_list = search_results.get('metadatas') if search_results else None
            distances_list = search_results.get('distances') if search_results else None

            if documents_list and metadatas_list and distances_list and documents_list[0]:
                documents = documents_list[0]
                metadatas = metadatas_list[0]
                distances = distances_list[0]
                logger.info(f"Found {len(documents)} documents.")
            else:
                logger.warning("Search returned no relevant documents.")
                yield f"event: error\ndata: {json.dumps({'message': 'Could not find any relevant documents for your question.'})}\n\n"
                return

            source_documents = [
                SourceDocument(
                    customer_id=str(md.get('customer_id', 'N/A')),
                    full_journey=doc,
                    call_ids=str(md.get('call_ids', 'N/A')),
                    last_call_date=str(md.get('last_call_date', 'N/A')),
                    distance=dist
                ) for doc, md, dist in zip(documents, metadatas, distances)
            ]
            yield f"event: sources\ndata: {json.dumps({'sources': [doc.dict() for doc in source_documents]})}\n\n"

            yield f"event: status_update\ndata: {json.dumps({'status': status_manager.get_message('synthesizing')})}\n\n"
            prompt = prompt_engine.create_prompt(deconstructed_query.semantic_query, [doc.dict() for doc in source_documents])
            
            async for token in llm_handler.get_llm_response_stream(prompt, history=history_dicts):
                yield f"event: llm_response_chunk\ndata: {json.dumps({'token': token})}\n\n"

        elif deconstructed_query.intent == "chitchat":
            # Direct LLM response for chitchat
            yield f"event: status_update\ndata: {json.dumps({'status': status_manager.get_message('chitchat')})}\n\n"
            # For chitchat, we send empty sources so the UI can clear them
            yield f"event: sources\ndata: {json.dumps({'sources': []})}\n\n"
            
            async for token in llm_handler.get_llm_response_stream(deconstructed_query.semantic_query, is_chitchat=True, history=history_dicts):
                yield f"event: llm_response_chunk\ndata: {json.dumps({'token': token})}\n\n"

        elif deconstructed_query.intent == "sampling":
            yield f"event: status_update\ndata: {json.dumps({'status': status_manager.get_message('sampling')})}\n\n"
            
            search_results = vector_db.get_random_journeys(n_results=deconstructed_query.n_results)

            documents = search_results.get('documents') if search_results else None
            metadatas = search_results.get('metadatas') if search_results else None

            if documents and metadatas:
                logger.info(f"Found {len(documents)} random documents.")
            else:
                logger.warning("Sampling returned no documents.")
                yield f"event: error\ndata: {json.dumps({'message': 'Could not retrieve a sample of documents.'})}\n\n"
                return

            source_documents = [
                SourceDocument(
                    customer_id=str(md.get('customer_id', 'N/A')),
                    full_journey=doc,
                    call_ids=str(md.get('call_ids', 'N/A')),
                    last_call_date=str(md.get('last_call_date', 'N/A')),
                    distance=0.0  # Distance is not applicable for random sampling
                ) for doc, md in zip(documents, metadatas)
            ]
            yield f"event: sources\ndata: {json.dumps({'sources': [doc.dict() for doc in source_documents]})}\n\n"

            yield f"event: status_update\ndata: {json.dumps({'status': status_manager.get_message('synthesizing')})}\n\n"
            prompt = prompt_engine.create_prompt("Summarize the key themes from this random sample of customer interactions.", [doc.dict() for doc in source_documents])
            
            async for token in llm_handler.get_llm_response_stream(prompt, history=history_dicts):
                yield f"event: llm_response_chunk\ndata: {json.dumps({'token': token})}\n\n"
            
    except Exception as e:
        logger.error(f"Error during stream generation: {e}", exc_info=True)
        yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
    finally:
        # 5. Signal the end of the stream
        yield f"event: stream_end\ndata: {json.dumps({})}\n\n"


# --- API Endpoints ---
@router.post("/search", tags=["Search"])
async def search(search_query: SearchQuery):
    """
    Performs a RAG-based search. Can return a normal JSON response or a stream
    of Server-Sent Events based on the `stream` parameter.
    """
    logger.info(f"Received search query: '{search_query.query}' with stream={search_query.stream}")
    
    if search_query.stream:
        return StreamingResponse(
            stream_generator(search_query.query, search_query.history),
            media_type="text/event-stream"
        )
    else:
        # Non-streaming logic with intent routing
        try:
            history_dicts = [msg.dict() for msg in search_query.history] if search_query.history else None
            deconstructed_query = await query_agent.deconstruct_query(search_query.query, history=history_dicts)
            logger.info(f"Deconstructed query: '{deconstructed_query.semantic_query}' with intent: {deconstructed_query.intent}")

            if deconstructed_query.intent == "question":
                if deconstructed_query.hypothetical_document:
                    logger.info(f"HyDE document generated: {deconstructed_query.hypothetical_document}")

                search_text = deconstructed_query.hypothetical_document or deconstructed_query.semantic_query

                where_filter = {}
                if deconstructed_query.extracted_filters:
                    filters = [{f.field: {f.operator: f.value}} for f in deconstructed_query.extracted_filters]
                    where_filter = {"$and": filters} if len(filters) > 1 else filters[0]

                search_results = vector_db.search_journeys(
                    query_text=search_text,
                    n_results=deconstructed_query.n_results,
                    where_filter=where_filter
                )

                documents_list = search_results.get('documents') if search_results else None
                metadatas_list = search_results.get('metadatas') if search_results else None
                distances_list = search_results.get('distances') if search_results else None

                if not (documents_list and metadatas_list and distances_list and documents_list[0]):
                    return SearchResponse(llm_response="Could not find any relevant documents.", source_documents=[])

                documents = documents_list[0]
                metadatas = metadatas_list[0]
                distances = distances_list[0]

                source_documents = [
                    SourceDocument(
                        customer_id=str(md.get('customer_id', 'N/A')),
                        full_journey=doc,
                        call_ids=str(md.get('call_ids', 'N/A')),
                        last_call_date=str(md.get('last_call_date', 'N/A')),
                        distance=dist
                    ) for doc, md, dist in zip(documents, metadatas, distances)
                ]

                prompt = prompt_engine.create_prompt(deconstructed_query.semantic_query, [doc.dict() for doc in source_documents])
                llm_response = await llm_handler.get_llm_response(prompt, history=history_dicts)
                
                return SearchResponse(llm_response=llm_response, source_documents=source_documents)

            elif deconstructed_query.intent == "chitchat":
                llm_response = await llm_handler.get_llm_response(deconstructed_query.semantic_query, is_chitchat=True, history=history_dicts)
                return SearchResponse(llm_response=llm_response, source_documents=[])

            elif deconstructed_query.intent == "sampling":
                search_results = vector_db.get_random_journeys(n_results=deconstructed_query.n_results)

                documents = search_results.get('documents') if search_results else None
                metadatas = search_results.get('metadatas') if search_results else None

                if not (documents and metadatas):
                    return SearchResponse(llm_response="Could not retrieve a sample of documents.", source_documents=[])

                source_documents = [
                    SourceDocument(
                        customer_id=str(md.get('customer_id', 'N/A')),
                        full_journey=doc,
                        call_ids=str(md.get('call_ids', 'N/A')),
                        last_call_date=str(md.get('last_call_date', 'N/A')),
                        distance=0.0
                    ) for doc, md in zip(documents, metadatas)
                ]

                prompt = prompt_engine.create_prompt("Summarize the key themes from this random sample of customer interactions.", [doc.dict() for doc in source_documents])
                llm_response = await llm_handler.get_llm_response(prompt, history=history_dicts)
                
                return SearchResponse(llm_response=llm_response, source_documents=source_documents)

        except Exception as e:
            logger.error(f"An error occurred during non-streaming search: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal Server Error")