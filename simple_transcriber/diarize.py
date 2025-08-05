import os
import argparse
import json
from google.generativeai.client import configure
from google.generativeai.generative_models import GenerativeModel
from dotenv import load_dotenv

def diarize_transcript(transcript_path: str, prompt_path: str):
    """
    Uses the Gemini API to diarize a transcript based on a given prompt file.

    Args:
        transcript_path: Path to the formatted .txt transcript file.
        prompt_path: Path to the prompt template file.
    """
    if not os.path.exists(transcript_path):
        print(f"Error: Transcript file not found at '{transcript_path}'")
        return
    
    if not os.path.exists(prompt_path):
        print(f"Error: Prompt file not found at '{prompt_path}'")
        return

    print("Loading environment variables from .env file...")
    load_dotenv()
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        print("Error: GOOGLE_API_KEY not found in .env file.")
        return

    try:
        print("Configuring Google Generative AI...")
        configure(api_key=google_api_key)
        model = GenerativeModel('gemini-1.5-pro')

        print(f"Reading transcript from: {transcript_path}")
        with open(transcript_path, "r", encoding="utf-8") as f:
            transcript_text = f.read()

        print(f"Reading prompt template from: {prompt_path}")
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()
        
        # Replace the placeholder with the actual transcript content
        final_prompt = prompt_template.replace("{transcription_text}", transcript_text)

        print("\nSending request to Gemini API (this may take a moment)...")
        response = model.generate_content(final_prompt)
        
        print("\n--- Gemini API Response ---")
        # Clean up the response to extract the JSON part.
        raw_response_text = response.text
        json_start = raw_response_text.find('{')
        json_end = raw_response_text.rfind('}') + 1
        
        if json_start != -1 and json_end != 0:
            json_str = raw_response_text[json_start:json_end]
            parsed_json = json.loads(json_str)
            
            # Pretty-print the JSON output
            print(json.dumps(parsed_json, indent=2, ensure_ascii=False))
            
            # Also print the final transcript for easy reading
            if "full_transcript" in parsed_json:
                print("\n--- Diarized Transcript ---")
                print(parsed_json["full_transcript"].replace("\\n", "\n"))
                print("---------------------------\n")

        else:
            print("Could not find a valid JSON object in the response.")
            print("Raw response was:")
            print(raw_response_text)
        
        print("---------------------------\n")

    except Exception as e:
        print(f"\nAn error occurred: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Diarize a transcript using the Gemini API and a specific prompt.")
    parser.add_argument("transcript_file", help="The path to the formatted transcript .txt file.")
    # The prompt path is hardcoded to the one in the main app for consistency
    args = parser.parse_args()

    # Construct the relative path to the prompt from the script's location
    script_dir = os.path.dirname(__file__)
    prompt_file_path = os.path.join(script_dir, '..', 'chatbot_app', 'backend', 'app', 'prompts', 'post_process_advanced_diarization.txt')
    prompt_file_path = os.path.normpath(prompt_file_path)


    diarize_transcript(args.transcript_file, prompt_file_path)