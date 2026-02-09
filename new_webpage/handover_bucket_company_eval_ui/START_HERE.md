## Start Here — Company Evaluator UI Handover Bucket

### Purpose
This folder is a **handover “bucket”** you can copy into another repo where you are building a **webpage/UI**.
The UI flow is:

- User pastes a **company website URL**
- Backend runs the **Manuav company evaluator** (single model call + web search)
- UI displays:
  - **Manuav Fit score (0–10)**
  - **confidence** (low/medium/high)
  - **short reasoning**

Important: **API keys must remain server-side**. The browser should call your backend, not OpenAI/Gemini directly.

This bucket is designed to coexist with a **second bucket** from another project that generates **sales pitches**.
Recommended UI orchestration:

- Step 1: call **Company Evaluation** (this bucket) → get score + reasoning + company_name
- Step 2: call **Sales Pitch Generator** (other bucket) using the same URL and/or the evaluation output

### What’s included
- **Docs**
  - `FILES_INDEX.md`: what each file is for
  - `ENV_VARS.md`: env vars to copy/port into the web repo runtime
  - `API_CONTRACT.md`: suggested backend API contract for the webpage to call
  - `SECURITY_COST_OPS.md`: key handling + cost guardrails + operational notes
- **Portable Python implementation (recommended integration path)**
  - `python/app_fastapi.py`: small FastAPI service exposing `POST /evaluate`
  - `python/manuav_eval/*`: the evaluator “engine” copied from this repo
  - `python/rubrics/manuav_rubric_v4_en.md`: the rubric used by the evaluator
  - `python/scripts/*`: replicas of the CLI scripts used in this repo (for reference/debug)

### Recommended integration approach for the webpage
You have two good options. In practice, **Option A** is simplest for a web UI.

#### Option A (recommended): run the evaluator as a small internal HTTP service
- Run `python/app_fastapi.py` as a backend service (same deployment as your web app, or as a sidecar).
- Your webpage calls it via `fetch('/api/company-eval')` (or directly `http://.../evaluate` internally).

Pros:
- Clean separation between UI (Node/Next/etc.) and evaluation logic (Python).
- Keeps `OPENAI_API_KEY` on the server.
- Easy to add observability (costs, tool calls, retries).

#### Option B: embed Python directly into an existing Python backend
If your web project already has a Python backend:
- Copy `python/manuav_eval/` + `python/rubrics/`
- Import `manuav_eval.evaluate_company_with_usage_and_web_search_artifacts(...)`
- Return JSON to the UI

### Quickstart (local dev)
From `handover_bucket_company_eval_ui/python/`:

1) Create venv + install deps

```bash
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
```

2) Create `.env`

```bash
copy .env.example .env
```

3) Edit `.env` and set at least `OPENAI_API_KEY=...`

4) Run the API

```bash
python -m uvicorn app_fastapi:app --reload --port 8001
```

5) Test

```bash
curl -X POST http://127.0.0.1:8001/evaluate -H "Content-Type: application/json" -d "{\"url\":\"https://example.com\"}"
```

### What the other agent should implement in the web repo
- A new page with:
  - URL input + submit
  - loading / error states
  - display of `manuav_fit_score`, `confidence`, `reasoning`
- A server-side route that calls **this evaluator** (either via HTTP to the FastAPI service, or by importing Python directly).
- Later: a second call to the **sales pitch bucket** and render those results alongside the evaluation.

