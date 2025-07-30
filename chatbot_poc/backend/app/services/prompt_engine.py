import os
from typing import List, Dict

def create_prompt_from_template(template_name: str, variables: Dict[str, str]) -> str:
    """
    Loads a prompt template from the 'prompts' directory, formats it with the
    provided variables, and returns the final prompt string.
    """
    # Build a robust path to the project's root directory
    # __file__ is .../transcription/chatbot_poc/backend/app/services/prompt_engine.py
    # We want to get to .../transcription/
    project_root = os.path.realpath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
    template_path = os.path.join(project_root, 'prompts', template_name)
    
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            template_str = f.read()
        return template_str.format(**variables)
    except FileNotFoundError:
        raise FileNotFoundError(f"Prompt template not found at: {template_path}")
    except KeyError as e:
        raise KeyError(f"Missing variable {e} in the provided dictionary for template {template_name}")

def create_prompt(query: str, search_results: List[Dict]) -> str:
    """
    Creates a detailed prompt for the language model based on the user's query
    and the retrieved search results.
    """
    
    print(f"DEBUG: Query received by prompt engine: '{query}'") # Debugging print statement

    context = ""
    for i, result in enumerate(search_results):
        context += f"--- Document {i+1} ---\n"
        context += f"Customer ID: {result.get('customer_id', 'N/A')}\n"
        context += f"Call IDs: {result.get('call_ids', 'N/A')}\n"
        context += f"Transcript:\n{result.get('full_journey', 'N/A')}\n\n"

    prompt = f"""
    You are an expert AI assistant for analyzing customer call transcripts for a lead acquisition campaign.
    Your task is to provide a clear, concise, and insightful answer to the user's query based on the provided documents.

    **User Query:** "{query}"

    **Context from relevant call transcripts:**
    {context}

    **Instructions:**
    1.  Carefully read the user's query and the provided context.
    2.  Synthesize the information from the documents to directly answer the query.
    3.  Do not just list the documents. Provide a coherent, analytical response.
    4.  If the documents do not contain enough information to answer the query, state that clearly.
    5.  Keep your answer concise and to the point.

    **Formatting Instructions:**
    - **Structure:** Organize your response with clear headers (e.g., `## Key Findings`), sub-headers (`### Positive Signals`), and bulleted lists (`-`) for easy readability.
    - **Clarity:** Use bold text (`**text**`) to emphasize key concepts, metrics, or findings.
    - **Visuals:** Present information in a clean, well-structured, and visually appealing way. Use separators (`---`) to break up long sections if needed.
    - **Example:** Follow this structure for your response:

    ## Analysis of Positive Customer Signals
    
    Based on the provided call transcripts, here is a breakdown of the key positive signals indicating engagement and potential interest from customers.
    
    ### **1. Willingness to Assist & Provide Contact Info**
    A primary positive indicator is the willingness of call recipients to help facilitate communication, even if they are not the direct decision-maker.
    
    - **Key Action:** Offering to pass on messages or provide alternative contact details (e.g., email addresses).
    > **Example:** In Document 1, the receptionist actively suggests forwarding the information to the correct person.
    
    ### **2. Acknowledgment & Follow-Up Opportunities**
    This section highlights instances where customers acknowledge receipt of materials and express intent for future action.
    
    - **Key Action:** Confirming they have received postal information and are willing to pass it to relevant parties.
    > **Example:** Document 2 shows a customer confirming receipt and promising to forward the materials for follow-up.
    
    ---

    **Your Answer:**
    """
    
    return prompt.strip()