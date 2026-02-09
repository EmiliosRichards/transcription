from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from manuav_eval import evaluate_company_with_usage_and_web_search_artifacts, evaluate_company_with_usage_and_web_search_debug
from manuav_eval.costing import (
    compute_cost_usd,
    compute_web_search_tool_cost_usd,
    pricing_from_env,
    web_search_pricing_from_env,
)


def _truthy(s: str | None) -> bool:
    return (s or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int | None = None) -> int | None:
    v = os.environ.get(name)
    if v is None or str(v).strip() == "":
        return default
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _env_float(name: str, default: float | None = None) -> float | None:
    v = os.environ.get(name)
    if v is None or str(v).strip() == "":
        return default
    try:
        return float(str(v).strip())
    except Exception:
        return default


def _bundled_rubric_path() -> Path:
    # Resolve relative to this file so the service works regardless of CWD.
    return (Path(__file__).resolve().parent / "rubrics" / "manuav_rubric_v4_en.md").resolve()


@dataclass(frozen=True)
class Attempt:
    result: Dict[str, Any]
    usage: Any
    web_search_calls: int
    url_citations: List[Dict[str, str]]
    ws_debug: Optional[Dict[str, Any]] = None


class EvaluateOptions(BaseModel):
    model: Optional[str] = None
    rubric_file: Optional[str] = None
    max_tool_calls: Optional[int] = None
    reasoning_effort: Optional[str] = None
    prompt_cache: Optional[bool] = None
    prompt_cache_retention: Optional[str] = None
    service_tier: Optional[str] = None
    timeout_seconds: Optional[float] = None
    flex_max_retries: Optional[int] = None
    flex_fallback_to_auto: Optional[bool] = None
    second_query_on_uncertainty: Optional[bool] = None
    retry_disambiguation_on_low_confidence: Optional[bool] = None
    retry_max_tool_calls: Optional[int] = None


class EvaluateRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    options: Optional[EvaluateOptions] = None


class EvaluateResponse(BaseModel):
    result: Dict[str, Any]
    meta: Dict[str, Any]


app = FastAPI(title="Manuav Company Evaluator (UI handover service)")


# Load .env for local dev only (prod should inject env vars).
if not os.environ.get("PYTEST_CURRENT_TEST"):
    load_dotenv(override=False)


