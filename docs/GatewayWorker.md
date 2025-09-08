## 24/7 Transcription Gateway + Worker

This document explains the architecture, endpoints, storage layout, deployment, operations, and troubleshooting for the 24/7 “gateway API + worker” that processes on‑demand transcription requests.

### High‑level
- A small HTTPS API receives a recording identifier (or exact URL), looks it up in Postgres (source of truth), downloads the audio, uploads it to Backblaze B2 with a clean path convention, and inserts a job row into `media_pipeline.audio_files`.
- A 24/7 worker watches `media_pipeline.audio_files` (scoped to the gateway area), transcribes each pending item via OpenAI, uploads transcripts to B2, and upserts `media_pipeline.transcriptions`.

Why this design:
- DB is the source of truth (derive phone/campaign via joins, not client input).
- Safe: API and worker run next to Postgres on the same server; DB is not publicly exposed.
- Reliable & idempotent: claims prevent overlap; on‑demand processing; restarts resilient.
- Clean B2 organization: predictable campaign‑based paths.

---

## Components

### 1) Gateway API (FastAPI + Uvicorn)
- Entrypoint: `chatbot_app/backend/gateway.py`
- Routers included:
  - `app.routers.transcription_router` (existing project routes)
  - `app.routers.media_router` (new gateway endpoints)
- Intentionally excludes ingestion/search/chat to avoid Chroma/sqlite constraints on Debian 11.

#### Endpoints
- POST `/api/media/transcribe`
  - Headers: `X-API-Key: <your_key>`
  - Content-Type: `application/x-www-form-urlencoded`
  - Form body (one is required):
    - `recording_id`: preferred (string; may be non‑numeric)
    - OR `url`: exact `public.recordings.location`
  - Optional body:
    - `b2_prefix`: prepends a tenant/namespace (e.g., `gateway`)
    - `phone`, `campaign`, `campaign_id`: fallbacks (DB remains the source of truth)
  - Response: `{ audio_file_id, status: "QUEUED", b2_key, b2_url }`
  - Behavior:
    1) Looks up the recording via `public.recordings` + `public.contacts` + optional `public.campaign_map`:
       - Try exact `r.id::text = :recording_id`
       - Fallback `r.location LIKE ('%' || :recording_id || '%')`
    2) Normalizes `phone` and resolves `campaign_name` from DB
    3) Downloads `url` → uploads to B2 at:
       - `[<b2_prefix>/]<campaign>/audio/<phone>/<uuid>.<ext>`
    4) Inserts `media_pipeline.audio_files` (idempotent) with:
       - `phone` (normalized), `campaign_name`, `recording_id` (text), `url`, `url_sha1`, `started`, `stopped`, `b2_object_key`, `source_table='public.recordings'`, `source_row_id` (numeric only, else NULL)

- GET `/api/media/status/{audio_file_id}`
  - Headers: `X-API-Key: <your_key>`
  - Response: `{ status: pending|completed|failed, transcript, metadata }`
  - `metadata` includes `b2_transcript_json_key` and `b2_transcript_txt_key` when completed.

### 2) Worker (`data_pipelines.scripts.transcribe_gpt4o`)
- Service runs module mode: `python -m data_pipelines.scripts.transcribe_gpt4o`.
- Scoped to the gateway area with `--b2-prefix gateway/` so it only processes API‑created jobs.
- Uses DB selection + claims:
  - Pending = `media_pipeline.audio_files` row with no completed row in `media_pipeline.transcriptions`.
  - Claims prevent overlap across workers; TTL auto‑expires.
- Small batch size: `--max-files 1 --max-workers 2` for on‑demand behavior.
- Uploads transcripts to B2 and upserts DB results.

### 3) B2 layout
- Audio upload (by API):
  - `[<b2_prefix>/]<campaign>/audio/<phone>/<uuid>.<ext>`
  - Typical production prefix: `b2_prefix=gateway` adds a top‑level namespace.
- Transcript upload (by worker):
  - `<campaign>/transcriptions/json/<rest>.json`
  - `<campaign>/transcriptions/txt/<rest>.txt`
  - Note: transcripts mirror the audio’s path under the campaign, not the gateway prefix.

### 4) DB schema (relevant)
- `media_pipeline.audio_files` — job catalog (see `media_pipeline_psql_setup.md`)
- `media_pipeline.transcriptions` — 1:1 results with metadata and optional `raw_response`
- `media_pipeline.transcription_claims` — claim queue
- `media_pipeline.transcription_failures` — cooldown/permanent failure tracking

---

## Deployment

### Server (Contabo)
- Reverse proxy (Caddy) on :80/:443:
```
transcribe.vertikon.ltd {
	encode gzip
	reverse_proxy 127.0.0.1:8000
}
```

- API service (systemd): `/etc/systemd/system/transcribe-api.service`
```
[Unit]
Description=Transcription Gateway (Uvicorn)
After=network.target

[Service]
WorkingDirectory=/opt/transcribe/transcription/chatbot_app/backend
EnvironmentFile=/opt/transcribe/transcription/.env
ExecStart=/opt/transcribe/transcription/chatbot_app/backend/.venv/bin/uvicorn gateway:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
User=emilios
Group=emilios

[Install]
WantedBy=multi-user.target
```

