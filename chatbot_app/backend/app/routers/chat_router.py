import logging
import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, ConfigDict
from typing import List, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, desc, select, delete

from app import database

# --- Logging Setup ---
logger = logging.getLogger(__name__)

# --- Router Setup ---
router = APIRouter()

# --- DB Dependency ---
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with database.AsyncSessionLocal() as session:
        yield session

# --- Pydantic Models ---
class ChatSessionInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    session_id: str
    start_time: datetime.datetime
    initial_message: str

class ChatLogInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: str
    content: str

# --- API Endpoints ---
@router.get("/chats", tags=["Chat"], response_model=List[ChatSessionInfo])
async def get_chat_sessions(db: AsyncSession = Depends(get_db)):
    """
    Retrieves a list of all past chat sessions from the database.
    """
    logger.info("Received request to /chats")
    try:
        # Subquery to get the first message (user's initial query) for each session
        first_message_subq = select(
            database.ChatLog.session_id,
            database.ChatLog.content.label('initial_message')
        ).where(
            database.ChatLog.id.in_(
                select(func.min(database.ChatLog.id)).group_by(database.ChatLog.session_id)
            )
        ).subquery('first_messages')

        # Main query to get session info and order by the latest message in each session
        stmt = select(
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
        )
        result = await db.execute(stmt)
        sessions = result.all()

        return [ChatSessionInfo.model_validate(session) for session in sessions]
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
        # Check if any logs exist for this session
        result = await db.execute(select(database.ChatLog).filter(database.ChatLog.session_id == session_id))
        chat_logs = result.scalars().first()
        if not chat_logs:
            raise HTTPException(status_code=404, detail="Chat session not found")
        
        # Delete all logs for the session
        stmt = delete(database.ChatLog).where(database.ChatLog.session_id == session_id)
        await db.execute(stmt)
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
        # Find the message to delete
        result = await db.execute(select(database.ChatLog).filter(database.ChatLog.id == message_id))
        chat_log_entry = result.scalars().first()
        if not chat_log_entry:
            raise HTTPException(status_code=404, detail="Chat message not found")

        session_id = chat_log_entry.session_id

        # Check if this is the first message in the session
        result = await db.execute(select(func.min(database.ChatLog.id)).filter(database.ChatLog.session_id == session_id))
        first_message_id = result.scalar()

        if message_id == first_message_id:
            # If it's the first message, delete the entire session
            logger.info(f"Message {message_id} is the first in session {session_id}. Deleting entire session.")
            stmt = delete(database.ChatLog).where(database.ChatLog.session_id == session_id)
            await db.execute(stmt)
        else:
            # Otherwise, delete this message and all subsequent ones
            logger.info(f"Deleting messages from session {session_id} starting from message {message_id}.")
            stmt = delete(database.ChatLog).where(
                database.ChatLog.session_id == session_id,
                database.ChatLog.id >= message_id
            )
            await db.execute(stmt)
        
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
        result = await db.execute(select(database.ChatLog).filter(database.ChatLog.session_id == session_id).order_by(database.ChatLog.created_at))
        chat_logs = result.scalars().all()
        if not chat_logs:
            raise HTTPException(status_code=404, detail="Chat session not found")
        return [ChatLogInfo.model_validate(log) for log in chat_logs]
    except Exception as e:
        logger.error(f"An error occurred while fetching chat log for session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")