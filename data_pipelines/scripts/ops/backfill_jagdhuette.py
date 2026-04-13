"""
Backfill Jagdhuette recordings into the transcription API.

Queries public.recordings for Jagdhuette campaigns, filters out recordings
already in media_pipeline.audio_files, and submits the rest to the local
transcription API.

Usage (on Contabo server 185.216.75.247):
    python backfill_jagdhuette.py              # Dry run — shows what would be submitted
    python backfill_jagdhuette.py --execute    # Submit recordings to the API
    python backfill_jagdhuette.py --execute --batch-size 50  # Submit in batches of 50
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.parse

import psycopg2

# Jagdhuette campaign IDs (from manuav-platform client_portal.campaign_dialfire_configs)
CAMPAIGN_IDS = [
    "VD65QPHNN6CSVBP6",   # Manuav Dev Org "Default"
    "YHSF97B9FVFFRL6Z",   # MANUAV "MANUAV Leadinfo"
    "E7ZVULZVFA9TRHY2",   # TegolySign "TegolySign Jagdhütte"
]

API_URL = os.environ.get("TRANSCRIPTION_API_URL", "http://127.0.0.1:8000")
API_KEY = os.environ.get("API_KEY", "")
DB_URL = os.environ.get("DATABASE_URL", "")


def get_db_connection():
    url = DB_URL
    if not url:
        url = "postgresql://postgres:Kii366@localhost:5432/dialfire"
    # Convert asyncpg URL to psycopg2 format
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    return psycopg2.connect(url)


def get_recordings_to_backfill(conn):
    """Find recordings not yet in media_pipeline.audio_files."""
    cur = conn.cursor()
    placeholders = ",".join(["%s"] * len(CAMPAIGN_IDS))
    cur.execute(f"""
        SELECT r.id::text AS recording_id,
               r.location AS audio_url,
               c."$phone" AS phone,
               c."$campaign_id" AS campaign_id,
               r.started,
               r.stopped
        FROM public.recordings r
        JOIN public.contacts c ON r.contact_id = c."$id"
        WHERE c."$campaign_id" IN ({placeholders})
          AND r.location IS NOT NULL AND r.location != ''
          AND NOT EXISTS (
              SELECT 1 FROM media_pipeline.audio_files af
              WHERE af.recording_id = r.id::text
          )
        ORDER BY r.started DESC
    """, CAMPAIGN_IDS)

    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    cur.close()
    return rows


def submit_to_api(recording_id, b2_prefix="gateway"):
    """Submit a single recording to the transcription API."""
    data = urllib.parse.urlencode({
        "recording_id": recording_id,
        "b2_prefix": b2_prefix,
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
            return {"ok": True, "status_code": resp.status, "body": body}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "status_code": e.code, "body": body}
    except Exception as e:
        return {"ok": False, "status_code": 0, "body": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Backfill Jagdhuette recordings")
    parser.add_argument("--execute", action="store_true", help="Actually submit (default is dry run)")
    parser.add_argument("--batch-size", type=int, default=0, help="Stop after N submissions (0 = all)")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between submissions (default 0.5)")
    args = parser.parse_args()

    if not API_KEY:
        # Try to read from .env
        env_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("API_KEY="):
                        os.environ["API_KEY"] = line.strip().split("=", 1)[1]
                        break

    api_key = os.environ.get("API_KEY", "")
    if args.execute and not api_key:
        print("Error: API_KEY not set. Set it in env or .env file.")
        sys.exit(1)

    conn = get_db_connection()
    recordings = get_recordings_to_backfill(conn)
    conn.close()

    print(f"Found {len(recordings)} recordings to backfill")
    print()

    # Summary by campaign
    by_campaign = {}
    for r in recordings:
        cid = r["campaign_id"]
        by_campaign[cid] = by_campaign.get(cid, 0) + 1
    for cid, count in sorted(by_campaign.items()):
        print(f"  {cid}: {count} recordings")
    print()

    if not recordings:
        print("Nothing to backfill.")
        return

    if not args.execute:
        print("DRY RUN — use --execute to submit")
        print()
        for i, r in enumerate(recordings[:10]):
            print(f"  [{i+1}] {r['recording_id']}  {r['phone']}  {r['campaign_id']}  {r['started']}")
        if len(recordings) > 10:
            print(f"  ... and {len(recordings) - 10} more")
        return

    # Execute
    limit = args.batch_size if args.batch_size > 0 else len(recordings)
    submitted = 0
    succeeded = 0
    short_circuited = 0
    failed = 0

    print(f"Submitting {min(limit, len(recordings))} recordings...")
    print()

    for i, r in enumerate(recordings[:limit]):
        result = submit_to_api(r["recording_id"])

        if result["ok"]:
            status = result["body"].get("status", "unknown")
            if status == "completed":
                short_circuited += 1
                label = "ALREADY DONE"
            else:
                succeeded += 1
                label = "QUEUED"
            print(f"  [{i+1}/{limit}] {label} — {r['recording_id']}  (audio_file_id={result['body'].get('audio_file_id')})")
        else:
            failed += 1
            print(f"  [{i+1}/{limit}] FAILED ({result['status_code']}) — {r['recording_id']}  {result['body'][:100]}")

        submitted += 1
        if i < limit - 1:
            time.sleep(args.delay)

    print()
    print(f"Done. Submitted: {submitted} | Queued: {succeeded} | Already done: {short_circuited} | Failed: {failed}")
    print()
    if succeeded > 0:
        print(f"Worker will process {succeeded} recordings. At ~30-60s each, estimated time: {succeeded * 45 // 60} - {succeeded * 60 // 60} minutes.")


if __name__ == "__main__":
    main()
