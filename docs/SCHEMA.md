# Transcription System — Database Schema

> Last updated: 2026-04-02
> Server: 185.216.75.247 | Database: `dialfire` | PostgreSQL

## Overview

The `dialfire` database contains three logical groups of tables:

1. **`public.*`** — Dialfire source tables (owned by `kubrakiv`, synced by `dbsync2`). Read-only for transcription.
2. **`media_pipeline.*`** — Current production transcription schema. Created Sep 2025.
3. **`transcription.*`** — New schema from monorepo refactor (Mar 2026). Not yet deployed.

---

## 1. Source tables (public, read-only)

These are synced from Dialfire by the `dbsync2` service. Do not write to them.

| Table | Owner | Purpose |
|---|---|---|
| `contacts` | kubrakiv | Contact/lead records with phone, campaign_id |
| `recordings` | kubrakiv | Call recordings with URLs, start/stop times |
| `connections` | kubrakiv | Call connection events |
| `transactions` | kubrakiv | Transaction records |
| `inbound_calls` | kubrakiv | Inbound call records |
| `agent_state_durations` | kubrakiv | Agent state tracking |
| `payload_conn_map_staging` | postgres | Staging table for payload mapping |

### Key joins for transcription

```sql
-- Recording -> Contact -> Campaign
SELECT r.id, r.location AS audio_url,
       c."$phone", c."$campaign_id",
       COALESCE(cm.campaign, c."$campaign_id") AS campaign_name,
       r.started, r.stopped
FROM public.recordings r
JOIN public.contacts c ON r.contact_id = c."$id"
LEFT JOIN public.campaign_map cm ON cm.campaign_id = c."$campaign_id"
```

**Note:** `campaign_map` may not exist on this server (it was optional on the old server). Check before querying.

---

## 2. Current production schema: `media_pipeline`

Created manually via DDL. See `media_pipeline_psql_setup.md` for full setup script.

### `media_pipeline.audio_files`

Job catalog — one row per audio file to process.

| Column | Type | Notes |
|---|---|---|
| `id` | BIGSERIAL PK | Auto-increment |
| `phone` | TEXT | Normalized (digits + `+`) |
| `campaign_name` | TEXT | Human-readable campaign label |
| `recording_id` | TEXT | `PR_<uuid>` from source URL; partial unique |
| `url` | TEXT NOT NULL | Source audio URL |
| `url_sha1` | TEXT NOT NULL UNIQUE | Dedupe key |
| `content_sha256` | TEXT | Optional file checksum |
| `started` | TIMESTAMPTZ | Call start |
| `stopped` | TIMESTAMPTZ | Call end |
| `duration_seconds` | DOUBLE PRECISION | Computed |
| `b2_object_key` | TEXT | B2 storage key |
| `local_path` | TEXT | Local cache (nullable) |
| `file_size_bytes` | BIGINT | Optional |
| `source_table` | TEXT | Provenance (`public.recordings`) |
| `source_row_id` | BIGINT | FK to source |
| `metadata` | JSONB | Per-job data (e.g. `{"prompt": "..."}`) |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |

### `media_pipeline.transcriptions`

One transcription per audio file (1:1).

| Column | Type | Notes |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `audio_file_id` | BIGINT NOT NULL UNIQUE | FK -> audio_files, CASCADE |
| `provider` | TEXT | `OpenAI`, `WhisperX`, etc. |
| `model` | TEXT | `whisper-1`, `gpt-4o-mini-transcribe`, etc. |
| `status` | TEXT DEFAULT 'completed' | pending / completed / failed |
| `transcript_text` | TEXT | Full transcript |
| `segments` | JSONB | Word/segment timings |
| `diarization` | JSONB | Speaker info |
| `metadata` | JSONB | B2 keys, language, timings |
| `raw_response` | JSONB | Full provider response |
| `b2_transcript_key` | TEXT | B2 key for transcript file |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |
| `completed_at` | TIMESTAMPTZ | |

### `media_pipeline.transcription_claims`

Prevents worker overlap. Worker claims a job, processes it, releases.

| Column | Type | Notes |
|---|---|---|
| `audio_file_id` | BIGINT PK | FK -> audio_files |
| `worker_id` | TEXT | Hostname or process ID |
| `claimed_at` | TIMESTAMPTZ DEFAULT now() | |
| `expires_at` | TIMESTAMPTZ | TTL for auto-release |

### `media_pipeline.transcription_failures`

Tracks failures for cooldown and permanent skip logic.

| Column | Type | Notes |
|---|---|---|
| `audio_file_id` | BIGINT PK | FK -> audio_files, CASCADE |
| `provider` | TEXT | |
| `model` | TEXT | |
| `status` | TEXT | `transient` or `permanent` |
| `error_code` | INTEGER | HTTP/provider error code |
| `error_message` | TEXT | |
| `attempt_count` | INTEGER DEFAULT 1 | |
| `first_failed_at` | TIMESTAMPTZ DEFAULT now() | |
| `last_failed_at` | TIMESTAMPTZ DEFAULT now() | |

