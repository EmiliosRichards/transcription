## Security, cost, and ops notes (for the web/UI integration)

### Key security (non-negotiable)
- **Never put `OPENAI_API_KEY` or `GEMINI_API_KEY` in the browser.**
- The webpage must call a **server-side** endpoint that runs the evaluator.
- Don’t commit `.env` files with real secrets.

### Cost controls (what actually drives spend)
OpenAI runs here use:
- **1 model call** (plus an optional retry in some configurations)
- **web search tool calls** inside that call (bounded by `max_tool_calls`)

Recommended production guardrails:
- `MANUAV_MAX_TOOL_CALLS=2` (keeps search behavior bounded and predictable)
- `MANUAV_SECOND_QUERY_ON_UNCERTAINTY=1` (allows *one* extra query only for disambiguation)
- Avoid always-on retry unless needed:
  - `MANUAV_RETRY_DISAMBIGUATION_ON_LOW_CONFIDENCE=1` only if you accept a second call when confidence is low

### Web search billing semantics (OpenAI)
This repo’s evaluator code treats **query-type web searches** as the **billable** unit (dashboard “Web Searches” appears to count those).

- In the original scripts:
  - `web_search_calls` = **billable query count** (best estimate)
  - debug breakdown: `web_search_calls_query/open/unknown`
  - `web_search_tool_calls_total` = total tool invocations (query + open/visit)

### Reliability knobs
- Flex mode can be cheaper on tokens but slower and may occasionally return transient `429 Resource Unavailable`.
  - Use `MANUAV_OPENAI_TIMEOUT_SECONDS=900` and retries (`MANUAV_FLEX_MAX_RETRIES`) if enabling Flex.

### Observability recommended for UI
For the web UI, you’ll typically log/store (server-side):
- input URL
- output score + confidence
- web_search_calls
- token usage + estimated costs (optional)
- latency / duration

### Data handling
The evaluator:
- performs external web research via provider tooling
- produces a short reasoning string without URLs (URLs may be available via citations/annotations)

If you display citations/sources:
- treat them as best-effort and not exhaustive
- they may include third-party URLs; consider safe-link handling in UI

