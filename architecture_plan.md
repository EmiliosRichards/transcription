# Transcription Pipeline Architecture Plan

This document outlines the plan for re-architecting the transcription processing pipeline to handle long-form, complex conversations.

## 1. Problem Statement

The current system fails on long transcripts because:
-   It uses naive character-based chunking, which destroys conversational context.
-   It cannot maintain speaker identity across chunks.
-   The LLM prompts are not sophisticated enough to handle complex, multi-topic conversations.

## 2. Proposed Architecture

We will implement a multi-stage processing pipeline:

1.  **Transcription & Diarization**: Transcribe audio to text with generic speaker labels.
2.  **Speaker Identification**: Use a dedicated service to replace generic labels with identified speaker names.
3.  **Intelligent Segmentation**: Use an LLM to segment the transcript by topic.
4.  **Enriched Chunk Processing**: Process each segment with global and local context.
5.  **Final Aggregation**: Combine the processed segments into a final, structured document.

## 3. Phase 1: Speaker Identification

### 3.1. Technology Selection

**Decision**: We will use **Azure AI Speech** for Speaker Recognition.

**Reasoning**:
-   High accuracy.
-   User-friendly API and SDK.
-   The Voice Profile Enrollment feature is a direct fit for our needs.

### 3.2. Implementation Steps

-   **[ ] Step 1: Set up Azure Account & Resources**:
    -   Create a free Azure account if one does not exist.
    -   Create a new "Speech service" resource in the Azure portal.
    -   Securely store the API key and region information in our application's configuration.
-   **[ ] Step 2: Implement Voice Enrollment Workflow**:
    -   Create a simple UI or a script that allows an administrator to upload a short audio file (15-30 seconds of clear speech) for each known speaker.
    -   Use the Azure Speech SDK to create a unique voice profile for each speaker from their audio sample.
    -   Store the mapping between our internal user/speaker ID and the Azure-generated `profileId` in our database.
-   **[ ] Step 3: Integrate into Transcription Pipeline**:
    -   Modify the transcription process to call the Azure batch transcription API with the list of enrolled `profileId`s.
    -   The API will return a transcript with identified speakers.
    -   Save this enriched transcript to the database.