---

## 3. New schema: `transcription` (monorepo, not yet deployed)

Managed by Alembic. Migration: `b7f6d9d8a3c1_create_owned_transcription_schema.py`

### `transcription.audio_files`

| Column | Type | Notes |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `source_type` | TEXT | `url`, `upload`, `dialfire_recording` |
| `source_system` | TEXT | |
| `recording_id` | TEXT | Partial unique (WHERE NOT NULL) |
| `source_url` | TEXT | |
| `url_sha1` | TEXT | Partial unique (WHERE NOT NULL) |
| `content_sha256` | TEXT | Partial unique (WHERE NOT NULL) |
| `phone` | TEXT | |
| `campaign_name` | TEXT | |
| `started_at` | TIMESTAMPTZ | |
| `stopped_at` | TIMESTAMPTZ | |
| `duration_seconds` | DOUBLE PRECISION | |
| `b2_audio_key` | TEXT | |
| `file_size_bytes` | BIGINT | |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |

### `transcription.jobs`

Job queue with claim-based processing.

| Column | Type | Notes |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `job_type` | TEXT | `TRANSCRIBE_AUDIO`, `POST_PROCESS_TRANSCRIPT`, `CLASSIFY_TRANSCRIPT`, `EXPORT_TRANSCRIPT` |
| `audio_file_id` | BIGINT FK | |
| `status` | TEXT | `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED` |
| `priority` | INTEGER DEFAULT 100 | Lower = higher priority |
| `payload_json` | JSONB | Job-specific config |
| `result_json` | JSONB | Output data |
| `claimed_by` | TEXT | Worker hostname |
| `claim_expires_at` | TIMESTAMPTZ | Auto-release TTL |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ DEFAULT now() | |

**Index:** `(status, priority, created_at)` for efficient job claiming.

### `transcription.job_attempts`

Audit trail for every processing attempt.

| Column | Type | Notes |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `job_id` | BIGINT FK | |
| `attempt_number` | INTEGER | |
| `status` | TEXT | |
| `provider` | TEXT | `OpenAI`, etc. |
| `model` | TEXT | `whisper-1`, etc. |
| `error_code` | TEXT | |
| `error_message` | TEXT | |
| `meta_json` | JSONB | |
| `started_at` | TIMESTAMPTZ DEFAULT now() | |
| `finished_at` | TIMESTAMPTZ | |

### `transcription.transcriptions`

One per audio file (unique on audio_file_id).

| Column | Type | Notes |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `audio_file_id` | BIGINT FK UNIQUE | |
| `status` | TEXT | `PENDING`, `COMPLETED`, `FAILED` |
| `provider` | TEXT | |
| `model` | TEXT | |
| `language` | TEXT | |
| `transcript_text` | TEXT | |
| `raw_segments_json` | JSONB | |
| `processed_segments_json` | JSONB | |
| `diarization_json` | JSONB | |
| `metadata_json` | JSONB | |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ DEFAULT now() | |

### `transcription.artifacts`

Registry of all stored objects (audio, transcripts, exports).

| Column | Type | Notes |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `audio_file_id` | BIGINT FK | |
| `transcription_id` | BIGINT FK | Nullable |
| `job_id` | BIGINT FK | Nullable |
| `artifact_type` | TEXT | `audio`, `transcript_json`, `transcript_txt`, `transcript_docx`, `classification_json` |
| `storage_provider` | TEXT | `b2`, `s3`, `local` |
| `object_key` | TEXT | Unique with storage_provider |
| `mime_type` | TEXT | |
| `size_bytes` | BIGINT | |
| `checksum_sha256` | TEXT | |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |

---

## Data migration: media_pipeline → transcription

When deploying the monorepo version, existing data needs to be migrated:

```sql
-- 1. Audio files
INSERT INTO transcription.audio_files (
    source_type, recording_id, source_url, url_sha1, content_sha256,
    phone, campaign_name, started_at, stopped_at, duration_seconds,
    b2_audio_key, file_size_bytes, created_at
)
SELECT
    'dialfire_recording', recording_id, url, url_sha1, content_sha256,
    phone, campaign_name, started, stopped, duration_seconds,
    b2_object_key, file_size_bytes, created_at
FROM media_pipeline.audio_files;

-- 2. Transcriptions (map old audio_file_id to new)
-- Requires a mapping table or subquery to match by recording_id/url_sha1

-- 3. Verify counts
SELECT 'media_pipeline' AS schema, COUNT(*) FROM media_pipeline.audio_files
UNION ALL
SELECT 'transcription', COUNT(*) FROM transcription.audio_files;
```

Full migration script should be written and tested on staging (173.249.24.215) before running on production.
