import logging
import time
from fastapi import APIRouter, HTTPException, Request, File, UploadFile, Form, Depends, Query, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, AsyncGenerator, List, Literal, cast
from app.services import vector_db, prompt_engine, llm_handler, transcription, task_manager, diarization
import tempfile
import os
import shutil
from app.services.query_agent import QueryAgent
from app.services.status_manager import status_manager
import json
import uuid
from sqlalchemy import func, desc, select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app import database
import datetime

# --- Logging Setup ---
logger = logging.getLogger(__name__)

# --- Router Setup ---
router = APIRouter()
query_agent = QueryAgent()

# --- DB Dependency (Async) ---
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with database.AsyncSessionLocal() as session:
        yield session

# --- Pydantic Models ---
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str

    model_config = ConfigDict(from_attributes=True)

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

class CompanyNameCorrectionRequest(BaseModel):
    transcription_id: int
    full_transcript: str
    correct_company_name: str

class TranscriptionInfo(BaseModel):
    id: int
    audio_source: Optional[str] = None
    created_at: datetime.datetime
    
    model_config = ConfigDict(from_attributes=True)

class ChatSessionInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    session_id: str
    start_time: datetime.datetime
    initial_message: str

class ChatLogInfo(BaseModel):
    id: int
    role: str
    content: str

    model_config = ConfigDict(from_attributes=True)

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
        stmt = select(database.ChatLog).filter(database.ChatLog.session_id == session_id).order_by(database.ChatLog.id.desc()).limit(10)
        result = await db.execute(stmt)
        db_history_messages = list(result.scalars().all())
        db_history_messages.reverse() # Order from oldest to newest
        history = [ChatMessage.model_validate(msg) for msg in db_history_messages]
        history_dicts = [msg.model_dump() for msg in history]

        # 2. Deconstruct Query to determine intent
        logger.info("STREAM: Yielding status_update: understanding")
        yield f"event: status_update\ndata: {json.dumps({'status': status_manager.get_message('understanding')})}\n\n"
        deconstructed_query = query_agent.deconstruct_query(query, history=history_dicts)
        logger.info(f"Deconstructed query: '{deconstructed_query.semantic_query}' with intent: {deconstructed_query.intent}")

        # 2. Route based on intent
        if deconstructed_query.intent == "question":
            if vector_db.get_collection_count() == 0:
                logger.warning("Attempted to search an empty vector database.")
                yield f"event: error\ndata: {json.dumps({'message': 'The knowledge base is empty. Please transcribe audio files to enable search.'})}\n\n"
                return

            if deconstructed_query.hypothetical_document:
                logger.info("STREAM: Yielding status_update: hyde")
                yield f"event: status_update\ndata: {json.dumps({'status': status_manager.get_message('hyde')})}\n\n"
                logger.info(f"HyDE document generated: {deconstructed_query.hypothetical_document}")

            logger.info("STREAM: Yielding status_update: searching")
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
            logger.info("STREAM: Yielding sources")
            yield f"event: sources\ndata: {json.dumps({'sources': [doc.model_dump() for doc in source_documents]})}\n\n"

            logger.info("STREAM: Yielding status_update: synthesizing")
            yield f"event: status_update\ndata: {json.dumps({'status': status_manager.get_message('synthesizing')})}\n\n"
            prompt = prompt_engine.create_prompt(deconstructed_query.semantic_query, [doc.model_dump() for doc in source_documents])
            
            async for token in llm_handler.get_llm_response_stream(prompt, history=history_dicts):
                full_response += token
                logger.debug(f"STREAM: Yielding llm_response_chunk: {token}")
                yield f"event: llm_response_chunk\ndata: {json.dumps({'token': token})}\n\n"

        elif deconstructed_query.intent == "chitchat":
            logger.info("STREAM: Yielding status_update: chitchat")
            yield f"event: status_update\ndata: {json.dumps({'status': status_manager.get_message('chitchat')})}\n\n"
            logger.info("STREAM: Yielding sources (empty for chitchat)")
            yield f"event: sources\ndata: {json.dumps({'sources': []})}\n\n"
            async for token in llm_handler.get_llm_response_stream(deconstructed_query.semantic_query, is_chitchat=True, history=history_dicts):
                full_response += token
                logger.debug(f"STREAM: Yielding llm_response_chunk: {token}")
                yield f"event: llm_response_chunk\ndata: {json.dumps({'token': token})}\n\n"

        elif deconstructed_query.intent == "sampling":
            logger.info("STREAM: Yielding status_update: sampling")
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
            logger.info("STREAM: Yielding sources (sampling)")
            yield f"event: sources\ndata: {json.dumps({'sources': [doc.model_dump() for doc in source_documents]})}\n\n"

            logger.info("STREAM: Yielding status_update: synthesizing (sampling)")
            yield f"event: status_update\ndata: {json.dumps({'status': status_manager.get_message('synthesizing')})}\n\n"
            prompt = prompt_engine.create_prompt("Summarize the key themes from this random sample of customer interactions.", [doc.model_dump() for doc in source_documents])
            
            async for token in llm_handler.get_llm_response_stream(prompt, history=history_dicts):
                full_response += token
                logger.debug(f"STREAM: Yielding llm_response_chunk: {token}")
                yield f"event: llm_response_chunk\ndata: {json.dumps({'token': token})}\n\n"
            
    except Exception as e:
        logger.error(f"Error during stream generation: {e}", exc_info=True)
        logger.error(f"STREAM: Yielding error: {e}")
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
        logger.info("STREAM: Yielding stream_end")
        yield f"event: stream_end\ndata: {json.dumps({'session_id': session_id, 'assistant_message_id': assistant_log_id})}\n\n"


