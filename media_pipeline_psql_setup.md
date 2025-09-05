# Media Pipeline Schema Handover — Integration Guide

This document is a practical handover for an AI agent or engineer to **programmatically write to** and **read from** the `media_pipeline` schema in the `manuav` PostgreSQL database, and to understand how it relates to the existing source tables (`public.recordings`, `public.contacts`, optional `public.campaign_map`). It includes:

* A concise **data model** and relationships
* Column-by-column breakdowns and constraints
* **Idempotent insert/backfill** patterns (conflict-safe)
* Reference **queries** for reads and exports
* Operational notes (transactions, hashing, time zones, resets)

---

## 1) Source → Target Overview

### Existing source tables (read-only for this pipeline)

* **`public.contacts`**

  * `"$id"` (PK)
  * `"$phone"` (raw phone; may include spaces/dashes)
  * `"$campaign_id"` (campaign identifier; not all legacy campaigns exist in `campaign_map`)

* **`public.recordings`**

  * `id` (row id)
  * `contact_id` → FK to `contacts."$id"`
  * `location` (URL to audio, e.g., `https://vault.24dial.com/vr/PR_<uuid>.mp3`)
  * `started`, `stopped` (often stored as text; cast to timestamp/timestamptz when needed)

* **`public.campaign_map`** *(optional for names)*

  * `campaign_id` (maps to `contacts."$campaign_id"`)
  * `campaign` (human-readable name)

**Key existing join:** `recordings.contact_id = contacts."$id"` → then use `contacts."$campaign_id"` for campaign filtering/labeling.

---

## 2) New schema (write targets)

All new objects are in **`media_pipeline`** to keep data isolated.

### 2.1 Tables

#### `media_pipeline.audio_files`

Catalog of every audio file we ingest.

| Column             | Type                                 | Notes / Requirements                                                                               |
| ------------------ | ------------------------------------ | -------------------------------------------------------------------------------------------------- |
| `id`               | `BIGSERIAL` PK                       | Auto-increment                                                                                     |
| `phone`            | `TEXT`                               | Normalized phone (digits + `+`). Recommend: `regexp_replace(trim(c."$phone"), '[^0-9+]', '', 'g')` |
| `campaign_name`    | `TEXT`                               | Free text label (e.g., `manualf2 campaigns` or from `campaign_map`)                                |
| `recording_id`     | `TEXT`                               | Optional. Prefer **`PR_<uuid>` extracted from URL** when present; null allowed                     |
| `url`              | `TEXT NOT NULL`                      | Source URL to the audio                                                                            |
| `url_sha1`         | `TEXT NOT NULL`                      | **Deterministic hash of `url`**; used as the primary dedupe key                                    |
| `content_sha256`   | `TEXT`                               | Optional checksum of downloaded bytes (computed after fetch)                                       |
| `started`          | `TIMESTAMPTZ`                        | Call start time (store with timezone)                                                              |
| `stopped`          | `TIMESTAMPTZ`                        | Call end time                                                                                      |
| `duration_seconds` | `DOUBLE PRECISION`                   | Optional; can compute as `EXTRACT(EPOCH FROM (stopped - started))`                                 |
| `index_in_phone`   | `INTEGER`                            | Optional sequence per phone (e.g., `row_number()` over `[phone, started]`)                         |
| `b2_object_key`    | `TEXT`                               | Destination key if uploaded to Backblaze B2                                                        |
| `local_path`       | `TEXT`                               | Local cache path; may be NULL if cleaned                                                           |
| `file_size_bytes`  | `BIGINT`                             | Optional, when known                                                                               |
| `source_table`     | `TEXT`                               | Provenance (e.g., `public.recordings`)                                                             |
| `source_row_id`    | `BIGINT`                             | Source table row id (e.g., `recordings.id`)                                                        |
| `created_at`       | `TIMESTAMPTZ NOT NULL DEFAULT now()` | Insertion timestamp                                                                                |