_cors = (os.environ.get("CORS_ALLOW_ORIGINS") or "").strip()
if _cors:
    origins = [o.strip() for o in _cors.split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


def _run_attempt(
    *,
    url: str,
    model: str,
    rubric_file: str,
    max_tool_calls: int | None,
    reasoning_effort: str | None,
    prompt_cache: bool | None,
    prompt_cache_retention: str | None,
    service_tier: str | None,
    timeout_seconds: float | None,
    flex_max_retries: int | None,
    flex_fallback_to_auto: bool | None,
    second_query_on_uncertainty: bool,
    extra_user_instructions: str | None,
) -> Attempt:
    if extra_user_instructions and extra_user_instructions.strip():
        # Need the debug-capable path to inject extra instructions (used for retry).
        res, usage, ws = evaluate_company_with_usage_and_web_search_debug(
            url,
            model,
            rubric_file=rubric_file,
            max_tool_calls=max_tool_calls,
            reasoning_effort=reasoning_effort,
            prompt_cache=prompt_cache,
            prompt_cache_retention=prompt_cache_retention,
            service_tier=service_tier,
            timeout_seconds=timeout_seconds,
            flex_max_retries=flex_max_retries,
            flex_fallback_to_auto=flex_fallback_to_auto,
            include_sources=False,
            extra_user_instructions=extra_user_instructions,
            second_query_on_uncertainty=second_query_on_uncertainty,
        )
        by_kind_completed = (ws or {}).get("by_kind_completed") or {}
        billed_q = int(by_kind_completed.get("query", 0) or 0)
        citations = (ws or {}).get("url_citations") or []
        return Attempt(result=res, usage=usage, web_search_calls=billed_q, url_citations=citations, ws_debug=ws)

    res, usage, billed_q, citations = evaluate_company_with_usage_and_web_search_artifacts(
        url,
        model,
        rubric_file=rubric_file,
        max_tool_calls=max_tool_calls,
        reasoning_effort=reasoning_effort,
        prompt_cache=prompt_cache,
        prompt_cache_retention=prompt_cache_retention,
        service_tier=service_tier,
        timeout_seconds=timeout_seconds,
        flex_max_retries=flex_max_retries,
        flex_fallback_to_auto=flex_fallback_to_auto,
        second_query_on_uncertainty=second_query_on_uncertainty,
    )
    return Attempt(result=res, usage=usage, web_search_calls=int(billed_q), url_citations=citations, ws_debug=None)


@app.post("/evaluate", response_model=EvaluateResponse)
def evaluate(req: EvaluateRequest) -> EvaluateResponse:
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY on server.")

    opts = req.options or EvaluateOptions()

    model = (opts.model or os.environ.get("OPENAI_MODEL") or "gpt-4.1-mini").strip()
    if not model:
        raise HTTPException(status_code=400, detail="Missing model (empty).")

    rubric_file = (opts.rubric_file or os.environ.get("MANUAV_RUBRIC_FILE") or str(_bundled_rubric_path())).strip()

    max_tool_calls = opts.max_tool_calls
    if max_tool_calls is None:
        max_tool_calls = _env_int("MANUAV_MAX_TOOL_CALLS", None)

    second_query = bool(opts.second_query_on_uncertainty) if opts.second_query_on_uncertainty is not None else _truthy(
        os.environ.get("MANUAV_SECOND_QUERY_ON_UNCERTAINTY")
    )

    service_tier = (opts.service_tier or os.environ.get("MANUAV_SERVICE_TIER") or "auto").strip()
    timeout_seconds = opts.timeout_seconds
    if timeout_seconds is None:
        timeout_seconds = _env_float("MANUAV_OPENAI_TIMEOUT_SECONDS", None)
    # Flex can be slower; default to 900s if flex and unset.
    if timeout_seconds is None and service_tier.lower() == "flex":
        timeout_seconds = 900.0

    prompt_cache = opts.prompt_cache if opts.prompt_cache is not None else _truthy(os.environ.get("MANUAV_PROMPT_CACHE"))
    prompt_cache_retention = opts.prompt_cache_retention or os.environ.get("MANUAV_PROMPT_CACHE_RETENTION") or None
    reasoning_effort = (opts.reasoning_effort or os.environ.get("MANUAV_REASONING_EFFORT") or "").strip() or None

    flex_max_retries = opts.flex_max_retries
    if flex_max_retries is None:
        flex_max_retries = _env_int("MANUAV_FLEX_MAX_RETRIES", None)
    flex_fallback_to_auto = (
        bool(opts.flex_fallback_to_auto)
        if opts.flex_fallback_to_auto is not None
        else _truthy(os.environ.get("MANUAV_FLEX_FALLBACK_TO_AUTO"))
    )

    retry_on_low = (
        bool(opts.retry_disambiguation_on_low_confidence)
        if opts.retry_disambiguation_on_low_confidence is not None
        else _truthy(os.environ.get("MANUAV_RETRY_DISAMBIGUATION_ON_LOW_CONFIDENCE"))
    )
    retry_max_tool_calls = opts.retry_max_tool_calls
    if retry_max_tool_calls is None:
        retry_max_tool_calls = _env_int("MANUAV_RETRY_MAX_TOOL_CALLS", 3) or 3

    url = (req.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="Missing url.")

    attempts: List[Attempt] = []
    try:
        a1 = _run_attempt(
            url=url,
            model=model,
            rubric_file=rubric_file,
            max_tool_calls=max_tool_calls,
            reasoning_effort=reasoning_effort,
            prompt_cache=prompt_cache,
            prompt_cache_retention=prompt_cache_retention,
            service_tier=service_tier,
            timeout_seconds=timeout_seconds,
            flex_max_retries=flex_max_retries,
            flex_fallback_to_auto=flex_fallback_to_auto,
            second_query_on_uncertainty=second_query,
            extra_user_instructions=None,
        )
        attempts.append(a1)

        selected = a1
        retry_used = False
        retry_selected = "first"

        conf1 = str((a1.result or {}).get("confidence") or "").strip().lower()
        if retry_on_low and conf1 == "low":
            retry_used = True
            retry_max = int(retry_max_tool_calls or 3)
            if max_tool_calls is not None:
                retry_max = max(int(max_tool_calls), retry_max)
            disambig_prompt = (
                "Perform TWO distinct web searches before scoring.\n"
                "1) Search using the provided domain/company name (e.g., '<domain>').\n"
                "2) Search again with a disambiguation query that adds legal-entity/location hints, e.g. "
                "'<name> GmbH impressum', '<name> Munich impressum', '<name> HRB'.\n"
                "If results are ambiguous/conflicting, prefer sources that match the provided domain and DACH legal/imprint details; "
                "otherwise explicitly note uncertainty.\n"
            )
            a2 = _run_attempt(
                url=url,
                model=model,
                rubric_file=rubric_file,
                max_tool_calls=retry_max,
                reasoning_effort=reasoning_effort,
                prompt_cache=prompt_cache,
                prompt_cache_retention=prompt_cache_retention,
                service_tier=service_tier,
                timeout_seconds=timeout_seconds,
                flex_max_retries=flex_max_retries,
                flex_fallback_to_auto=flex_fallback_to_auto,
                second_query_on_uncertainty=False,
                extra_user_instructions=disambig_prompt,
            )
            attempts.append(a2)
            conf2 = str((a2.result or {}).get("confidence") or "").strip().lower()
            if conf2 and conf2 != "low":
                selected = a2
                retry_selected = "retry"

        # Aggregate usage + tool calls across attempts (retry costs are real).
        pricing = pricing_from_env(os.environ)
        tool_pricing = web_search_pricing_from_env(os.environ)
        flex_discount = float(os.environ.get("MANUAV_FLEX_TOKEN_DISCOUNT", "0.5") or 0.5)
        apply_flex_discount = service_tier.strip().lower() == "flex"

        web_search_calls = sum(int(a.web_search_calls or 0) for a in attempts)
        token_cost_raw = sum(compute_cost_usd(a.usage, pricing) for a in attempts)
        token_cost = (token_cost_raw * flex_discount) if apply_flex_discount else token_cost_raw
        web_search_cost = compute_web_search_tool_cost_usd(web_search_calls, tool_pricing)
        total_cost = token_cost + web_search_cost

        def _u_int(obj: Any, attr: str, default: int = 0) -> int:
            try:
                return int(getattr(obj, attr, default) or 0)
            except Exception:
                return default

        usage_input = sum(_u_int(a.usage, "input_tokens") for a in attempts)
        usage_output = sum(_u_int(a.usage, "output_tokens") for a in attempts)
        usage_total = sum(_u_int(a.usage, "total_tokens") for a in attempts)
        cached = 0
        reasoning_tokens = 0
        for a in attempts:
            try:
                cached += int(getattr(getattr(a.usage, "input_tokens_details", None), "cached_tokens", 0) or 0)
            except Exception:
                cached += 0
            try:
                reasoning_tokens += int(getattr(getattr(a.usage, "output_tokens_details", None), "reasoning_tokens", 0) or 0)
            except Exception:
                reasoning_tokens += 0

        # Merge citations across attempts (dedupe by URL).
        cites: List[Dict[str, str]] = []
        seen = set()
        for a in attempts:
            for c in a.url_citations or []:
                url_c = (c.get("url") or "").strip()
                if not url_c or url_c in seen:
                    continue
                seen.add(url_c)
                cites.append({"url": url_c, "title": (c.get("title") or "").strip()})

        meta = {
            "provider": "openai",
            "model": model,
            "rubric_file": rubric_file,
            "web_search_calls": int(web_search_calls),
            "usage": {
                "input_tokens": int(usage_input),
                "cached_input_tokens": int(cached),
                "output_tokens": int(usage_output),
                "reasoning_tokens": int(reasoning_tokens),
                "total_tokens": int(usage_total),
            },
            "estimated_cost_usd": {
                "token_cost_usd": round(float(token_cost), 6),
                "web_search_tool_cost_usd": round(float(web_search_cost), 6),
                "total_cost_usd": round(float(total_cost), 6),
            },
            "url_citations": cites,
            "retry": {"used": bool(retry_used), "selected": retry_selected},
        }
        return EvaluateResponse(result=selected.result, meta=meta)

    except HTTPException:
        raise
    except Exception as e:
        # Treat provider errors as 502 for cleaner UI handling.
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}")

