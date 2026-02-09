## Suggested API contract for the webpage

This bucket ships a Python FastAPI service that exposes `POST /evaluate`.
Your web project can either:

- call it directly (internal HTTP), or
- implement a web-app route (e.g. `/api/company-eval`) that proxies to it.

### Endpoint: `POST /evaluate`

#### Request body
Minimum:

```json
{
  "url": "https://company.com"
}
```

Optional overrides (advanced; usually you’ll hide these behind admin config):

```json
{
  "url": "https://company.com",
  "options": {
    "model": "gpt-4.1-mini",
    "max_tool_calls": 2,
    "service_tier": "flex",
    "second_query_on_uncertainty": true,
    "prompt_cache": true,
    "prompt_cache_retention": "24h",
    "reasoning_effort": "low",
    "rubric_file": null
  }
}
```

Notes:
- `url` may be provided without scheme; the evaluator normalizes it to `https://...`.
- `rubric_file`: if null/unset, the service uses the bucket’s included rubric.

#### Response body
The evaluator result is always in `result` and matches the strict schema:

- `input_url` (string)
- `company_name` (string)
- `manuav_fit_score` (0–10)
- `confidence` (`low|medium|high`)
- `reasoning` (short, URL-free)

The service also returns `meta` for UI/debug/cost display.

```json
{
  "result": {
    "input_url": "https://company.com",
    "company_name": "Company GmbH",
    "manuav_fit_score": 7.0,
    "confidence": "medium",
    "reasoning": "Clear B2B offer with DACH signals and plausible mid-market ACVs; evidence for DACH case studies is partial. Category looks competitive but still pitchable; onboarding capacity seems productized enough for scale."
  },
  "meta": {
    "provider": "openai",
    "model": "gpt-4.1-mini",
    "rubric_file": "C:/.../rubrics/manuav_rubric_v4_en.md",
    "web_search_calls": 1,
    "usage": {
      "input_tokens": 1234,
      "cached_input_tokens": 0,
      "output_tokens": 210,
      "reasoning_tokens": 0,
      "total_tokens": 1444
    },
    "estimated_cost_usd": {
      "token_cost_usd": 0.000000,
      "web_search_tool_cost_usd": 0.010000,
      "total_cost_usd": 0.010000
    },
    "url_citations": [
      { "url": "https://company.com/pricing", "title": "Pricing" }
    ]
  }
}
```

### Error semantics (recommended for UI)
- **400**: invalid URL payload (empty/too long)
- **502**: upstream/provider failure (OpenAI/Gemini error)
- **500**: unexpected server error

### Frontend TypeScript types (example)

```ts
export type ManuavConfidence = "low" | "medium" | "high";

export interface ManuavEvalResult {
  input_url: string;
  company_name: string;
  manuav_fit_score: number; // 0..10
  confidence: ManuavConfidence;
  reasoning: string;
}

export interface ManuavEvalMeta {
  provider: "openai" | "gemini";
  model: string;
  rubric_file: string;
  web_search_calls: number;
  usage?: {
    input_tokens: number;
    cached_input_tokens: number;
    output_tokens: number;
    reasoning_tokens: number;
    total_tokens: number;
  };
  estimated_cost_usd?: {
    token_cost_usd: number;
    web_search_tool_cost_usd: number;
    total_cost_usd: number;
  };
  url_citations?: Array<{ url: string; title: string }>;
}

export interface ManuavEvalResponse {
  result: ManuavEvalResult;
  meta: ManuavEvalMeta;
}
```

