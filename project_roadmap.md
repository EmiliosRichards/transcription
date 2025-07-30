# Project Roadmap: Advanced AI Analyst

This document outlines the phased development plan to evolve the chatbot from a proof-of-concept to an advanced, dynamic analytical tool.

---

### Phase 4: UI/UX Overhaul & Core Backend Fix
*   **Objective:** Make the UI more practical and fix the underlying data format for dates.
*   **Tasks:**
    - [x] **Implement Full Transcript View:** When a user clicks on a source, a modal or an expandable section will appear, showing the entire journey transcript.
    - [x] **Implement Streaming Responses:** The bot's answers will stream in token-by-token for a much better user experience.
    - [-] **Fix Date Metadata:** Re-run the embedding pipeline to store dates as Unix timestamps. (Scripts are complete and tested on a sample; pending run on full dataset).

---

### Phase 5: The Intelligent Query Agent
*   **Objective:** Build the "brains" of the operation to understand user intent.
*   **Tasks:**
    - [x] **Create the Query Agent Service:** This service will take the user's raw query and use an LLM to deconstruct it.
    - [x] **Implement Intent Recognition:** The agent will classify the query (specific search, conceptual search, sample request).
    - [x] **Implement Dynamic `n_results`:** Based on the intent, the agent will determine the optimal number of sources to retrieve (e.g., 1 for a specific customer, 5 for a broad summary).
    - [x] **Integrate Agent into API:** The main API endpoint will now call the agent first to generate the search parameters.

---

### Phase 6: Advanced Retrieval Strategies
*   **Objective:** Enable the system to answer abstract and complex questions.
*   **Tasks:**
    - [x] **Implement HyDE (Hypothetical Document Embeddings):** For conceptual queries like "find calls with bad outcomes," the agent will generate a hypothetical example to find the most relevant real journeys.
    - [x] **Implement Dynamic Sampling:** Add logic to handle requests for "a random mix" or "a representative sample" of calls.

---

### Future Technology Considerations
- [ ] **Re-ranking:** After the initial retrieval, use a more powerful model to re-rank the results for relevance before generation.
- [ ] **Function Calling / Tool Use:** For highly specific, data-driven questions, enable the AI agent to call dedicated functions to get precise answers.



### Phase 7: Transcription Service Enhancement
*   **Objective:** Improve the accuracy, usability, and data persistence of the audio transcription feature.
*   **Tasks:**
    - [x] **Advanced Speaker Diarization Prompt:** Enhance the post-processing prompt to intelligently identify and label speakers with specific roles (e.g., Agent, Decision-Maker, Gatekeeper, Other) instead of generic labels.
    - [x] **Transcription Accuracy Disclaimer:** Add a small, non-intrusive disclaimer or note on the transcription page to inform users that the transcription is AI-generated and may contain inaccuracies, especially with names or technical terms.
    - [x] **Company Name Correction Feature:** Implement a UI element (e.g., an input box and a "Correct" button) that allows the user to provide the correct company name. This will trigger a new API call to a dedicated prompt that finds and replaces the incorrect company name mentioned by the agent in the processed transcript.
    - [x] **SQL Database for Transcripts & Chats:** Design and implement a SQL database schema to store raw transcriptions, post-processed conversations, and chatbot interaction logs for future analysis and retrieval.


    [x] are the chats continuous 

    [x] can we adjust the name on the home page to Lorenz

    [ ] adjust the loading words

    [x] bring back the clean background gradient

    [x] remove the u and b

    deploy 