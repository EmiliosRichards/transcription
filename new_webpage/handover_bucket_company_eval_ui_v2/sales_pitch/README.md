## Sales pitch handover (v2) — quickstart

### What this is
This folder contains a **portable** implementation of the sales pitch pipeline:

1) Summarize company from URL (German, web search)
2) Extract attributes (includes “who we can call” fields)
3) Match a golden partner (audience-first matching)
4) Generate a German phone pitch (match + no-match templates)

### Files you will most likely vendor
- `prompts/*`
- `python/pitch_engine.py`
- `python/app_fastapi.py` (optional, if you want a standalone service)

---

## Local run (optional FastAPI wrapper)
From `sales_pitch/python/`:

1) Create venv + install deps

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

2) Create `.env`

```powershell
Copy-Item .env.example .env
```

3) Edit `.env` and set:
- `OPENAI_API_KEY=...`
- `GOLDEN_PARTNERS_CSV=...` (path to `kgs_001_ER47_20250626.csv`)

4) Run

```powershell
python -m uvicorn app_fastapi:app --reload --port 8002
```

5) Test

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8002/pitch" -ContentType "application/json" -Body (@{
  url = "https://example.com"
  company_name = ""
  description = $null
  eval_positives = @()
  eval_concerns = @()
  fit_attributes = @{}
} | ConvertTo-Json -Depth 10)
```

