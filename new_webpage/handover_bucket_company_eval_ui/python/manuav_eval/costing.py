from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from openai.types.responses.response_usage import ResponseUsage


@dataclass(frozen=True)
class PricingPer1M:
    input_usd: float = 1.75
    cached_input_usd: float = 0.175
    output_usd: float = 14.0


@dataclass(frozen=True)
class WebSearchPricing:
    per_1k_calls_usd: float = 10.0


def compute_cost_usd(usage: ResponseUsage, pricing: PricingPer1M) -> float:
    """Compute USD cost from token usage using per-1M token pricing."""
    cached = int(getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    non_cached = max(0, input_tokens - cached)
    return (
        (non_cached / 1_000_000.0) * pricing.input_usd
        + (cached / 1_000_000.0) * pricing.cached_input_usd
        + (output_tokens / 1_000_000.0) * pricing.output_usd
    )


def compute_web_search_tool_cost_usd(web_search_calls: int, pricing: WebSearchPricing) -> float:
    calls = max(0, int(web_search_calls))
    return calls * (pricing.per_1k_calls_usd / 1000.0)


def pricing_from_env(env: dict, default: Optional[PricingPer1M] = None) -> PricingPer1M:
    """Read OpenAI pricing config from environment."""
    base = default or PricingPer1M()

    def _get_float(key: str, fallback: float) -> float:
        v = env.get(key)
        if v is None or str(v).strip() == "":
            return fallback
        return float(str(v).strip())

    return PricingPer1M(
        input_usd=_get_float("MANUAV_PRICE_INPUT_PER_1M", base.input_usd),
        cached_input_usd=_get_float("MANUAV_PRICE_CACHED_INPUT_PER_1M", base.cached_input_usd),
        output_usd=_get_float("MANUAV_PRICE_OUTPUT_PER_1M", base.output_usd),
    )


def web_search_pricing_from_env(env: dict, default: Optional[WebSearchPricing] = None) -> WebSearchPricing:
    base = default or WebSearchPricing()
    v = env.get("MANUAV_PRICE_WEB_SEARCH_PER_1K")
    if v is None or str(v).strip() == "":
        return base
    return WebSearchPricing(per_1k_calls_usd=float(str(v).strip()))


# Gemini costing is intentionally omitted from this UI bucket.
# (The main repo includes Gemini support; add it here only if your web project needs it.)

