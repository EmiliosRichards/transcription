import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Callable, Optional, Tuple

# --- Structured Filter Configuration ---
FILTER_RULES: List[Dict[str, Any]] = [
    {
        "name": "date_filter",
        "pattern": re.compile(r"\b(last|past)\s+(\d+)\s+days?\b", re.IGNORECASE),
        "handler": lambda match: (
            "last_call_date",
            {
                "$gte": int(
                    (datetime.now() - timedelta(days=int(match.group(2)))).timestamp()
                )
            },
        ),
    },
    {
        "name": "sentiment_filter",
        "pattern": re.compile(
            r"\bsentiment\s+(greater|less)\s+than\s+([1-5])\b", re.IGNORECASE
        ),
        "handler": lambda match: (
            "average_sentiment",
            {
                "$gt"
                if match.group(1).lower() == "greater"
                else "$lt": int(match.group(2))
            },
        ),
    },
    {
        "name": "outcome_filter",
        "pattern": re.compile(
            r"\boutcome\s+(?:is\s+)?['\"]?([^'\"]+)['\"]?\b", re.IGNORECASE
        ),
        "handler": lambda match: ("journey_outcomes", {"$in": [match.group(1).strip()]}),
    },
]


def parse_query_for_filters(
    query: str,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Parses a query for various filter expressions and returns a ChromaDB-compatible
    'where' filter and a cleaned query.
    """
    where_clauses = {}
    cleaned_query = query

    for rule in FILTER_RULES:
        match = rule["pattern"].search(cleaned_query)
        if match:
            field, condition = rule["handler"](match)
            where_clauses[field] = condition
            cleaned_query = cleaned_query.replace(match.group(0), "", 1).strip()

    if not cleaned_query.strip():
        cleaned_query = "show all information"

    if not where_clauses:
        return None, cleaned_query

    if len(where_clauses) > 1:
        return {"$and": [{k: v} for k, v in where_clauses.items()]}, cleaned_query

    return where_clauses, cleaned_query