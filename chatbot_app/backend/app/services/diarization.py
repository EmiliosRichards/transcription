import os
import json
import logging
from google.generativeai.client import configure
from google.generativeai.generative_models import GenerativeModel
from google.generativeai.types import GenerationConfig, HarmCategory, HarmBlockThreshold
from app.config import settings
from app.services.prompt_engine import create_prompt_from_template

# --- Logging Setup ---
logger = logging.getLogger(__name__)

# --- Configuration ---
# This service requires the GOOGLE_API_KEY to be set in the environment.
try:
    configure(api_key=settings.GOOGLE_API_KEY)
except Exception as e:
    logger.error(f"Failed to configure Google Generative AI: {e}", exc_info=True)

def process_full_transcript(transcription_segments: list[dict], task_id: str) -> dict:
    """
    Formats a list of timestamped transcription segments and sends it to the
    Gemini model for advanced diarization. Saves the raw response for debugging.
    """
    logger.info("Formatting timestamped transcript and sending to Gemini for processing...")
    
    # Format the segments into a human-readable, timestamped string
    formatted_transcript = "\n".join(
        f"[{segment['start']:07.2f} -> {segment['end']:07.2f}] {segment['text']}"
        for segment in transcription_segments
    )

    model = GenerativeModel('gemini-1.5-pro')
    
    # Use the prompt from the file via the prompt engine. This ensures consistency.
    prompt = create_prompt_from_template(
        "post_process_advanced_diarization.txt",
        {"transcription_text": formatted_transcript}
    )

    response = None
    try:
        # Configure generation settings to be more permissive
        generation_config = GenerationConfig(
            temperature=0.2,
            max_output_tokens=15000, # Increased token limit
        )
        
        # Disable safety filters that might prematurely end the response
        safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }

        response_stream = model.generate_content(
            prompt,
            generation_config=generation_config,
            safety_settings=safety_settings,
            stream=True
        )
        
        # Iterate through the stream and build the full response
        raw_response_text = ""
        for chunk in response_stream:
            if chunk.text:
                raw_response_text += chunk.text
        
        logger.info(f"Full streamed response received from Gemini.")

        # --- Save response for debugging ---
        try:
            logs_dir = os.path.join(os.path.dirname(__file__), '..', 'llm_logs')
            os.makedirs(logs_dir, exist_ok=True)
            log_file_path = os.path.join(logs_dir, f"{task_id}_gemini_response.txt")
            with open(log_file_path, "w", encoding="utf-8") as f:
                f.write(raw_response_text)
            logger.info(f"Saved Gemini response to {log_file_path}")
        except Exception as log_e:
            logger.error(f"Failed to save LLM log file: {log_e}", exc_info=True)
        # ---

        # Clean up the response to extract the JSON part.
        json_start = raw_response_text.find('{')
        json_end = raw_response_text.rfind('}') + 1
        
        if json_start != -1 and json_end != 0:
            json_str = raw_response_text[json_start:json_end]
            return json.loads(json_str)
        else:
            raise ValueError("No valid JSON object found in the Gemini response.")
    except Exception as e:
        logger.error(f"An error occurred while calling the Gemini API: {e}", exc_info=True)
        raw_response_text = response.text if response else "No response"
        logger.error(f"Raw Gemini response was: {raw_response_text}")
        # Re-raise the exception to be handled by the background task manager
        raise e