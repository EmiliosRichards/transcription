"""
Auto-transcribe new recordings for configured campaigns.

Runs as a cron job (every 5 minutes). Finds recordings in public.recordings
that are not yet in media_pipeline.audio_files for the campaigns listed in
the config file, and submits them to the local transcription API.

Config file: /opt/transcribe/transcription/data_pipelines/scripts/ops/campaigns.txt
  One campaign ID per line. Lines starting with # are ignored.

Usage:
    python auto_transcribe.py                  # Single run
    python auto_transcribe.py --dry-run        # Show what would be submitted

Setup as cron (every 5 minutes):
    crontab -e
    */5 * * * * cd /opt/transcribe/transcription && /usr/bin/env bash -c 'export $(grep -v "^#" .env | xargs) && python3 data_pipelines/scripts/ops/auto_transcribe.py >> /var/log/auto_transcribe.log 2>&1'

Context: See MASTER_PLAN.md in manuav-platform repo, Phase 2.2.
  The Jagdhuette app reads transcripts from media_pipeline.audio_files +
  media_pipeline.transcriptions via Railway → Contabo SSL connection.
  This script ensures new calls are automatically queued for transcription.
"""

import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime

import psycopg2

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "campaigns.txt")
LOG_PREFIX = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

API_URL = os.environ.get("TRANSCRIPTION_API_URL", "http://127.0.0.1:8000")
API_KEY = os.environ.get("API_KEY", "")
DB_URL = os.environ.get("DATABASE_URL", "")


def log(msg):
    print(f"[{LOG_PREFIX}] {msg}", flush=True)


def load_campaign_ids():
    if not os.path.exists(CONFIG_FILE):
        log(f"ERROR: Config file not found: {CONFIG_FILE}")
        sys.exit(1)
    ids = []
    with open(CONFIG_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                ids.append(line)
    if not ids:
        log("WARNING: No campaign IDs in config file")
    return ids


def get_db_connection():
    url = DB_URL
    if not url:
        url = "postgresql://postgres:Kii366@localhost:5432/dialfire"
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    return psycopg2.connect(url)


def find_new_recordings(conn, campaign_ids):
    cur = conn.cursor()
    placeholders = ",".join(["%s"] * len(campaign_ids))
    cur.execute(f"""
        SELECT r.id::text AS recording_id,
               c."$campaign_id" AS campaign_id
        FROM public.recordings r
        JOIN public.contacts c ON r.contact_id = c."$id"
        WHERE c."$campaign_id" IN ({placeholders})
          AND r.location IS NOT NULL AND r.location != ''
          AND NOT EXISTS (
              SELECT 1 FROM media_pipeline.audio_files af
              WHERE af.recording_id = r.id::text
          )
        ORDER BY r.started DESC
    """, campaign_ids)
    rows = cur.fetchall()
    cur.close()
    return rows


def submit(recording_id):
    data = urllib.parse.urlencode({
        "recording_id": recording_id,
        "b2_prefix": "gateway",
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{API_URL}/api/media/transcribe",
        data=data,
        headers={
            "X-API-Key": API_KEY,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return True, body
    except urllib.error.HTTPError as e:
        return False, {"status_code": e.code, "detail": e.read().decode("utf-8", errors="replace")[:200]}
    except Exception as e:
        return False, {"detail": str(e)}


def mark_as_skipped(conn, recording_id, campaign_id, reason):
    """Insert a placeholder row so this recording is not retried."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO media_pipeline.audio_files
            (phone, campaign_name, recording_id, url, url_sha1, source_table)
        VALUES
            ('unknown', %s, %s, %s, md5(%s), 'skipped')
        ON CONFLICT DO NOTHING
    """, (campaign_id, recording_id, f"SKIPPED: {reason}", recording_id))
    conn.commit()
    cur.close()


def main():
    dry_run = "--dry-run" in sys.argv

    if not API_KEY and not dry_run:
        log("ERROR: API_KEY not set")
        sys.exit(1)

    campaign_ids = load_campaign_ids()
    if not campaign_ids:
        return

    conn = get_db_connection()
    new_recordings = find_new_recordings(conn, campaign_ids)

    if not new_recordings:
        conn.close()
        log(f"No new recordings found for {len(campaign_ids)} campaigns")
        return

    log(f"Found {len(new_recordings)} new recordings to transcribe")

    if dry_run:
        conn.close()
        for rid, cid in new_recordings[:10]:
            log(f"  DRY RUN: would submit {rid} ({cid})")
        if len(new_recordings) > 10:
            log(f"  ... and {len(new_recordings) - 10} more")
        return

    queued = 0
    already_done = 0
    failed = 0
    skipped = 0

    for rid, cid in new_recordings:
        ok, result = submit(rid)
        if ok:
            status = result.get("status", "")
            if status == "completed":
                already_done += 1
            else:
                queued += 1
        else:
            status_code = result.get("status_code", 0)
            detail = result.get("detail", "")
            # Permanent failures (400 = bad request, 404 = not found) — mark as skipped so we don't retry
            if status_code in (400, 404):
                mark_as_skipped(conn, rid, cid, detail[:200])
                skipped += 1
                log(f"  SKIPPED (permanent): {rid} — {detail[:100]}")
            else:
                # Transient failures (500, timeout, etc.) — don't mark, will retry next run
                failed += 1
                log(f"  FAILED (will retry): {rid} — {detail[:100]}")

    conn.close()

    log(f"Done: queued={queued} already_done={already_done} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()
