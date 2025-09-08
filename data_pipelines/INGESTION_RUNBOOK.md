## CSV → Backblaze B2 → media_pipeline.audio_files Runbook

This runbook explains how to ingest call audio listed in a CSV, upload each file to Backblaze B2, and record rows in the `media_pipeline.audio_files` table. It is written for quick, safe, repeatable runs.

### What this pipeline does
- Reads a CSV with columns like: `phone`, `campaign_name`, `recordings_row_id`, `url`, `duration_seconds`, `started`, `stopped`.
- Downloads each `url` temporarily, uploads it to B2 under a folder-like key, then removes the local file.
- Inserts a row into `media_pipeline.audio_files` for each item with:
  - `phone`, `campaign_name`, `recording_id` (if present), `url`, `url_sha1` (full SHA-1 of URL),
  - `started`, `stopped`, `duration_seconds`,
  - `b2_object_key` (the uploaded path inside the bucket), `file_size_bytes`,
  - `source_row_id` (from CSV `recordings_row_id`),
  - `source_table` left NULL by design (optional provenance).

Idempotency: the script computes a full SHA‑1 of `url` and checks before inserting. If a row already exists (same `url_sha1`), it skips inserting and avoids re-uploading for those rows in subsequent runs.

---

### Prerequisites
- Python environment with repo requirements installed.
- `.env` file containing:
  - `DATABASE_URL` — e.g. `postgresql+psycopg2://user:pass@host:port/db`.
  - Backblaze/S3-compatible credentials (either BACKBLAZE_* or AWS_*):
    - `BACKBLAZE_B2_S3_ENDPOINT` (or `AWS_ENDPOINT_URL`)
    - `BACKBLAZE_B2_REGION` (or `AWS_REGION`)
    - `BACKBLAZE_B2_KEY_ID` (or `AWS_ACCESS_KEY_ID`)
    - `BACKBLAZE_B2_APPLICATION_KEY` (or `AWS_SECRET_ACCESS_KEY`)
    - `BACKBLAZE_B2_BUCKET` (or `B2_BUCKET_NAME`) — e.g. `campaign-analysis`

The downloader loads `.env` automatically for B2. You still provide the DB URL via `--db-url` (you can pass `$env:DATABASE_URL`).

---

### Quick full-run (production) command

If you are using the remote Postgres over an SSH tunnel:

1) Open the tunnel in a separate terminal and keep it running:

```powershell
ssh -o ExitOnForwardFailure=yes -L 5433:localhost:5432 emilios@173.249.24.215 -N
```

2) Run the full ingestion with the recommended prefix (no spaces):

```powershell
python data_pipelines\scripts\download_audio_from_csv.py \
  --csv-path "data_pipelines\data\sql imports\Dexter_Campaigns_another_but_this_time_with_the_one_off_archived_mappings_SELECT_202508271751.csv" \
  --db-url "postgresql+psycopg2://postgres:Kii366@localhost:5433/manuav" \
  --table-name "media_pipeline.audio_files" \
  --output-root "data_pipelines\data\audio_tmp" \
  --upload-to-b2 \
  --b2-prefix "dexter-audio" \
  --remove-local-after-upload
```

Notes:
- Prefix recommendation: use `dexter-audio` (hyphenated). Tools behave better than with spaces.
- If you store the URL in an env var on Windows PowerShell, avoid quoting the whole URL and URL‑encode special characters in the password (e.g., `$passEsc = [System.Uri]::EscapeDataString('P@ss;word')`).

---

### Script
`data_pipelines/scripts/download_audio_from_csv.py`

- Accepts `url` (or legacy `location`) as the audio URL column.
- Copies CSV `recordings_row_id` → `source_row_id` in `media_pipeline.audio_files`.
- Computes a full `url_sha1` for deduplication.
- Organization in B2: keys look like `audio/<prefix>/<phone>/<filename>.mp3`. The file name encodes ordering and basic context.

---

### Staged rollout (recommended)

1) Dry run — validate parsing and planned writes (no downloads, no DB writes):

```powershell
# Load .env into the session (simple parser for PowerShell)
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
  $pair = $_ -split '=',2
  if ($pair.Length -eq 2) { [Environment]::SetEnvironmentVariable($pair[0], $pair[1]) }
}

python data_pipelines\scripts\download_audio_from_csv.py \
  --csv-path "<PATH TO YOUR CSV>" \
  --dry-run \
  --output-root "data_pipelines\data\audio_tmp"
```

