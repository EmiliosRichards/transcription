# Dexter Pipeline Lineage

How we got here — the evolution of the Dexter call analysis pipeline across three phases.

## Phase A: Discovery (`dexter_analysis_pitch-regeneration/`)

**Goal:** Figure out *what categories exist* in the call data — no predefined taxonomy.

**Method:**
1. Exported ~1,200 Dexter contacts from `dexter_final_numbers_appended.csv` (random selection)
2. Queried their call recordings from the media_pipeline DB
3. LLM free-extraction: for each contact, GPT labels the outcome and reason freely (no categories given)
4. Embedded those free-text labels as vectors (OpenAI embeddings)
5. Clustered similar labels together using HDBSCAN
6. Named the clusters with LLM assistance
7. Compressed into a fixed taxonomy (top-K clusters + "Other")

**Output:** A discovered taxonomy of GK (Gatekeeper) and DM (Decision Maker) categories with example quotes. This became the basis for `Kundenzitate und Antworten 3.xlsx`.

**Key scripts:** `extract_free_labels.py` → `embed_and_save.py` → `hdbscan_pass1.py` → `name_clusters.py` → `build_limited_taxonomy.py`

**Also produced:** The reachable contact lists:
- `new_folder/reachable_gk_cluster_full_list.csv` (838 GK contacts)
- `new_folder/reachable_dm_cluster_full_list.csv` (325 DM contacts)
- These are subsets of the 1,203 contacts in `dexter_final_numbers_appended.csv`

## Phase B / v2: Fixed Taxonomy Classification (`dexter_v2_fixed_taxonomy/`)

**Goal:** Classify all contacts using the taxonomy discovered in Phase A.

**Method:**
1. Extracted categories from Excel → `categories.json`
2. Exported calls from media_pipeline DB (with optional Dialfire outcome filtering)
3. LLM classification: for each contact, classify into exactly one fixed category
4. Generated follow-up lists (Zentrale contacts, unknown systems)
5. Generated pitch drafts from templates

**Limitations:**
- Assumed two separate DBs (media + Dialfire) — now migrated to one
- No reference company matching (no "nearest Dexter customer" in pitches)
- No name extraction from transcripts
- No do-not-call detection
- Used gpt-4o-mini with a simpler prompt
- Sent calls newest-first to LLM (worse classification accuracy)
- Lots of diagnostic/preflight scripts (01b-01e, 06-08) for the two-DB setup

## Phase 3: Production Pipeline (`dexter_phase_3/`)

**Goal:** Refined production pipeline with personalised follow-up pitches.

**What changed from v2:**
- Single DB (everything on 185.216.75.247)
- Upgraded model (gpt-5.4-mini-2026-03-17)
- Much better prompt: detailed guidance on name extraction, system detection, role identification
- Chronological call order (oldest→newest) for better LLM attention on recent calls
- Contact name extraction (AP name + role + GK name) with fallback chain
- Do-not-call flag — requires 3+ rejections across separate calls (single "nein" is normal rejection)
- Real geographic distance matching (pgeocode, km-based) instead of PLZ numeric diff
- Proximity-aware pitch wording ("bei Ihnen in der Nähe" vs neutral phrasing)
- "Raus" contacts kept in CSV flagged instead of excluded
- Facility name deduplication in pitch templates ("Haus Seniorenzentrum X" → "Seniorenzentrum X")
- Optional LLM pitch enhancement step (04b) for light personalisation
- Suggested new category field for when LLM identifies a clear taxonomy gap
- Pre-filtering: success, Bestandskunde, nie_wieder_anrufen contacts excluded before processing

## Data Flow

```
dexter_final_numbers_appended.csv (1,203 contacts, random selection)
         │
         ▼
   Phase A: Discovery
   (free labels → embeddings → clustering → taxonomy)
         │
         ▼
   Kundenzitate und Antworten 3.xlsx (10 GK + 11 DM categories)
         │
         ▼
   Phase 3: Production Pipeline
   (classify → match reference → generate pitch → export CSV)
         │
         ▼
   final_output.csv (per-contact: classification + pitch + reference)
```

## Transcription

All 97,816 Dexter call recordings were transcribed using:
- **Model:** OpenAI whisper-1
- **Language:** German (de)
- **Prompt:** Domain keywords (Medifox Dan, Connext Vivendi, Senso, etc.)
- **Storage:** `media_pipeline.transcriptions` table + Backblaze B2
- **Coverage:** 100% — all audio files have completed transcriptions as of Sep 2025
- **Latest call in DB:** Aug 25, 2025

The transcription pipeline lives in `data_pipelines/scripts/transcription/transcribe_gpt4o.py` and runs via the Gateway Worker (documented in `docs/GatewayWorker.md`).

**Recommended upgrade:** Replace whisper-1 keyword list with a contextual prompt for gpt-4o-transcribe. See NOTES.md for the recommended prompt.
