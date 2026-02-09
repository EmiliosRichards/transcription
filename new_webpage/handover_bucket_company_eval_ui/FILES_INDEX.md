## Files index — what’s in this bucket

### Top-level docs
- **`START_HERE.md`**
  - Primary entrypoint for the UI/web agent.
  - Explains purpose, recommended integration approach, and quickstart.
- **`FILES_INDEX.md`** (this file)
  - Short explanation of each file/folder.
- **`ENV_VARS.md`**
  - Which environment variables must be transferred to the web project runtime.
  - Safe defaults + cost guardrails.
- **`API_CONTRACT.md`**
  - Suggested HTTP contract between the webpage and the evaluator backend.
- **`SECURITY_COST_OPS.md`**
  - Key handling, cost semantics (web-search billing), and operational notes.

### Portable Python implementation (copyable)
Folder: **`python/`**

- **`python/app_fastapi.py`**
  - Minimal FastAPI app exposing `POST /evaluate` for a single company URL.
  - Returns evaluator result + optional usage/cost metadata.
- **`python/requirements.txt`**
  - Python deps for the service and evaluator.
- **`python/.env.example`**
  - Example env file (no secrets). Copy to `.env` and fill values.
- **`python/manuav_eval/`**
  - The evaluator engine (copied from this repo).
  - Key file: `manuav_eval/evaluator.py`
- **`python/rubrics/manuav_rubric_v4_en.md`**
  - Rubric used by default for the Manuav Fit score.
- **`python/scripts/`**
  - Replicas of CLI scripts used in this repo (reference/debug).
  - Not required for the webpage, but useful for troubleshooting.

