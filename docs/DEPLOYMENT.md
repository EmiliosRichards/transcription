# Transcription System — Deployment Guide

> Last updated: 2026-04-02
> Production server: 185.216.75.247

## Server access

```bash
ssh root@185.216.75.247
# or
ssh -L 5432:localhost:5432 root@185.216.75.247   # with DB tunnel for DBeaver
```

User `emilios` exists but has no password set. Services run as `emilios`. To set a password: `sudo passwd emilios`.

## Application layout

```
/opt/transcribe/transcription/
├── .env                          # credentials (not in git)
├── chatbot_app/backend/
│   ├── .venv/                    # Python virtual environment
│   ├── gateway.py                # API entry point
│   └── app/routers/media_router.py
├── data_pipelines/scripts/
│   ├── transcribe_gpt4o.py       # Worker script
│   └── ...
└── docs/
```

## Environment variables

File: `/opt/transcribe/transcription/.env`

```bash
OPENAI_API_KEY=<OpenAI project key>
DATABASE_URL=postgresql+asyncpg://postgres:<password>@localhost:5432/dialfire
BACKBLAZE_B2_BUCKET=campaign-analysis
BACKBLAZE_B2_KEY_ID=<B2 key ID>
BACKBLAZE_B2_APPLICATION_KEY=<B2 app key>
BACKBLAZE_B2_S3_ENDPOINT=https://s3.eu-central-003.backblazeb2.com
GOOGLE_API_KEY=dummy-ok
API_KEY=<API auth token>
```

**Important:** DATABASE_URL points to `dialfire` (not `manuav`). Do not append `?sslmode=disable` — asyncpg doesn't support it.

## Systemd services

### API service

File: `/etc/systemd/system/transcribe-api.service`

```ini
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

### Worker service

File: `/etc/systemd/system/transcribe-worker.service`

```ini
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

### Caddy reverse proxy

File: `/etc/caddy/Caddyfile`

```
transcribe.vertikon.ltd {
    encode gzip
    reverse_proxy 127.0.0.1:8000
}
```

## Common operations

### Restart services

```bash
sudo systemctl restart transcribe-api transcribe-worker
```

### Check status

```bash
sudo systemctl status transcribe-api
sudo systemctl status transcribe-worker
```

### View logs

```bash
journalctl -u transcribe-api -n 200 -f
journalctl -u transcribe-worker -n 200 -f
```

### Update code from git

```bash
cd /opt/transcribe/transcription && git pull
sudo systemctl restart transcribe-api transcribe-worker
```

### Clear stuck claims

```bash
cd /tmp && sudo -u postgres psql -d dialfire -c "
  DELETE FROM media_pipeline.transcription_claims
  WHERE claimed_at < now() - interval '2 hours';
"
```

### Check pending jobs

```bash
cd /tmp && sudo -u postgres psql -d dialfire -c "
  SELECT COUNT(*) AS pending
  FROM media_pipeline.audio_files af
  WHERE NOT EXISTS (
    SELECT 1 FROM media_pipeline.transcriptions t
    WHERE t.audio_file_id = af.id AND t.status = 'completed'
  );
"
```

### Check completed transcriptions

```bash
cd /tmp && sudo -u postgres psql -d dialfire -c "
  SELECT COUNT(*) FROM media_pipeline.audio_files;
  SELECT COUNT(*) FROM media_pipeline.transcriptions WHERE status = 'completed';
"
```

## Known issues

### Dialfire dbsync2 lock contention

The `dbsync2` service (user `kubrakiv`, running locally) syncs data from Dialfire and runs `CREATE INDEX IF NOT EXISTS` on the `contacts` table after each batch. With many parallel workers, this causes cascading lock contention that can block all writes to `contacts` for 30+ minutes and delay DDL on other tables.

**Diagnosis:**
```bash
cd /tmp && sudo -u postgres psql -d dialfire -c "
  SELECT pid, usename, application_name, state,
         age(clock_timestamp(), query_start) AS duration,
         substring(query, 1, 120) AS query
  FROM pg_stat_activity
  WHERE query LIKE 'CREATE INDEX%';
"
```

**Immediate relief:**
```sql
SELECT pg_cancel_backend(pid)
FROM pg_stat_activity
WHERE query LIKE 'CREATE INDEX IF NOT EXISTS%'
  AND pid != pg_backend_pid();
```

See ARCHITECTURE.md for details. Root fix: change dbsync2 to use `CREATE INDEX CONCURRENTLY` or skip index creation on every sync cycle.
