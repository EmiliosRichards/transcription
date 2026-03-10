from __future__ import annotations

import hashlib
import json
import random
import re
import time
from urllib.parse import urlparse
from typing import Any, Dict

from openai import OpenAI
from openai.types.responses.response_usage import ResponseUsage

from .rubric_loader import load_rubric_text
from .schema import OUTPUT_SCHEMA_WITH_SOURCES, REASONING_MAX_LENGTH, json_schema_text_config


BASE_SYSTEM_PROMPT = """\
You are a specialized evaluation assistant for Manuav, a B2B cold outbound (phone outreach) and lead-generation agency.

You will be given:
- a company website URL
- a rubric (below)

Your job:
- research the company using the web search tool (this is required)
- apply the rubric
- return ONLY valid JSON matching the provided schema (no extra keys, no markdown)

Evidence discipline:
- Do not hallucinate. If something is unknown, say so, lower confidence, and be conservative.

Research process (required):
- Use the web search tool to:
  - visit/review the company website (home, product, pricing, cases, careers, legal/imprint/contact)
  - search the web for corroborating third-party evidence
- Use the web search tool strategically.
  - If you have a limited tool-call/search budget, prioritize validating the rubric’s hard lines and the biggest unknowns first.
- Prefer primary sources first, then reputable third-party sources. Prioritize DACH-relevant signals.
- You do NOT need to output a sources list in JSON. Keep the output compact.

Entity disambiguation (guideline):
- Be mindful of same-name/lookalike companies. Use your judgment to sanity-check that a source is actually about the company behind the provided website URL.
- Helpful identity signals include:
  - domain consistency and links from the official site
  - legal entity name and imprint/registration details
  - headquarters/location and language/market focus
  - product description, ICP, and branding match
  - the official LinkedIn/company page referenced by the website
- If attribution is uncertain, either avoid relying on the source or briefly note the uncertainty in your reasoning.

Hard rule (important):
- The company you are evaluating is the one behind the provided domain. Do not accidentally evaluate a different company with a similar name.
- Prioritize evidence that is clearly tied to the provided domain (especially the site itself, imprint/legal pages, and any linked official profiles).
"""

_U2028 = "\u2028"
_U2029 = "\u2029"
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
_URL_RE = re.compile(r"https?://\S+")


