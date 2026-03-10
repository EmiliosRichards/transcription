## Pipeline compatibility notes (read before porting)

### Goal
Port evaluator + sales pitch improvements **without breaking existing UI/backend wiring**.

### What changed in outputs (additive)
The evaluator output now includes additional keys beyond the original v1 bucket:
- `positives`: list of strings
- `concerns`: list of strings
- structured attributes / flags (e.g., `is_saas_software`, size/innovation indicator text)

These keys are **additive**. Existing callers can keep using:
- `manuav_fit_score`
- `confidence`
- `reasoning`

### How to avoid breaking clients
- If your UI/API client strictly validates JSON keys:
  - Update its type/schema to allow the new keys, OR
  - Ignore unknown keys (recommended).
- If you have a strict Pydantic response model, change it to:
  - `Dict[str, Any]` for `result`, or
  - Explicitly include the new keys.

### Sales pitch pipeline dependencies
The pitch pipeline expects:
- a company URL
- (optionally) a company name
- a German description summary (if not provided, it will generate one)

Optional but recommended inputs (if available from evaluator):
- evaluator `positives` and `concerns`
- evaluator structured flags / fit attributes

The pitch pipeline is designed so these inputs are **optional**; you can pass empty lists/dicts without breaking.

### Explicit exclusions for the separate evaluator repo
When porting this bucket to the other repo:
- Do NOT add “company visited Manuav website” context.
- Do NOT increase max tool calls.
- Do NOT alter second-query behavior (keep the repo’s existing settings/logic).

