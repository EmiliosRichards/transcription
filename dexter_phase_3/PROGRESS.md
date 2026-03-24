# Dexter Phase 3 — Progress Tracker

## Status: All scripts written. Ready for .env setup and testing.

---

### Phase 1: Setup & Data Prep
- [x] 1.1 — Convert Excel -> taxonomy.json (10 GK + 11 DM) + referenzen.csv (51 facilities)
- [x] 1.2 — Set up config.yml (two-DB architecture: Media DB + Dialfire DB)
- [x] 1.3 — Write classification prompt (prompts/classify_journey.txt)
- [x] 1.4 — Set up project structure (folders, requirements.txt, .env.example)
- [x] 1.5 — Write all pipeline scripts (00 through 05)
- [x] 1.6 — Discovered reference-bucket with full DB schemas; updated pipeline for two-DB setup
- [x] 1.7 — PLZ/ort solved: comes from Dialfire contacts table, enriched during export

### Phase 2: Export Journeys
- [x] 2.1 — DB architecture understood (Media DB @ 173.249.24.215, Dialfire @ 185.216.75.247)
- [ ] 2.2 — Set up .env with real MEDIA_DB_URL + DIALFIRE_DB_URL credentials
- [ ] 2.3 — Open SSH tunnel and test `01_export_journeys.py` with --max-journeys 10

### Phase 3: Classification
- [ ] 3.1 — Test `02_classify.py` on small batch, review accuracy
- [ ] 3.2 — Tune prompt if needed based on results
- [ ] 3.3 — Run on full dataset

### Phase 4: Reference Matching
- [ ] 4.1 — Test `03_match_reference.py`, verify geographic sense

### Phase 5: Pitch Generation
- [ ] 5.1 — Test `04_generate_pitches.py`, review sample pitches

### Phase 6: Final Export
- [ ] 6.1 — Run `05_export_final.py`, end-to-end test
- [ ] 6.2 — Deliver final CSV

---

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-24 | No embeddings/clustering | Taxonomy is small (~20 categories), direct LLM classification is simpler and sufficient |
| 2026-03-24 | Template-based pitches (not LLM-generated) | Templates already exist in Excel, just need placeholder filling |
| 2026-03-24 | PLZ-based reference matching | Geographic proximity for "nearest referral we can name" |
| 2026-03-24 | Fresh pipeline in dexter_phase_3/ | Clean start, borrowing patterns from v2 but not carrying over complexity |
| 2026-03-24 | Two-DB architecture | Media DB (173.249.24.215) for transcripts, Dialfire (185.216.75.247) for contacts/PLZ |
| 2026-03-24 | PLZ from Dialfire contacts table | contacts.plz and contacts.ort are available, enriched during journey export |
| 2026-03-24 | Chronological call order for LLM | Oldest call first, newest last — LLM recency bias helps classify on latest info |
| 2026-03-24 | do_not_call flag added | LLM detects explicit "stop calling" requests independent of category |
| 2026-03-24 | Real km distance for ref matching | pgeocode replaces PLZ numeric diff, 50km threshold for "nah" vs "fern" |

## Blockers

| Blocker | Owner | Status |
|---------|-------|--------|
| .env with real DB credentials | Emilios | Done |
| Confirm Dexter campaign_id(s) in Dialfire | Emilios | Done (10 IDs) |

## Come Back To

| Item | Notes |
|------|-------|
| Programmatic system pre-scan | Grep all transcripts for known system names (from Whisper prompt) before LLM call, inject as hint. Catches systems mentioned in early calls that get truncated. |
| Push colleagues for AP name tracking | AP_Vorname/AP_Nachname in Dialfire are almost always empty. Agents should fill these in after calls. Currently relying on LLM to extract garbled names from ASR. |
| Transcription of new calls | Calls after Aug 25, 2025 exist in DB but may not be transcribed. Need to run transcription pipeline or Gateway Worker for new recordings. |
