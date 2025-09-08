## User Instruction Manual — Audio Download and Transcription Pipelines

This guide explains how to:
- Connect to the remote Postgres DB through SSH
- Download audio from a CSV to Backblaze B2 and catalog to SQL
- Transcribe audio from B2 and save results to SQL and B2

Assumes Windows PowerShell and a cloned repo at `C:\Users\<you>\Projects\transcription`.

---

### 0) Prerequisites
- Python v3.10+ and a virtualenv with project requirements installed
- A `.env` file in the project root containing Backblaze credentials (or AWS-compatible):
  - `BACKBLAZE_B2_S3_ENDPOINT`, `BACKBLAZE_B2_REGION`
  - `BACKBLAZE_B2_KEY_ID`, `BACKBLAZE_B2_APPLICATION_KEY`
  - `BACKBLAZE_B2_BUCKET` (e.g., `campaign-analysis`)
- OpenAI key (for transcription): `OPENAI_API_KEY`

---

### 1) SSH tunnel to Postgres

Create `~/.ssh/config` (Windows: `C:\Users\<you>\.ssh\config`) with:
```
Host manuav-db
  HostName 173.249.24.215
  User emilios
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
  ServerAliveInterval 60
  ServerAliveCountMax 3
  TCPKeepAlive yes
  ExitOnForwardFailure yes
  LocalForward 5433 localhost:5432
```

Start the tunnel (foreground):
```powershell
ssh -N manuav-db
```

Or keep it running in background (auto-restart loop):
```powershell
Start-Job -Name manuavTunnel -ScriptBlock {
  while ($true) { try { ssh -q -N manuav-db } catch {}; Start-Sleep 5 }
}
# Check / stop
Get-Job manuavTunnel
Stop-Job manuavTunnel; Remove-Job manuavTunnel
```

Set a robust DB URL in your shell (with keepalives):
```powershell
$env:DATABASE_URL = "postgresql+psycopg2://postgres:Kii366@localhost:5433/manuav?keepalives=1&keepalives_idle=60&keepalives_interval=30&keepalives_count=5"
```

Quick DB connectivity test:
```powershell
python - << 'PY'
from sqlalchemy import create_engine, text
e = create_engine("postgresql+psycopg2://postgres:Kii366@localhost:5433/manuav")
with e.connect() as c:
  print(c.execute(text("select current_database(), current_user")).fetchone())
PY
```

---

### 2) Download audio from CSV → B2 → SQL (media_pipeline.audio_files)

Script: `data_pipelines/scripts/download_audio_from_csv.py`

What it does:
- Reads CSV rows (`phone`, `campaign_name`, `recording_id` optional, `url`, `duration_seconds`, `started`, `stopped`, `recordings_row_id`)
- Downloads audio to a temp folder, uploads to B2, removes the local copy
- Inserts a row into `media_pipeline.audio_files` with dedupe by `url_sha1`
- Sets `source_row_id` from CSV `recordings_row_id` (provenance). `source_table` is left NULL by design

Concurrency (faster runs):
- Use `--max-workers N` to process phones in parallel (start with 4; try 6–8 if stable).
- Each phone still preserves its own file order; different phones run concurrently.
- Network ops (download/upload) are retried with exponential backoff; DB inserts remain idempotent via `url_sha1`.

Dry run (no downloads/DB writes):
```powershell
python data_pipelines\scripts\download_audio_from_csv.py `
  --csv-path "data_pipelines\data\sql imports\<your_file>.csv" `
  --dry-run `
  --output-root "data_pipelines\data\audio_tmp"
```

Small batch (limit N):
```powershell
python data_pipelines\scripts\download_audio_from_csv.py `
  --csv-path "data_pipelines\data\sql imports\<your_file>.csv" `
  --db-url "$env:DATABASE_URL" `
  --table-name "media_pipeline.audio_files" `
  --output-root "data_pipelines\data\audio_tmp" `
  --upload-to-b2 `
  --b2-prefix "dexter/audio" `
  --remove-local-after-upload `
  --max-workers 4 `
  --limit 200
```

Full run (no limit):
```powershell
python data_pipelines\scripts\download_audio_from_csv.py `
  --csv-path "data_pipelines\data\sql imports\<your_file>.csv" `
  --db-url "$env:DATABASE_URL" `
  --table-name "media_pipeline.audio_files" `
  --output-root "data_pipelines\data\audio_tmp" `
  --upload-to-b2 `
  --b2-prefix "dexter/audio" `
  --remove-local-after-upload `
  --max-workers 4
```

