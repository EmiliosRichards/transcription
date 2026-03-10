from __future__ import annotations

from typing import Any, Dict


REASONING_MAX_LENGTH = 600  # keep outputs compact to reduce output tokens/cost

# v2 schema: additive fields beyond the original v1 bucket
OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "input_url": {"type": "string"},
        "company_name": {"type": "string"},
        "manuav_fit_score": {"type": "number", "minimum": 0, "maximum": 10},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "reasoning": {"type": "string", "maxLength": REASONING_MAX_LENGTH},
        "positives": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        "concerns": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        "company_size_indicators_text": {"anyOf": [{"type": "string", "maxLength": 800}, {"type": "null"}]},
        "innovation_level_indicators_text": {"anyOf": [{"type": "string", "maxLength": 800}, {"type": "null"}]},
        "targets_specific_industry_type": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
        "is_startup": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
        "is_ai_software": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
        "is_innovative_product": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
        "is_disruptive_product": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
        "is_vc_funded": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
        "is_saas_software": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
        "is_complex_solution": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
        "is_investment_product": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
    },
    "required": [
        "input_url",
        "company_name",
        "manuav_fit_score",
        "confidence",
        "reasoning",
        "positives",
        "concerns",
        "company_size_indicators_text",
        "innovation_level_indicators_text",
        "targets_specific_industry_type",
        "is_startup",
        "is_ai_software",
        "is_innovative_product",
        "is_disruptive_product",
        "is_vc_funded",
        "is_saas_software",
        "is_complex_solution",
        "is_investment_product",
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

