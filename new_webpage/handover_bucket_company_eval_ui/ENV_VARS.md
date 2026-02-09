## Env vars to transfer into the web project runtime

### Required (OpenAI path)
- **`OPENAI_API_KEY`**: required. Must live **server-side** only.

### Recommended defaults for predictable cost
- **`OPENAI_MODEL`**: model name (example used in this repo varies; choose what the web app will standardize on).
  - Example default in the original CLI: `gpt-4.1-mini`
- **`MANUAV_MAX_TOOL_CALLS=2`**
  - Cost guardrail: caps the total number of web-search tool invocations within the single evaluation call.
- **`MANUAV_SECOND_QUERY_ON_UNCERTAINTY=1`**
  - Soft toggle: allows a second **disambiguation** query only when the first query doesn’t identify the company behind the domain.

### Optional reliability/cost controls (OpenAI)
- **Flex (optional)**:
  - `MANUAV_SERVICE_TIER=flex`
  - `MANUAV_OPENAI_TIMEOUT_SECONDS=900`
  - `MANUAV_FLEX_MAX_RETRIES=5`
  - `MANUAV_FLEX_FALLBACK_TO_AUTO=1`
  - `MANUAV_FLEX_TOKEN_DISCOUNT=0.5` (used for **local estimation only**; billing is authoritative)

- **Prompt caching (optional, model-dependent)**:
  - `MANUAV_PROMPT_CACHE=1`
  - `MANUAV_PROMPT_CACHE_RETENTION=24h`

- **Reasoning effort (optional)**:
  - `MANUAV_REASONING_EFFORT=low` (or unset for auto)

### Optional retry (extra cost, only triggers on low confidence)
- **`MANUAV_RETRY_DISAMBIGUATION_ON_LOW_CONFIDENCE=1`**
  - If the first attempt returns `confidence=low`, runs **one** retry with stronger disambiguation instructions.
- **`MANUAV_RETRY_MAX_TOOL_CALLS=3`**
  - Tool-call budget used for the retry call.

### Rubric selection/versioning
- **`MANUAV_RUBRIC_FILE`**
  - In the original repo, default is `rubrics/manuav_rubric_v4_en.md`.
  - In this bucket’s FastAPI wrapper we set an **absolute** default to the bucket’s included rubric; you can still override via env.

### Cost estimation vars (optional; for dashboards/logging only)
These are not required for the evaluator to work; they only affect the **estimated** cost fields emitted by scripts/services.

- OpenAI token pricing (USD per 1M tokens):
  - `MANUAV_PRICE_INPUT_PER_1M`
  - `MANUAV_PRICE_CACHED_INPUT_PER_1M`
  - `MANUAV_PRICE_OUTPUT_PER_1M`
- Web search pricing:
  - `MANUAV_PRICE_WEB_SEARCH_PER_1K` (default `10.0` => $0.01 per billed query)

### Gemini (only if you enable Gemini in your web app)
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `GEMINI_PRICE_INPUT_PER_1M`
- `GEMINI_PRICE_OUTPUT_PER_1M`
- `GEMINI_PRICE_SEARCH_PER_1K`

### What NOT to transfer
- Do **not** copy `.env` files containing real keys into source control.
- Do **not** expose `OPENAI_API_KEY`/`GEMINI_API_KEY` to the browser.

