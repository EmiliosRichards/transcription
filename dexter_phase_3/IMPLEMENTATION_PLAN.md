# Dexter Phase 3 — Implementation Plan

## Pipeline Scripts

We'll create a clean new pipeline in `dexter_phase_3/` with numbered scripts (inspired by the v2 structure but simplified).

```
dexter_phase_3/
├── config/
│   ├── taxonomy.json          ← generated from Excel (categories + templates)
│   ├── referenzen.csv         ← generated from Excel (golden partners)
│   └── config.yml             ← DB connection, model, run settings
├── prompts/
│   ├── classify_journey.txt   ← system prompt for classification
│   └── generate_pitch.txt     ← system prompt for pitch generation (if needed)
├── scripts/
│   ├── 00_prepare_inputs.py   ← convert Excel → taxonomy.json + referenzen.csv
│   ├── 01_export_journeys.py  ← pull calls from DB, group by contact
│   ├── 02_classify.py         ← LLM classification into fixed taxonomy
│   ├── 03_match_reference.py  ← find nearest Dexter reference per contact
│   ├── 04_generate_pitches.py ← fill templates with dynamic fields
│   └── 05_export_final.py     ← combine everything into output CSV
├── runs/                      ← one subfolder per run (timestamped)
├── PIPELINE_OVERVIEW.md
├── IMPLEMENTATION_PLAN.md
└── PROGRESS.md
```

---

## Phase 1: Setup & Data Prep

### Task 1.1 — Convert Excel inputs to machine-readable formats
- **Script:** `00_prepare_inputs.py`
- **What:** Read both Excel files, produce:
  - `config/taxonomy.json` — structured categories with IDs, quotes, templates
  - `config/referenzen.csv` — clean CSV of reference companies (Träger, Einrichtung, Ort, PLZ, System)
- **Notes:**
  - GK sheet has 6 columns (Kategorie, 4 Kundenzitate, Antworten)
  - DM sheet has 4 columns (Kategorie, Kundenzitat 1 [multi-line], Antworten individualisiert, Generische Antwort)
  - Some DM "Antworten" contain conditional logic (e.g. "Achtung! Je nach Antwort reagieren") — preserve as-is
  - Categories marked "raus" should be flagged as `action: "exclude"`

### Task 1.2 — Set up DB connection config
- **What:** Create `config/config.yml` with:
  - DATABASE_URL (or SSH tunnel details for Contabo Postgres)
  - OPENAI_API_KEY reference (from env)
  - Model selection (default: whatever is already configured)
  - Run settings (max journeys for testing, workers, etc.)
- **Blocker:** Need Emilios to provide/confirm DB connection details
  - How to connect (direct URL vs SSH tunnel?)
  - Which tables contain the Dexter call data
  - Schema for recordings / transcriptions / contacts

---

## Phase 2: Export Journeys

### Task 2.1 — Export and group Dexter calls from DB
- **Script:** `01_export_journeys.py`
- **What:**
  - Query `media_pipeline.audio_files` + `media_pipeline.transcriptions` for Dexter calls
  - Filter: `b2_object_key LIKE 'dexter/audio/%'` (or equivalent scope)
  - Group by phone number → one journey per contact
  - For each journey: collect all calls chronologically with timestamps + transcript text
  - Include any Dialfire metadata if available (contact_id, status, etc.)
- **Output:** `runs/<run_id>/journeys.jsonl` — one JSON object per contact
- **Fields per journey:**
  ```json
  {
    "phone": "+49...",
    "campaign_name": "...",
    "num_calls": 5,
    "calls": [
      {
        "audio_id": 123,
        "started": "2025-06-15T10:00:00",
        "transcript_text": "...",
        "status": "completed"
      }
    ],
    "dialfire_contact_id": "..."
  }
  ```
- **DB schema dependency:** Need to confirm exact table/column names with Emilios

---

## Phase 3: Classification

### Task 3.1 — Build classification prompt
- **File:** `prompts/classify_journey.txt`
- **Approach:**
  - System prompt provides the full taxonomy (all GK + DM categories with example quotes)
  - User prompt provides the stitched transcript (most recent call first, capped by word count)
  - LLM returns JSON: `{ role, category_id, category_label, confidence, evidence_quote, last_call_date, reason_summary }`
- **Design:** Direct classification — no embeddings needed for ~20 categories
  - Temperature = 0 for deterministic results
  - JSON mode enforced
  - Evidence validation (check quote exists in transcript)

