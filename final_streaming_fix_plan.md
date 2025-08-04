# Final Plan: A Frame-Based Approach to Text Streaming

## 1. The Problem: Event Loop Saturation

Our previous attempts failed because we were trying to update the React state for every single token chunk received from the server. While the backend stream is fast, the browser's rendering engine cannot keep up. The high frequency of state updates saturates the browser's main thread (the event loop), preventing it from repainting the screen. This is why the UI freezes and then shows the entire text at once.

## 2. The Architectural Solution: Decouple and Batch

The correct solution is to decouple the data-receiving logic from the rendering logic. We will batch the incoming text chunks and only update the UI once per browser frame, which is the most efficient way to handle animations and high-frequency updates.

This will be achieved using a `requestAnimationFrame` loop.

### How it Works:
1.  **Buffer:** A simple queue (an array) will be created to act as a buffer. When a `llm_response_chunk` arrives from the server, its content will be pushed into this buffer instead of immediately triggering a state update.
2.  **Animation Frame Loop:** A `requestAnimationFrame` loop will be started when the stream begins. This loop asks the browser to call our update function right before the next repaint.
3.  **Batch Update:** Inside the animation frame callback, we will:
    *   Check if the buffer contains any text chunks.
    *   If it does, we will empty the buffer, join all the chunks into a single string, and call the `appendLastMessageChunk` function in our Zustand store **only once** with this batched content.
4.  **Termination:** The loop will continue as long as the stream is active and will terminate when the `stream_end` event is received.

This architecture guarantees that no matter how many chunks arrive between frames (e.g., 10, 50, 100), we will only trigger a single React re-render per frame. This will keep the UI responsive and allow the text to stream smoothly.

## 3. Implementation Steps

1.  **Modify `useChatApi.ts`:**
    *   Introduce a `chunkQueue` ref to hold the incoming text chunks.
    *   Introduce an `animationFrameId` ref to manage the loop.
    *   In the `llm_response_chunk` event listener, instead of calling the store, we will just push the token into the `chunkQueue`.
    *   Create a `processQueue` function that performs the batch update logic described above.
    *   Start the `requestAnimationFrame(processQueue)` loop when the first chunk arrives.
    *   Stop the loop in the `stream_end` and `error` event listeners.
2.  **No Changes to Components:** This is a pure logic change. No modifications will be needed for `MessageBubble` or any other React component.

This is the definitive and correct architectural pattern for this problem.