**Indexes/uniques**

* `uq_audio_files_recording_id` — **UNIQUE** on (`recording_id`) **WHERE `recording_id IS NOT NULL`**
* `uq_audio_files_url_sha1` — **UNIQUE** on (`url_sha1`)
* `ix_audio_files_phone` — index on (`phone`)
* `ix_audio_files_started` — index on (`started`)

> **Dedup rules:** Accept multiple rows with `recording_id = NULL`. Enforce uniqueness when `recording_id` is present (partial unique). Always enforce unique `url_sha1`.

#### `media_pipeline.transcriptions`

Exactly one transcription per audio file.

| Column              | Type                                 | Notes                                       |
| ------------------- | ------------------------------------ | ------------------------------------------- |
| `id`                | `BIGSERIAL` PK                       |                                             |
| `audio_file_id`     | `BIGINT NOT NULL`                    | **FK → `audio_files.id` ON DELETE CASCADE** |
| `provider`          | `TEXT`                               | e.g., `OpenAI`, `WhisperX`, `Mistral`       |
| `model`             | `TEXT`                               | e.g., `gpt-4o-mini-transcribe`, `large-v3`  |
| `status`            | `TEXT NOT NULL DEFAULT 'completed'`  | `pending` / `completed` / `failed`          |
| `created_at`        | `TIMESTAMPTZ NOT NULL DEFAULT now()` |                                             |
| `completed_at`      | `TIMESTAMPTZ`                        | When finished                               |
| `transcript_text`   | `TEXT`                               | Full text (unless huge)                     |
| `segments`          | `JSONB`                              | Word/segment timings                        |
| `diarization`       | `JSONB`                              | Speaker info                                |
| `metadata`          | `JSONB`                              | Extra info (language, timings, B2 keys, etc.) |
| `raw_response`      | `JSONB`                              | Full provider response (optional column)    |
| `b2_transcript_key` | `TEXT`                               | If transcript stored in B2                  |

**Unique**

* `uq_transcriptions_audio_file_id` — **UNIQUE** on (`audio_file_id`) ensuring 1:1 with `audio_files`

**Cascade behavior**

* Deleting an `audio_files` row **auto-deletes** its transcription(s).

#### `media_pipeline.transcription_failures`

Tracks last failure per audio file (for cooldowns and permanent skips).

