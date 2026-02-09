import argparse
import json
import os
import sys

from dotenv import load_dotenv

from manuav_eval import evaluate_company_with_usage_and_web_search_artifacts
from manuav_eval.costing import compute_cost_usd, compute_web_search_tool_cost_usd, pricing_from_env, web_search_pricing_from_env


def _truthy(s: str | None) -> bool:
    return (s or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def main() -> int:
    # Local dev convenience; prod should inject env vars.
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        load_dotenv(override=False)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(description="Single-call Manuav company evaluator (URL -> score).")
    p.add_argument("url", help="Company website URL (e.g., https://example.com)")
    p.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"))
    p.add_argument("--rubric-file", default=os.environ.get("MANUAV_RUBRIC_FILE") or None)
    p.add_argument("--max-tool-calls", type=int, default=int(os.environ["MANUAV_MAX_TOOL_CALLS"]) if os.environ.get("MANUAV_MAX_TOOL_CALLS") else None)
    p.add_argument("--service-tier", default=os.environ.get("MANUAV_SERVICE_TIER", "auto"))
    p.add_argument("--timeout-seconds", type=float, default=float(os.environ["MANUAV_OPENAI_TIMEOUT_SECONDS"]) if os.environ.get("MANUAV_OPENAI_TIMEOUT_SECONDS") else None)
    p.add_argument("--flex-max-retries", type=int, default=int(os.environ.get("MANUAV_FLEX_MAX_RETRIES", "5") or 5))
    p.add_argument("--flex-fallback-to-auto", action="store_true", default=_truthy(os.environ.get("MANUAV_FLEX_FALLBACK_TO_AUTO")))
    p.add_argument("--prompt-cache", action="store_true", default=_truthy(os.environ.get("MANUAV_PROMPT_CACHE")))
    p.add_argument("--prompt-cache-retention", default=os.environ.get("MANUAV_PROMPT_CACHE_RETENTION") or None)
    p.add_argument("--reasoning-effort", default=os.environ.get("MANUAV_REASONING_EFFORT") or None)
    p.add_argument("--second-query-on-uncertainty", action="store_true", default=_truthy(os.environ.get("MANUAV_SECOND_QUERY_ON_UNCERTAINTY")))
    p.add_argument("--no-cost", action="store_true", help="Do not print estimated cost to stderr.")
    args = p.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        print("Missing OPENAI_API_KEY env var.", file=sys.stderr)
        return 2

    # Flex can be slower; default to a larger timeout if not set explicitly.
    timeout_seconds = args.timeout_seconds
    if timeout_seconds is None and (args.service_tier or "").strip().lower() == "flex":
        timeout_seconds = 900.0

    result, usage, web_search_calls, citations = evaluate_company_with_usage_and_web_search_artifacts(
        args.url,
        args.model,
        rubric_file=args.rubric_file,
        max_tool_calls=args.max_tool_calls,
        reasoning_effort=args.reasoning_effort,
        prompt_cache=args.prompt_cache,
        prompt_cache_retention=args.prompt_cache_retention,
        service_tier=args.service_tier,
        timeout_seconds=timeout_seconds,
        flex_max_retries=args.flex_max_retries,
        flex_fallback_to_auto=args.flex_fallback_to_auto,
        second_query_on_uncertainty=bool(args.second_query_on_uncertainty),
    )

    if not args.no_cost:
        pricing = pricing_from_env(os.environ)
        tool_pricing = web_search_pricing_from_env(os.environ)
        token_cost_raw = compute_cost_usd(usage, pricing)
        flex_discount = float(os.environ.get("MANUAV_FLEX_TOKEN_DISCOUNT", "0.5") or 0.5)
        token_cost = (token_cost_raw * flex_discount) if (args.service_tier or "").strip().lower() == "flex" else token_cost_raw
        web_search_cost = compute_web_search_tool_cost_usd(web_search_calls, tool_pricing)
        total = token_cost + web_search_cost
        cached = int(getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0)
        print(
            f"Estimated cost_usd={total:.6f} (service_tier={args.service_tier}, tokens={token_cost:.6f}, web_search_calls={web_search_calls}, web_search_tool_cost={web_search_cost:.6f}, input={int(usage.input_tokens)}, cached={cached}, output={int(usage.output_tokens)})",
            file=sys.stderr,
        )

    # Keep strict JSON output on stdout (for scripting).
    print(json.dumps(result, indent=2, ensure_ascii=False))
    # Citations are optional; print to stderr to avoid polluting stdout JSON contract.
    if citations:
        print(f"url_citations={json.dumps(citations, ensure_ascii=False)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