Verification (SQL):
```sql
SELECT COUNT(*) AS total_for_prefix
FROM media_pipeline.audio_files
WHERE b2_object_key LIKE 'dexter/audio/%';

SELECT id, phone, campaign_name, b2_object_key, source_row_id, created_at
FROM media_pipeline.audio_files
WHERE b2_object_key LIKE 'dexter/audio/%'
ORDER BY id DESC
LIMIT 20;

-- Dedupe guard (should be zero rows)
SELECT url_sha1, COUNT(*) c
FROM media_pipeline.audio_files
WHERE b2_object_key LIKE 'dexter/audio/%'
GROUP BY url_sha1 HAVING COUNT(*) > 1;
```

Resuming after interruption:
- Just re-run the same command (no `--limit`). Existing rows are skipped by `url_sha1` and/or local file presence.

Filtering and caps (important):
- `--only-new` filters rows against the DB first (by `url_sha1`). Dry-run prints nothing if that slice is already in the DB.
- `--limit N` limits the first N CSV rows before filtering. Use it only when you truly want “first N rows”.
- `--max-files N` caps after `--only-new` and preserves phone groups. It selects about N new files anywhere in the CSV without splitting a phone, then stops.

Failure tracking and skipping (recommended for large runs):
- Enable a small failure cache so the downloader avoids re-trying dead links.
- Table: `media_pipeline.audio_failures (url_sha1 PK, url, first_seen_at, last_attempt_at, attempts, status, http_status, error, ignore_until)`
  - `status='permanent'` (e.g., 404) → skipped forever
  - `status='transient'` → skipped until `ignore_until` (cooldown) passes
- Flags:
  - `--skip-failed` — exclude cached failures (permanent or cooling down) from `--only-new`
  - `--cooldown-minutes 60` — how long to wait before retrying transient failures
- Example:
```powershell
python data_pipelines\scripts\download_audio_from_csv.py `
  --csv-path "data_pipelines\data\sql imports\<your_file>.csv" `
  --db-url "$env:DATABASE_URL" `
  --table-name "media_pipeline.audio_files" `
  --output-root "data_pipelines\data\audio_tmp" `
  --upload-to-b2 `
  --b2-prefix "dexter/audio" `
  --remove-local-after-upload `
  --only-new `
  --skip-failed `
  --cooldown-minutes 60 `
  --max-files 2000 `
  --max-workers 4
```

Cap total new files without splitting a phone (`--max-files`):
```powershell
python data_pipelines\scripts\download_audio_from_csv.py `
  --csv-path "data_pipelines\data\sql imports\<your_file>.csv" `
  --db-url "$env:DATABASE_URL" `
  --table-name "media_pipeline.audio_files" `
  --output-root "data_pipelines\data\audio_tmp" `
  --upload-to-b2 `
  --b2-prefix "dexter/audio" `
  --remove-local-after-upload `
  --only-new `
  --max-files 2000 `
  --max-workers 4
```

Resume helpers (when the first N CSV rows are already done):
- Resume by DB difference (recommended): process only rows not yet in the DB by `url_sha1`.
  ```powershell
  python data_pipelines\scripts\download_audio_from_csv.py \
    --csv-path "data_pipelines\data\sql imports\<your_file>.csv" \
    --db-url "$env:DATABASE_URL" \
    --table-name "media_pipeline.audio_files" \
    --output-root "data_pipelines\data\audio_tmp" \
    --upload-to-b2 \
    --b2-prefix "dexter/audio" \
    --remove-local-after-upload \
    --only-new \
    --max-workers 4
  ```
- Resume by position (skip first N rows in the CSV):
  ```powershell
  python data_pipelines\scripts\download_audio_from_csv.py \
    --csv-path "data_pipelines\data\sql imports\<your_file>.csv" \
    --db-url "$env:DATABASE_URL" \
    --table-name "media_pipeline.audio_files" \
    --output-root "data_pipelines\data\audio_tmp" \
    --upload-to-b2 \
    --b2-prefix "dexter/audio" \
    --remove-local-after-upload \
    --csv-start-index 50000 \
    --limit 2000 \
    --max-workers 4
  ```