| Column          | Type                                 | Notes                                                        |
| --------------- | ------------------------------------ | ------------------------------------------------------------ |
| `audio_file_id` | `BIGINT PRIMARY KEY`                 | FK → `audio_files.id` ON DELETE CASCADE                      |
| `provider`      | `TEXT`                               | e.g., `OpenAI`                                              |
| `model`         | `TEXT`                               | e.g., `whisper-1`                                           |
| `status`        | `TEXT`                               | `transient` or `permanent`                                   |
| `error_code`    | `INTEGER`                            | Optional HTTP/code                                           |
| `error`         | `TEXT`                               | Truncated message (~2k)                                      |
| `attempts`      | `INTEGER NOT NULL DEFAULT 1`         | Auto-incremented on upsert                                   |
| `last_attempt_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | Updated on each upsert                                       |
| `ignore_until`  | `TIMESTAMPTZ`                        | When set (transient), skip until this time                   |

Indexes:
- Consider index on `ignore_until` when querying active cooldowns.

#### `media_pipeline.transcription_claims`

Simple claim queue to prevent overlap across workers/terminals.

| Column         | Type                                 | Notes                                        |
| -------------- | ------------------------------------ | -------------------------------------------- |
| `audio_file_id`| `BIGINT PRIMARY KEY`                 | FK → `audio_files.id` ON DELETE CASCADE      |
| `claimed_by`   | `TEXT NOT NULL`                      | Hostname/worker id                           |
| `claimed_at`   | `TIMESTAMPTZ NOT NULL DEFAULT now()` |                                              |
| `expires_at`   | `TIMESTAMPTZ`                        | Claim TTL; rows auto-ignored after expiry    |

Indexes:
- `ix_transcription_claims_expires` on (`expires_at`).

---

## 3) Programmatic write patterns

### 3.1 Prereqs

* If computing `url_sha1` in SQL: enable pgcrypto once per DB

  ```sql
  CREATE EXTENSION IF NOT EXISTS pgcrypto;
  ```
* Otherwise compute hashes in code and pass them as parameters.

### 3.2 Insert (idempotent) — audio file

Use **conflict-safe** inserts. Prefer `url_sha1` for dedupe. If you also have `recording_id` (PR\_\*), it will be enforced when not null.

```sql
-- Required params: :url, :url_sha1
-- Optional params shown with COALESCE or passed NULL
INSERT INTO media_pipeline.audio_files (
  phone, campaign_name, recording_id,
  url, url_sha1, content_sha256,
  started, stopped, duration_seconds, index_in_phone,
  b2_object_key, local_path, file_size_bytes,
  source_table, source_row_id
) VALUES (
  :phone, :campaign_name, :recording_id,
  :url, :url_sha1, :content_sha256,
  :started, :stopped, :duration_seconds, :index_in_phone,
  :b2_object_key, :local_path, :file_size_bytes,
  :source_table, :source_row_id
)
ON CONFLICT (url_sha1) DO NOTHING
RETURNING id;
```

**Notes**

* If you want “generic” dedupe across any unique, you can use `ON CONFLICT DO NOTHING` (no target). Targeting `(url_sha1)` is faster and clearer.
* To compute `duration_seconds` server-side: omit it and later `UPDATE` with `EXTRACT(EPOCH FROM (stopped - started))`.

### 3.3 Insert-or-update — transcription (1:1 with audio)

Preferred (with `raw_response` column present):
```sql
INSERT INTO media_pipeline.transcriptions (
  audio_file_id, provider, model, status, created_at, completed_at,
  transcript_text, segments, diarization, metadata, raw_response, b2_transcript_key
) VALUES (
  :audio_file_id, :provider, :model, :status, now(), :completed_at,
  :transcript_text, :segments::jsonb, :diarization::jsonb, :metadata::jsonb, :raw_response::jsonb, :b2_transcript_key
)
ON CONFLICT (audio_file_id) DO UPDATE SET
  provider         = EXCLUDED.provider,
  model            = EXCLUDED.model,
  status           = EXCLUDED.status,
  completed_at     = EXCLUDED.completed_at,
  transcript_text  = EXCLUDED.transcript_text,
  segments         = EXCLUDED.segments,
  diarization      = EXCLUDED.diarization,
  metadata         = EXCLUDED.metadata,
  raw_response     = EXCLUDED.raw_response,
  b2_transcript_key= EXCLUDED.b2_transcript_key;
```

Fallback (without `raw_response` column):
```sql
INSERT INTO media_pipeline.transcriptions (
  audio_file_id, provider, model, status, created_at, completed_at,
  transcript_text, segments, diarization, metadata, b2_transcript_key
) VALUES (
  :audio_file_id, :provider, :model, :status, now(), :completed_at,
  :transcript_text, :segments::jsonb, :diarization::jsonb, :metadata::jsonb, :b2_transcript_key
)
ON CONFLICT (audio_file_id) DO UPDATE SET
  provider         = EXCLUDED.provider,
  model            = EXCLUDED.model,
  status           = EXCLUDED.status,
  completed_at     = EXCLUDED.completed_at,
  transcript_text  = EXCLUDED.transcript_text,
  segments         = EXCLUDED.segments,
  diarization      = EXCLUDED.diarization,
  metadata         = EXCLUDED.metadata,
  b2_transcript_key= EXCLUDED.b2_transcript_key;