async def streaming_search_generator(query: str, session_id: Optional[str]):
    """A self-contained generator that manages its own DB session for streaming."""
    async with database.AsyncSessionLocal() as db:
        current_session_id = session_id if session_id else str(uuid.uuid4())
        
        # Save user's message before starting the stream
        user_log = database.ChatLog(session_id=current_session_id, role="user", content=query)
        db.add(user_log)
        await db.commit()
        await db.refresh(user_log)
        logger.info(f"Saved user query for session {current_session_id} with ID {user_log.id}")

        # First, yield the user message ID so the frontend can update its state
        logger.info("STREAM: Yielding user_message_saved")
        yield f"event: user_message_saved\ndata: {json.dumps({'user_message_id': user_log.id, 'session_id': current_session_id})}\n\n"
        
        # Then, yield everything from the main stream generator
        logger.info("STREAM: Starting main stream generator")
        async for chunk in stream_generator(query, db, current_session_id):
            yield chunk
        logger.info("STREAM: Finished main stream generator")

@router.get("/search", tags=["Search"])
async def search(
    query: str = Query(..., description="The search query."),
    stream: bool = Query(False, description="Whether to stream the response."),
    session_id: Optional[str] = Query(None, description="The session ID for the chat."),
    db: AsyncSession = Depends(get_db)
):
    """
    Performs a RAG-based search. Can return a normal JSON response or a stream
    of Server-Sent Events based on the `stream` parameter.
    """
    logger.info(f"Received search query: '{query}' with stream={stream}")
    
    if stream:
        return StreamingResponse(
            streaming_search_generator(query, session_id),
            media_type="text/event-stream"
        )
    else:
        # Non-streaming logic with intent routing
        try:
            current_session_id = session_id if session_id else str(uuid.uuid4())
            # Save user message first
            user_log = database.ChatLog(session_id=current_session_id, role="user", content=query)
            db.add(user_log)
            await db.commit()
            
            # Fetch history from DB for context
            stmt = select(database.ChatLog).filter(database.ChatLog.session_id == current_session_id).order_by(database.ChatLog.id.desc()).limit(10)
            result = await db.execute(stmt)
            db_history_messages = list(result.scalars().all())
            db_history_messages.reverse()
            history = [ChatMessage.model_validate(msg) for msg in db_history_messages]
            history_dicts = [msg.model_dump() for msg in history]

            deconstructed_query = query_agent.deconstruct_query(query, history=history_dicts)
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
                    prompt = prompt_engine.create_prompt(deconstructed_query.semantic_query, [doc.model_dump() for doc in source_documents])
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
                    prompt = prompt_engine.create_prompt("Summarize this sample.", [doc.model_dump() for doc in source_documents])
                    llm_response = await llm_handler.get_llm_response(prompt, history=history_dicts)
                else:
                    llm_response = "Could not retrieve a sample of documents."

            # Save assistant response
            assistant_log = database.ChatLog(session_id=current_session_id, role="assistant", content=llm_response)
            db.add(assistant_log)
            await db.commit()
            
            return SearchResponse(llm_response=llm_response, source_documents=source_documents)

        except Exception as e:
            logger.error(f"An error occurred during non-streaming search: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal Server Error")