Ordering mitigation (when to run):
- If you ran with `--max-workers` and you rely on strict per‑phone chronological ordering, recompute `index_in_phone` once after a large ingest:
```sql
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

---

### 3) Transcribe from B2 → SQL (media_pipeline.transcriptions) and B2 (JSON/TXT)

Script: `data_pipelines/scripts/transcribe_gpt4o.py`

What it does:
- Scans B2 under a prefix for audio keys
- Downloads each to temp, optional preprocess, sends to OpenAI transcription API
- Saves raw JSON locally and uploads to B2; also uploads plain `.txt`
- Upserts `media_pipeline.transcriptions` for each audio file

#### Best practice: multi-terminal run with claims (fast and safe)

Use DB-driven selection with claims to split the work across 3–5 terminals without overlap. The probe excludes claims so it won’t hold items during a dry-run.

Prereqs:
- Ensure `$env:DATABASE_URL` is set and reachable (see section 1). Ensure `OPENAI_API_KEY` and Backblaze envs are set or present in `.env`.
- Columns: optional `raw_response` JSONB in `media_pipeline.transcriptions` if you want full API responses stored.

Recommended loop (PowerShell):
```powershell
$common = @(
  '--b2-prefix','dexter/audio',
  '--bucket','campaign-analysis',
  '--output-dir','data_pipelines\\data\\transcriptions\\whisper1',
  '--model','whisper-1','--timestamps','segment',
  '--language','de','--prompt-file','data_pipelines/whisper_dexter_prompt',
  '--db-url',"$env:DATABASE_URL",
  '--db-audio-table','media_pipeline.audio_files',
  '--db-transcriptions-table','media_pipeline.transcriptions',
  '--db-skip-existing','--only-new','--skip-failed','--cooldown-minutes','60',
  '--max-workers','4',
  '--upload-transcripts-to-b2','--b2-out-prefix','dexter/transcriptions/json',
  '--upload-transcripts-txt-to-b2','--b2-out-txt-prefix','dexter/transcriptions/txt',
  '--no-local-save',
  '--require-db','--db-failure-threshold','3',
  '--select-from-db','--use-claims','--claim-ttl-minutes','60','--no-head'
)
$probeArgs = $common | Where-Object { $_ -ne '--use-claims' }
while ($true) {
  python data_pipelines\\scripts\\transcribe_gpt4o.py @common --max-files 1000
  $probe = (python data_pipelines\\scripts\\transcribe_gpt4o.py @probeArgs --max-files 1 --dry-run) | Select-String 'Selected: '
  if (-not $probe) { break }
  Start-Sleep -Seconds 5
}
```

How it works and tips:
- `--select-from-db` builds the candidate set directly from SQL (fast) and preserves whole `<phone>/` groups; `--max-files` is an approximate cap not splitting the last phone.
- `--use-claims` ensures each terminal claims different files; no overlap. Claims expire after `--claim-ttl-minutes` if a terminal dies.
- The probe removes `--use-claims` so the dry-run does not claim items.
- Concurrency: start with 2–3 terminals or reduce `--max-workers` if you see 429/timeouts; increase cautiously if stable.
- Keep `--no-local-save` if you only need uploads; logs and `_summary.json` still write under `--output-dir/run_.../`.
- If you need preprocessing, add `--preprocess ...` flags; it adds CPU time before the API call.

Recommended settings (Whisper-1, gentle preprocessing, prompt, resume, nested outputs):
```powershell
python data_pipelines\scripts\transcribe_gpt4o.py `
  --b2-prefix "dexter/audio" `
  --output-dir "data_pipelines\data\transcriptions\whisper1" `
  --model "whisper-1" `
  --timestamps segment `
  --language de `
  --prompt-file "data_pipelines/whisper_dexter_prompt" `
  --preprocess --pp-sr 16000 --pp-mono 1 --pp-trim-sec 0.5 --pp-trim-db -55 `
  --tail-guard --tg-max-no-speech 0.8 --tg-min-avg-logprob -1.2 --tg-max-seg-sec 1.0 `
  --bucket "$env:BACKBLAZE_B2_BUCKET" `
  --db-url "$env:DATABASE_URL" `
  --db-audio-table "media_pipeline.audio_files" `
  --db-transcriptions-table "media_pipeline.transcriptions" `
  --db-skip-existing `
  --only-new `
  --skip-failed `
  --cooldown-minutes 60 `
  --max-workers 6 `
  --max-files 50 `
  --upload-transcripts-to-b2 `
  --b2-out-prefix "dexter/transcriptions/json" `
  --upload-transcripts-txt-to-b2 `
  --b2-out-txt-prefix "dexter/transcriptions/txt" `
  --no-local-save
```