2) Small batch — limit to 10; upload to B2; remove local copies; write to DB:

```powershell
python data_pipelines\scripts\download_audio_from_csv.py \
  --csv-path "<PATH TO YOUR CSV>" \
  --db-url "$env:DATABASE_URL" \
  --table-name "media_pipeline.audio_files" \
  --output-root "data_pipelines\data\audio_tmp" \
  --upload-to-b2 \
  --b2-prefix "audio/dexter" \
  --remove-local-after-upload \
  --limit 10
```

3) Verify in Postgres:

```sql
-- Recent sample under the chosen prefix
SELECT id, phone, campaign_name, b2_object_key, source_row_id, created_at
FROM media_pipeline.audio_files
WHERE b2_object_key LIKE 'audio/dexter/%'
ORDER BY id DESC
LIMIT 10;

-- Count inserted under prefix
SELECT COUNT(*)
FROM media_pipeline.audio_files
WHERE b2_object_key LIKE 'audio/dexter/%';

-- Dedupe guard check (should normally return zero rows)
SELECT url_sha1, COUNT(*) c
FROM media_pipeline.audio_files
GROUP BY url_sha1
HAVING COUNT(*) > 1
ORDER BY c DESC;
```

4) Full run — same as the small batch, just remove `--limit`:

```powershell
python data_pipelines\scripts\download_audio_from_csv.py \
  --csv-path "<PATH TO YOUR CSV>" \
  --db-url "$env:DATABASE_URL" \
  --table-name "media_pipeline.audio_files" \
  --output-root "data_pipelines\data\audio_tmp" \
  --upload-to-b2 \
  --b2-prefix "dexter-audio" \
  --remove-local-after-upload
```

---

### Behavior and guarantees
- Bucket selection: taken from `.env` `BACKBLAZE_B2_BUCKET` (e.g., `campaign-analysis`).
- Folder-like structure: `--b2-prefix` becomes the beginning of the key (e.g., `dexter-audio/<phone>/<filename>`). S3/B2 are key stores; UIs show these as folders.
- Deduplication: pre-check by `url_sha1` (and `recording_id` when present). Reruns skip existing rows and avoid re-uploading those items.
- Provenance: `source_row_id` is set from CSV `recordings_row_id`. `source_table` intentionally left NULL unless you decide to populate it.
- Local files: Removed immediately after a successful B2 upload when `--remove-local-after-upload` is used.

---

### Connecting to the right database (common pitfalls)

- Neon vs local: If `.env` holds a Neon `DATABASE_URL`, but you intend to use your local/tunneled DB, override `--db-url` explicitly (see full-run command above) or set `DATABASE_URL` to the local value for the session.
- Driver mismatch: If your URL says `postgresql+asyncpg`, the downloader automatically switches to `postgresql+psycopg2` to use the sync engine.
- PowerShell quoting: Avoid surrounding the entire URL in quotes when exporting, or strip them before use; URL‑encode passwords with special characters.

---

### Optional cleanup (if a test batch needs to be reverted)

```sql
-- Example: delete rows created recently under a specific prefix
DELETE FROM media_pipeline.audio_files
WHERE b2_object_key LIKE 'audio/dexter/%'
  AND created_at >= now() - interval '30 minutes';
```

---

### Troubleshooting
- Missing campaign names: if some `campaign_name` values show campaign IDs, add or fix mappings in `public.campaign_map`, or use one-off inline mappings in your SELECT/backfill queries.
- Credentials: ensure `.env` has the required BACKBLAZE_* (or AWS_*) variables and `DATABASE_URL`.
- Network/permission errors: verify endpoint, bucket name, and keys; B2 bucket must exist.
- Schema missing: The downloader auto-creates the schema if needed. If you still see “schema does not exist”, confirm you’re pointed at the correct DB/port.
- Permission denied: Grant rights to your user (run as a superuser):
  ```sql
  GRANT USAGE ON SCHEMA media_pipeline TO emilios;
  GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA media_pipeline TO emilios;
  GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA media_pipeline TO emilios;
  ALTER DEFAULT PRIVILEGES IN SCHEMA media_pipeline
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO emilios;
  ALTER DEFAULT PRIVILEGES IN SCHEMA media_pipeline
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO emilios;
  ```

---

### File references
- Downloader: `data_pipelines/scripts/download_audio_from_csv.py`
- Schema reference: `media_pipeline_psql_setup.md`