def _sanitize_reasoning(text: str, *, max_len: int = REASONING_MAX_LENGTH) -> str:
    """
    Best-effort enforcement of the output contract for `reasoning`.
    - no URLs in reasoning
    - length capped
    - normalize U+2028/U+2029 which can break some JSONL consumers

    Note: We preserve line breaks (UI can render with whitespace-pre-wrap).
    """
    s = (text or "").strip()
    if not s:
        return ""

    s = s.replace(_U2028, " ").replace(_U2029, " ")
    s = _MD_LINK_RE.sub(r"\1", s)
    s = _URL_RE.sub("", s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    lines_in = [ln.strip() for ln in s.split("\n")]
    lines: list[str] = []
    for ln in lines_in:
        if not ln:
            continue
        prefix = ""
        body = ln
        if body.startswith("-"):
            prefix = "- "
            body = body[1:].lstrip()
        elif body.startswith("•"):
            prefix = "- "
            body = body[1:].lstrip()
        body = re.sub(r"\s+", " ", body).strip()
        if not body:
            continue
        lines.append(f"{prefix}{body}" if prefix else body)
    s = "\n".join(lines).strip()

    if len(s) <= max_len:
        return s

    # Prefer cutting at a line boundary, then at sentence boundary.
    if "\n" in s:
        out_lines: list[str] = []
        remaining = max_len
        for ln in s.split("\n"):
            extra = 1 if out_lines else 0
            if len(ln) + extra > remaining:
                break
            out_lines.append(ln)
            remaining -= len(ln) + extra
        out = "\n".join(out_lines).rstrip()
        if out:
            return out

    s = s[:max_len].rstrip()
    for punct in (".", "!", "?"):
        cut = s.rfind(punct)
        if cut >= max(0, max_len - 160) and cut >= 200:
            return s[: cut + 1].rstrip()
    sp = s.rfind(" ")
    if sp >= max(0, max_len - 24) and sp >= 200:
        return s[:sp].rstrip()
    return s


def _extract_json_text(resp: Any) -> str:
    if hasattr(resp, "output_text") and isinstance(resp.output_text, str) and resp.output_text.strip():
        return resp.output_text
    try:
        parts = []
        for item in getattr(resp, "output", []) or []:
            for c in getattr(item, "content", []) or []:
                t = getattr(c, "text", None)
                if isinstance(t, str) and t.strip():
                    parts.append(t)
        if parts:
            return "\n".join(parts)
    except Exception:
        pass
    raise RuntimeError("Could not extract text output from OpenAI response.")


def evaluate_company(
    url: str,
    model: str,
    *,
    rubric_file: str | None = None,
    max_tool_calls: int | None = None,
    reasoning_effort: str | None = None,
    prompt_cache: bool | None = None,
    prompt_cache_retention: str | None = None,
    service_tier: str | None = None,
    timeout_seconds: float | None = None,
    flex_max_retries: int | None = None,
    flex_fallback_to_auto: bool | None = None,
    second_query_on_uncertainty: bool = False,
) -> Dict[str, Any]:
    result, _usage, _ws = _evaluate_company_raw(
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
    return result


def evaluate_company_with_usage(
    url: str,
    model: str,
    *,
    rubric_file: str | None = None,
    max_tool_calls: int | None = None,
    reasoning_effort: str | None = None,
    prompt_cache: bool | None = None,
    prompt_cache_retention: str | None = None,
    service_tier: str | None = None,
    timeout_seconds: float | None = None,
    flex_max_retries: int | None = None,
    flex_fallback_to_auto: bool | None = None,
    second_query_on_uncertainty: bool = False,
) -> tuple[Dict[str, Any], ResponseUsage]:
    result, usage, _ws = _evaluate_company_raw(
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
    if usage is None:
        raise RuntimeError("OpenAI response did not include usage.")
    return result, usage


def evaluate_company_with_usage_and_web_search_calls(
    url: str,
    model: str,
    *,
    rubric_file: str | None = None,
    max_tool_calls: int | None = None,
    reasoning_effort: str | None = None,
    prompt_cache: bool | None = None,
    prompt_cache_retention: str | None = None,
    service_tier: str | None = None,
    timeout_seconds: float | None = None,
    flex_max_retries: int | None = None,
    flex_fallback_to_auto: bool | None = None,
    second_query_on_uncertainty: bool = False,
) -> tuple[Dict[str, Any], ResponseUsage, int]:
    result, usage, ws_stats = _evaluate_company_raw(
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
    if usage is None:
        raise RuntimeError("OpenAI response did not include usage.")
    return result, usage, _billable_web_search_calls(ws_stats)


def evaluate_company_with_usage_and_web_search_debug(
    url: str,
    model: str,
    *,
    rubric_file: str | None = None,
    max_tool_calls: int | None = None,
    reasoning_effort: str | None = None,
    prompt_cache: bool | None = None,
    prompt_cache_retention: str | None = None,
    service_tier: str | None = None,
    timeout_seconds: float | None = None,
    flex_max_retries: int | None = None,
    flex_fallback_to_auto: bool | None = None,
    include_sources: bool = False,
    extra_user_instructions: str | None = None,
    second_query_on_uncertainty: bool = False,
) -> tuple[Dict[str, Any], ResponseUsage, Dict[str, Any]]:
    result, usage, ws_stats = _evaluate_company_raw(
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
        include_sources=include_sources,
        extra_user_instructions=extra_user_instructions,
        second_query_on_uncertainty=second_query_on_uncertainty,
    )
    if usage is None:
        raise RuntimeError("OpenAI response did not include usage.")
    return result, usage, ws_stats


def evaluate_company_with_usage_and_web_search_artifacts(
    url: str,
    model: str,
    *,
    rubric_file: str | None = None,
    max_tool_calls: int | None = None,
    reasoning_effort: str | None = None,
    prompt_cache: bool | None = None,
    prompt_cache_retention: str | None = None,
    service_tier: str | None = None,
    timeout_seconds: float | None = None,
    flex_max_retries: int | None = None,
    flex_fallback_to_auto: bool | None = None,
    second_query_on_uncertainty: bool = False,
) -> tuple[Dict[str, Any], ResponseUsage, int, list[dict[str, str]]]:
    result, usage, ws_stats = _evaluate_company_raw(
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
    if usage is None:
        raise RuntimeError("OpenAI response did not include usage.")
    billed = _billable_web_search_calls(ws_stats)
    citations = ws_stats.get("url_citations") or []
    return result, usage, billed, citations


def _billable_web_search_calls(ws_stats: Dict[str, Any]) -> int:
    by_kind_completed = ws_stats.get("by_kind_completed") or {}
    if isinstance(by_kind_completed, dict) and "query" in by_kind_completed:
        try:
            return int(by_kind_completed.get("query", 0) or 0)
        except Exception:
            return 0
    # Fallback to best-effort count across tool kinds.
    try:
        return int(sum(int(v or 0) for v in by_kind_completed.values()))
    except Exception:
        return 0


def _web_search_call_debug(resp: Any) -> Dict[str, Any]:
    """
    Best-effort extraction of tool-call debug info from OpenAI responses.
    """
    ws: Dict[str, Any] = {"by_kind_completed": {}, "url_citations": []}
    try:
        for item in getattr(resp, "output", []) or []:
            if getattr(item, "type", None) != "tool_call":
                continue
            name = getattr(item, "name", None) or getattr(item, "tool_name", None) or ""
            if not isinstance(name, str):
                name = str(name)
            ws["by_kind_completed"][name] = int(ws["by_kind_completed"].get(name, 0) or 0) + 1
    except Exception:
        pass
    # Citations are optional and provider-dependent; leave empty if not present.
    return ws


def _normalize_service_tier(service_tier: str | None) -> str | None:
    st = (service_tier or "").strip().lower()
    if not st:
        return None
    if st not in {"auto", "flex"}:
        return None
    return st


def _evaluate_company_raw(
    url: str,
    model: str,
    *,
    rubric_file: str | None = None,
    max_tool_calls: int | None = None,
    reasoning_effort: str | None = None,
    prompt_cache: bool | None = None,
    prompt_cache_retention: str | None = None,
    service_tier: str | None = None,
    timeout_seconds: float | None = None,
    flex_max_retries: int | None = None,
    flex_fallback_to_auto: bool | None = None,
    include_sources: bool = False,
    extra_user_instructions: str | None = None,
    second_query_on_uncertainty: bool = False,
) -> tuple[Dict[str, Any], ResponseUsage | None, Dict[str, Any]]:
    client = OpenAI()
    rubric_path, rubric_text = load_rubric_text(rubric_file)
    system_prompt = f"{BASE_SYSTEM_PROMPT}\n\nRubric file: {rubric_path}\n\n{rubric_text}\n"

    normalized_url = (url or "").strip()
    if normalized_url and not normalized_url.lower().startswith(("http://", "https://")):
        normalized_url = f"https://{normalized_url}"
    parsed = urlparse(normalized_url)
    domain = (parsed.netloc or "").strip().lower()
    if domain.startswith("www."):
        domain = domain[4:]

    tool_budget_line = (
        f"- Tool-call budget: you can make at most {max_tool_calls} web search tool call(s). Use them wisely.\n"
        if max_tool_calls is not None
        else ""
    )

    sources_instruction = ""
    text_cfg = json_schema_text_config()
    if include_sources:
        sources_instruction = (
            "- Include a short sources list in JSON under key `sources` (max 8 items).\n"
            "  - Each item: {url, title (optional), note (very short)}.\n"
            "  - URLs are allowed ONLY inside `sources`, not in `reasoning`.\n"
        )
        text_cfg = json_schema_text_config(schema=OUTPUT_SCHEMA_WITH_SOURCES)

    extra_instruction_block = ""
    if extra_user_instructions and extra_user_instructions.strip():
        extra_instruction_block = f"\nExtra instructions (debug):\n{extra_user_instructions.strip()}\n"
    elif second_query_on_uncertainty:
        # IMPORTANT: keep the original bucket semantics (disambiguation only).
        extra_instruction_block = (
            "\nExtra instructions:\n"
            "- Default to ONE web search query.\n"
            "- If (and only if) the first query does NOT yield trustworthy evidence about the company behind the provided domain "
            "(e.g., domain seems inactive/parked, results point to different entities, or multiple similarly named companies appear), "
            "you SHOULD run exactly ONE additional disambiguation query.\n"
            "- Do NOT use a second query just to gather extra detail (e.g., pricing/ARPU) when the company is already clearly identified.\n"
            "- Do not use more than two queries total.\n"
        )

    user_prompt = f"""\
Evaluate this company for Manuav using web research and the Manuav Fit logic.

Scoring lens (important):
- Do NOT judge fit only by the company's "majority business" (e.g., "90% B2C so it's a bad fit").
- Manuav only needs a credible *sales opportunity wedge* to be valuable: a specific, reachable buyer segment with budget and repeatable sales motion (often B2B), even if it is a minority of the business.
- Mixed B2C/B2B is NOT a negative by itself: if there is any credible B2B wedge, do not penalize just for being mixed; instead, reflect the wedge and list what needs validation (deal size, buying process, dedicated sales motion).

Instructions:
- CRITICAL: Anchor identity to the provided domain: {domain or "(unknown domain)"}.
- Your FIRST web search query should be domain-anchored to avoid lookalikes, e.g.:
  - site:{domain} (impressum OR kontakt OR about OR "über uns" OR karriere OR product OR pricing OR sortiment OR zielgruppen OR b2b OR firmenkunden OR gewerbekunden OR geschäftskunden OR großhandel OR "für unternehmen")
- Prefer sources that clearly refer to {domain} (the website itself and pages it links to).
- Use the web search tool to research:
  - the company website itself (product/service, ICP, pricing, cases, careers, legal/imprint)
  - and the broader web for each rubric category (DACH presence, operational status, TAM, competition, innovation, economics, onboarding, pitchability, risk).
{tool_budget_line}- Be conservative when evidence is missing.
{extra_instruction_block}- In the JSON output:
  - set input_url exactly to the Company website URL below
  - Output language: Write `reasoning`, `positives`, and `concerns` in German (Deutsch).
  - Output format (hard requirement):
    - `reasoning`: 1–2 short sentences summarizing the fit (neutral tone allowed: "nicht schlecht, nicht ideal").
    - `positives`: 0–6 concise bullet-like strings (each a complete sentence) describing what could make them a good fit for Manuav.
    - `concerns`: 0–6 concise bullet-like strings (each a complete sentence) describing concerns / open questions that reduce fit.
      - If evidence is missing/ambiguous, phrase as an open question to validate (e.g., "Unklar, ob …; falls ja/nein, würde das den Fit verbessern/verschlechtern.").
    - Do NOT be overly harsh. Low scores should have more `concerns` and fewer `positives`, and vice versa.
    - Hard cap: {REASONING_MAX_LENGTH} characters for `reasoning` only.
  - Also fill these structured attributes (use null if unknown; do not guess):
    - `company_size_indicators_text` (German): any concrete signals (team size, locations, #customers, revenue class, “Mittelstand”, etc.).
    - `innovation_level_indicators_text` (German): any concrete innovation/tech/product signals (AI, automation, patents, “innovativ”, etc.).
    - `targets_specific_industry_type` (array of strings): 0–6 specific target industries/types inferred. Keep items short.
    - Flags (booleans or null): `is_startup`, `is_ai_software`, `is_innovative_product`, `is_disruptive_product`, `is_vc_funded`, `is_saas_software`, `is_complex_solution`, `is_investment_product`.
{sources_instruction}  - do NOT include URLs in `reasoning`.

Company website URL: {normalized_url}
"""

    create_kwargs: Dict[str, Any] = {
        "model": model,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "tools": [{"type": "web_search_preview"}],
        "text": text_cfg,
    }

    st = _normalize_service_tier(service_tier)
    if st is not None:
        create_kwargs["service_tier"] = st
    if max_tool_calls is not None:
        create_kwargs["max_tool_calls"] = max_tool_calls
    if reasoning_effort:
        create_kwargs["reasoning"] = {"effort": reasoning_effort}
    if prompt_cache:
        h = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()[:12]
        create_kwargs["prompt_cache_key"] = f"manuav:{model}:{h}"
        if prompt_cache_retention:
            create_kwargs["prompt_cache_retention"] = prompt_cache_retention

    call_client = client
    if timeout_seconds is not None and hasattr(client, "with_options"):
        call_client = client.with_options(timeout=float(timeout_seconds))

    max_retries = int(flex_max_retries) if flex_max_retries is not None else 0
    fallback = bool(flex_fallback_to_auto) if flex_fallback_to_auto is not None else False

    retry_meta: Dict[str, Any] = {
        "service_tier_requested": (st or "auto"),
        "service_tier_used": (st or "auto"),
        "attempts": 0,
        "retries": 0,
        "sleep_seconds_total": 0.0,
        "fallback_used": False,
    }

    for attempt in range(max_retries + 1):
        try:
            retry_meta["attempts"] += 1
            resp = call_client.responses.create(**create_kwargs)
            break
        except Exception as e:  # pragma: no cover
            # Only retry flex-related transient errors; otherwise raise.
            if st != "flex":
                raise
            msg = str(e).lower()
            status = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
            retryable = (status in (500, 502, 503, 504, 429)) or ("rate limit" in msg) or ("resource unavailable" in msg)
            if not retryable:
                raise

            if attempt >= max_retries:
                if fallback:
                    create_kwargs.pop("service_tier", None)
                    retry_meta["fallback_used"] = True
                    retry_meta["service_tier_used"] = "auto"
                    retry_meta["attempts"] += 1
                    resp = call_client.responses.create(**create_kwargs)
                    break
                raise

            retry_meta["retries"] += 1
            base = 1.0
            delay = min(60.0, base * (2**attempt))
            delay = delay * (0.8 + 0.4 * random.random())
            retry_meta["sleep_seconds_total"] = float(retry_meta["sleep_seconds_total"]) + float(delay)
            time.sleep(delay)

    text = _extract_json_text(resp)
    result = json.loads(text)
    if isinstance(result, dict) and isinstance(result.get("reasoning"), str):
        result["reasoning"] = _sanitize_reasoning(result["reasoning"])
    ws_stats = _web_search_call_debug(resp)
    ws_stats["flex"] = retry_meta
    return result, getattr(resp, "usage", None), ws_stats

