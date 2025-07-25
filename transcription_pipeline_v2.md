# Transcription Pipeline Architecture (v2.1)

## 1. Overview

This document outlines the architecture for a modular and flexible transcription pipeline. The primary goal is to allow for interchangeable transcription providers (Local Whisper, OpenAI API, Mistral API) while integrating with a consistent diarization and post-processing workflow. This version emphasizes a clean, modular file structure for maintainability.

## 2. Core Principles

*   **Modularity**: Each step of the pipeline (downloading, transcription, diarization, post-processing) will be a separate, independent script or module.
*   **Configurability**: The transcription module will be configurable to easily switch between different providers without code changes.
*   **Decoupling**: Transcription and diarization are treated as parallel processes. Both take the original audio file as input. This decoupling is key to the system's flexibility.
*   **Organization**: The file structure is designed to be clean, intuitive, and easy to extend.

## 3. Proposed File Structure

```
.
├── scripts/
│   ├── 1_select_recordings.py
│   ├── 2_download_audio.py
│   └── pipeline/
│       ├── __init__.py
│       ├── transcription.py   # Core transcription logic
│       ├── diarization.py     # Core diarization logic
│       ├── postprocessing.py  # Merging and cleaning logic
│       └── providers/
│           ├── __init__.py
│           ├── local_whisper.py
│           ├── openai_api.py
│           └── mistral_api.py
└── run_pipeline.py            # Main script to orchestrate the pipeline
```

## 4. Pipeline Flow & Component Breakdown

The overall data flow remains the same, but the implementation will be spread across the new file structure.

1.  **`run_pipeline.py`**: This script will be the main orchestrator. It will:
    *   Get the list of audio files to process.
    *   For each file, it will call the transcription, diarization, and post-processing functions in order.
    *   It will handle configuration, such as which transcription provider to use.

2.  **`scripts/pipeline/transcription.py`**: This module will contain a main function, e.g., `transcribe_audio(audio_path, provider)`, which will dynamically import and use the correct provider from the `providers` sub-directory.

3.  **`scripts/pipeline/providers/`**: Each file in this directory will implement a single function, e.g., `transcribe(audio_path)`, that handles the specifics of that particular API or local model.

4.  **`scripts/pipeline/diarization.py`**: This will contain the logic for running `pyannote.audio` on an audio file and returning the speaker timeline.

5.  **`scripts/pipeline/postprocessing.py`**: This will contain the logic for merging the transcript and the speaker timeline into the final, clean output.

This highly modular structure will make the codebase much easier to understand, maintain, and extend in the future.

### Component Breakdown

1.  **Audio Files**: The 100 selected `.mp3` files located in `data/audio/selected_for_poc/`.
2.  **Transcription Module**: A single script (`run_transcription.py`) that takes an audio file and a provider name (`local`, `openai`, or `mistral`) as input. It returns the raw text transcript.
3.  **Diarization Module**: A script (`run_diarization.py`) that uses `pyannote.audio` to process an audio file and produce a speaker timeline (who spoke and when).
4.  **Post-processing Script**: A script (`run_postprocessing.py`) that takes the raw transcript and the speaker timeline as input and generates the final, formatted, speaker-labeled transcript.
5.  **Final Transcript**: The clean, ready-for-analysis text output.
6.  **Embedding & Analysis**: The subsequent steps outlined in the original `prd.md` (embedding, tagging, analysis).

## 4. Implementation Plan

This architecture translates into the following implementation steps:

1.  **Implement the modular transcription script** (`run_transcription.py`) with functions for each provider.
2.  **Implement the diarization script** (`run_diarization.py`) using your existing `pyannote.audio` logic.
3.  **Implement the post-processing script** (`run_postprocessing.py`) to merge the outputs.
4.  Create a master script (`main.py` or `run_pipeline.py`) to orchestrate the execution of these modules for all 100 audio files.