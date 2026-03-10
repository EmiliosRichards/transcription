## Evaluator handover (v2) — how to apply to the other evaluator repo

### What this is
This `python/` folder contains the **updated evaluator engine** files you should vendor into the separate evaluator repo that currently uses the v1 bucket (`handover_bucket_company_eval_ui`).

### What to copy (recommended)
Replace the corresponding files in the other repo with:
- `manuav_eval/evaluator.py`
- `manuav_eval/schema.py`
- `rubrics/manuav_rubric_v4_en.md`

You can keep the rest of the other repo’s service code (FastAPI wrapper, costing, env vars, etc.) unchanged.

### What you will get
- German `reasoning` + `positives` + `concerns`
- “Opportunity wedge” scoring lens (mixed B2C/B2B is not penalized if any credible B2B wedge exists)
- Structured attributes/flags in the JSON output
- Domain-anchored first web search query to reduce lookalike mistakes

### What you will NOT get (by design)
- No “company visited Manuav website” context.
- No change to your default tool-call budget behavior.
- No change required to second-query behavior/settings.

