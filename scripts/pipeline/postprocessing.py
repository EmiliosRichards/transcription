import os
import json
import time
from google.generativeai.client import configure
from google.generativeai.generative_models import GenerativeModel
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
configure(api_key=os.environ.get("GOOGLE_API_KEY"))

def load_prompt(prompt_name: str) -> str:
    """Loads a prompt template from the prompts directory."""
    prompt_path = os.path.join("prompts", f"{prompt_name}.txt")
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise ValueError(f"Prompt file not found: {prompt_path}")

def process_transcription_with_llm(transcription_text: str, base_filename: str, diarized: bool):
    """
    Sends the transcription to a Gemini model for processing and logs the interaction.
    """
    print("Sending transcription to the LLM for processing...")
    model = GenerativeModel('gemini-1.5-pro-latest')
    
    prompt_name = "post_process_diarized" if diarized else "post_process_simple"
    prompt_template = load_prompt(prompt_name)
    prompt = prompt_template.format(transcription_text=transcription_text)

    # --- Logging ---
    os.makedirs("output/logs/context", exist_ok=True)
    os.makedirs("output/logs/responses", exist_ok=True)
    with open(f"output/logs/context/{base_filename}.txt", "w", encoding="utf-8") as f:
        f.write(prompt)
    
    response = None
    try:
        response = model.generate_content(prompt)
        raw_response_text = response.text
        with open(f"output/logs/responses/{base_filename}.txt", "w", encoding="utf-8") as f:
            f.write(raw_response_text)

        # Clean up the response to extract the JSON part.
        cleaned_response = raw_response_text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned_response)
    except Exception as e:
        print(f"An error occurred while calling the LLM: {e}")
        raw_response_text = response.text if response else "No response"
        print(f"Raw response was: {raw_response_text}")
        return None

def combine_transcript_and_diarization(transcript: str, diarization_result, base_filename: str, diarized: bool):
    """
    Combines the raw transcript with the speaker timeline to produce
    a speaker-labeled transcript.
    """
    processed_data = process_transcription_with_llm(transcript, base_filename, diarized)
    return processed_data