What’s written to SQL (per row):
- `provider = 'OpenAI'`
- `model = 'whisper-1'` (from `--model`)
- `status` (pending → completed/failed), `created_at` (DB default), `completed_at` (set on finish)
- `transcript_text = data.text` (plain text)
- `segments = {"segments": data.segments}` when present (timestamps and confidences from verbose_json)
- `diarization = NULL` (not produced here)
- `metadata` JSON includes language, bucket, audio `b2_key`, size_bytes, timings, error, `b2_transcript_json_key`, `b2_transcript_txt_key`
- `b2_transcript_key` column set to the JSON B2 key
- `raw_response` JSONB — if the column exists, the full API JSON is stored

Verification (SQL):
```sql
SELECT t.id, a.b2_object_key AS audio_key, t.status, t.model, t.completed_at,
       t.b2_transcript_key,
       t.metadata->>'b2_transcript_json_key' AS json_key,
       t.metadata->>'b2_transcript_txt_key'  AS txt_key,
       LEFT(t.transcript_text, 120) AS preview
FROM media_pipeline.transcriptions t
JOIN media_pipeline.audio_files a ON a.id = t.audio_file_id
ORDER BY t.id DESC
LIMIT 20;

-- Ensure raw_response is stored
SELECT t.id, jsonb_typeof(t.raw_response) AS raw_type
FROM media_pipeline.transcriptions t
ORDER BY t.id DESC
LIMIT 5;
```

Full run: remove `--max-files 50` and re-run the same command.

Skipping already-completed rows: add `--db-skip-existing` to skip audio that already have `status = 'completed'` in `transcriptions`.
Resume after tunnel drop: once the tunnel is back, the script reconnects automatically. If the run aborted, just re-run with `--db-skip-existing` to fill any gaps.

Key arguments explained (simple):
- `--b2-prefix`: where audio lives in the bucket (e.g., `dexter/audio/<phone>/<file>`).
- `--output-dir`: local folder where JSON results are written before upload; each run writes into `run_YYYYMMDD_HHMMSSZ/`.
- `--model`: transcription model, e.g., `whisper-1`.
- `--timestamps`: `segment`, `word`, `both`, or `none`.
- `--language`: language hint (e.g., `de`).
- `--prompt` / `--prompt-file`: short domain list to bias recognition (Whisper supports this).
- `--db-url`: Postgres connection (use your tunneled URL with keepalives). If omitted, the script uses `DATABASE_URL` env var.
- `--db-audio-table` / `--db-transcriptions-table`: target tables.
- `--db-skip-existing`: skip items that already have completed transcriptions.
- `--upload-transcripts-to-b2` / `--b2-out-prefix`: upload JSON transcripts and set their B2 folder.
- `--upload-transcripts-txt-to-b2` / `--b2-out-txt-prefix`: upload TXT transcripts and set their B2 folder.
- `--no-local-save`: do not write per-file JSON/TXT locally; `_log.jsonl` and `_summary.json` are still written.
- `--preprocess`, `--pp-*`: optional gentle normalization (16 kHz, mono) and optional light tail trim.
- `--tail-guard`: gentle last-segment drop if likely silence/noise.
- `--max-workers`: concurrent transcription workers (start with 4; if stable try 6–8).
- `--only-new`: skip audio that already have a completed transcription in the DB.
- `--max-files`: cap total items to process after DB filtering.
- `--skip-failed`: skip items recorded in `media_pipeline.transcription_failures` (permanent or cooling down).
- `--cooldown-minutes`: how long transient failures are ignored before retrying.

### Quick recipes (copy/paste)

- Full run (standard)
```powershell
python data_pipelines\scripts\transcribe_gpt4o.py `
  --b2-prefix "dexter/audio" `
  --output-dir "data_pipelines\data\transcriptions\whisper1" `
  --model "whisper-1" --timestamps segment `
  --language de --prompt-file "data_pipelines/whisper_dexter_prompt" `
  --preprocess --pp-sr 16000 --pp-mono 1 --pp-trim-sec 0.5 --pp-trim-db -55 `
  --tail-guard `
  --db-skip-existing --only-new --skip-failed --cooldown-minutes 60 `
  --max-workers 6 `
  --upload-transcripts-to-b2 --b2-out-prefix "dexter/transcriptions/json" `
  --upload-transcripts-txt-to-b2 --b2-out-txt-prefix "dexter/transcriptions/txt" `
  --no-local-save `
  --require-db --halt-on-db-error --db-failure-threshold 3
```