```

### 3.4 Upsert failure (cooldown/permanent)

```sql
INSERT INTO media_pipeline.transcription_failures (
  audio_file_id, provider, model, status, error_code, error, ignore_until
) VALUES (
  :audio_file_id, :provider, :model, :status, :error_code, :error,
  CASE WHEN :status = 'transient' THEN (now() + make_interval(mins := :cooldown_minutes)) ELSE NULL END
)
ON CONFLICT (audio_file_id) DO UPDATE SET
  last_attempt_at = now(),
  attempts        = media_pipeline.transcription_failures.attempts + 1,
  status          = EXCLUDED.status,
  error_code      = EXCLUDED.error_code,
  error           = EXCLUDED.error,
  ignore_until    = EXCLUDED.ignore_until;
```

### 3.5 Claims: create/release

Create claim (example; in code this is done in bulk with a CTE):
```sql
INSERT INTO media_pipeline.transcription_claims (audio_file_id, claimed_by, expires_at)
VALUES (:audio_file_id, :claimed_by, (now() + make_interval(mins := :ttl)))
ON CONFLICT (audio_file_id) DO NOTHING;
```

Release claim:
```sql
DELETE FROM media_pipeline.transcription_claims WHERE audio_file_id = :audio_file_id;
```

### 3.4 Deriving fields (agent tips)

* **Normalize phone**: `regexp_replace(trim(phone_raw), '[^0-9+]', '', 'g')`
* **Extract `recording_id` from URL** (when URL contains `PR_<uuid>`):

  ```sql
  SELECT (regexp_match(:url, '/(PR_[^./]+)'))[1];  -- returns NULL if no match
  ```
* **Hash URL** in SQL (if pgcrypto enabled): `encode(digest(:url,'sha1'),'hex')`
* **Compute duration**: `EXTRACT(EPOCH FROM (stopped - started))`
* **Index per phone**: `row_number() OVER (PARTITION BY phone ORDER BY started)`
* **Timestamps**: always use `timestamptz`. Cast source strings: `started::timestamptz`.

---

## 4) Backfill from existing `recordings` + `contacts`

**Goal:** populate `audio_files` from current data without duplicates. Example below labels everything as `manualf2 campaigns`. Filter the `IN (...)` list or remove it to backfill all.

```sql
-- Optional: CREATE EXTENSION pgcrypto;  -- if you want to hash in SQL

WITH src AS (
  SELECT
    -- normalized phone
    regexp_replace(trim(c."$phone"), '[^0-9+]', '', 'g') AS phone,
    'manualf2 campaigns' AS campaign_name,
    -- prefer PR_<uuid> from URL; fallback to NULL
    COALESCE((regexp_match(r.location, '/(PR_[^./]+)'))[1], NULL) AS recording_id,
    r.location AS url,
    encode(digest(r.location,'sha1'),'hex') AS url_sha1,   -- or pass precomputed
    r.started::timestamptz AS started,
    r.stopped::timestamptz AS stopped,
    NULL::double precision AS duration_seconds,            -- fill later if desired
    NULL::integer AS index_in_phone,
    NULL::text AS b2_object_key,
    NULL::text AS local_path,
    NULL::bigint AS file_size_bytes,
    'public.recordings' AS source_table,
    r.id AS source_row_id
  FROM public.recordings r
  JOIN public.contacts   c ON r.contact_id = c."$id"
  WHERE c."$phone" IS NOT NULL
    AND c."$campaign_id" IN (
      'RDSFPLHE9BT68CFW','6CV8XLPGJYESMKUQ','PNUYAU4HZH6SNGVV','ZPKZDSD766UJLW59',
      '72LZE7Q2B2RQSQJ5','3SY5V6Z5C3GSXRA4','H2C8QWP35CYFC8ZM','CBDZK4LRSQRN3JMN'
    )
)
INSERT INTO media_pipeline.audio_files (
  phone, campaign_name, recording_id, url, url_sha1,
  content_sha256, started, stopped, duration_seconds, index_in_phone,
  b2_object_key, local_path, file_size_bytes, source_table, source_row_id
)
SELECT
  phone, campaign_name, recording_id, url, url_sha1,
  NULL, started, stopped, duration_seconds, index_in_phone,
  b2_object_key, local_path, file_size_bytes, source_table, source_row_id
