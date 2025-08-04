# Frontend Streaming Refactor Plan

This document outlines the plan to refactor the frontend chat to provide a direct, real-time streaming experience.

## 1. Current Implementation Analysis

The current implementation uses a combination of simulated status messages and a batched streaming approach. This creates a disconnected user experience with unnecessary loading indicators.

## 2. Proposed Changes

The goal is to remove all simulated loading and spinners and show the chatbot's response as a direct stream of text.

### 2.1. `useChatApi.ts`

*   **Remove Simulation**: The `simulationIntervalRef` and related logic will be completely removed.
*   **Simplify Streaming**: The `requestAnimationFrame` logic will be replaced with a direct append of incoming text chunks.
*   **State Management**: The `isLoading` and `isSimulating` states will be removed from the `useChatStore`.

### 2.2. `MessageList.tsx`

*   **Remove Status Display**: The `StatusDisplay` component will be removed.

### 2.3. `MessageBubble.tsx`

*   **Remove Streaming Cursor**: The `StreamingCursor` component will be removed.

## 3. New Streaming Workflow

The following Mermaid diagram illustrates the new, simplified streaming workflow:

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant Backend

    User->>Frontend: Sends a message
    Frontend->>Backend: /api/search (stream=true)
    Backend-->>Frontend: Event: user_message_saved
    Backend-->>Frontend: Event: llm_response_chunk
    Frontend->>Frontend: Appends chunk to message
    Backend-->>Frontend: Event: llm_response_chunk
    Frontend->>Frontend: Appends chunk to message
    ...
    Backend-->>Frontend: Event: stream_end
```

## 4. Implementation Steps

1.  Modify `useChatStore.ts` to remove `isLoading`, `isSimulating`, and `simulatedStatus`.
2.  Modify `useChatApi.ts` to remove the simulation logic and simplify the streaming mechanism.
3.  Modify `MessageList.tsx` to remove the `StatusDisplay` component.
4.  Modify `MessageBubble.tsx` to remove the `StreamingCursor`.

This plan will result in a much cleaner and more responsive user experience.