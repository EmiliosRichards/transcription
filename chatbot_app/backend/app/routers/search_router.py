import logging
import json
import uuid
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, AsyncGenerator, Literal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app import database
from app.services import vector_db, prompt_engine, llm_handler
from app.services.query_agent import QueryAgent
from app.services.status_manager import status_manager

# --- Logging Setup ---
logger = logging.getLogger(__name__)

# --- Router Setup ---
router = APIRouter()
query_agent = QueryAgent()

# --- DB Dependency ---
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with database.AsyncSessionLocal() as session:
        yield session

# --- Pydantic Models ---
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str

    class Config:
        from_attributes = True

class SearchQuery(BaseModel):
    query: str
    stream: bool = False
    history: Optional[List[ChatMessage]] = Field(default=None, description="A list of previous messages in the conversation.")
    session_id: Optional[str] = None

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
async def stream_generator(query: str, db: AsyncSession, session_id: str) -> AsyncGenerator[str, None]:
    """
    A generator that yields Server-Sent Events for the RAG pipeline,
    routing based on the user's detected intent and saving the conversation.
    It fetches the last 10 messages to provide conversational context.
    """
    full_response = ""
    try:
        # 1. Fetch conversation history for context
        result = await db.execute(
            select(database.ChatLog)
            .filter(database.ChatLog.session_id == session_id)
            .order_by(database.ChatLog.id.desc())
            .limit(10)
        )
        db_history_messages = list(result.scalars().all())
        db_history_messages.reverse() # Order from oldest to newest
        history = [ChatMessage.from_orm(msg) for msg in db_history_messages]
        history_dicts = [msg.dict() for msg in history]

        # 2. Deconstruct Query to determine intent
        yield f"event: status_update\ndata: {json.dumps({'status': status_manager.get_message('understanding')})}\n\n"
        deconstructed_query = await query_agent.deconstruct_query(query, history=history_dicts)
        logger.info(f"Deconstructed query: '{deconstructed_query.semantic_query}' with intent: {deconstructed_query.intent}")

        # 2. Route based on intent
        if deconstructed_query.intent == "question":
            if vector_db.get_collection_count() == 0:
                logger.warning("Attempted to search an empty vector database.")
                yield f"event: error\ndata: {json.dumps({'message': 'The knowledge base is empty. Please transcribe audio files to enable search.'})}\n\n"
                return

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
                query_text=search_text, n_results=deconstructed_query.n_results, where_filter=where_filter
            )

            documents_list = search_results.get('documents') if search_results else None
            metadatas_list = search_results.get('metadatas') if search_results else None
            distances_list = search_results.get('distances') if search_results else None

            if not (documents_list and metadatas_list and distances_list and documents_list[0]):
                logger.warning("Search returned no relevant documents.")
                yield f"event: error\ndata: {json.dumps({'message': 'Could not find any relevant documents for your question.'})}\n\n"
                return

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
            yield f"event: sources\ndata: {json.dumps({'sources': [doc.dict() for doc in source_documents]})}\n\n"

            yield f"event: status_update\ndata: {json.dumps({'status': status_manager.get_message('synthesizing')})}\n\n"
            prompt = prompt_engine.create_prompt(deconstructed_query.semantic_query, [doc.dict() for doc in source_documents])
            
            async for token in llm_handler.get_llm_response_stream(prompt, history=history_dicts):
                full_response += token
                yield f"event: llm_response_chunk\ndata: {json.dumps({'token': token})}\n\n"

        elif deconstructed_query.intent == "chitchat":
            yield f"event: status_update\ndata: {json.dumps({'status': status_manager.get_message('chitchat')})}\n\n"
            yield f"event: sources\ndata: {json.dumps({'sources': []})}\n\n"
            async for token in llm_handler.get_llm_response_stream(deconstructed_query.semantic_query, is_chitchat=True, history=history_dicts):
                full_response += token
                yield f"event: llm_response_chunk\ndata: {json.dumps({'token': token})}\n\n"

        elif deconstructed_query.intent == "sampling":
            yield f"event: status_update\ndata: {json.dumps({'status': status_manager.get_message('sampling')})}\n\n"
            search_results = vector_db.get_random_journeys(n_results=deconstructed_query.n_results)
            documents = search_results.get('documents') if search_results else None
            metadatas = search_results.get('metadatas') if search_results else None

            if not (documents and metadatas):
                logger.warning("Sampling returned no documents.")
                yield f"event: error\ndata: {json.dumps({'message': 'Could not retrieve a sample of documents.'})}\n\n"
                return

            source_documents = [
                SourceDocument(
                    customer_id=str(md.get('customer_id', 'N/A')),
                    full_journey=doc,
                    call_ids=str(md.get('call_ids', 'N/A')),
                    last_call_date=str(md.get('last_call_date', 'N/A')),
                    distance=0.0
                ) for doc, md in zip(documents, metadatas)
            ]
            yield f"event: sources\ndata: {json.dumps({'sources': [doc.dict() for doc in source_documents]})}\n\n"

            yield f"event: status_update\ndata: {json.dumps({'status': status_manager.get_message('synthesizing')})}\n\n"
            prompt = prompt_engine.create_prompt("Summarize the key themes from this random sample of customer interactions.", [doc.dict() for doc in source_documents])
            
            async for token in llm_handler.get_llm_response_stream(prompt, history=history_dicts):
                full_response += token
                yield f"event: llm_response_chunk\ndata: {json.dumps({'token': token})}\n\n"
            
    except Exception as e:
        logger.error(f"Error during stream generation: {e}", exc_info=True)
        yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
    finally:
        # 5. Save the assistant's full response
        assistant_log_id = None
        if full_response:
            assistant_log = database.ChatLog(session_id=session_id, role="assistant", content=full_response)
            db.add(assistant_log)
            await db.commit()
            await db.refresh(assistant_log)
            assistant_log_id = assistant_log.id
            logger.info(f"Saved assistant response for session {session_id} with ID {assistant_log_id}")
        # 6. Signal the end of the stream, and send back the session_id and the new message ID
        yield f"event: stream_end\ndata: {json.dumps({'session_id': session_id, 'assistant_message_id': assistant_log_id})}\n\n"


