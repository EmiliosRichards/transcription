## Evaluator updates (v1 bucket → this repo’s current evaluator behavior)

### Scope of this doc
This section describes what changed in the **company evaluator system** compared to the original handover bucket:
`new_webpage/handover_bucket_company_eval_ui`.

It also explains how to port the changes into the separate evaluator repo safely.

---

## Summary of changes (plain English)

### 1) Output contract is now structured (still JSON, but richer)
**Before (v1 bucket)**:
- Output schema was:
  - `input_url`, `company_name`, `manuav_fit_score`, `confidence`, `reasoning`

**Now (this repo)**:
- Output schema includes **additional keys**:
  - `positives` (list)
  - `concerns` (list)
  - structured attributes/flags (size/innovation text + boolean flags like SaaS/AI/complexity)

Why:
- The UI can display “why good” and “why risky / open questions” clearly.
- Sales pitch + partner matching can reuse evaluator signals (optional).

### 2) Language + formatting are explicitly controlled
**Before**:
- Reasoning language was not pinned; formatting could drift.

**Now**:
- `reasoning`, `positives`, `concerns` are required in **German**.
- `reasoning` is a short 1–2 sentence summary.
- `positives` / `concerns` are short bullet-like strings.

### 3) Mixed B2C/B2B is no longer treated as “bad”
This is a key logic change.

**Before**:
- “Fundamentally B2C” was treated as a near hard fail.

**Now**:
- The evaluator uses an **opportunity wedge** lens:
  - Manuav only needs **any credible B2B wedge** (reachable buyer persona + plausible economics + repeatable motion).
  - Mixed B2C/B2B should **not** be penalized for being mixed.
  - Uncertainty should show up as **lower confidence** + open questions in `concerns`.

✅ This mixed B2C/B2B logic is included in this update bucket in BOTH places that matter:
- **Rubric**: `python/rubrics/manuav_rubric_v4_en.md` (B2B clarity section)
- **Evaluator prompt**: `python/manuav_eval/evaluator.py` (Scoring lens block)

### 4) Research discipline is more explicit
Still one web-search call by default, but:
- The prompt emphasizes **domain anchoring** to avoid lookalike companies.
- The reasoning is sanitized to remove URLs and keep output compact.

### 5) Second query: no change required in the separate evaluator repo
The separate evaluator repo can keep its existing second-query logic/settings.
This v2 bucket does **not** require changing second-query behavior.

---

## Files to port (drop-in)
Copy these into the other repo (they’re placed in the same relative paths inside this bucket):
- `python/manuav_eval/evaluator.py`
- `python/manuav_eval/schema.py`
- `python/rubrics/manuav_rubric_v4_en.md`

---

## What to NOT port (per request)
- Do not add any “visited Manuav website” context into the evaluator prompt.
- Do not increase tool-call budgets (keep your existing defaults).
- Do not change second-query behavior.

