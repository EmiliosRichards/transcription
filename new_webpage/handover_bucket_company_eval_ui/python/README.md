## Python service (FastAPI) — local run

### Install

```bash
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
```

### Configure

```bash
copy .env.example .env
```

Set at least:
- `OPENAI_API_KEY=...`

Recommended cost guardrail:
- `MANUAV_MAX_TOOL_CALLS=2`

### Run

```bash
python -m uvicorn app_fastapi:app --reload --port 8001
```

### Test

```bash
curl -X POST http://127.0.0.1:8001/evaluate -H "Content-Type: application/json" -d "{\"url\":\"https://example.com\"}"
```