- Worker service (systemd): `/etc/systemd/system/transcribe-worker.service`
```
[Unit]
Description=Transcription Worker
After=network.target

[Service]
WorkingDirectory=/opt/transcribe/transcription
Environment=PYTHONPATH=/opt/transcribe/transcription
EnvironmentFile=/opt/transcribe/transcription/.env
ExecStart=/opt/transcribe/transcription/chatbot_app/backend/.venv/bin/python -m data_pipelines.scripts.transcribe_gpt4o --b2-prefix gateway/ --output-dir /opt/transcribe/transcription/data_pipelines/data/transcriptions/whisper1 --model whisper-1 --timestamps segment --select-from-db --use-claims --claim-ttl-minutes 60 --db-skip-existing --only-new --skip-failed --cooldown-minutes 60 --max-files 1 --max-workers 2 --upload-transcripts-to-b2 --b2-out-prefix transcriptions/json --upload-transcripts-txt-to-b2 --b2-out-txt-prefix transcriptions/txt --no-local-save --no-head
Restart=always
RestartSec=5
User=emilios
Group=emilios

[Install]
WantedBy=multi-user.target
```

### Environment (`/opt/transcribe/transcription/.env`)
```
OPENAI_API_KEY=...
GOOGLE_API_KEY=dummy-ok
DATABASE_URL=postgresql+asyncpg://postgres:<PASS>@localhost:5432/<DBNAME>
BACKBLAZE_B2_S3_ENDPOINT=https://s3.eu-central-003.backblazeb2.com
BACKBLAZE_B2_BUCKET=campaign-analysis
BACKBLAZE_B2_KEY_ID=...
BACKBLAZE_B2_APPLICATION_KEY=...
API_KEY=<long_random_token>
```

---

## Operations

### Client usage
- Submit (recording_id):
```
curl -H "X-API-Key: <key>" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     --data "recording_id=<RID>&b2_prefix=gateway" \
     https://transcribe.vertikon.ltd/api/media/transcribe
```
- Submit (url):
```
curl -H "X-API-Key: <key>" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     --data "url=<URL>&b2_prefix=gateway" \
     https://transcribe.vertikon.ltd/api/media/transcribe
```
- Poll:
```
curl -H "X-API-Key: <key>" \
     https://transcribe.vertikon.ltd/api/media/status/<audio_file_id>
```

### Routine ops
- Update code & restart:
```
cd /opt/transcribe/transcription && git pull
sudo systemctl restart transcribe-api transcribe-worker
```
- Logs:
```
journalctl -u transcribe-api -n 200 -f
journalctl -u transcribe-worker -n 200 -f
```
- Clear claims (stuck):
```
DELETE FROM media_pipeline.transcription_claims;
```
- Clear transient cooldowns:
```
DELETE FROM media_pipeline.transcription_failures WHERE status='transient';
```

---

## Troubleshooting (common)

- 404 at `/`: normal — use `/docs` or `/api/*`.
- Chroma/sqlite errors on Debian 11: avoided by using minimal `gateway.py` (do not import search/ingestion routes).
- asyncpg + `sslmode=disable`: remove `?sslmode=disable` from `DATABASE_URL`.
- SQL CONCAT param type error: use `('%' || :rid || '%')` instead of `CONCAT('%', :rid, '%')`.
- Non‑numeric `recordings.id`: treat as text; only cast to int for `source_row_id` if numeric.
- “Provide file or url”: you’re hitting an old handler — restart `transcribe-api` and verify `/openapi.json` shows `recording_id`/`url`.
- “Current command vanished”: restart the unit after editing the systemd file.
- Import errors for worker: ensure `data_pipelines/__init__.py` and `data_pipelines/scripts/__init__.py`; set `PYTHONPATH` to the directory that contains `data_pipelines`.

---

## Improvements (future work)

- Default gateway prefix via env (e.g., `GATEWAY_B2_PREFIX=gateway`) so clients don’t need to pass `b2_prefix`.
- Add a proper `company` column to `media_pipeline.audio_files` instead of overloading campaign names for alt grouping.
- Rerun endpoint (`/api/media/rerun/{audio_file_id}`) to requeue failed jobs.
- Webhook callback on completion; optional Slack/email notifications.
- Basic rate‑limiting per API key; size/format validation.
- Health/metrics endpoints; Prometheus/Alerting.
- Dockerize + CI/CD for simpler deploys/rollbacks.
- Tests for DB lookup (recording_id/url) and B2 path construction.

---

## Quick Checklist

1) Verify DNS & HTTPS (`/docs` should load)
2) Confirm `.env` (no `sslmode=disable` with asyncpg)
3) API service running (`transcribe-api`)
4) Worker service running and scoped to `gateway/`
5) Submit → Poll → Verify DB & B2 paths

This system is designed to be robust, minimal, and easy for teammates to understand and operate. Hand this doc to any engineer to quickly orient themselves and safely extend the pipeline.


