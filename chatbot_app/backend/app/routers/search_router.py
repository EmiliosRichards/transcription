import logging
from fastapi import APIRouter, HTTPException, Request, File, UploadFile, Form, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, AsyncGenerator, List, Literal
from app.services import vector_db, prompt_engine, llm_handler, transcription
import tempfile
import os
from app.services.query_agent import QueryAgent
from app.services.status_manager import status_manager
import json
import uuid
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from app import database
import datetime

# --- Logging Setup ---
logger = logging.getLogger(__name__)

# --- Router Setup ---
router = APIRouter()
query_agent = QueryAgent()

# --- DB Dependency ---
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

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

class TranscriptionProcessRequest(BaseModel):
    transcription_id: int
    transcription: str

class CompanyNameCorrectionRequest(BaseModel):
    transcription_id: int
    full_transcript: str
    correct_company_name: str

class TranscriptionInfo(BaseModel):
    id: int
    audio_source: Optional[str] = None
    created_at: datetime.datetime
    
    class Config:
        from_attributes = True

class ChatSessionInfo(BaseModel):
    session_id: str
    start_time: datetime.datetime
    initial_message: str

class ChatLogInfo(BaseModel):
    id: int
    role: str
    content: str

    class Config:
        from_attributes = True

# --- Helper for Streaming ---
async def stream_generator(query: str, db: Session, session_id: str) -> AsyncGenerator[str, None]:
    """
    A generator that yields Server-Sent Events for the RAG pipeline,
    routing based on the user's detected intent and saving the conversation.
    It fetches the last 10 messages to provide conversational context.
    """
    full_response = ""
    try:
        # 1. Fetch conversation history for context
        # Fetch the last 10 messages to use as context
        db_history_messages = db.query(database.ChatLog).filter(database.ChatLog.session_id == session_id).order_by(database.ChatLog.id.desc()).limit(10).all()
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
            db.commit()
            db.refresh(assistant_log)
            assistant_log_id = assistant_log.id
            logger.info(f"Saved assistant response for session {session_id} with ID {assistant_log_id}")
        # 6. Signal the end of the stream, and send back the session_id and the new message ID
        yield f"event: stream_end\ndata: {json.dumps({'session_id': session_id, 'assistant_message_id': assistant_log_id})}\n\n"


@router.post("/search", tags=["Search"])
async def search(search_query: SearchQuery, db: Session = Depends(get_db)):
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
        db.commit()
        db.refresh(user_log)
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
            db.commit() # Commit the user log here
            
            # Fetch history from DB for context
            db_history_messages = db.query(database.ChatLog).filter(database.ChatLog.session_id == session_id).order_by(database.ChatLog.id.desc()).limit(10).all()
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
            db.commit()
            
            return SearchResponse(llm_response=llm_response, source_documents=source_documents)

        except Exception as e:
            logger.error(f"An error occurred during non-streaming search: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/transcribe", tags=["Transcription"])