FROM src
ON CONFLICT (url_sha1) DO NOTHING;

-- (optional) compute duration after backfill
UPDATE media_pipeline.audio_files
SET duration_seconds = EXTRACT(EPOCH FROM (stopped - started))
WHERE duration_seconds IS NULL AND started IS NOT NULL AND stopped IS NOT NULL;

-- (optional) assign index_in_phone per phone chronologically
WITH ordered AS (
  SELECT id,
         row_number() OVER (PARTITION BY phone ORDER BY started NULLS LAST) AS rn
  FROM media_pipeline.audio_files
)
UPDATE media_pipeline.audio_files a
SET index_in_phone = o.rn
FROM ordered o
WHERE a.id = o.id;
```

> Swap the campaign label to a dynamic name by `LEFT JOIN campaign_map cm ON c."$campaign_id" = cm.campaign_id` and selecting `cm.campaign`.

---

## 5) Reference read queries

### 5.1 Full call log (one row per recording) — ordered by phone, then time

```
SELECT
  a.phone,
  a.campaign_name,
  COALESCE(a.recording_id, 'N/A') AS recording_id,
  a.url AS location,
  a.duration_seconds,
  a.started,
  a.stopped
FROM media_pipeline.audio_files a
WHERE a.phone IS NOT NULL
ORDER BY a.phone, a.started NULLS LAST, a.id;
```

### 5.2 Grouped by phone — chronological URL list

```
SELECT
  a.phone,
  a.campaign_name,
  COUNT(*) AS total_recordings,
  MIN(a.started) AS first_call_time,
  MAX(a.started) AS last_call_time,
  STRING_AGG(a.url, E'\n' ORDER BY a.started NULLS LAST) AS recording_urls
FROM media_pipeline.audio_files a
GROUP BY a.phone, a.campaign_name
ORDER BY a.phone, first_call_time;
```

### 5.3 Orphan check (defensive)

```
SELECT COUNT(*) AS orphan_transcriptions
FROM media_pipeline.transcriptions t
LEFT JOIN media_pipeline.audio_files a ON a.id = t.audio_file_id
WHERE a.id IS NULL;
```

---

## 6) Operations & Safety

* **Transactions**: For multi-statement jobs, wrap in `BEGIN … COMMIT`; use `ROLLBACK` to abort. DBeaver’s Auto-commit setting controls whether you need explicit `BEGIN/COMMIT`.
* **Idempotency**: All backfills and inserts use `ON CONFLICT` so reruns won’t duplicate.
* **Time zones**: Store `started`/`stopped` as `TIMESTAMPTZ`. Cast source strings with `::timestamptz`.
* **Hashing**: `url_sha1` should be stable across runs; compute with pgcrypto or your application.
* **Resets**: To clear for re-testing: `TRUNCATE media_pipeline.transcriptions, media_pipeline.audio_files RESTART IDENTITY;`
* **Performance**: Indexes on `phone` and `started` support typical reads; `url_sha1` unique supports fast dedupe.
* **Cascade**: Verified `ON DELETE CASCADE` from `transcriptions.audio_file_id` → `audio_files.id`.
* **Claims**: Clear stuck claims (e.g., after killing workers): `DELETE FROM media_pipeline.transcription_claims;`
* **Cooldowns**: To re-enable transient failures immediately: `DELETE FROM media_pipeline.transcription_failures WHERE status='transient';`

---

## 7) Minimal API contract for an agent

When creating an audio row, the **only required fields** are `url` and `url_sha1`. All others are optional.

**Expected JSON payload (example):**

```json
{
  "phone": "+4915110635004",
  "campaign_name": "manualf2 campaigns",
  "recording_id": "PR_9f6e898f-c98b-d1d6-21c6-5a06e1db363b",
  "url": "https://vault.24dial.com/vr/PR_9f6e898f-c98b-d1d6-21c6-5a06e1db363b.mp3",
  "url_sha1": "<sha1 of url>",
  "started": "2024-10-31T10:57:01.569Z",
  "stopped": "2024-10-31T10:59:39.488Z",
  "duration_seconds": 157.919,
  "source_table": "public.recordings",
  "source_row_id": 123456
}
```

**Insert then upsert transcription:**

1. Insert audio (capture returned `id`).
2. Insert transcription with `audio_file_id = id`.
3. If reprocessing, the `ON CONFLICT (audio_file_id) DO UPDATE` path updates fields in-place.

---

## 8) Appendix — DDL (for reference)

```sql
CREATE SCHEMA IF NOT EXISTS media_pipeline;

