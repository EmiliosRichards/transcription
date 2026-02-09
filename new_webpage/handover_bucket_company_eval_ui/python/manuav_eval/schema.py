from __future__ import annotations

from typing import Any, Dict


REASONING_MAX_LENGTH = 600  # keep outputs compact to reduce output tokens/cost

OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "input_url": {"type": "string"},
        "company_name": {"type": "string"},
        "manuav_fit_score": {"type": "number", "minimum": 0, "maximum": 10},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "reasoning": {"type": "string", "maxLength": REASONING_MAX_LENGTH},
    },
    "required": [
        "input_url",
        "company_name",
        "manuav_fit_score",
        "confidence",
        "reasoning",
    ],
}


OUTPUT_SCHEMA_WITH_SOURCES: Dict[str, Any] = {
    **OUTPUT_SCHEMA,
    "properties": {
        **(OUTPUT_SCHEMA.get("properties") or {}),
        "sources": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "url": {"type": "string"},
                    "title": {"type": "string"},
                    "note": {"type": "string", "maxLength": 160},
                },
                # OpenAI strict JSON Schema requires `required` includes every property key.
                "required": ["url", "title", "note"],
            },
        },
    },
    "required": [*OUTPUT_SCHEMA.get("required", []), "sources"],
}


def json_schema_text_config(
    *,
    name: str = "manuav_company_fit",
    strict: bool = True,
    schema: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "format": {
            "type": "json_schema",
            "name": name,
            "strict": strict,
            "schema": schema or OUTPUT_SCHEMA,
        }
    }

