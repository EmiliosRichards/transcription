"""
01_export_journeys.py
Export Dexter call journeys from the single Postgres (185.216.75.247).
Both media_pipeline schema and Dialfire tables (contacts, etc.) live here.

Groups all calls by phone number into chronological journeys,
enriched with contact metadata (PLZ, ort, firma) from Dialfire contacts.

Pre-requisite: SSH tunnel if connecting via localhost:
    ssh -L 5432:localhost:5432 emilios@185.216.75.247

Usage:
    python scripts/01_export_journeys.py --run runs/test_run
    python scripts/01_export_journeys.py --run runs/test_run --max-journeys 10
"""

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def load_config() -> dict:
    with open(ROOT / "config" / "config.yml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    db_url = cfg.get("database_url", "")
    if db_url.startswith("${") and db_url.endswith("}"):
        env_key = db_url[2:-1]
        cfg["database_url"] = os.environ.get(env_key, "")
    return cfg


def fetch_calls(engine, scope: str) -> list[dict]:
    """Fetch Dexter calls with transcripts from media_pipeline."""
    query = text("""
        SELECT
            af.id AS audio_id,
            af.phone,
            af.campaign_name,
            af.b2_object_key,
            af.started,
            af.stopped,
            t.transcript_text,
            t.status AS transcription_status,
            t.completed_at
        FROM media_pipeline.audio_files af
        LEFT JOIN media_pipeline.transcriptions t ON t.audio_file_id = af.id
        WHERE af.b2_object_key LIKE :scope
        ORDER BY af.phone, af.started
    """)
    with engine.connect() as conn:
        rows = conn.execute(query, {"scope": scope}).fetchall()

    return [{
        "audio_id": r.audio_id,
        "phone": r.phone,
        "campaign_name": r.campaign_name,
        "started": r.started.isoformat() if r.started else None,
        "stopped": r.stopped.isoformat() if r.stopped else None,
        "transcript_text": r.transcript_text or "",
        "transcription_status": r.transcription_status,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
    } for r in rows]


def fetch_contacts_by_phones(engine, phones: set[str], campaign_ids: list[str]) -> dict[str, dict]:
    """Fetch contact metadata from Dialfire contacts table, keyed by phone.
    Two-pass approach:
      1. Get contact data from Dexter campaigns (status, AP name)
      2. Fill in missing PLZ/ort/firma from any campaign row for the same phone
    """
    if not phones:
        return {}

    contact_map = {}
    phone_list = list(phones)
    batch_size = 500

    if campaign_ids:
        cid_placeholders = ", ".join(f":cid{i}" for i in range(len(campaign_ids)))
        campaign_clause = f'AND "$campaign_id" IN ({cid_placeholders})'
        cid_params = {f"cid{i}": c for i, c in enumerate(campaign_ids)}
    else:
        campaign_clause = ""
        cid_params = {}

    # Pass 1: Dexter campaign contacts (for status, AP name, and possibly PLZ)
    for i in range(0, len(phone_list), batch_size):
        batch = phone_list[i:i + batch_size]
        ph_placeholders = ", ".join(f":p{j}" for j in range(len(batch)))
        ph_params = {f"p{j}": p for j, p in enumerate(batch)}

        query = text(f"""
            SELECT DISTINCT ON ("$phone")
                "$id" AS contact_id, "$phone" AS phone,
                firma, plz, ort, strasse,
                "AP_Vorname" AS ap_vorname, "AP_Nachname" AS ap_nachname,
                "$status" AS status, "$status_detail" AS status_detail
            FROM public.contacts
            WHERE "$phone" IN ({ph_placeholders}) {campaign_clause}
            ORDER BY "$phone", "$changed" DESC NULLS LAST
        """)
        try:
            with engine.connect() as conn:
                rows = conn.execute(query, {**ph_params, **cid_params}).fetchall()
            for r in rows:
                if r.phone:
                    contact_map[r.phone] = {
                        "dialfire_contact_id": r.contact_id or "",
                        "firma": r.firma or "",
                        "plz": r.plz or "",
                        "ort": r.ort or "",
                        "ap_vorname": r.ap_vorname or "",
                        "ap_nachname": r.ap_nachname or "",
                        "dialfire_status": r.status or "",
                        "dialfire_status_detail": r.status_detail or "",
                    }
        except Exception as e:
            print(f"  Warning: pass1 batch {i} failed: {e}")

    # Pass 2: For contacts missing PLZ, try any campaign row
    missing_plz = [p for p in contact_map if not contact_map[p].get("plz")]
    if missing_plz:
        print(f"  Pass 2: filling PLZ for {len(missing_plz)} contacts from other campaigns...")
        for i in range(0, len(missing_plz), batch_size):
            batch = missing_plz[i:i + batch_size]
            ph_placeholders = ", ".join(f":p{j}" for j in range(len(batch)))
            ph_params = {f"p{j}": p for j, p in enumerate(batch)}

            query = text(f"""
                SELECT DISTINCT ON ("$phone")
                    "$phone" AS phone, firma, plz, ort
                FROM public.contacts
                WHERE "$phone" IN ({ph_placeholders})
                  AND plz IS NOT NULL AND plz != ''
                ORDER BY "$phone", "$changed" DESC NULLS LAST
            """)
            try:
                with engine.connect() as conn:
                    rows = conn.execute(query, ph_params).fetchall()
                for r in rows:
                    if r.phone and r.phone in contact_map:
                        contact_map[r.phone]["plz"] = r.plz or ""
                        contact_map[r.phone]["ort"] = r.ort or ""
                        if not contact_map[r.phone]["firma"] and r.firma:
                            contact_map[r.phone]["firma"] = r.firma
            except Exception as e:
                print(f"  Warning: pass2 batch {i} failed: {e}")

    return contact_map


def export_journeys(cfg: dict, run_dir: Path, max_journeys: int | None = None):
    db_url = cfg.get("database_url", "")
    if not db_url:
        print("ERROR: DATABASE_URL not set. Configure in .env")
        return

    scope = cfg.get("audio_scope", "dexter/audio/%")
    campaign_ids = cfg.get("dexter_campaign_ids", [])

    print(f"Connecting to DB...")
    engine = create_engine(db_url)

    # Step 1: Fetch all calls with transcripts
    print(f"Step 1: Fetching calls (scope={scope})...")
    calls = fetch_calls(engine, scope)
    print(f"  {len(calls)} call records")

    if not calls:
        print("No records found. Check DATABASE_URL, SSH tunnel, and audio_scope.")
        return

    # Step 2: Enrich with contact metadata from Dialfire
    phones = {c["phone"] for c in calls if c.get("phone")}
    print(f"Step 2: Enriching {len(phones)} phones from contacts table...")
    contact_map = fetch_contacts_by_phones(engine, phones, campaign_ids)
    print(f"  Matched {len(contact_map)} contacts")

    if not calls:
        print("No records found. Check DATABASE_URL, SSH tunnel, and audio_scope.")
        return

    # Group by phone
    journeys_by_phone = defaultdict(list)
    for call in calls:
        phone = call.get("phone")
        if not phone:
            continue
        journeys_by_phone[phone].append(call)

    journeys = []
    for phone, phone_calls in journeys_by_phone.items():
        phone_calls.sort(key=lambda c: c["started"] or "")

        # Look up contact metadata from the contact_map
        contact_meta = contact_map.get(phone, {
            "firma": "", "plz": "", "ort": "",
            "ap_vorname": "", "ap_nachname": "",
            "dialfire_contact_id": "", "dialfire_status": "",
            "dialfire_status_detail": "",
        })

        # Strip contact fields from individual calls (save space)
        clean_calls = []
        for c in phone_calls:
            clean_calls.append({
                "audio_id": c["audio_id"],
                "started": c["started"],
                "stopped": c["stopped"],
                "transcript_text": c["transcript_text"],
                "transcription_status": c["transcription_status"],
            })

        journeys.append({
            "phone": phone,
            "campaign_name": phone_calls[-1]["campaign_name"],
            "num_calls": len(clean_calls),
            "calls": clean_calls,
            **contact_meta,
        })

    journeys.sort(key=lambda j: j["num_calls"], reverse=True)

    if max_journeys:
        journeys = journeys[:max_journeys]

    # Write
    run_dir.mkdir(parents=True, exist_ok=True)
    out_path = run_dir / "journeys.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for j in journeys:
            f.write(json.dumps(j, ensure_ascii=False) + "\n")

    total_calls = sum(j["num_calls"] for j in journeys)
    with_transcript = sum(
        1 for j in journeys for c in j["calls"] if c["transcript_text"]
    )
    with_plz = sum(1 for j in journeys if j.get("plz"))

    report = {
        "exported_at": datetime.now().isoformat(),
        "scope": scope,
        "campaign_ids": campaign_ids,
        "total_journeys": len(journeys),
        "total_calls": total_calls,
        "calls_with_transcript": with_transcript,
        "contacts_with_plz": with_plz,
        "calls_per_journey": {
            "min": min(j["num_calls"] for j in journeys) if journeys else 0,
            "max": max(j["num_calls"] for j in journeys) if journeys else 0,
            "avg": round(total_calls / len(journeys), 1) if journeys else 0,
        },
    }
    report_path = run_dir / "export_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nExported {len(journeys)} journeys ({total_calls} calls, {with_transcript} transcribed, {with_plz} with PLZ)")
    print(f"  -> {out_path}")
    print(f"  -> {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Export Dexter call journeys")
    parser.add_argument("--run", type=Path, required=True, help="Run output directory")
    parser.add_argument("--max-journeys", type=int, default=None)
    args = parser.parse_args()

    cfg = load_config()
    run_dir = ROOT / args.run if not args.run.is_absolute() else args.run
    export_journeys(cfg, run_dir, args.max_journeys)


if __name__ == "__main__":
    main()