- Small incremental batch (~N new files; preserves phone groups)
```powershell
python data_pipelines\scripts\transcribe_gpt4o.py `
  --b2-prefix "dexter/audio" `
  --output-dir "data_pipelines\data\transcriptions\whisper1" `
  --model "whisper-1" --timestamps segment `
  --db-skip-existing --only-new --skip-failed --cooldown-minutes 60 `
  --max-workers 2 --max-files 5 `
  --upload-transcripts-to-b2 --b2-out-prefix "dexter/transcriptions/json" `
  --upload-transcripts-txt-to-b2 --b2-out-txt-prefix "dexter/transcriptions/txt" `
  --no-local-save --require-db --halt-on-db-error --db-failure-threshold 3
```

- Dry-run (see what would be selected)
```powershell
python data_pipelines\scripts\transcribe_gpt4o.py ... --dry-run
```

- Per-phone slice
```powershell
python data_pipelines\scripts\transcribe_gpt4o.py ... --b2-prefix "dexter/audio/+41449051141"
```

- Tail live logs for the newest run
```powershell
$run = Get-ChildItem "data_pipelines\data\transcriptions\whisper1" -Directory |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content (Join-Path $run.FullName "_log.jsonl") -Wait
```

- Verify DB writes (recent rows)
```sql
SELECT t.id, t.status, t.model, t.completed_at,
       a.b2_object_key, t.b2_transcript_key,
       LEFT(COALESCE(t.transcript_text,''), 120) AS preview
FROM media_pipeline.transcriptions t
JOIN media_pipeline.audio_files a ON a.id=t.audio_file_id
ORDER BY t.id DESC
LIMIT 20;
```

- Resume check (no dupes, remaining work)
```sql
-- should be zero
SELECT audio_file_id, COUNT(*) c
FROM media_pipeline.transcriptions
GROUP BY audio_file_id HAVING COUNT(*)>1;

SELECT COUNT(*) AS remaining
FROM media_pipeline.audio_files a
LEFT JOIN media_pipeline.transcriptions t ON t.audio_file_id=a.id AND t.status='completed'
WHERE a.b2_object_key LIKE 'dexter/audio/%' AND t.id IS NULL;
```

- Failure cache test
```powershell
$env:OPENAI_API_KEY = "bad"
python data_pipelines\scripts\transcribe_gpt4o.py ... --b2-prefix "dexter/audio/+41449051141" --max-workers 1 --max-files 1 --require-db --halt-on-db-error
Remove-Item Env:OPENAI_API_KEY
python data_pipelines\scripts\transcribe_gpt4o.py ... --b2-prefix "dexter/audio/+41449051141" --max-workers 1 --max-files 1 --require-db --halt-on-db-error
```
```sql
SELECT status, attempts, ignore_until, LEFT(error,160)
FROM media_pipeline.transcription_failures
ORDER BY last_attempt_at DESC LIMIT 5;
```

Notes:
- Selection preserves whole `<phone>/` groups; `--max-files` is an approximate cap.
- Outputs mirror audio paths in B2 to avoid filename collisions.
- Each run writes to `--output-dir/run_YYYYMMDD_HHMMSSZ/` for logs and summary.

---

### 4) Troubleshooting
- Tunnel drops: keep-alive job above; add DB keepalives in the URL; scripts enable connection pre_ping and recycle.
  - After a tunnel drop mid-run: when the tunnel returns, new DB checkouts auto‑reconnect and the job typically continues.
  - Any statements in-flight at the moment of the drop may have failed. It’s safe to re-run to fill gaps.
  - Use the same flags you normally use (e.g., downloader: `--only-new`, transcriber: `--db-skip-existing`).
  - Quick sanity check:
    ```sql
    SELECT COUNT(*) FROM media_pipeline.audio_files
    WHERE b2_object_key LIKE 'dexter/audio/%';
    ```
- Wrong DB: compare `$env:DATABASE_URL` host:port:db with what you see in DBeaver; re-run with the correct `--db-url` override.
- Schema missing: the downloader auto-creates `media_pipeline` if absent. If you still see errors, you’re likely on a different DB.
- Permissions: grant on schema/tables if your user is not owner.
- URL quoting: in PowerShell, avoid double-quoted URLs with `$` in passwords; URL-encode or use single quotes.

Additional tips:
- B2 outputs mirror audio folder structure to avoid filename collisions: `dexter/transcriptions/json/<phone>/<file>.json` and similarly for TXT.
- Per-run subfolders: each run writes to `--output-dir/run_YYYYMMDD_HHMMSSZ/` so summaries/logs don’t overwrite.
- DB URL fallback: if `--db-url` is omitted, the script uses `DATABASE_URL` from the environment.

