# Dexter Phase 3 Pipeline — Overview

## What This Pipeline Does (Plain English)

Dexter is a long-standing client. Their product is a **voice documentation app for nursing staff** (Sprachdokumentation für Pflegemitarbeiter via mobiler App). We've been cold-calling ~12,000 care home contacts for them across many rounds, but we need a **fresh angle** — personalized follow-up pitches based on what happened in previous calls.

### The Pipeline in One Sentence

> Pull every call we've ever made to each contact, figure out *why* they said no last time, then generate a tailored German follow-up pitch that references a real nearby Dexter customer.

### Step by Step

```
┌──────────────────────────────────────────────────────────┐
│ 1. EXPORT JOURNEYS                                       │
│    Pull all Dexter call recordings from our Postgres DB  │
│    Group them by contact (phone number)                  │
│    Each contact's full call history = one "journey"      │
└──────────────────────┬───────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────┐
│ 2. PREPARE TRANSCRIPTS                                   │
│    For each journey, gather all available transcripts    │
│    Stitch them together chronologically                  │
│    (Calls already transcribed via Whisper in earlier     │
│     pipeline runs — we just read what's in the DB)      │
└──────────────────────┬───────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────┐
│ 3. CLASSIFY                                              │
│    Send the journey transcript to an LLM                 │
│    Determine: GK (Gatekeeper) or DM (Decision Maker)?   │
│    Classify into one of the fixed categories:            │
│      - GK: 10 categories (e.g. "Bereits Anbieter",      │
│        "Kein Interesse", "Entscheider abwesend"...)      │
│      - DM: 11 categories (e.g. "Kein Bedarf",           │
│        "Schlechtes Timing", "Kein Budget"...)            │
│    Extract: last call date, reason, evidence quote       │
└──────────────────────┬───────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────┐
│ 4. MATCH REFERENCE COMPANY                               │
│    From the Referenzen list (~1000 Dexter customers),   │
│    find the nearest one to this contact's location       │
│    "Die nächste Referenz, die wir nennen können, ist..." │
│    Match by PLZ / city proximity                         │
└──────────────────────┬───────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────┐
│ 5. GENERATE PITCH                                        │
│    Use the response template for that category           │
│    Fill in placeholders:                                 │
│      [Datum]         → date of last call                 │
│      [Name Heim]     → matched reference company name    │
│      [Ort in der Nähe] → reference company's city        │
│      [Grund]         → extracted reason from transcript  │
│    For some categories the answer is "raus" (exclude)    │
└──────────────────────┬───────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────┐
│ 6. EXPORT CSV                                            │
│    One row per contact:                                  │
│    phone, campaign, role (GK/DM), category, last_date,  │
│    reason, evidence_quote, ref_company, ref_city,        │
│    ref_system, pitch_text, dialfire_id                   │
└──────────────────────────────────────────────────────────┘
```

## Key Design Decisions

### No embeddings / clustering needed
The taxonomy is small and fixed (10 GK + 11 DM categories, all defined in the Excel). The LLM can classify directly — no need for the embedding → HDBSCAN → cluster naming pipeline from Phase A.

### Templates come from the Excel
Each category already has a ready-made German response template. We just need to fill in the dynamic fields. Some categories are marked "raus" (remove from calling list).

### Reference matching is geographic
The Referenzen list has ~1,000 facilities with PLZ and city. We match by proximity so the pitch can say "das Haus X bei Ihnen in der Nähe" credibly. The phrasing is: "Die nächste Referenz, die wir nennen können, ist [Name] in [Ort]."

### Transcripts are already in the DB
The data_pipelines and gateway worker have already transcribed most Dexter calls. We read from `media_pipeline.transcriptions` — no need to re-transcribe.

## Input Files

| File | What it is |
|------|-----------|
| `Kundenzitate und Antworten 3.xlsx` | Taxonomy: GK (10 cats) and DM (11 cats) with customer quotes and response templates |
| `Dexter Jagdhütte.xlsx → Referenzen_200226` | ~1,000 existing Dexter customer facilities with Träger, name, city, PLZ, system |
| `Dexter Jagdhütte.xlsx → Tabelle1` | Activity log of recent appointments (not directly used in pipeline, useful for context) |

## Output

A single CSV with one row per contact, ready for agents to use in follow-up calls.
