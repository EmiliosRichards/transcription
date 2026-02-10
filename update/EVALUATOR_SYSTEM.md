## Current evaluator system — how it works (OpenAI + web search)

This document captures how the **current evaluator** works in this repo so it can be reused in a webpage/UI project.

Primary code:
- Engine: `manuav_eval/evaluator.py`
- Output contract: `manuav_eval/schema.py`
- Rubric: `rubrics/manuav_rubric_v4_en.md`

---

## What it does (one sentence)
Given a **company website URL**, the system runs **one** OpenAI Responses API call with **Web Search enabled**, applies the **Manuav rubric**, and returns **strict JSON** containing a **Manuav Fit score (0–10)** + **confidence** + **short reasoning**.

---

## Inputs
### Required
- **Company website URL** (string)
  - If provided without scheme, the evaluator normalizes it to `https://...`.

### Optional configuration inputs (important for UI/backends)
These parameters change behavior/cost but not the output schema shape.

- **`model`**: OpenAI model name
- **`rubric_file`**: rubric path (defaults to `rubrics/manuav_rubric_v4_en.md`)
- **`max_tool_calls`**: caps web-search tool calls in the single evaluation call (cost guardrail)
- **`service_tier`**: `auto` or `flex` (Flex can be slower, may need retries)
- **`timeout_seconds`**, **Flex retries/backoff**
- **`prompt_cache`** and `prompt_cache_retention` (model-dependent)
- **`reasoning_effort`** (optional)
- **`second_query_on_uncertainty`** (soft disambiguation behavior toggle)

---

## What LLM calls we make

### Default behavior (OpenAI)
**One** call:
- `client.responses.create(...)`
- `tools=[{"type": "web_search_preview"}]`
- strict JSON schema output: `text={"format": {"type":"json_schema", ...}}`
- optional `max_tool_calls` set as a hard guardrail

### Optional “retry call” (when enabled in scripts)
Not part of the core evaluator function; implemented in runner scripts (`scripts/evaluate.py`, `scripts/evaluate_list.py`):
- If attempt 1 returns `confidence=low`, run **one extra evaluation call** with stronger disambiguation instructions.
- Costs/tool calls are aggregated across attempts (because billing happens for both).

---

## How we try to ensure we are evaluating the *correct* company
There is no deterministic “entity resolution” algorithm here; correctness is enforced by:

### 1) Domain-anchored research discipline (prompt)
The system prompt explicitly instructs the model to avoid same-name/lookalike attribution errors and to prefer identity signals tied to the provided website:
- domain consistency + links from the official site
- legal entity name + imprint/registration details
- HQ/location and language/market focus
- product/ICP/branding match
- the official LinkedIn/company page referenced by the website

If attribution is uncertain, the prompt instructs the model to either avoid relying on that source or explicitly note uncertainty and lower confidence.

### 2) Conservative scoring when evidence is missing or ambiguous
The rubric and system prompt emphasize:
- “Do not hallucinate”
- “If unknown, say so”
- “Lower confidence and be conservative”

### 3) Optional disambiguation behavior toggles
- **Second query on uncertainty** (`MANUAV_SECOND_QUERY_ON_UNCERTAINTY=1`):
  - Prompt tells the model: default to **one** query; allow exactly **one** additional disambiguation query only if the first query doesn’t identify the right entity behind the domain (parked domain, conflicting entities, etc.).
- **Retry on low confidence** (`MANUAV_RETRY_DISAMBIGUATION_ON_LOW_CONFIDENCE=1`):
  - Runner performs a second model call with explicit “two distinct searches” instructions (e.g., include `GmbH impressum`, location hints, `HRB`).

In a UI/backoffice context, the practical “correct-company” guardrails are:
- keep `max_tool_calls` small but non-zero (usually 2)
- enable second-query-on-uncertainty for sticky cases
- optionally enable retry-on-low-confidence if you can tolerate extra cost for hard cases

---

## Prompt construction (exact structure)
The evaluator constructs:

### System message
`BASE_SYSTEM_PROMPT` + `Rubric file: <path>` + full rubric markdown text

### User message
An instruction block that:
- requires web research (official site + broader web)
- optionally includes a “tool-call budget” line (if `max_tool_calls` is set)
- optionally includes extra disambiguation instructions
- instructs strict JSON-only output and reasoning length constraints
- places the **company URL at the end** (helps prompt caching by keeping earlier parts static)

For a copy of the exact base prompt text and the user prompt template, see:
- `update/prompts/openai_prompt_reference.md`

---

## Outputs

### Primary JSON output (strict schema)
The model returns **only** JSON matching `manuav_eval/schema.py`:
- `input_url` (string)
- `company_name` (string)
- `manuav_fit_score` (number 0–10)
- `confidence` (`low|medium|high`)
- `reasoning` (short, max 600 chars; URLs removed)

### Optional artifacts (used by scripts / useful for UI telemetry)
Depending on which helper you call, you can also obtain:
- **token usage** (input/output/cached/reasoning/total)
- **web_search_calls** (best-effort billable “query” count)
- **url citations** extracted from Responses API output annotations (when available)
- web-search debug breakdown (query vs open/visit)

### Post-processing applied
Even though the schema caps reasoning, models sometimes include URLs. The evaluator applies best-effort sanitization:
- strip URLs and markdown links from `reasoning`
- collapse whitespace
- enforce hard length cap (attempt to end on sentence boundary)

---

## Files duplicated for reference
- Prompt reference: `update/prompts/openai_prompt_reference.md`
- Rubric copy: `update/rubrics/manuav_rubric_v4_en.md`

