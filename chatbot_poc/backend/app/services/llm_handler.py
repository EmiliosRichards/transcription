import os
import openai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- OpenAI Client Setup ---
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("The OPENAI_API_KEY environment variable is not set.")

client = openai.AsyncOpenAI(api_key=api_key)

async def get_llm_response(prompt: str) -> str:
    """
    Sends a prompt to the OpenAI API and returns the model's response.
    """
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=1024,
        )
        return response.choices[0].message.content or "No response from the model."
    except Exception as e:
        print(f"An error occurred while communicating with the OpenAI API: {e}")
        return "Sorry, I encountered an error while generating a response."

async def get_llm_response_stream(prompt: str):
    """
    Sends a prompt to the OpenAI API and yields the response in a stream.
    """
    try:
        stream = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=1024,
            stream=True,
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content
    except Exception as e:
        print(f"An error occurred while communicating with the OpenAI API: {e}")
        yield "Sorry, I encountered an error while generating a response."