# Final Plan: Replicating the Proven `old_commit` Logic

## 1. Root Cause Analysis

All previous attempts failed because they did not correctly replicate the core logic of the working `old_commit/chat-interface (1).tsx` file. The key was not just creating a placeholder, but a specific, two-step update process that primes the UI for streaming.

The successful sequence is:
1.  **Immediate Placeholder:** An empty assistant message is added to the UI *immediately* upon sending the user's query. This creates a stable component for React to manage.
2.  **"First Chunk Reset":** Upon receiving the *very first* `llm_response_chunk`, the code performs a seemingly redundant but critical action: it explicitly sets the placeholder's content to an empty string (`''`). This initial state update clears the `StatusBox` from the UI and prepares the component to receive the streaming text, preventing the renderer from freezing.

My previous attempts missed this crucial "first chunk reset" step, which is why they failed.

## 2. The New Implementation Plan

This plan abandons all previous complex solutions (like `requestAnimationFrame`) and precisely replicates the simpler, proven logic from the old code, adapted for our modern hook-based architecture.

### Step 1: Refactor `useChatStore.ts`
The store needs a new function to handle the "first chunk reset" logic.

*   **Action:** Create a new function in the store called `setLastMessageContent`. This function will be responsible for replacing the entire content of the last message.
*   **Rationale:** This provides a clean, dedicated function for the "first chunk reset" action, separating it from the `appendLastMessageChunk` logic.

### Step 2: Refactor `useChatApi.ts`
This hook will be rewritten to orchestrate the new, correct sequence of events.

*   **Action 1 (Placeholder):** On `handleSendMessage`, immediately add both the user's message and an empty assistant message placeholder to the store.
*   **Action 2 (First Chunk):** In the `llm_response_chunk` event listener, on the very first chunk (`!isStreaming`), call the new `setLastMessageContent` function to replace the placeholder's content with the first token.
*   **Action 3 (Subsequent Chunks):** For all subsequent chunks, call the existing `appendLastMessageChunk` function to append the new tokens.
*   **Rationale:** This precisely mirrors the successful logic from `old_commit`, ensuring the UI is stable before the stream begins.

### Step 3: No Changes to UI Components
The existing UI components (`MessageBubble.tsx`, `MessageList.tsx`) are already correctly configured from our last attempt to handle a placeholder message that contains a status box. No further changes are needed there.

This plan is a direct translation of a known, working solution into our current architecture. It is the definitive path to fixing this issue.