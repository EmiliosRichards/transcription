# Transcription System — Architecture

> Last updated: 2026-04-02

## System overview

The transcription system is an async audio transcription pipeline. An HTTP API accepts recording references, downloads audio, uploads it to Backblaze B2 object storage, and enqueues a job. A background worker picks up pending jobs, sends audio to OpenAI Whisper for transcription, and stores results back to B2 and Postgres.

```
                          HTTPS (Caddy auto-SSL)
Client App ──────────────────────────────────────────► :443
                                                        │
                                                  reverse_proxy
                                                        │
                                                        ▼
                                               FastAPI Gateway
                                               (uvicorn :8000)
                                                        │
                            ┌───────────────────────────┼───────────────────────────┐
                            │                           │                           │
                            ▼                           ▼                           ▼
                     Source DB lookup           Upload audio to B2          Insert job to DB
                   (recordings/contacts)      (campaign-analysis)       (transcription schema)
                                                                                │
                                                                                ▼
                                                                        ┌───────────────┐
                                                                        │  Worker loop   │
                                                                        │  (polling DB)  │
                                                                        └───────┬───────┘
                                                                                │
                                                  ┌─────────────────────────────┼─────────────────┐
                                                  │                             │                 │
                                                  ▼                             ▼                 ▼
                                           Download from B2            OpenAI Whisper API   Upload transcript
                                                                                            to B2 + upsert DB
```

## Components

### 1. API Gateway

- **Framework:** FastAPI (Python 3.9+)
- **Server:** Uvicorn, bound to 127.0.0.1:8000
- **Auth:** API key via `X-API-Key` header
- **Endpoints:**
  - `POST /api/media/transcribe` — submit a recording for transcription
  - `GET /api/media/status/{audio_file_id}` — poll for result
- **Key behavior:**
  - Looks up recording metadata from source tables (contacts, recordings, campaign_map)
  - Downloads audio from source URL, uploads to B2
  - Short-circuits if transcription already exists (idempotent)
  - Returns immediately with job ID; processing is async

### 2. Worker

- **Process:** Background Python process, runs continuously
- **Job selection:** Polls DB for pending audio files with no completed transcription
- **Claim system:** Prevents multiple workers from processing the same file
- **Processing:** Downloads audio from B2 -> sends to OpenAI Whisper API -> uploads transcript JSON+TXT back to B2 -> upserts result to DB
- **Batch size:** 1 file at a time, 2 max concurrent workers

### 3. Database (PostgreSQL)

- **Server:** 185.216.75.247, localhost:5432
- **Database:** `dialfire`
- **Schemas:**
  - `public` — source tables (recordings, contacts, campaign_map) owned by Dialfire/dbsync2
  - `media_pipeline` — transcription job tables (current production)
  - `transcription` — new schema (monorepo architecture, not yet deployed)

### 4. Object Storage (Backblaze B2)

- **Bucket:** `campaign-analysis`
- **Audio path:** `[prefix/]<campaign>/audio/<phone>/<uuid>.<ext>`
- **Transcript paths:**
  - JSON: `[prefix/]<campaign>/transcriptions/json/<rest>.json`
  - TXT: `[prefix/]<campaign>/transcriptions/txt/<rest>.txt`
- **Production prefix:** `gateway`

### 5. Reverse Proxy (Caddy)

- **Domain:** `transcribe.vertikon.ltd`
- **Ports:** 80 (redirect), 443 (HTTPS with auto Let's Encrypt)
- **Target:** 127.0.0.1:8000

## Codebase locations

There are **two repositories** containing this system. They have diverged and are being unified.

| Repository | Path | Role | Notes |
|---|---|---|---|
| **Standalone repo** | `EmiliosRichards/transcription` | Currently deployed on production | Original codebase. Worker uses `transcribe_gpt4o.py` CLI script. Has `media_pipeline` schema. |
| **Monorepo** | `manuav-platform/apps/transcription` | Target architecture | Restructured (`api/`, `web/`, `pipelines/`). New `transcription` schema, dedicated `worker.py`, dual-DB support, Alembic migrations. |

### Directory mapping (standalone -> monorepo)

| Standalone repo | Monorepo |
|---|---|
| `chatbot_app/backend/` | `api/` |
| `chatbot_app/frontend/` | `web/` |
| `data_pipelines/` | `pipelines/data_pipelines/` |
| `docs/` | `legacy/` |

### Features only in standalone repo (need porting)

- `prompt` parameter on API (per-job Whisper biasing prompt)
- `pitch_template` in `company_intel.py` (classic vs bullets)
- 7 standalone transcription scripts (`transcribe_gpt4o.py`, etc.)
- Dexter Phase 3 pipeline

### Features only in monorepo (not yet deployed)

- SQLAlchemy ORM models for `transcription` schema
- `FOR UPDATE SKIP LOCKED` job queue with attempt tracking
- Dedicated `worker.py` with health check server
- Dual-database support (platform + legacy Dialfire)
- Alembic schema migrations
- Artifact registry (linking B2 objects to audio files)

## Infrastructure

| Resource | Value |
|---|---|
| **Production server** | 185.216.75.247 (Contabo) |
| **Staging server** | 173.249.24.215 (Contabo) — services stopped, data intact |
| **Domain** | transcribe.vertikon.ltd |
| **DNS provider** | IONOS |
| **B2 bucket** | campaign-analysis |
| **B2 region** | eu-central-003 |
| **GitHub repo** | EmiliosRichards/transcription |
| **Monorepo** | (manuav-platform, private) |
