# Dexter Phase 3 Pipeline — Overview

## What This Pipeline Does (Plain English)

Dexter is a long-standing client. Their product is a **voice documentation app for nursing staff** (Sprachdokumentation für Pflegemitarbeiter via mobiler App). We've been cold-calling ~16,000+ care home contacts for them across many campaign rounds, but we need a **fresh angle** — personalized follow-up pitches based on what happened in previous calls.

### The Pipeline in One Sentence

> Pull every call we've ever made to each contact, figure out *why* they said no last time, then generate a tailored German follow-up pitch that references a real nearby Dexter customer.

### Step by Step

```
┌──────────────────────────────────────────────────────────┐
│ 0. PREPARE INPUTS                                        │
│    Convert Excel files → taxonomy.json + referenzen.csv  │
│    (one-time setup, re-run if taxonomy changes)          │
└──────────────────────┬───────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────┐
│ 1. EXPORT JOURNEYS                                       │
│    Pull all Dexter call recordings from Postgres         │
│    (media_pipeline.audio_files + transcriptions)         │
│    Group by phone number → one "journey" per contact     │
│    Enrich with Dialfire contact data (firma, PLZ, ort)   │
└──────────────────────┬───────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────┐
│ 2. CLASSIFY                                              │
│    Send journey transcripts to LLM (chronological order) │
│    Determine: GK (Gatekeeper) or DM (Decision Maker)    │
│    Classify into one of 21 fixed categories              │
│    Extract: names, system, evidence, do-not-call flag    │
│    Optionally suggest new categories if warranted        │
└──────────────────────┬───────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────┐
│ 3. MATCH REFERENCE COMPANY                               │
│    From ~51 existing Dexter customer facilities          │
│    Find nearest by real km distance (pgeocode)           │
│    ≤50km = "nah" (bei Ihnen in der Nähe)                │
│    >50km = "fern" (neutral phrasing)                     │
│    Prefer same-system match (30% distance bonus)         │
└──────────────────────┬───────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────┐
│ 4. GENERATE PITCH (template)                             │
│    Look up response template for that category           │
│    Fill placeholders: [Datum], [Name Heim], [Ort], etc.  │
│    "Raus" categories → flagged, no pitch generated       │
│    No AP name found → fallback to "der zuständigen       │
│    Person"                                               │
├──────────────────────────────────────────────────────────┤
│ 4b. ENHANCE PITCH (optional, LLM)                        │
│    Take template pitch + call transcript history         │
│    LLM makes small personalising tweaks                  │
│    References specific objections, names, systems        │
│    If no improvement warranted → keeps original          │
└──────────────────────┬───────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────┐
│ 5. EXPORT FINAL CSV                                      │
│    One row per contact with all fields                   │
│    Both template and enhanced pitch (if available)       │
│    Ready for agent use                                   │
└──────────────────────────────────────────────────────────┘
```

## Key Design Decisions

### No embeddings / clustering needed
The taxonomy is small and fixed (10 GK + 11 DM categories, discovered in Phase A). The LLM classifies directly — no need for the embedding → HDBSCAN → cluster naming pipeline.

### Templates + optional LLM enhancement
Each category has a ready-made German response template from the Excel. Step 4 fills placeholders mechanically. Step 4b optionally sends the template + transcript to an LLM for light personalisation (referencing specific objections, names, systems mentioned).

### Reference matching is real geographic distance
Uses `pgeocode` library for PLZ → lat/lon conversion and Haversine distance. Threshold: ≤50km = "nah" (can say "bei Ihnen in der Nähe"), >50km = "fern" (neutral phrasing). System match gives 30% distance bonus.

### Do-not-call detection requires repeated rejection
A single "nein danke" is a normal rejection (handled by categories). Do-not-call is only flagged when the contact has pushed back across **3+ separate calls** with escalating frustration.

### Chronological call order for LLM
Calls are sent oldest-first so the LLM reads the most recent call last — exploiting recency bias for better classification accuracy.

### "Raus" contacts stay in the CSV
Categories marked "raus" (Zentrale, Falsche Organisation) are kept in the output with `action=raus` instead of being dropped. This allows auditing and potential future re-routing to central contacts.

## Infrastructure

### Database
- **Single Postgres** on Contabo server `185.216.75.247`, database `dialfire`
- Connected via SSH tunnel: `ssh -L 5432:localhost:5432 root@185.216.75.247`
- **Schema `media_pipeline`**: audio_files, transcriptions, transcription_claims, etc.
- **Schema `public`**: Dialfire contacts table with campaign data
- Old server `173.249.24.215` (port 5433 tunnel) has some legacy contact records

### Transcription
- 97,816 Dexter calls transcribed with OpenAI whisper-1
- German language, domain keyword prompt
- Stored in `media_pipeline.transcriptions` + Backblaze B2
- Transcription pipeline: `data_pipelines/scripts/transcription/transcribe_gpt4o.py`

### LLM
- Classification + enhancement: `gpt-5.4-mini-2026-03-17` (configurable in config.yml)
- ~5,000–9,000 tokens per classification (varies by call count)

## Input Files

| File | What it is |
|------|-----------|
| `Kundenzitate und Antworten 3.xlsx` | Taxonomy: GK (10 cats) and DM (11 cats) with customer quotes and response templates |
| `Dexter Jagdhütte.xlsx → Referenzen_200226` | ~51 existing Dexter customer facilities with Träger, name, city, PLZ, system |
| `Dexter Jagdhütte.xlsx → Tabelle1` | Activity log of recent appointments (context only) |

## Output

Final CSV with one row per contact. Key columns:
- Contact info (phone, firma, PLZ, ort)
- Classification (role, category, confidence, evidence, reason)
- Names extracted (AP name + role, GK name)
- System in use
- Reference match (facility, city, distance, proximity)
- Do-not-call flag + evidence + call count
- Template pitch + enhanced pitch (if step 4b was run)
- Suggested new category (if LLM identified a gap in taxonomy)
- Dialfire contact ID and status
