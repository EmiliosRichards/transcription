# Dexter Phase 3 — Notes & Open Items

*Last updated: 2026-03-26*

## Notes for Team

### 1. AP Name Tracking in Dialfire

The `AP_Vorname` and `AP_Nachname` fields in Dialfire contacts are almost always empty for Dexter contacts. This means we have no reliable source for the decision maker's name — we're relying entirely on the LLM extracting names from garbled ASR transcripts, which is unreliable.

**Action:** Push agents to fill in AP name fields after calls. Even a last name ("Herr Weddeck") is valuable. This directly improves pitch quality — templates like "Da sagten Sie mir, dass [mein AP] aktuell nicht erreichbar sei" sound much better with a real name than "der zuständigen Person".

### 2. Programmatic System Pre-Scan (future)

For contacts with many calls (50+), the system name (Vivendi, Senso, Medifox, etc.) might only be mentioned in an early call that gets truncated from the LLM context window (3000 word limit).

**Idea:** Before sending to the LLM, grep all transcripts for known system names and inject matches as a hint. The known systems are already in the Whisper prompt:
```
Medifox Dan, Connext Vivendi, Senso, CGM, C&S, CareCloud, Sinfonie,
myneva, OptaData, Noventi, Cairful, Euregon, Micos, Curasoft, Voize,
SIS, DM7, SNAP
```

### 3. Transcription of New Calls

Calls after Aug 25, 2025 exist in the DB as `audio_files` rows but may not be transcribed yet. The transcription pipeline (`data_pipelines/scripts/transcription/transcribe_gpt4o.py` and Gateway Worker) needs to be run for new recordings. All existing Dexter calls (97,816) are transcribed with OpenAI whisper-1 using a German-language prompt.

---

## Infrastructure Context

### Server Setup
| Server | IP | Role | DB |
|--------|-----|------|-----|
| **Production** | 185.216.75.247 | Dialfire DB + media_pipeline | `dialfire` on port 5432 |
| **Legacy/Staging** | 173.249.24.215 | Old server, has some legacy contact records | `dialfire` on port 5432 |

### SSH Tunnels
```bash
# Production (primary — use this)
ssh -L 5432:localhost:5432 root@185.216.75.247

# Legacy (only needed for 142 orphaned contacts)
ssh -L 5433:localhost:5432 root@173.249.24.215
```

### Dialfire Campaign IDs

**Active campaigns (have contacts in DB):**
| Campaign ID | Contacts | Notes |
|------------|----------|-------|
| H2C8QWP35CYFC8ZM | 10,164 | Main Dexter campaign |
| 6FLEGYS7RGQL483P | 8,757 | Second main campaign |
| 2SAA6AP74RYPNDL3 | 548 | |
| JDVTGVTLTS99ZXC3 | 412 | |
| TT7P45HZLKQAQ78C | ? | Confirmed Dexter by Emilios |
| CBDZK4LRSQRN3JMN | ? | Confirmed Dexter by Emilios |

**Empty campaigns (in original config but 0 contacts on new server):**
RDSFPLHE9BT68CFW, 6CV8XLPGJYESMKUQ, PNUYAU4HZH6SNGVV, ZPKZDSD766UJLW59, 72LZE7Q2B2RQSQJ5, 3SY5V6Z5C3GSXRA4
— These may have had contacts on the old server. The new server only has 4 campaigns with data.

**Other campaigns with shared phone numbers (NOT Dexter campaigns):**
CEFBRJ877268Z89D (100 contacts), Z6JLZEY97MFLH2QN (7 contacts), plus ~28 others. Contact data (firma, PLZ, ort) can be pulled from these for the 502 contacts not in Dexter campaigns.

### Audio File Campaign Names (not IDs)
Audio files have `campaign_name` (human readable) but **not** `campaign_id`:
```
Dexter PLZ 1-2-8, Dexter PLZ 4+5, DEXTER PLZ 9, Dexter PLZ 0-3-6-7,
Dexter Altersheim, Dexter_PLZ_4-9, Dexter_PLZ_0-3
```
These are regional splits. No direct mapping from `campaign_name` → `campaign_id` exists in the DB.

### Contact Coverage
- **16,671** unique phones across the active Dexter campaigns
- **97,816** Dexter audio files in media_pipeline
- **142 orphaned contacts** — have audio files but no contact record on either server

---

## Contact Selection Context