async def transcribe(file: Optional[UploadFile] = File(None), url: Optional[str] = Form(None), db: Session = Depends(get_db)):
    """
    Transcribes an audio file from a file upload or a URL and saves the raw
    transcription to the database.
    """
    logger.info("Received request to /transcribe")
    if not file and not url:
        logger.error("No file or URL provided.")
        raise HTTPException(status_code=400, detail="Either a file or a URL must be provided.")

    audio_source = file.filename if file and file.filename else url

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            logger.info(f"Created temporary directory: {temp_dir}")
            if file and file.filename:
                temp_path = os.path.join(temp_dir, file.filename)
                with open(temp_path, "wb") as buffer:
                    buffer.write(await file.read())
                audio_path = temp_path
            elif url:
                audio_path = transcription.download_file(url, temp_dir)
            else:
                raise HTTPException(status_code=400, detail="No file or URL provided")

            logger.info("Starting transcription...")
            transcript_text = transcription.transcribe_audio(audio_path)
            logger.info("Transcription successful.")

            # Save to database
            new_transcription = database.Transcription(
                audio_source=audio_source,
                raw_transcription=transcript_text
            )
            db.add(new_transcription)
            db.commit()
            db.refresh(new_transcription)
            
            return {"transcription": transcript_text, "transcription_id": new_transcription.id}

    except Exception as e:
        logger.error(f"An error occurred during transcription: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@router.post("/post-process-transcription", tags=["Transcription"])
async def post_process_transcription(request: TranscriptionProcessRequest, db: Session = Depends(get_db)):
    """
    Receives a raw transcription and its ID, post-processes it, and saves
    the processed version to the database.
    """
    logger.info(f"Received request to /post-process-transcription for ID: {request.transcription_id}")
    try:
        # 1. Create the prompt using the new template
        prompt = prompt_engine.create_prompt_from_template(
            "post_process_advanced_diarization.txt",
            {"transcription_text": request.transcription}
        )
        logger.info("Generated advanced diarization prompt.")

        # 2. Get the response from the LLM
        llm_response_str = await llm_handler.get_llm_response(prompt)
        logger.info("Received response from LLM.")

        # 3. Parse the JSON response from the LLM
        # The response is often wrapped in ```json ... ```, so we need to extract it.
        try:
            json_start = llm_response_str.find('{')
            json_end = llm_response_str.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON object found in the LLM response.")
            
            json_str = llm_response_str[json_start:json_end]
            response_data = json.loads(json_str)
            logger.info("Successfully parsed JSON from LLM response.")
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse JSON from LLM response: {e}")
            logger.error(f"Raw LLM response was: {llm_response_str}")
            raise HTTPException(status_code=500, detail="Failed to parse response from the language model.")

        # 4. Return the processed transcript
        processed_transcript = response_data.get("full_transcript")
        if not processed_transcript:
            raise HTTPException(status_code=500, detail="LLM response did not contain 'full_transcript'.")

        # Update database
        db_transcription = db.query(database.Transcription).filter(database.Transcription.id == request.transcription_id).first()
        if not db_transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")
        
        db_transcription.processed_transcription = processed_transcript
        db.commit()

        return {"processed_transcription": processed_transcript}

    except Exception as e:
        logger.error(f"An error occurred during transcription post-processing: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@router.post("/correct-company-name", tags=["Transcription"])
async def correct_company_name(request: CompanyNameCorrectionRequest, db: Session = Depends(get_db)):
    """
    Receives a processed transcript and its ID, and a correct company name,
    and uses an LLM to replace the incorrect company name.
    """
    logger.info(f"Received request to /correct-company-name for ID: {request.transcription_id}")
    try:
        prompt = prompt_engine.create_prompt_from_template(
            "correct_company_name.txt",
            {
                "full_transcript": request.full_transcript,
                "correct_company_name": request.correct_company_name
            }
        )
        logger.info("Generated company name correction prompt.")

        llm_response_str = await llm_handler.get_llm_response(prompt)
        logger.info("Received response from LLM for company name correction.")

        try:
            json_start = llm_response_str.find('{')
            json_end = llm_response_str.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON object found in the LLM response for correction.")
            
            json_str = llm_response_str[json_start:json_end]
            response_data = json.loads(json_str)
            logger.info("Successfully parsed JSON from LLM correction response.")
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse JSON from LLM correction response: {e}")
            logger.error(f"Raw LLM correction response was: {llm_response_str}")
            raise HTTPException(status_code=500, detail="Failed to parse correction response from the language model.")

        corrected_transcript = response_data.get("corrected_transcript")
        if not corrected_transcript:
            raise HTTPException(status_code=500, detail="LLM correction response did not contain 'corrected_transcript'.")

        # Update database
        db_transcription = db.query(database.Transcription).filter(database.Transcription.id == request.transcription_id).first()
        if not db_transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")

        db_transcription.corrected_transcription = corrected_transcript
        db.commit()

        return {"corrected_transcript": corrected_transcript}

    except Exception as e:
        logger.error(f"An error occurred during company name correction: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@router.get("/transcriptions", tags=["Transcription"], response_model=List[TranscriptionInfo])
async def get_transcriptions(db: Session = Depends(get_db)):
    """
    Retrieves a list of all past transcriptions from the database.
    """
    logger.info("Received request to /transcriptions")
    try:
        transcriptions = db.query(database.Transcription).order_by(database.Transcription.created_at.desc()).all()
        
        # Convert SQLAlchemy objects to Pydantic models using from_orm
        return [TranscriptionInfo.from_orm(t) for t in transcriptions]
    except Exception as e:
        logger.error(f"An error occurred while fetching transcriptions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@router.get("/chats", tags=["Chat"], response_model=List[ChatSessionInfo])
async def get_chat_sessions(db: Session = Depends(get_db)):
    """
    Retrieves a list of all past chat sessions from the database.
    """
    logger.info("Received request to /chats")
    try:
        # This is a simplified way to get chat sessions.
        # A more robust implementation might involve a separate table for sessions.
        # To order by the *most recent activity*, we need to find the MAX timestamp for each session.
        # 1. Find the most recent timestamp and the first message for each session.
        
        # Subquery to get the first message (user's initial query) for each session
        first_message_subq = db.query(
            database.ChatLog.session_id,
            database.ChatLog.content.label('initial_message')
        ).filter(
            database.ChatLog.id.in_(
                db.query(func.min(database.ChatLog.id)).group_by(database.ChatLog.session_id)
            )
        ).subquery('first_messages')

        # Main query to get session info and order by the latest message in each session
        sessions = db.query(
            database.ChatLog.session_id,
            func.max(database.ChatLog.created_at).label('last_activity'),
            first_message_subq.c.initial_message
        ).join(
            first_message_subq,
            database.ChatLog.session_id == first_message_subq.c.session_id
        ).group_by(
            database.ChatLog.session_id,
            first_message_subq.c.initial_message
        ).order_by(
            desc('last_activity')
        ).all()

        return [
            ChatSessionInfo(
                session_id=session.session_id,
                start_time=session.last_activity, # Using last_activity for sorting, but can be named anything
                initial_message=session.initial_message[:100]
            ) for session in sessions
        ]
    except Exception as e:
        logger.error(f"An error occurred while fetching chat sessions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@router.delete("/chats/{session_id}", tags=["Chat"], status_code=204)
async def delete_chat_session(session_id: str, db: Session = Depends(get_db)):
    """
    Deletes all logs for a specific chat session.
    """
    logger.info(f"Received request to delete chat session ID: {session_id}")
    try:
        # Check if any logs exist for this session
        chat_logs = db.query(database.ChatLog).filter(database.ChatLog.session_id == session_id).first()
        if not chat_logs:
            raise HTTPException(status_code=404, detail="Chat session not found")
        
        # Delete all logs for the session
        db.query(database.ChatLog).filter(database.ChatLog.session_id == session_id).delete(synchronize_session=False)
        db.commit()
        return
    except Exception as e:
        logger.error(f"An error occurred while deleting chat session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@router.delete("/chats/messages/{message_id}", tags=["Chat"], status_code=204)
async def delete_chat_message(message_id: int, db: Session = Depends(get_db)):
    """
    Deletes a message.
    - If it's the first message, the entire chat session is deleted.
    - Otherwise, deletes the message and all subsequent messages in the session.
    """
    logger.info(f"Received request to delete chat message ID: {message_id}")
    try:
        # Find the message to delete
        chat_log_entry = db.query(database.ChatLog).filter(database.ChatLog.id == message_id).first()
        if not chat_log_entry:
            raise HTTPException(status_code=404, detail="Chat message not found")

        session_id = chat_log_entry.session_id

        # Check if this is the first message in the session
        first_message_id = db.query(func.min(database.ChatLog.id)).filter(database.ChatLog.session_id == session_id).scalar()

        if message_id == first_message_id:
            # If it's the first message, delete the entire session
            logger.info(f"Message {message_id} is the first in session {session_id}. Deleting entire session.")
            db.query(database.ChatLog).filter(database.ChatLog.session_id == session_id).delete(synchronize_session=False)
        else:
            # Otherwise, delete this message and all subsequent ones
            logger.info(f"Deleting messages from session {session_id} starting from message {message_id}.")
            db.query(database.ChatLog).filter(
                database.ChatLog.session_id == session_id,
                database.ChatLog.id >= message_id
            ).delete(synchronize_session=False)
        
        db.commit()
        return
    except Exception as e:
        logger.error(f"An error occurred while deleting chat message {message_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@router.get("/chats/{session_id}", tags=["Chat"], response_model=List[ChatLogInfo])
async def get_chat_log(session_id: str, db: Session = Depends(get_db)):
    """
    Retrieves all messages for a specific chat session.
    """
    logger.info(f"Received request for chat log for session ID: {session_id}")
    try:
        chat_logs = db.query(database.ChatLog).filter(database.ChatLog.session_id == session_id).order_by(database.ChatLog.created_at).all()
        if not chat_logs:
            raise HTTPException(status_code=404, detail="Chat session not found")
        return [ChatLogInfo.from_orm(log) for log in chat_logs]
    except Exception as e:
        logger.error(f"An error occurred while fetching chat log for session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@router.delete("/transcriptions/{transcription_id}", tags=["Transcription"], status_code=204)
async def delete_transcription(transcription_id: int, db: Session = Depends(get_db)):
    """
    Deletes a transcription by its ID.
    """
    logger.info(f"Received request to delete transcription ID: {transcription_id}")
    try:
        db_transcription = db.query(database.Transcription).filter(database.Transcription.id == transcription_id).first()
        if not db_transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")
        
        db.delete(db_transcription)
        db.commit()
        return
    except Exception as e:
        logger.error(f"An error occurred while deleting transcription {transcription_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@router.get("/transcriptions/{transcription_id}", tags=["Transcription"])
async def get_transcription(transcription_id: int, db: Session = Depends(get_db)):
    """
    Retrieves a single transcription by its ID.
    """
    logger.info(f"Received request for transcription ID: {transcription_id}")
    try:
        db_transcription = db.query(database.Transcription).filter(database.Transcription.id == transcription_id).first()
        if not db_transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")
        
        return {
            "raw_transcription": db_transcription.raw_transcription,
            "processed_transcription": db_transcription.processed_transcription,
            "corrected_transcription": db_transcription.corrected_transcription,
        }

    except Exception as e:
        logger.error(f"An error occurred while fetching transcription {transcription_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")