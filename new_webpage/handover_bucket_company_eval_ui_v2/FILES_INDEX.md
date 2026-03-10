## Files index — what’s in this v2 update bucket

### Top-level docs
- **`START_HERE.md`**
  - What this bucket is for + what to port.
- **`FILES_INDEX.md`** (this file)
  - Short explanation of each file/folder.
- **`EVALUATOR_UPDATES.md`**
  - Detailed breakdown of evaluator changes vs the original setup.
- **`SALES_PITCH_UPDATES.md`**
  - Detailed breakdown of the pitch/matching changes and prompt updates.
- **`PIPELINE_COMPATIBILITY.md`**
  - How to port safely without breaking end-to-end behavior.

### Evaluator — portable Python files (drop-in)
Folder: `python/`

- `python/manuav_eval/evaluator.py`
  - Updated evaluator engine (OpenAI Responses + web_search tool).
  - **Does NOT** include “visited Manuav website” context.
  - **Does NOT** change second-query behavior beyond what the original bucket already does.
- `python/manuav_eval/schema.py`
  - Strict JSON schema (now includes `positives`, `concerns`, and structured flags/attributes).
- `python/manuav_eval/rubric_loader.py`, `python/manuav_eval/__init__.py`
  - Small helpers for loading rubric text + exports.
- `python/rubrics/manuav_rubric_v4_en.md`
  - Updated rubric: mixed B2C/B2B is not penalized if there is any credible B2B wedge.

### Sales pitch — prompts + portable code
Folder: `sales_pitch/`

- `sales_pitch/prompts/attribute_extractor_prompt.txt`
  - Updated: `callable_account_types` + `callable_buyer_roles` and “any B2B wedge = potential”.
- `sales_pitch/prompts/german_partner_matching_prompt.txt`
  - Updated: matching weighted heavily toward “who we can call” (buyer persona/contact list overlap).
- `sales_pitch/prompts/german_sales_pitch_generation_prompt.txt`
- `sales_pitch/prompts/german_sales_pitch_generation_prompt_no_match.txt`
- `sales_pitch/python/pitch_engine.py`
  - Self-contained pitch pipeline (summarize → extract attrs → load partners → match → pitch).
- `sales_pitch/python/app_fastapi.py`
  - Optional small FastAPI wrapper exposing `POST /pitch`.

