import logging
from typing import Dict, Any, Literal, Optional
import uuid

logger = logging.getLogger(__name__)

# In-memory dictionary to store task statuses
# In a production environment, you might replace this with Redis or a database
_tasks: Dict[str, Dict[str, Any]] = {}

Status = Literal["PENDING", "PROCESSING", "SUCCESS", "ERROR"]

def create_task() -> str:
    """Creates a new task and returns its ID."""
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {
        "status": "PENDING",
        "progress": 0,
        "message": "Task has been created and is waiting to be processed.",
        "result": None,
        "estimated_time": None
    }
    logger.info(f"Task created with ID: {task_id}")
    return task_id

def get_task_status(task_id: str) -> Dict[str, Any] | None:
    """Retrieves the status of a specific task."""
    return _tasks.get(task_id)

def update_task_status(task_id: str, status: Status, progress: int, message: str, estimated_time: Optional[int] = None):
    """Updates the status, progress, and message of a task."""
    if task_id in _tasks:
        _tasks[task_id]["status"] = status
        _tasks[task_id]["progress"] = progress
        _tasks[task_id]["message"] = message
        if estimated_time is not None:
            _tasks[task_id]["estimated_time"] = estimated_time
        logger.debug(f"Task {task_id} updated: Status={status}, Progress={progress}%, Message='{message}'")
    else:
        logger.warning(f"Attempted to update non-existent task with ID: {task_id}")

def set_task_success(task_id: str, result: Any):
    """Marks a task as successful and stores its result."""
    if task_id in _tasks:
        _tasks[task_id]["status"] = "SUCCESS"
        _tasks[task_id]["progress"] = 100
        _tasks[task_id]["message"] = "Transcription completed successfully."
        _tasks[task_id]["result"] = result
        logger.info(f"Task {task_id} marked as SUCCESS.")
    else:
        logger.warning(f"Attempted to set success for non-existent task with ID: {task_id}")

def set_task_error(task_id: str, error_message: str):
    """Marks a task as failed and stores the error message."""
    if task_id in _tasks:
        _tasks[task_id]["status"] = "ERROR"
        _tasks[task_id]["message"] = error_message
        logger.error(f"Task {task_id} marked as ERROR: {error_message}")
    else:
        logger.warning(f"Attempted to set error for non-existent task with ID: {task_id}")

def remove_task(task_id: str):
    """Removes a task from the store, e.g., after the result has been fetched."""
    if task_id in _tasks:
        del _tasks[task_id]
        logger.info(f"Task {task_id} removed from store.")