def run_transcription_task(
    task_id: str,
    audio_path: str,
    audio_source: str,
    temp_dir: str
):
    """
    The actual transcription process, designed to be run in the background.
    This function is synchronous and self-contained. It now saves the
    timestamped segments as a JSON string in the database.
    """
    # --- Define a permanent directory for audio files ---
    permanent_audio_dir = os.path.join(os.path.dirname(__file__), '..', 'audio_files')
    os.makedirs(permanent_audio_dir, exist_ok=True)
    
    # --- Generate a unique filename to prevent overwrites ---
    original_filename = os.path.basename(audio_path)
    _, file_extension = os.path.splitext(original_filename)
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    permanent_audio_path = os.path.join(permanent_audio_dir, unique_filename)

    try:
        # --- Move the audio file to the permanent location ---
        shutil.copy(audio_path, permanent_audio_path)
        logger.info(f"Copied audio file to permanent storage: {permanent_audio_path}")

        # This needs its own database session because it runs in a separate thread
        with database.SessionLocal() as db:
            logger.info(f"Background task started for task_id: {task_id}")
            
            transcription_segments = transcription.transcribe_audio(audio_path, task_id)
            logger.info(f"Transcription successful for task_id: {task_id}.")

            # Serialize the list of segments into a JSON string for DB storage
            raw_transcription_json = json.dumps(transcription_segments)

            logger.info(f"Saving transcription to database for task_id: {task_id}...")
            new_transcription = database.Transcription(
                audio_source=audio_source,
                raw_transcription=raw_transcription_json,
                audio_file_path=permanent_audio_path  # --- Save the permanent path ---
            )
            db.add(new_transcription)
            db.commit()
            db.refresh(new_transcription)
            
            result = {"transcription_segments": transcription_segments, "transcription_id": new_transcription.id}
            task_manager.set_task_success(task_id, result)
            logger.info(f"Background task finished successfully for task_id: {task_id}.")

    except Exception as e:
        logger.error(f"An error occurred during background transcription for task_id {task_id}: {e}", exc_info=True)
        task_manager.set_task_error(task_id, f"Internal Server Error: {e}")
    finally:
        # Clean up the temporary directory
        try:
            shutil.rmtree(temp_dir)
            logger.info(f"Successfully cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            logger.error(f"Failed to clean up temporary directory {temp_dir}: {e}", exc_info=True)

@router.post("/transcribe", tags=["Transcription"], status_code=202)
async def transcribe(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None)
):
    """
    Starts a transcription task in the background.
    """
    logger.info("Received request to /transcribe")
    if not file and not url:
        logger.error("No file or URL provided.")
        raise HTTPException(status_code=400, detail="Either a file or a URL must be provided.")

    task_id = task_manager.create_task()
    audio_source = file.filename if file and file.filename else url

    if not audio_source:
        task_manager.set_task_error(task_id, "Could not determine audio source from request.")
        raise HTTPException(status_code=400, detail="Could not determine audio source from request.")

    try:
        # Create a persistent temporary directory that will be cleaned up by the background task
        temp_dir = tempfile.mkdtemp()
        logger.info(f"Created temporary directory for task {task_id}: {temp_dir}")

        if file and file.filename:
            temp_path = os.path.join(temp_dir, file.filename)
            task_manager.update_task_status(task_id, "PROCESSING", 2, f"Uploading file: {file.filename}")
            logger.info(f"Saving uploaded file to: {temp_path}")
            with open(temp_path, "wb") as buffer:
                while content := await file.read(1024 * 1024):  # Read in 1MB chunks
                    buffer.write(content)
            audio_path = temp_path
            logger.info(f"File saved successfully for task {task_id}.")
        elif url:
            logger.info(f"Downloading file from URL for task {task_id}: {url}")
            # Note: download_file is synchronous, but should be fast enough.
            # For very large remote files, this could also be backgrounded.
            audio_path = transcription.download_file(url, temp_dir, task_id)
            logger.info(f"File downloaded successfully to: {audio_path}")
        else:
            # This case is already checked, but as a safeguard:
            raise HTTPException(status_code=400, detail="No file or URL provided")

        background_tasks.add_task(
            run_transcription_task,
            task_id=task_id,
            audio_path=audio_path,
            audio_source=audio_source,
            temp_dir=temp_dir
        )

        return {"task_id": task_id, "message": "Transcription task started."}

    except Exception as e:
        logger.error(f"An error occurred starting the transcription task {task_id}: {e}", exc_info=True)
        task_manager.set_task_error(task_id, f"Failed to start transcription task: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@router.get("/transcribe/status/{task_id}", tags=["Transcription"])
async def get_transcription_status(task_id: str):
    """
    Retrieves the status of a transcription task.
    """
    logger.info(f"Received status request for task ID: {task_id}")
    status = task_manager.get_task_status(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # The task is no longer removed immediately upon completion to prevent a race
    # condition where the frontend might poll for status after the task is already
    # deleted. A more robust solution would involve a TTL or a separate cleanup job.
    return JSONResponse(content=status)

def run_post_processing_task(task_id: str, transcription_id: int):
    """
    The actual post-processing logic, designed to be run in the background.
    It now deserializes the timestamped segments from the database and passes
    them to the appropriate processing pipeline.
    """
    transcription_segments = []
    # --- Step 1: Fetch data in a short-lived session ---
    try:
        with database.SessionLocal() as db:
            db_transcription = db.get(database.Transcription, transcription_id)
            if not db_transcription:
                raise ValueError(f"Transcription with ID {transcription_id} not found.")
            
            raw_json_content = cast(str, db_transcription.raw_transcription)
            if not raw_json_content:
                raise ValueError("Transcription has no raw text to process.")
            
            transcription_segments = json.loads(raw_json_content)
            if not isinstance(transcription_segments, list):
                 raise ValueError("Deserialized transcription is not a list.")

    except Exception as e:
        logger.error(f"Failed to fetch and parse transcription for task {task_id}: {e}", exc_info=True)
        task_manager.set_task_error(task_id, f"Failed to fetch transcription: {e}")
        return  # Exit if we can't even get the data

    # --- Step 2: Process transcript based on length ---
    try:
        # Reconstruct the full text to check its length
        full_text_for_length_check = " ".join(seg['text'] for seg in transcription_segments)

        if len(full_text_for_length_check) > 3000:
            # Use the robust Gemini pipeline for long transcripts, passing the structured segments
            task_manager.update_task_status(
                task_id, "PROCESSING", 50, "Transcript is long, using advanced diarization pipeline..."
            )
            processed_data = diarization.process_full_transcript(transcription_segments, task_id)
            full_processed_transcript = processed_data.get("full_transcript")
            if not full_processed_transcript:
                raise ValueError("The advanced diarization pipeline did not return a 'full_transcript'.")
        else:
            # For shorter transcripts, format the segments and use the OpenAI model.
            task_manager.update_task_status(
                task_id, "PROCESSING", 50, "Processing short transcript..."
            )
            formatted_transcript = "\n".join(
                f"[{segment['start']:07.2f} -> {segment['end']:07.2f}] {segment['text']}"
                for segment in transcription_segments
            )
            prompt = prompt_engine.create_prompt_from_template(
                "post_process_advanced_diarization.txt", {"transcription_text": formatted_transcript}
            )
            llm_response_str = llm_handler.get_llm_response_sync(prompt)
            
            # --- Save response for debugging ---
            try:
                logs_dir = os.path.join(os.path.dirname(__file__), '..', 'llm_logs')
                os.makedirs(logs_dir, exist_ok=True)
                log_file_path = os.path.join(logs_dir, f"{task_id}_openai_response.txt")
                with open(log_file_path, "w", encoding="utf-8") as f:
                    f.write(llm_response_str)
                logger.info(f"Saved OpenAI response to {log_file_path}")
            except Exception as log_e:
                logger.error(f"Failed to save LLM log file: {log_e}", exc_info=True)
            # ---

            json_start = llm_response_str.find('{')
            json_end = llm_response_str.rfind('}') + 1
            
            if json_start != -1 and json_end != 0:
                json_str = llm_response_str[json_start:json_end]
                response_data = json.loads(json_str)
                full_processed_transcript = response_data.get("full_transcript")
                if not full_processed_transcript:
                    raise ValueError("LLM response did not contain 'full_transcript'.")
            else:
                raise ValueError("No JSON object found in the LLM response.")

    except Exception as e:
        logger.error(f"An error occurred during transcript processing for task {task_id}: {e}", exc_info=True)
        task_manager.set_task_error(task_id, f"Internal Server Error during processing: {e}")
        return

    # --- Step 3: Save results in a new short-lived session ---
    try:
        with database.SessionLocal() as db:
            db_transcription = db.get(database.Transcription, transcription_id)
            if not db_transcription:
                 raise ValueError(f"Transcription with ID {transcription_id} vanished from DB.")
            
            setattr(db_transcription, 'processed_transcription', full_processed_transcript)
            db.commit()

            result = {"processed_transcription": full_processed_transcript}
            task_manager.set_task_success(task_id, result)
            logger.info(f"Background post-processing finished successfully for task_id: {task_id}.")

    except Exception as e:
        logger.error(f"Failed to save processed transcription for task {task_id}: {e}", exc_info=True)
        task_manager.set_task_error(task_id, f"Failed to save result: {e}")

@router.post("/post-process-transcription", tags=["Transcription"], status_code=202)
async def post_process_transcription(request: TranscriptionProcessRequest, background_tasks: BackgroundTasks):
    """
    Starts a post-processing task in the background.
    """
    logger.info(f"Received request to /post-process-transcription for ID: {request.transcription_id}")
    task_id = task_manager.create_task()
    
    background_tasks.add_task(
        run_post_processing_task,
        task_id=task_id,
        transcription_id=request.transcription_id
    )

    return {"task_id": task_id, "message": "Post-processing task started."}

@router.post("/correct-company-name", tags=["Transcription"])
async def correct_company_name(request: CompanyNameCorrectionRequest, db: AsyncSession = Depends(get_db)):
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
        stmt = select(database.Transcription).filter(database.Transcription.id == request.transcription_id)
        result = await db.execute(stmt)
        db_transcription = result.scalars().first()
        if not db_transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")

        db_transcription.corrected_transcription = corrected_transcript
        await db.commit()

        return {"corrected_transcript": corrected_transcript}

    except Exception as e:
        logger.error(f"An error occurred during company name correction: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@router.get("/transcriptions", tags=["Transcription"], response_model=List[TranscriptionInfo])
async def get_transcriptions(db: AsyncSession = Depends(get_db)):
    """
    Retrieves a list of all past transcriptions from the database.
    """
    logger.info("Received request to /transcriptions")
    try:
        stmt = select(database.Transcription).order_by(database.Transcription.created_at.desc())
        result = await db.execute(stmt)
        transcriptions = result.scalars().all()
        
        return [TranscriptionInfo.model_validate(t, from_attributes=True) for t in transcriptions]
    except Exception as e:
        logger.error(f"An error occurred while fetching transcriptions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@router.get("/chats", tags=["Chat"], response_model=List[ChatSessionInfo])
async def get_chat_sessions(db: AsyncSession = Depends(get_db)):
    """
    Retrieves a list of all past chat sessions from the database.
    """
    logger.info("Received request to /chats")
    try:
        first_message_subq = select(
            database.ChatLog.session_id,
            database.ChatLog.content.label('initial_message')
        ).filter(
            database.ChatLog.id.in_(
                select(func.min(database.ChatLog.id)).group_by(database.ChatLog.session_id)
            )
        ).subquery('first_messages')

        stmt = select(
            database.ChatLog.session_id,
            func.max(database.ChatLog.created_at).label('start_time'),
            first_message_subq.c.initial_message
        ).join(
            first_message_subq,
            database.ChatLog.session_id == first_message_subq.c.session_id
        ).group_by(
            database.ChatLog.session_id,
            first_message_subq.c.initial_message
        ).order_by(
            desc('start_time')
        )
        
        result = await db.execute(stmt)
        sessions = result.all()

        # Convert SQLAlchemy Row objects to a dict-like structure for Pydantic validation
        return [ChatSessionInfo.model_validate(session._mapping) for session in sessions]
    except Exception as e:
        logger.error(f"An error occurred while fetching chat sessions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@router.delete("/chats/{session_id}", tags=["Chat"], status_code=204)
async def delete_chat_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """
    Deletes all logs for a specific chat session.
    """
    logger.info(f"Received request to delete chat session ID: {session_id}")
    try:
        stmt = select(database.ChatLog).filter(database.ChatLog.session_id == session_id)
        result = await db.execute(stmt)
        chat_logs = result.scalars().first()
        if not chat_logs:
            raise HTTPException(status_code=404, detail="Chat session not found")
        
        delete_stmt = delete(database.ChatLog).filter(database.ChatLog.session_id == session_id)
        await db.execute(delete_stmt)
        await db.commit()
        return
    except Exception as e:
        logger.error(f"An error occurred while deleting chat session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@router.delete("/chats/messages/{message_id}", tags=["Chat"], status_code=204)
async def delete_chat_message(message_id: int, db: AsyncSession = Depends(get_db)):
    """
    Deletes a message.
    - If it's the first message, the entire chat session is deleted.
    - Otherwise, deletes the message and all subsequent messages in the session.
    """
    logger.info(f"Received request to delete chat message ID: {message_id}")
    try:
        stmt = select(database.ChatLog).filter(database.ChatLog.id == message_id)
        result = await db.execute(stmt)
        chat_log_entry = result.scalars().first()
        if not chat_log_entry:
            raise HTTPException(status_code=404, detail="Chat message not found")

        session_id = chat_log_entry.session_id

        first_message_id_stmt = select(func.min(database.ChatLog.id)).filter(database.ChatLog.session_id == session_id)
        result = await db.execute(first_message_id_stmt)
        first_message_id = result.scalar_one_or_none()

        if message_id == first_message_id:
            logger.info(f"Message {message_id} is the first in session {session_id}. Deleting entire session.")
            delete_stmt = delete(database.ChatLog).filter(database.ChatLog.session_id == session_id)
            await db.execute(delete_stmt)
        else:
            logger.info(f"Deleting messages from session {session_id} starting from message {message_id}.")
            delete_stmt = delete(database.ChatLog).filter(
                database.ChatLog.session_id == session_id,
                database.ChatLog.id >= message_id
            )
            await db.execute(delete_stmt)
        
        await db.commit()
        return
    except Exception as e:
        logger.error(f"An error occurred while deleting chat message {message_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@router.get("/chats/{session_id}", tags=["Chat"], response_model=List[ChatLogInfo])
async def get_chat_log(session_id: str, db: AsyncSession = Depends(get_db)):
    """
    Retrieves all messages for a specific chat session.
    """
    logger.info(f"Received request for chat log for session ID: {session_id}")
    try:
        stmt = select(database.ChatLog).filter(database.ChatLog.session_id == session_id).order_by(database.ChatLog.created_at)
        result = await db.execute(stmt)
        chat_logs = result.scalars().all()
        if not chat_logs:
            raise HTTPException(status_code=404, detail="Chat session not found")
        return [ChatLogInfo.model_validate(log, from_attributes=True) for log in chat_logs]
    except Exception as e:
        logger.error(f"An error occurred while fetching chat log for session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@router.delete("/transcriptions/{transcription_id}", tags=["Transcription"], status_code=204)
async def delete_transcription(transcription_id: int, db: AsyncSession = Depends(get_db)):
    """
    Deletes a transcription by its ID.
    """
    logger.info(f"Received request to delete transcription ID: {transcription_id}")
    try:
        stmt = select(database.Transcription).filter(database.Transcription.id == transcription_id)
        result = await db.execute(stmt)
        db_transcription = result.scalars().first()
        if not db_transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")
        
        await db.delete(db_transcription)
        await db.commit()
        return
    except Exception as e:
        logger.error(f"An error occurred while deleting transcription {transcription_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@router.get("/transcriptions/{transcription_id}", tags=["Transcription"])
async def get_transcription(transcription_id: int, db: AsyncSession = Depends(get_db)):
    """
    Retrieves a single transcription by its ID.
    """
    logger.info(f"Received request for transcription ID: {transcription_id}")
    try:
        stmt = select(database.Transcription).filter(database.Transcription.id == transcription_id)
        result = await db.execute(stmt)
        db_transcription = result.scalars().first()
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