CREATE TABLE IF NOT EXISTS media_pipeline.audio_files (
  id                BIGSERIAL PRIMARY KEY,
  phone             TEXT,
  campaign_name     TEXT,
  recording_id      TEXT,
  url               TEXT NOT NULL,
  url_sha1          TEXT NOT NULL,
  content_sha256    TEXT,
  started           TIMESTAMPTZ,
  stopped           TIMESTAMPTZ,
  duration_seconds  DOUBLE PRECISION,
  index_in_phone    INTEGER,
  b2_object_key     TEXT,
  local_path        TEXT,
  file_size_bytes   BIGINT,
  source_table      TEXT,
  source_row_id     BIGINT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_audio_files_recording_id
  ON media_pipeline.audio_files (recording_id)
  WHERE recording_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_audio_files_url_sha1
  ON media_pipeline.audio_files (url_sha1);

CREATE INDEX IF NOT EXISTS ix_audio_files_phone   ON media_pipeline.audio_files (phone);
CREATE INDEX IF NOT EXISTS ix_audio_files_started ON media_pipeline.audio_files (started);

CREATE TABLE IF NOT EXISTS media_pipeline.transcriptions (
  id                 BIGSERIAL PRIMARY KEY,
  audio_file_id      BIGINT NOT NULL REFERENCES media_pipeline.audio_files(id) ON DELETE CASCADE,
  provider           TEXT,
  model              TEXT,
  status             TEXT NOT NULL DEFAULT 'completed',
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at       TIMESTAMPTZ,
  transcript_text    TEXT,
  segments           JSONB,
  diarization        JSONB,
  metadata           JSONB,
  raw_response       JSONB,
  b2_transcript_key  TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_transcriptions_audio_file_id
  ON media_pipeline.transcriptions (audio_file_id);

-- Optional column for existing deployments
ALTER TABLE media_pipeline.transcriptions ADD COLUMN IF NOT EXISTS raw_response jsonb;

-- Failures table (cooldowns/permanent)
CREATE TABLE IF NOT EXISTS media_pipeline.transcription_failures (
  audio_file_id    BIGINT PRIMARY KEY
                   REFERENCES media_pipeline.audio_files(id) ON DELETE CASCADE,
  provider         TEXT,
  model            TEXT,
  status           TEXT,
  error_code       INTEGER,
  error            TEXT,
  attempts         INTEGER NOT NULL DEFAULT 1,
  last_attempt_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  ignore_until     TIMESTAMPTZ
);

-- Claims table (overlap prevention)
CREATE TABLE IF NOT EXISTS media_pipeline.transcription_claims (
  audio_file_id BIGINT PRIMARY KEY
                REFERENCES media_pipeline.audio_files(id) ON DELETE CASCADE,
  claimed_by    TEXT NOT NULL,
  claimed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_transcription_claims_expires
  ON media_pipeline.transcription_claims (expires_at);
```

---

**This guide is ready to hand to an AI agent.** It provides the schema, the relationships to source data, safe write/read patterns, and operational safeguards so the agent can integrate reliably.
