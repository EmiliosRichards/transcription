# Dexter v2 (Fixed Taxonomy) — End-to-end Usage

This folder is a **production-shaped** Dexter pipeline:

- Instead of AI inventing unlimited categories, we use a **fixed list of categories** (GK + DM) from your Excel workbook.
- The model’s job becomes: **pick the best matching category from the list** (plus `Other/Unclear`) and provide an evidence quote.

## What you need first

- **Postgres** connection string in `$env:DATABASE_URL`
- **OpenAI** API key in `$env:OPENAI_API_KEY`
- Your taxonomy Excel file:
  - `new_folder\GK_DM_Kategorien und Kundenzitate.xlsx`

Recommended: create a local `.env` file for secrets (do not commit it). Example:

```env
DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/dbname
DIALFIRE_DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5434/dialfire
OPENAI_API_KEY=sk-...
DEXTER_V2_MODEL=gpt-4o-mini
```

All scripts in this folder auto-load `.env` (if present) via `python-dotenv`.

### Optional (recommended): skip “success” contacts using Dialfire reporting DB

If you provide `DIALFIRE_DATABASE_URL`, the exporter can filter out contacts whose **latest** `transactions_status` is `success`
(and keep only `open`/`declined`), based on `public.agent_data_v3` (default).

Typical setup is an SSH tunnel that exposes the remote Dialfire Postgres as a local port:

```powershell
# Keep this running in a separate terminal
ssh -L 5434:localhost:5432 root@185.216.75.247
```

Then set:

```env
DIALFIRE_DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5434/dialfire
```

## Folder layout per run

Each run goes into a new run folder (recommended):

- `runs\<run_id>\inputs\` (exported calls)
- `runs\<run_id>\taxonomy\` (frozen categories used for this run)
- `runs\<run_id>\outputs\` (classifications + follow-up lists + pitch drafts)
- `runs\<run_id>\reports\` (QA and summary)

## Step-by-step (PowerShell)

```powershell
# 0) Pick a run folder
$run = "dexter_v2_fixed_taxonomy\runs\2026-02-05_run1"

# 1) Extract fixed categories from the Excel into JSON (frozen into the run folder)
python dexter_v2_fixed_taxonomy\scripts\00_extract_categories_from_excel.py `
  --xlsx "new_folder\GK_DM_Kategorien und Kundenzitate.xlsx" `
  --out "$run\taxonomy\categories.json"

# 2) Export the latest Dexter calls from Postgres -> grouped JSONL input
#    (This replaces the old “run SQL in DBeaver and save CSV” step.)
python dexter_v2_fixed_taxonomy\scripts\01_export_calls_from_db.py `
  --db-url "$env:DATABASE_URL" `
  --scope "a.b2_object_key like 'dexter/audio/%'" `
  --group-by phone_campaign `
  --only-completed `
  --outcome-filter not_success `
  --out-flat "$run\inputs\calls_flat.csv" `
  --out-grouped "$run\inputs\calls_grouped.jsonl"

# 3) Classify each journey into ONE of the fixed categories (GK or DM) + extract system-in-use
python dexter_v2_fixed_taxonomy\scripts\02_classify_journeys.py `
  --in "$run\inputs\calls_grouped.jsonl" `
  --taxonomy "$run\taxonomy\categories.json" `
  --out-jsonl "$run\outputs\journey_classifications.jsonl" `
  --out-csv "$run\outputs\journey_classifications.csv"

# Optional: summarize results (category distribution, unknown rates)
python dexter_v2_fixed_taxonomy\scripts\05_summarize_results.py `
  --in "$run\outputs\journey_classifications.csv" `
  --out "$run\reports\summary.json"

# 4) Produce follow-up lists (Zentrale + unknown system)
python dexter_v2_fixed_taxonomy\scripts\03_export_followup_lists.py `
  --in "$run\outputs\journey_classifications.csv" `
  --outdir "$run\outputs"

# 5) Generate pitch drafts (placeholder templates for now)
python dexter_v2_fixed_taxonomy\scripts\04_generate_pitch_drafts.py `
  --in "$run\outputs\journey_classifications.csv" `
  --templates "dexter_v2_fixed_taxonomy\taxonomy\pitch_templates_placeholder.csv" `
  --out "$run\outputs\pitch_drafts.csv"
```

## Key outputs you’ll open in Excel

- **`journey_classifications.csv`**: one row per phone+campaign journey with:
  - GK/DM detected
  - category chosen (from your fixed list)
  - evidence quote
  - system-in-use extraction
- **`zentrale_followup.csv`**: journeys where “Zentrale/Hauptstelle” is the reason bucket
- **`system_unknown_followup.csv`**: journeys where “system currently used” is still unknown
- **`pitch_drafts.csv`**: placeholder follow-up pitches per journey (templates can be filled later)

