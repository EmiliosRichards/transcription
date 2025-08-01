from typing import Dict, Any, Optional, List, Literal
from pydantic import BaseModel, Field

from app.services.llm_handler import client
from app.config import settings

# --- Pydantic Models for Structured LLM Output ---

class ExtractedFilters(BaseModel):
    """Defines the structure for filters extracted by the LLM."""
    field: str = Field(..., description="The metadata field to filter on (e.g., 'tags', 'journey_outcomes').")
    operator: str = Field(..., description="The logical operator (e.g., '$in', '$gte', '$eq').")
    value: Any = Field(..., description="The value to compare against.")

class DeconstructedQuery(BaseModel):
    """The structured output of the query deconstruction process."""
    intent: Literal["question", "chitchat", "sampling"] = Field(
        ...,
        description="The user's intent. Is it a 'question' for the knowledge base, 'chitchat', or a request for a 'sampling' of documents?"
    )
    semantic_query: str = Field(
        ..., description="A refined, clean query string for vector search, stripped of all filter-related language. For chitchat, this can be the original query."
    )
    extracted_filters: List[ExtractedFilters] = Field(
        default_factory=list,
        description="A list of structured filters extracted from the natural language query. This should be empty for chitchat."
    )
    n_results: int = Field(
        default=3,
        description="Optimal number of documents to retrieve. More for broad questions, less for specific ones. Default to 3."
    )
    hypothetical_document: Optional[str] = Field(
        default=None,
        description="A hypothetical document generated to improve search for abstract queries."
    )

# --- Query Agent Service ---

class QueryAgent:
    """
    An intelligent agent that deconstructs a user's natural language query
    into a structured format for database retrieval.
    """
    def __init__(self):
        self.client = client

    async def deconstruct_query(self, query: str, history: Optional[List[Dict[str, Any]]] = None) -> DeconstructedQuery:
        """
        Processes a raw query using an LLM to get a structured output including
        the user's intent, a semantic query, and any extracted filters.
        It uses the provided conversation history to better understand context.
        """
        system_prompt = self._get_system_prompt()
        
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": f"Deconstruct the following user query: \"{query}\""})

        response = await self.client.chat.completions.create(
            model=settings.MAIN_LLM_MODEL,
            messages=messages,
            response_model=DeconstructedQuery, # type: ignore
            temperature=0.0,
        )
        return response

    def _get_system_prompt(self) -> str:
        """
        Creates the system prompt that instructs the LLM on how to deconstruct the query.
        """
        return """
You are an expert at deconstructing user queries into a structured JSON format.
Your task is to analyze the user's LATEST query, using the context from the preceding conversation history to resolve ambiguities.
Based on the user's latest query, extract FIVE key components:

1.  **intent**: First, determine the user's intent.
    -   Classify as **"question"** if the user is asking for specific information that is likely contained in the knowledge base (e.g., asking about objections, sentiment, specific calls).
    -   Classify as **"chitchat"** if the user is making small talk, asking a general knowledge question, or saying hello/thank you.
    -   Classify as **"sampling"** if the user asks for "a random sample," "a representative mix," or a "random selection" of calls.
 
 2.  **semantic_query**:
     -   If the intent is "question", this should be a concise version of the query, suitable for a vector database search. It should capture the core *meaning* of the user's request, stripped of any specific filter commands.
     -   If the intent is "chitchat", this can be the original user query.
     -   If the intent is "sampling", this field can be an empty string.

3.  **n_results**:
    -   If the intent is "question" or "sampling", estimate the optimal number of documents to retrieve based on the following hierarchy:
    -   **User-Specified**: If the user explicitly asks for a number (e.g., "find 10 examples"), use that number, up to a maximum of 10.
    -   **Broad/Analytical Queries**: For broad, analytical, or comparative questions (e.g., "summarize the main issues," "what are common complaints?"), use a higher number between 5 and 10.
    -   **Specific Queries**: For highly specific queries (e.g., "find call ID 123-abc"), use a low number like 1 or 2.
    -   **Default**: For all other standard questions, default to 5.
    -   If the intent is "chitchat", this field can be omitted (it will default to 0).

4.  **extracted_filters**:
    -   If the intent is "question", this is a list of all filters mentioned in the query. You must map them to the correct field names and operators.
    -   If the intent is "chitchat" or "sampling", this should be an empty list unless the user specifies filters (e.g., "a random sample from last week").

5.  **hypothetical_document**:
    -   If the `semantic_query` is abstract, conceptual, or implies a pattern (e.g., "bad outcomes," "successful sales tactics," "frustrated customers"), generate a short, hypothetical document that exemplifies the ideal search result.
    -   This document will be used to find real documents that are semantically similar.
    -   If the query is specific and not abstract (e.g., "find call ID 123," "show me transcripts from last week"), this field MUST be null.

Available filter fields:
- `last_call_date` (operator: `$gte`, value: Unix timestamp)
- `average_sentiment` (operators: `$gt`, `$lt`, value: integer 1-5)
- `journey_outcomes` (operator: `$in`, value: list of strings)
- `tags` (operator: `$in`, value: list of strings)

---
**Example 1: A specific question**
User Query: "show me transcripts from the last 30 days about billing problems with unhappy customers"
Your JSON Output:
{
  "intent": "question",
  "semantic_query": "billing problems with unhappy customers",
  "n_results": 5,
  "hypothetical_document": null,
  "extracted_filters": [
    {
      "field": "last_call_date",
      "operator": "$gte",
      "value": "<timestamp_for_30_days_ago>"
    },
    {
      "field": "tags",
      "operator": "$in",
      "value": ["billing"]
    },
    {
      "field": "average_sentiment",
      "operator": "$lt",
      "value": 3
    }
  ]
}

---
**Example 2: Chitchat**
User Query: "hello there, how are you?"
Your JSON Output:
{
  "intent": "chitchat",
  "semantic_query": "hello there, how are you?",
  "n_results": 0,
  "extracted_filters": [],
  "hypothetical_document": null
}

---
**Example 3: Abstract HyDE Query**
User Query: "Find me examples of calls with really bad outcomes"
Your JSON Output:
{
  "intent": "question",
  "semantic_query": "calls with bad outcomes",
  "n_results": 5,
  "hypothetical_document": "The customer was extremely frustrated because their issue has been unresolved for three weeks. They mentioned they are considering leaving for a competitor. The agent was unable to offer a satisfactory solution, and the call ended with the customer hanging up. The journey outcome was 'unresolved' and sentiment was negative.",
  "extracted_filters": []
}

---
**Example 4: A sampling request**
User Query: "can you give me a random sample of 10 calls?"
Your JSON Output:
{
  "intent": "sampling",
  "semantic_query": "",
  "n_results": 10,
  "hypothetical_document": null,
  "extracted_filters": []
}

---
Now, deconstruct the user's query.
"""