### The original 1,203 contacts (`dexter_final_numbers_appended.csv`)
- Randomly selected during Phase A for taxonomy discovery
- 701 found in the 4 active Dexter campaigns on new server
- 502 found in older campaigns (on old server or non-Dexter campaigns on new server)
- Many were manually moved to `export_negative` task in preparation for the new campaign
- The `$task` column values: 516 `anrufen_stufe`, 144 `export_negative`, 537 empty, 6 `export_aufzeichnungen`

### Selection for Phase 3 (`runs/selection_1250.csv`)
- 1,250 contacts selected (expecting ~25% raus/unknown, targeting ~1,000 pitchable)
- 836 from the original CSV, last called before July 2025 (8+ month gap)
- 414 from the wider pool (14,925 eligible), last called before March 2025 (12+ month gap)
- Pre-filtered to exclude: success, Bestandskunde, nie_wieder_anrufen, wrong numbers, duplicates, non-existent companies
- 711 need closing in old campaigns before import into new campaign
  - 30 of those are actively callable right now (anrufen_stufe + anrufen_status=open) — priority
  - CSV has `active_contact_id` + `active_campaign_id` for Dialfire update

### Dialfire Status Guide
| Status field | Meaning |
|---|---|
| `$status` | Top-level: open, success, failed |
| `$status_detail` | Sub-status: $none, $follow_up_auto, $follow_up_personal, $assigned, $duplicate |
| `$task` | What queue: anrufen_stufe (call), export_negative (excluded), export_aufzeichnungen |
| `$$anrufen_status` | Calling task status: open, declined, failed, success |
| `$$anrufen_status_detail` | Why: Zentrale, KI_Ansprechpartner, falsche_Zielgruppe, $do_not_call, Termin, etc. |

**Contacts that should NEVER be called:**
- `$$anrufen_status_detail` = `Nie_wieder_anrufen` or `nie_wieder_anrufen` or `will_nicht_mehr`
- `$$anrufen_status_detail` = `Bestandskunde` or `Bestandkunde` (already a customer)
- `$status` or `$$anrufen_status` = `success`
- Any Termin variant: `Termin`, `Termin_bestätigt`, `Termin_nach_Infomail`, `Termin_verschoben`, `selbständig_gebucht`

---

## Improved Whisper Prompt for Future Transcriptions

The current whisper-1 prompt is a flat keyword list. For future runs using `gpt-4o-transcribe`, use this contextual prompt instead:

```
Das folgende Gespräch ist ein Outbound-Kaltanruf der Firma Dexter an ein Pflegeheim oder einen ambulanten Pflegedienst. Dexter bietet eine KI-App für Sprachdokumentation in der Pflege an. Der Agent stellt sich vor und versucht, mit der Heimleitung, PDL oder Einrichtungsleitung zu sprechen.

Häufig genannte Software-Systeme: Medifox Dan, Connext Vivendi, Senso, Sinfonie, myneva, CareCloud, CGM, Euregon, Micos, Curasoft, Noventi, OptaData, SNAP, DM7, Voize, SIS.

Häufig genannte Rollen: PDL, Pflegedienstleitung, Heimleitung, Einrichtungsleitung, Verwaltungsleitung, Geschäftsführung, Träger, Stiftung, Bürgerspital.
```

**Why better:** Context tells the model what kind of conversation to expect. Proper nouns with variants improve recognition. Role names are domain jargon that ASR garbles without hints.

---

## Insights from Test Runs

### Classification
- `gpt-5.4-mini-2026-03-17` significantly better than `gpt-4o-mini` — varied confidence, better category accuracy
- Sending calls oldest-first (chronological) improves classification — LLM recency bias focuses attention on most recent call
- With gpt-4o-mini, contact with "Wir brauchen keine KI" was wrongly classified as GK01 (Bereits Anbieter). With gpt-5.4-mini, correctly classified as GK02 (Zentralisierte Entscheidung) with 0.98 confidence
- ~20-25% of contacts are raus or unknown (Zentrale, unreachable, wrong org)

### Reference Matching
- 51 reference facilities provide reasonable coverage but gaps exist (e.g. Frankfurt → Altena was 150km)
- PLZ prefix matching was unreliable (14xxx covers both Berlin and NRW) — real km distances are essential
- 50km threshold for "nah" vs "fern" works well

### Pitch Quality
- "Haus" prefix deduplication prevents awkward "dem Haus Seniorenzentrum X"
- LLM-enhanced pitches add genuine value — referencing specific objections, systems, call context
- Agent name placeholder ("mein Name ist...") is intentionally unfilled — agents fill their own name
- `[mein AP]` falls back to "der zuständigen Person" when no name found anywhere
