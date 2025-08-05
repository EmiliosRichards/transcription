from typing import Optional, List, Dict, Any
import logging
import openai
import instructor
from app.config import settings

logger = logging.getLogger(__name__)

# Patch the client with instructor
async_client = instructor.patch(openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY))
client = instructor.patch(openai.OpenAI(api_key=settings.OPENAI_API_KEY))

# --- System Prompts ---
CHITCHAT_SYSTEM_PROMPT = """
You are a helpful AI assistant for a business intelligence platform. Your primary role is to answer questions about company data.

However, you can also engage in general conversation (chitchat). When doing so, you must adhere to the following guidelines:

1.  **Maintain a Professional Persona:** Your tone should be friendly and helpful, but always within the context of a professional workplace tool.
2.  **Be Helpful but Brief:** Answer general questions concisely. Avoid long, multi-paragraph explanations on non-business topics.
3.  **Gently Redirect to Work:** After answering an off-topic question, gently guide the user back towards business-related tasks.
4.  **Avoid Sensitive and Inappropriate Topics:** Do not discuss personal opinions, politics, or other controversial subjects. Refuse any requests that are not safe for a work environment.
5.  **Do Not Hallucinate:** If you don't know an answer to a factual question, it is better to say you don't know than to make something up.

**Example of a good redirect:**
*User:* "What's the best way to cook a steak?"
*You:* "A great way is to pan-sear it with butter and herbs for a nice crust! Speaking of performance, was there any campaign data you wanted to analyze?"
"""
RAG_SYSTEM_PROMPT = "You are a helpful AI assistant. Your task is to synthesize an answer from the provided context. If the context is not sufficient, say you don't have enough information."

async def get_structured_response(prompt: str, response_model: Any) -> Any:
    """
    Sends a prompt to the OpenAI API and returns a structured response
    based on the provided Pydantic model.
    """
    try:
        response = await async_client.chat.completions.create(
            model=settings.MAIN_LLM_MODEL,
            messages=[{"role": "user", "content": prompt}], # type: ignore
            response_model=response_model,
            temperature=0.0,
        )
        logger.info(f"LLM structured response received: {response.model_dump_json(indent=2)}")
        return response
    except Exception as e:
        logger.error(f"An error occurred in get_structured_response: {e}", exc_info=True)
        return None


async def get_llm_response(prompt: str, is_chitchat: bool = False, history: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    Sends a prompt to the OpenAI API and returns the model's response.
    Routes to a different system prompt based on the intent and includes conversation history.
    """
    system_prompt = CHITCHAT_SYSTEM_PROMPT if is_chitchat else RAG_SYSTEM_PROMPT
    
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    try:
        response = await async_client.chat.completions.create(
            model=settings.MAIN_LLM_MODEL,
            messages=messages, # type: ignore
            temperature=0.7,
            max_tokens=1024,
        )
        logger.info(f"LLM response received: {response.choices[0].message.content}")
        return response.choices[0].message.content or "No response from the model."
    except Exception as e:
        logger.error(f"An error occurred in get_llm_response: {e}", exc_info=True)
        return "Sorry, I encountered an error while generating a response."

async def get_llm_response_stream(prompt: str, is_chitchat: bool = False, history: Optional[List[Dict[str, Any]]] = None):
    """
    Sends a prompt to the OpenAI API and yields the response in a stream.
    Routes to a different system prompt based on the intent and includes conversation history.
    """
    system_prompt = CHITCHAT_SYSTEM_PROMPT if is_chitchat else RAG_SYSTEM_PROMPT

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    try:
        stream = await async_client.chat.completions.create(
            model=settings.MAIN_LLM_MODEL,
            messages=messages, # type: ignore
            temperature=0.7,
            max_tokens=1024,
            stream=True,
        )
        async for chunk in stream:
            logger.info(f"LLM stream chunk received: {chunk.model_dump_json()}")
            content = chunk.choices[0].delta.content
            if content:
                yield content
    except Exception as e:
        logger.error(f"An error occurred in get_llm_response_stream: {e}", exc_info=True)
        yield "Sorry, I encountered an error while generating a response."

def get_llm_response_sync(prompt: str, is_chitchat: bool = False, history: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    Synchronous version of get_llm_response.
    """
    system_prompt = CHITCHAT_SYSTEM_PROMPT if is_chitchat else RAG_SYSTEM_PROMPT
    
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    try:
        response = client.chat.completions.create(
            model=settings.MAIN_LLM_MODEL,
            messages=messages, # type: ignore
            temperature=0.7,
            max_tokens=1024,
        )
        logger.info(f"LLM sync response received: {response.choices[0].message.content}")
        return response.choices[0].message.content or "No response from the model."
    except Exception as e:
        logger.error(f"An error occurred in get_llm_response_sync: {e}", exc_info=True)
        return "Sorry, I encountered an error while generating a response."