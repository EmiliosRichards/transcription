"""Pick 20 clean contacts from the 4 active Dexter campaigns on new server.
Checks ALL campaigns (not just Dexter) for exclusion statuses.
Exclusion rules are read from config/config.yml."""
import csv
import os
import random
from pathlib import Path

import yaml
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
engine = create_engine(os.environ["DATABASE_URL"])

with open(ROOT / "config" / "config.yml", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

ACTIVE_CIDS = cfg.get("dexter_campaign_ids", [])[:4]  # the 4 with contacts
rules = cfg.get("exclusion_rules", {})
EXCLUDE_STATUSES = set(rules.get("excluded_statuses", []))
EXCLUDE_TASKS = set(rules.get("excluded_tasks", []))
EXCLUDE_DETAILS = set(rules.get("excluded_anrufen_details", []))

with engine.connect() as conn:
    # Step 1: Get candidates from active campaigns with full data
    rows = conn.execute(text("""
        WITH contact_latest AS (
            SELECT DISTINCT ON ("$phone")
                "$phone" AS phone,
                "$id" AS contact_id,
                "$campaign_id" AS campaign_id,
                "$status" AS status,
                "$task" AS task,
                "$$anrufen_status" AS anrufen_status,
                "$$anrufen_status_detail" AS anrufen_status_detail,
                firma, plz, ort
            FROM public.contacts
            WHERE "$campaign_id" IN (:c0, :c1, :c2, :c3)
              AND firma IS NOT NULL AND firma != ''
              AND plz IS NOT NULL AND plz != ''
            ORDER BY "$phone", "$changed" DESC NULLS LAST
        ),
        last_calls AS (
            SELECT phone, max(started) AS last_call_date, count(*) AS total_calls,
                   count(t.transcript_text) AS transcribed
            FROM media_pipeline.audio_files af
            LEFT JOIN media_pipeline.transcriptions t ON t.audio_file_id = af.id
            WHERE af.b2_object_key LIKE 'dexter/audio/%%'
            GROUP BY af.phone
        )
        SELECT cl.phone, cl.contact_id, cl.campaign_id,
               cl.status, cl.task,
               cl.anrufen_status, cl.anrufen_status_detail,
               cl.firma, cl.plz, cl.ort,
               lc.last_call_date, lc.total_calls, lc.transcribed
        FROM contact_latest cl
        JOIN last_calls lc ON lc.phone = cl.phone
        WHERE lc.last_call_date < '2025-07-29'
          AND lc.transcribed >= 2
        ORDER BY random()
    """), {
        "c0": ACTIVE_CIDS[0], "c1": ACTIVE_CIDS[1],
        "c2": ACTIVE_CIDS[2], "c3": ACTIVE_CIDS[3],
    }).fetchall()

    print(f"Total candidates from active campaigns: {len(rows)}")

    # Step 2: Collect all phones, then check ALL campaigns for exclusion statuses
    candidate_phones = [r[0] for r in rows]

    # Batch query: for each phone, get ALL statuses across ALL campaigns
    excluded_phones = set()
    batch_size = 500
    for i in range(0, len(candidate_phones), batch_size):
        batch = candidate_phones[i:i + batch_size]
        ph_pl = ", ".join(f":p{j}" for j in range(len(batch)))
        ph_params = {f"p{j}": p for j, p in enumerate(batch)}

        # Build dynamic exclusion params
        ex_params = dict(ph_params)
        status_pl = ", ".join(f":es{j}" for j in range(len(EXCLUDE_STATUSES)))
        for j, s in enumerate(EXCLUDE_STATUSES):
            ex_params[f"es{j}"] = s
        task_pl = ", ".join(f":et{j}" for j in range(len(EXCLUDE_TASKS)))
        for j, t in enumerate(EXCLUDE_TASKS):
            ex_params[f"et{j}"] = t
        detail_pl = ", ".join(f":ed{j}" for j in range(len(EXCLUDE_DETAILS)))
        for j, d in enumerate(EXCLUDE_DETAILS):
            ex_params[f"ed{j}"] = d

        exclude_rows = conn.execute(text(f"""
            SELECT DISTINCT "$phone"
            FROM public.contacts
            WHERE "$phone" IN ({ph_pl})
            AND (
                "$status" IN ({status_pl})
                OR "$$anrufen_status" IN ({status_pl})
                OR "$task" IN ({task_pl})
                OR "$$anrufen_status_detail" IN ({detail_pl})
            )
        """), ex_params).fetchall()

        for er in exclude_rows:
            excluded_phones.add(er[0])

    print(f"Excluded (status in ANY campaign): {len(excluded_phones)}")

    # Step 3: Filter
    clean = []
    for r in rows:
        phone = r[0]
        if phone in excluded_phones:
            continue

        clean.append({
            "phone": phone,
            "contact_id": r[1],
            "campaign_id": r[2],
            "status": r[3] or "",
            "task": r[4] or "",
            "anrufen_status": r[5] or "",
            "anrufen_status_detail": r[6] or "",
            "firma": r[7],
            "plz": r[8],
            "ort": r[9],
            "last_call_date": str(r[10])[:10] if r[10] else "",
            "total_calls": r[11],
            "transcribed": r[12],
        })

    print(f"After exclusions: {len(clean)}")

    # Pick 20 random
    sample = clean[:20]

    print(f"\nSELECTED 20 CONTACTS:")
    print(f"{'Phone':20s}  {'Campaign':20s}  {'Status':8s}  {'Task':20s}  {'Anrufen':10s}  {'Detail':20s}  {'LastCall':12s}  {'Calls':5s}  {'Firma':30s}")
    print("-" * 160)
    phones = []
    for s in sample:
        print(f"{s['phone']:20s}  {s['campaign_id']:20s}  {s['status']:8s}  {s['task']:20s}  {s['anrufen_status']:10s}  {s['anrufen_status_detail']:20s}  {s['last_call_date']:12s}  {s['total_calls']:5d}  {s['firma'][:30]}")
        phones.append(s["phone"])

    # Verify: check if +4921212903 would be excluded now
    print()
    test_phone = "+4921212903"
    if test_phone in excluded_phones:
        print(f"VERIFICATION: {test_phone} is now EXCLUDED (correct!)")
    else:
        print(f"VERIFICATION: {test_phone} is NOT excluded (check why)")

    print(f"\nPhone list for --phones flag:")
    print(",".join(phones))
