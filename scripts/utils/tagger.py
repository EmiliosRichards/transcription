import os
import openai
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Setup OpenAI Client ---
# Ensure the API key is available
if "OPENAI_API_KEY" not in os.environ:
    raise EnvironmentError("OPENAI_API_KEY environment variable not found. Please create a .env file.")

openai.api_key = os.environ["OPENAI_API_KEY"]

def get_transcript_tag(transcript: str, model: str = "gpt-4.1-turbo") -> str:
    """
    Analyzes a transcript and assigns it a category using the OpenAI API.

    Args:
        transcript: The full text of the call transcript.
        model: The OpenAI model to use for the analysis.

    Returns:
        A string representing the assigned category, or "Error" if something went wrong.
    """
    prompt = f"""
    Categorize the following sales call transcript into exactly one of these categories:
    1. Relevant - Success
    2. Relevant - Failed but interested
    3. Relevant - Failed not interested
    4. Relevant - Failed saturated with customers
    5. Not Relevant (no useful conversation)

    Transcript:
    {transcript}

    Only reply with the exact category name.
    """
    try:
        response = openai.chat.completions.create(
            model="gpt-4.1",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        content = response.choices[0].message.content
        category = content.strip() if content else "Error: No content"
        return category
    except Exception as e:
        print(f"An error occurred during tagging for transcript snippet '{transcript[:50]}...': {e}")
        return "Error"