---

### 5) Reference files
- Downloader: `data_pipelines/scripts/download_audio_from_csv.py`
- Transcriber: `data_pipelines/scripts/transcribe_gpt4o.py`
- Ingestion runbook (deeper details): `data_pipelines/INGESTION_RUNBOOK.md`

---

## Appendix — Frequently Asked Questions (Q&A)

### Q: How do I verify I’m connected to the correct database (schema exists)?
- Print the URL in your shell: `$env:DATABASE_URL`
- Quick Python check:
  ```powershell
  python - << 'PY'
  import os
  from sqlalchemy import create_engine, text
  url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg","postgresql+psycopg2").strip('"')
  e = create_engine(url)
  with e.connect() as c:
      print(c.execute(text("select current_database(), current_user")).fetchone())
      has_schema = c.execute(text("select exists(select 1 from information_schema.schemata where schema_name='media_pipeline')")).scalar()
      print("has_media_pipeline =", has_schema)
  PY
  ```

### Q: What’s a B2 prefix vs bucket? Where are transcripts written?
- `BACKBLAZE_B2_BUCKET` is the bucket name (e.g., `campaign-analysis`).
- `--b2-prefix` determines where audio lives, e.g. `dexter/audio/<phone>/<filename>`.
- `--b2-out-prefix` is where transcript JSONs are uploaded, e.g. `dexter/transcriptions/json/<file>.json`.
- `--b2-out-txt-prefix` is where plain text transcripts are uploaded, e.g. `dexter/transcriptions/txt/<file>.txt`.

### Q: Will the downloader resume and skip already-processed rows?
- Yes. It checks `url_sha1` (and `recording_id` when present) in `media_pipeline.audio_files` and skips existing rows.
- If you use `--limit 10`, it always examines only the first 10 CSV rows. Remove `--limit` (or set higher) to continue past row 10.

### Q: I uploaded to the wrong B2 prefix. How do I fix it?
- Delete those objects in B2 under the wrong prefix and delete the matching DB rows:
  ```sql
  DELETE FROM media_pipeline.audio_files
  WHERE b2_object_key LIKE '<wrong-prefix>/%';
  ```
- Re-run the downloader with the correct `--b2-prefix`.

### Q: Neon vs local database — why don’t I see new rows in DBeaver?
- Your `.env` might point to Neon while DBeaver is on local. Override with `--db-url` or set `$env:DATABASE_URL` to the tunneled local URL.

### Q: What does the transcription job write to SQL?
- `provider` (OpenAI), `model` (e.g., `whisper-1`), `status`, `created_at`, `completed_at`,
  `transcript_text`, `segments` (JSONB), `metadata` (JSONB), `b2_transcript_key`, and `raw_response` (JSONB if the column exists).
- `segments` includes per-segment times and (if requested) words with timestamps. Full raw response is also stored/uploaded.

### Q: How do I store the full raw response?
- Ensure the column exists once:
  ```sql
  ALTER TABLE media_pipeline.transcriptions ADD COLUMN IF NOT EXISTS raw_response jsonb;
  ```
- The transcribe script will then save it automatically.

### Q: Can Whisper-1 use a prompt to improve names/terms?
- Yes. Use `--prompt "..."` or `--prompt-file "data_pipelines/whisper_dexter_prompt"`.
- The prompt used is saved into `metadata.prompt` for traceability.

### Q: Where do we store segment confidences and word-level timestamps?
- In `segments` (JSONB) and in `raw_response` (JSONB). No extra columns are needed unless you want SQL-native analytics.

### Q: What preprocessing should I use?
- Clean audio: leave preprocessing off; add `--language de` and a concise prompt.
- Noisy/phone audio: enable `--preprocess --pp-sr 16000 --pp-mono 1` and optional tail trim `--pp-trim-sec 0.5 --pp-trim-db -55`.
- Optional `--tail-guard` to drop an obviously non-speech last segment.

### Q: My SSH tunnel dropped mid-run. How do I make it robust?
- Keepalive job in PowerShell:
  ```powershell
  Start-Job -Name manuavTunnel -ScriptBlock { while ($true) { try { ssh -q -N manuav-db } catch {}; Start-Sleep 5 } }
  ```
- Use DB keepalives in the URL: `?keepalives=1&keepalives_idle=60&keepalives_interval=30&keepalives_count=5`.
- Scripts already enable `pool_pre_ping` and `pool_recycle` to survive idle drops.


