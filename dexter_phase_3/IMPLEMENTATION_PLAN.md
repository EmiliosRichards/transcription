# Dexter Phase 3 — Implementation Plan

*Last updated: 2026-03-26*

## Pipeline Structure

```
dexter_phase_3/
├── config/
│   ├── taxonomy.json          ← 10 GK + 11 DM categories from Excel
│   ├── referenzen.csv         ← 51 reference facilities from Excel
│   └── config.yml             ← DB URL, model, campaign IDs
├── prompts/
│   ├── classify_journey.txt   ← Classification system prompt
│   └── enhance_pitch.txt      ← Pitch enhancement system prompt
├── scripts/
│   ├── 00_prepare_inputs.py   ← Excel → taxonomy.json + referenzen.csv
│   ├── 01_export_journeys.py  ← DB → journeys.jsonl
│   ├── 02_classify.py         ← LLM classification
│   ├── 03_match_reference.py  ← PLZ-based reference matching (pgeocode)
│   ├── 04_generate_pitches.py ← Template placeholder filling
│   ├── 04b_enhance_pitches.py ← Optional LLM pitch personalisation
│   └── 05_export_final.py     ← Final CSV assembly
├── runs/                      ← Output per run
│   ├── selection_1250.csv     ← Contact selection for new campaign
│   ├── compare_test/          ← 16-contact test run
│   └── sample_20/             ← 20-contact sample run
├── .env                       ← DB + OpenAI credentials (gitignored)
├── PIPELINE_OVERVIEW.md
├── IMPLEMENTATION_PLAN.md
├── LINEAGE.md
├── NOTES.md
└── PROGRESS.md
```

## Execution

```
00_prepare_inputs.py     one-time (re-run if Excel changes)
        │
01_export_journeys.py    --run runs/<name> [--max-journeys N]
        │
02_classify.py           --run runs/<name>
        │
03_match_reference.py    --run runs/<name>
        │
04_generate_pitches.py   --run runs/<name>
        │
04b_enhance_pitches.py   --run runs/<name> [--max N]  (optional)
        │
05_export_final.py       --run runs/<name>
```

All scripts use `--run` to specify the run directory. Data flows via intermediate files:
- `journeys.jsonl` → `classifications.csv` → `classifications_with_refs.csv` → `pitches.csv` → `pitches_enhanced.csv` → `final_output.csv`

## Configuration

### config.yml
```yaml
database_url: env:DATABASE_URL          # from .env
openai_api_key: env:OPENAI_API_KEY      # from .env
model: gpt-5.4-mini-2026-03-17          # used for classification + enhancement
scope: dexter/audio/%                   # b2_object_key filter
campaign_ids: [...]                     # 12 Dexter campaign IDs
```

### .env
```
DATABASE_URL=postgresql+psycopg2://postgres:***@localhost:5432/dialfire
OPENAI_API_KEY=sk-proj-...
```
Requires SSH tunnel to Contabo: `ssh -L 5432:localhost:5432 root@185.216.75.247`

## Contact Selection

The file `runs/selection_1250.csv` contains 1,250 contacts for the new campaign:
- 836 from the original Phase A selection (`dexter_final_numbers_appended.csv`), last called before July 2025 (8+ month gap)
- 414 from the wider Dexter contact pool, last called before March 2025 (12+ month gap)

### Pre-filters applied:
- Must have full data (firma + PLZ + ort)
- Excluded: `success`, `Bestandskunde`, `nie_wieder_anrufen`, `will_nicht_mehr`, `Termin*`, `$wrong_number`, `$locked_number`, `$duplicate`, `Unternehmen_existiert_nicht`, `selbständig_gebucht`

### Action needed before running:
- 711 contacts need closing in old Dexter campaigns (CSV has `active_contact_id` + `active_campaign_id`)
- 30 of those are **actively callable** right now (anrufen_stufe + anrufen_status=open) — close these first
- 539 remaining are in `action_needed=none` — not in active campaigns, ready to go

## Open Items / Future Work

See NOTES.md for tracked items.