### Task 3.2 — Classification script
- **Script:** `02_classify.py`
- **What:**
  - Read `journeys.jsonl`
  - For each journey, build context from transcripts
  - Call LLM with classify prompt
  - Handle edge cases:
    - No transcripts → mark as "Nicht erreichbar"
    - Very short transcripts → mark as "Other/Unklar"
    - Empty/voicemail detection (reuse unreachable markers from v2)
  - Track token usage
  - Parallel processing with ThreadPoolExecutor
- **Output:** `runs/<run_id>/classifications.csv` + `.jsonl`

---

## Phase 4: Reference Matching

### Task 4.1 — Build reference matcher
- **Script:** `03_match_reference.py`
- **What:**
  - Load `referenzen.csv` (PLZ, Ort, Einrichtung, Träger, System)
  - For each classified contact, find the nearest reference facility
  - "Nearest" = geographic proximity by PLZ
    - Option A: Simple PLZ prefix matching (first 2-3 digits = same region)
    - Option B: PLZ → lat/lon lookup table for actual distance
    - Start with Option A, upgrade to B if needed
  - Also match by System if the contact's system is known (from classification)
- **Output:** Adds `ref_einrichtung`, `ref_ort`, `ref_plz`, `ref_system`, `ref_traeger` to each row
- **Phrasing:** "Die nächste Referenz, die wir nennen können, ist [Einrichtung] in [Ort]"
- **Note:** Need the contact's PLZ/city — may come from Dialfire data or need to be looked up

---

## Phase 5: Pitch Generation

### Task 5.1 — Template-based pitch generation
- **Script:** `04_generate_pitches.py`
- **What:**
  - For each classified contact, look up the response template from taxonomy.json
  - Fill in placeholders:
    - `[Datum]` / `[datum]` → date of the last (or most relevant) call
    - `[Name Heim]` → matched reference facility name
    - `[Ort in der Nähe]` → matched reference facility city
    - `[Grund]` → extracted reason/evidence from classification
    - `[mein AP]` → contact person name (if known from transcript or Dialfire)
  - For categories with `action: "exclude"` (marked "raus"), skip pitch generation
  - For DM categories: append the "Generische Antwort" follow-up
- **Decision:** Template filling might be enough (no LLM needed). But if the templates need more natural personalization, we can optionally use an LLM to smooth them.
- **Output:** `runs/<run_id>/pitches.csv`

---

## Phase 6: Final Export

### Task 6.1 — Combine into final output CSV
- **Script:** `05_export_final.py`
- **What:** Merge classifications + references + pitches into one CSV
- **Output columns:**
  | Column | Description |
  |--------|-------------|
  | phone | Contact phone number |
  | campaign_name | Dexter campaign |
  | num_calls | Total calls in journey |
  | role | GK or DM |
  | category_id | e.g. GK01, DM03 |
  | category_label | e.g. "Bereits Anbieter / System vorhanden" |
  | confidence | Classification confidence |
  | evidence_quote | German quote from transcript |
  | reason_summary | Brief reason extract |
  | last_call_date | Date of most recent call |
  | action | "pitch" or "exclude" |
  | ref_einrichtung | Matched reference facility |
  | ref_ort | Reference facility city |
  | ref_system | Reference facility's system |
  | pitch_text | Final pitch (or empty if excluded) |
  | generic_followup | DM generic follow-up text |
  | dialfire_contact_id | Dialfire reference (if available) |

---

## Open Questions / Blockers

1. **DB Connection:** How do we connect to the Contabo Postgres? SSH tunnel? Direct URL? What port?
2. **DB Schema:** Exact table names and columns for:
   - Dexter call recordings (audio_files? recordings?)
   - Transcriptions
   - Contact info (phone → PLZ/city mapping for reference matching)
   - Dialfire contact IDs
3. **Contact location:** Where do we get each contact's PLZ/city for reference matching?
   - From Dialfire data?
   - From a separate contacts table?
   - From the transcript itself (organization name → web lookup)?
4. **System detection:** Do we need to identify what system (Vivendi, Medifox, etc.) the contact uses? The DM "Technische Barrieren" template has conditional logic based on this.
5. **Which LLM model?** Use whatever is already configured (gpt-4o-mini?) — optimize later.
6. **Scale:** ~12,000 contacts. At ~$0.001/classification (mini model), that's ~$12 total. Manageable.

---

## Execution Order

```
Phase 1 ──→ Phase 2 ──→ Phase 3 ──→ Phase 4 ──→ Phase 5 ──→ Phase 6
 Setup       Export      Classify    Match Ref    Pitches     Export
 (local)     (needs DB)  (needs LLM) (local)      (local)     (local)
```

**Can start immediately:** Phase 1 (Excel conversion, prompt writing, config setup)
**Blocked on DB access:** Phase 2 onward
