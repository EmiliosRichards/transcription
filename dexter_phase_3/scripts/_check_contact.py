"""Deep-dive a single contact: all Dialfire records + all call transcripts."""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
engine = create_engine(os.environ["DATABASE_URL"])

phone = sys.argv[1] if len(sys.argv) > 1 else "+4921212903"

with engine.connect() as conn:
    print(f"ALL DIALFIRE RECORDS FOR {phone}")
    print("=" * 80)

    rows = conn.execute(text("""
        SELECT "$id", "$campaign_id", "$status", "$status_detail",
               "$task", "$$anrufen_status", "$$anrufen_status_detail",
               firma, plz, ort, "$changed"
        FROM public.contacts
        WHERE "$phone" = :phone
        ORDER BY "$changed" DESC NULLS LAST
    """), {"phone": phone}).fetchall()

    for i, r in enumerate(rows, 1):
        changed = str(r[10])[:16] if r[10] else "(null)"
        print(f"\n  Record {i} (changed: {changed})")
        print(f"    id:              {r[0]}")
        print(f"    campaign_id:     {r[1]}")
        print(f"    firma:           {r[7]}")
        print(f"    plz/ort:         {r[8]} {r[9]}")
        print(f"    $status:         {r[2]}")
        print(f"    $status_detail:  {r[3]}")
        print(f"    $task:           {r[4]}")
        print(f"    $$anrufen_status:        {r[5]}")
        print(f"    $$anrufen_status_detail:  {r[6]}")

    print(f"\n\n{'=' * 80}")
    print(f"ALL CALLS FOR {phone}")
    print("=" * 80)

    calls = conn.execute(text("""
        SELECT af.started, af.stopped, af.campaign_name,
               t.transcript_text, t.status
        FROM media_pipeline.audio_files af
        LEFT JOIN media_pipeline.transcriptions t ON t.audio_file_id = af.id
        WHERE af.phone = :phone AND af.b2_object_key LIKE 'dexter/audio/%%'
        ORDER BY af.started
    """), {"phone": phone}).fetchall()

    for i, c in enumerate(calls, 1):
        date = str(c[0])[:16]
        duration = ""
        if c[0] and c[1]:
            secs = (c[1] - c[0]).total_seconds()
            duration = f"{secs:.0f}s"
        txt = (c[3] or "").strip()
        print(f"\n--- Call {i} ({date}, {duration}, campaign: {c[2]}) ---")
        if txt and len(txt) > 20:
            print(txt)
        else:
            print("  (no meaningful transcript)")
