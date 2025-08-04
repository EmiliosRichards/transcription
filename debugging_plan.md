# Frontend Streaming Debugging Plan

This document outlines a systematic approach to diagnosing and fixing the text streaming issue in the chatbot's frontend.

### Objective
To make the assistant's response stream smoothly, word-by-word, as it is received from the backend, instead of appearing all at once.

### Hypothesis
The root cause is excessive re-rendering of the `MessageBubble` component. Although it is wrapped in `React.memo`, one of its props is likely "unstable," meaning it's being recreated on every render cycle. This defeats the memoization and forces a full re-render for every token received. The most likely culprit is the `message` object itself.

---

## Phase 1: Diagnose with React DevTools

This phase focuses on using the React DevTools to gather concrete data and confirm our hypothesis.

*   **Step 1.1: Profile Component Rendering**
    *   **Goal:** Identify exactly which components are re-rendering during the streaming process and why.
    *   **Action:** Use the "Profiler" tab in React DevTools to record a performance trace while the chatbot is generating a response.
    *   **Expected Outcome:** A flamegraph chart showing that `MessageBubble` (and potentially its children) re-renders many times. The profiler should tell us *why* it re-rendered (e.g., "props changed" or "hooks changed").

*   **Step 1.2: Inspect Prop Stability**
    *   **Goal:** If Step 1.1 confirms re-renders are due to prop changes, we need to identify the specific prop that is unstable.
    *   **Action:** Use the "Components" tab in React DevTools. We will select the last `MessageBubble` and inspect its props as the stream comes in.
    *   **Expected Outcome:** We will observe that the `message` object prop is a new object with every token update, causing the component to re-render.

## Phase 2: Analyze and Refactor State Management

Once the diagnosis is confirmed, we will fix the underlying cause in the state management logic.

*   **Step 2.1: Examine State Update Logic**
    *   **Goal:** Understand how the streaming data is processed and how the `messages` array in the `useChatStore` is updated.
    *   **Action:** Review the `useChatApi.ts` file, which contains the logic for handling the SSE stream and calling the store's update functions.
    *   **Expected Outcome:** We will likely find that the code creates a new `messages` array and a new final `message` object for each token, rather than immutably updating the `content` of the existing last message.

*   **Step 2.2: Implement a Stable Update Pattern**
    *   **Goal:** Refactor the state update logic to ensure the message object's identity is preserved during streaming.
    *   **Action:** Modify the update logic to find the last message in the array and only update its `content` property. This ensures that from React's perspective, the `message` prop for the `MessageBubble` remains the same object, allowing `React.memo` to work correctly.

## Phase 3: Verify the Fix

*   **Step 3.1: Re-Profile the Application**
    *   **Goal:** Confirm that the fix has resolved the unnecessary re-renders.
    *   **Action:** Repeat the profiling process from Step 1.1.
    *   **Expected Outcome:** The flamegraph will now show that the `MessageBubble` component does not re-render during the stream. Only the internal `ReactMarkdown` component should update as its content changes.

*   **Step 3.2: Visual Confirmation**
    *   **Goal:** Confirm the user experience is correct.
    *   **Action:** Observe the chatbot UI.
    *   **Expected Outcome:** The text streams smoothly into the message bubble.