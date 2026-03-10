## Sales pitch updates (matching + pitch generation)

### Scope
This section is ONLY about the **sales pitch system** (attribute extraction → partner matching → pitch writing).
It is separated from evaluator changes so the two repos/systems don’t get confused.

---

## Summary of changes

### 1) Attribute extraction now includes “who we can call”
We added two fields that reflect what actually drives outreach:
- `callable_account_types`: the account types you’d build contact lists from
- `callable_buyer_roles`: the roles you’d call

This makes downstream matching less “industry keyword” based and more “contact-list / buyer persona” based.

### 2) Partner matching is now buyer-audience first (weighted)
The matching prompt now explicitly weights:
- **~80%**: callable target audience / buyer persona overlap (who we can call)
- **~15%**: product/offer + sales motion similarity
- **~5%**: everything else (flags/size/innovation)

It also supports:
- `match_score`: High / Medium / Low
- `No suitable match found` is allowed when no credible anchor exists

### 3) Evaluator positives/concerns can be injected (optional)
If your pipeline already has evaluator `positives` / `concerns`, you can pass them into partner matching and pitch generation.
If not, pass empty lists — it still works.

### 4) The pitch templates were tightened for clarity (“we” = Manuav)
Pitch prompts are designed so:
- “we / wir” always refers to **Manuav**
- the matched partner is described in third person (to avoid confusion)

---

## Files to port (drop-in)
From this bucket:
- `sales_pitch/prompts/attribute_extractor_prompt.txt`
- `sales_pitch/prompts/german_partner_matching_prompt.txt`
- `sales_pitch/prompts/german_sales_pitch_generation_prompt.txt`
- `sales_pitch/prompts/german_sales_pitch_generation_prompt_no_match.txt`
- `sales_pitch/python/pitch_engine.py` (portable pipeline)
- `sales_pitch/python/app_fastapi.py` (optional API wrapper)

---

## How the new end-to-end flow works (Evaluator → Sales pitch)

### Step 1: Evaluator (separate system)
Call the evaluator and capture (at minimum):
- `input_url`, `company_name`, `manuav_fit_score`, `confidence`, `reasoning`

Optional-but-useful (new in v2):
- `positives` (list of strings, German)
- `concerns` (list of strings, German)
- structured flags/attributes (you can pass these through as a dict)

### Step 2: Pitch pipeline input (what you pass in)
The pitch pipeline takes:
- `url`
- `company_name` (optional)
- `description` (optional; if missing it will create one via web-search summary)
- `eval_positives` / `eval_concerns` (optional; pass empty lists if you don’t have them)
- `fit_attributes` (optional; pass `{}` if you don’t have them)

### Step 3: Pitch pipeline internal steps
Implemented in `sales_pitch/python/pitch_engine.py`:
- **Summarize** the company from URL (German) if `description` not provided
- **Extract attributes** from the German description using `sales_pitch/prompts/attribute_extractor_prompt.txt`
  - includes `callable_account_types` and `callable_buyer_roles`
- **Load golden partners** from CSV and render compact summaries (so the matcher can scan all partners)
- **Match partner** using `sales_pitch/prompts/german_partner_matching_prompt.txt`
  - weighted primarily by callable audience overlap (who we can call)
  - can return `No suitable match found`
- **Generate pitch**
  - If matched: `sales_pitch/prompts/german_sales_pitch_generation_prompt.txt` (includes `{avg_leads_per_day}`)
  - If no match: `sales_pitch/prompts/german_sales_pitch_generation_prompt_no_match.txt` (no numbers, no case study)

### Step 4: Output shape (what the UI expects)
The optional FastAPI wrapper `sales_pitch/python/app_fastapi.py` returns:
- `matched_partner_name`
- `sales_pitch` (filled)
- `sales_pitch_template` (for debugging)
- `match_reasoning` (list of strings)
- `avg_leads_per_day` (only if matched partner exists)