@router.post("/search", tags=["Search"])
async def search(search_query: SearchQuery, db: AsyncSession = Depends(get_db)):
    """
    Performs a RAG-based search. Can return a normal JSON response or a stream
    of Server-Sent Events based on the `stream` parameter.
    """
    logger.info(f"Received search query: '{search_query.query}' with stream={search_query.stream}")
    
    session_id = search_query.session_id if search_query.session_id else str(uuid.uuid4())

    if search_query.stream:
        # Save user's message before starting the stream
        user_log = database.ChatLog(session_id=session_id, role="user", content=search_query.query)
        db.add(user_log)
        await db.commit()
        await db.refresh(user_log)
        logger.info(f"Saved user query for session {session_id} with ID {user_log.id}")

        async def combined_generator():
            # First, yield the user message ID so the frontend can update its state
            yield f"event: user_message_saved\ndata: {json.dumps({'user_message_id': user_log.id, 'session_id': session_id})}\n\n"
            # Then, yield everything from the main stream generator
            async for chunk in stream_generator(search_query.query, db, session_id):
                yield chunk

        return StreamingResponse(
            combined_generator(),
            media_type="text/event-stream"
        )
    else:
        # Non-streaming logic with intent routing
        try:
            # Save user message first
            user_log = database.ChatLog(session_id=session_id, role="user", content=search_query.query)
            db.add(user_log)
            await db.commit() # Commit the user log here
            
            # Fetch history from DB for context
            result = await db.execute(
                select(database.ChatLog)
                .filter(database.ChatLog.session_id == session_id)
                .order_by(database.ChatLog.id.desc())
                .limit(10)
            )
            db_history_messages = list(result.scalars().all())
            db_history_messages.reverse()
            history = [ChatMessage.from_orm(msg) for msg in db_history_messages]
            history_dicts = [msg.dict() for msg in history]

            deconstructed_query = await query_agent.deconstruct_query(search_query.query, history=history_dicts)
            logger.info(f"Deconstructed query: '{deconstructed_query.semantic_query}' with intent: {deconstructed_query.intent}")

            llm_response = ""
            source_documents = []

            if deconstructed_query.intent == "question":
                if vector_db.get_collection_count() == 0:
                    return SearchResponse(llm_response="The knowledge base is empty.", source_documents=[])

                search_text = deconstructed_query.hypothetical_document or deconstructed_query.semantic_query
                search_results = vector_db.search_journeys(query_text=search_text, n_results=deconstructed_query.n_results)
                
                documents_list = search_results.get('documents') if search_results else None
                if documents_list and documents_list[0]:
                    documents = documents_list[0]
                    metadatas_list = search_results.get('metadatas') if search_results else None
                    distances_list = search_results.get('distances') if search_results else None

                    if not (metadatas_list and distances_list):
                         llm_response = "Could not find any relevant documents."
                    else:
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
                else:
                    llm_response = "Could not find any relevant documents."

            elif deconstructed_query.intent == "chitchat":
                llm_response = await llm_handler.get_llm_response(deconstructed_query.semantic_query, is_chitchat=True, history=history_dicts)

            elif deconstructed_query.intent == "sampling":
                search_results = vector_db.get_random_journeys(n_results=deconstructed_query.n_results)
                documents = search_results.get('documents') if search_results else None
                metadatas = search_results.get('metadatas') if search_results else None
                if documents and metadatas:
                    source_documents = [
                        SourceDocument(
                            customer_id=str(md.get('customer_id', 'N/A')),
                            full_journey=doc,
                            call_ids=str(md.get('call_ids', 'N/A')),
                            last_call_date=str(md.get('last_call_date', 'N/A')),
                            distance=0.0
                        ) for doc, md in zip(documents, metadatas)
                    ]
                    prompt = prompt_engine.create_prompt("Summarize this sample.", [doc.dict() for doc in source_documents])
                    llm_response = await llm_handler.get_llm_response(prompt, history=history_dicts)
                else:
                    llm_response = "Could not retrieve a sample of documents."

            # Save assistant response
            assistant_log = database.ChatLog(session_id=session_id, role="assistant", content=llm_response)
            db.add(assistant_log)
            await db.commit()
            
            return SearchResponse(llm_response=llm_response, source_documents=source_documents)

        except Exception as e:
            logger.error(f"An error occurred during non-streaming search: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal Server Error")