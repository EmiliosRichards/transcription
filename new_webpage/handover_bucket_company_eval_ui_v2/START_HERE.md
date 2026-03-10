## Start Here — Company Evaluator + Sales Pitch Update Bucket (v2)

### Purpose
This folder is a **handover “bucket”** you can copy into the *separate evaluator repo* that was originally set up using:
`new_webpage/handover_bucket_company_eval_ui`.

It documents and packages the **changes we made in this repo** so you can port them safely **without breaking the end-to-end pipeline**.

This bucket is intentionally split into two independent parts:

- **Part A — Evaluator system updates** (fit score + reasoning output contract)
- **Part B — Sales pitch system updates** (attribute extraction + partner matching + pitch prompts)

### Important exclusions (per request)
When porting to the separate evaluator repo, **do NOT add** the following behaviors:

- **No “inbound intent” context** (do not tell the LLM “this company visited Manuav’s website”).
- **No increase in web-search usage** (keep the default tool-call budget behavior of the other repo).
- **No “second query” behavior changes** for the separate evaluator repo (keep its existing second-query logic).

This bucket still contains the other improvements (output schema structure, wedge logic, German format, etc.).

---

## What changed conceptually (one paragraph)
We changed the evaluator from “mostly B2B = good / mostly B2C = bad” into an **opportunity-wedge evaluator**:
Manuav only needs a **credible B2B wedge** (even if it’s a minority segment) with a reachable buyer persona and plausible economics.
Mixed B2C/B2B should **not** be penalized for being mixed; instead, uncertainty should be expressed via **confidence** and **open concerns**.

---

## Where to start

### If you only want evaluator updates
Read:
- `EVALUATOR_UPDATES.md`

Then vendor these files into the other repo (paths inside this bucket are “drop-in”):
- `python/manuav_eval/evaluator.py`
- `python/manuav_eval/schema.py`
- `python/rubrics/manuav_rubric_v4_en.md`

### If you also want sales pitch updates
Read:
- `SALES_PITCH_UPDATES.md`

Then vendor:
- `sales_pitch/prompts/*`
- `sales_pitch/python/*` (portable pitch engine + optional FastAPI wrapper)

---

## Pipeline safety (do not break end-to-end)
Before swapping anything in the other repo, read:
- `PIPELINE_COMPATIBILITY.md`

Key point: most changes are **additive** (extra keys like `positives`, `concerns`, `fit_attributes`), so existing clients can keep using `reasoning` and ignore the extras.

