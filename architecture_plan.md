# Transcription Feature Architecture Plan

This document outlines the architectural changes required to fix the transcription feature. The plan is divided into two main sections: Backend Modifications and Frontend Modifications.

## Backend Modifications

The backend requires a new endpoint to check the status of a transcription task. This endpoint will be added to the existing `transcription_router.py` to maintain a clean and organized routing structure.

### 1. File to Modify

- **File:** `chatbot_app/backend/app/routers/transcription_router.py`

### 2. New Endpoint Design

A new `GET` endpoint will be added to the router to handle task status polling.

- **Route:** `/tasks/{task_id}`
- **Method:** `GET`
- **Description:** Retrieves the status of a transcription task by its ID.

### 3. Implementation Details

The following code should be added to `transcription_router.py`:

```python
from app.services import task_manager

class TaskStatus(BaseModel):
    status: str
    progress: int
    message: str
    result: Optional[Dict[str, Any]] = None

@router.get("/tasks/{task_id}", response_model=TaskStatus, tags=["Transcription"])
async def get_task_status(task_id: str):
    """Retrieves the status of a specific transcription task."""
    status = task_manager.get_task_status(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return status
```

### 4. JSON Response Structure

The endpoint will return a JSON object with the following structure:

- **On success:**
  ```json
  {
    "status": "SUCCESS",
    "progress": 100,
    "message": "Transcription completed successfully.",
    "result": {
      "transcription_id": 123,
      "raw_segments": [...],
      "processed_segments": [...]
    }
  }
  ```

- **While processing:**
  ```json
  {
    "status": "PROCESSING",
    "progress": 50,
    "message": "Transcription is in progress...",
    "result": null
  }
  ```

- **On error:**
  ```json
  {
    "status": "ERROR",
    "progress": 0,
    "message": "An error occurred during transcription.",
    "result": null
  }
  ```

## Frontend Modifications

The frontend API client needs to be updated to use the correct URLs for creating and polling transcription tasks.

### 1. File to Modify

- **File:** `chatbot_app/frontend/src/lib/hooks/useTranscribeApi.ts`

### 2. API Client Corrections

The following changes are required in the `useTranscribeApi.ts` file:

- **`handleSubmit` function:**
  - The `fetch` request URL on line 92 should be changed from `${backendUrl}/api/transcriptions/transcribe` to `${backendUrl}/transcribe`.

- **`pollTaskStatus` function:**
  - The `fetch` request URL on line 30 should be changed from `${backendUrl}/api/tasks/${taskId}` to `${backendUrl}/transcribe/tasks/${taskId}`.

### 3. Implementation Details

The following code snippets show the required changes:

**`handleSubmit` function:**

```typescript
// ...
const response = await fetch(`${backendUrl}/transcribe`, {
  method: "POST",
  body: formData,
});
// ...
```

**`pollTaskStatus` function:**

```typescript
// ...
const response = await fetch(`${backendUrl}/transcribe/tasks/${taskId}`);
// ...
