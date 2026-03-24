"""
01_export_journeys.py
Export Dexter call journeys from TWO databases:
  - Media DB (173.249.24.215): audio_files + transcriptions (media_pipeline schema)
  - Dialfire DB (185.216.75.247): contacts table (PLZ, ort, firma, etc.)

Produces journeys grouped by phone number with full call history + contact metadata.

Pre-requisite: SSH tunnel for Media DB:
    ssh -L 5433:localhost:5432 emilios@173.249.24.215

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
    # Resolve env vars
    for key in ["media_db_url", "dialfire_db_url"]:
        val = cfg.get(key, "")
        if val.startswith("${") and val.endswith("}"):
            env_key = val[2:-1]
            cfg[key] = os.environ.get(env_key, "")
    return cfg


def fetch_media_calls(engine, scope: str) -> list[dict]:
    """Fetch all Dexter calls with transcripts from media_pipeline."""
    query = text("""
        SELECT
            af.id AS audio_id,
            af.phone,
            af.campaign_name,
            af.b2_object_key,
            af.started,
            af.stopped,
            af.recording_id,
            af.source_row_id,
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

    results = []
    for row in rows:
        results.append({
            "audio_id": row.audio_id,
            "phone": row.phone,
            "campaign_name": row.campaign_name,
            "b2_object_key": row.b2_object_key,
            "started": row.started.isoformat() if row.started else None,
            "stopped": row.stopped.isoformat() if row.stopped else None,
            "recording_id": row.recording_id,
            "source_row_id": row.source_row_id,
            "transcript_text": row.transcript_text or "",
            "transcription_status": row.transcription_status,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        })
    return results


def fetch_dialfire_contacts(engine, phones: set[str]) -> dict[str, dict]:
    """Fetch contact metadata (PLZ, ort, firma) from Dialfire's contacts table.
    Returns a dict keyed by phone number."""

    if not phones:
        return {}

    # Dialfire stores phone in "$phone" column
    # We fetch in batches to avoid huge IN clauses
    contact_map = {}
    phone_list = list(phones)
    batch_size = 500

    for i in range(0, len(phone_list), batch_size):
        batch = phone_list[i:i + batch_size]
        # Build parameterized query
        placeholders = ", ".join(f":p{j}" for j in range(len(batch)))
        query = text(f"""
            SELECT DISTINCT ON ("$phone")
                "$id" AS contact_id,
                "$phone" AS phone,
                "$campaign_id" AS campaign_id,
                firma,
                plz,
                ort,
                strasse,
                "AP_Vorname" AS ap_vorname,
                "AP_Nachname" AS ap_nachname,
                "$status" AS status,
                "$status_detail" AS status_detail
            FROM contacts
            WHERE "$phone" IN ({placeholders})
            ORDER BY "$phone", "$changed" DESC NULLS LAST
        """)
        params = {f"p{j}": p for j, p in enumerate(batch)}

        try:
            with engine.connect() as conn:
                rows = conn.execute(query, params).fetchall()

            for row in rows:
                phone = row.phone
                if phone:
                    contact_map[phone] = {
                        "dialfire_contact_id": row.contact_id,
                        "dialfire_campaign_id": row.campaign_id,
                        "firma": row.firma or "",
                        "plz": row.plz or "",
                        "ort": row.ort or "",
                        "strasse": row.strasse or "",
                        "ap_vorname": row.ap_vorname or "",
                        "ap_nachname": row.ap_nachname or "",
                        "dialfire_status": row.status or "",
                        "dialfire_status_detail": row.status_detail or "",
                    }
        except Exception as e:
            print(f"  Warning: Dialfire batch query failed: {e}")
            # Continue with partial data

    return contact_map


def export_journeys(cfg: dict, run_dir: Path, max_journeys: int | None = None):
    # --- Connect to Media DB ---
    media_url = cfg.get("media_db_url", "")
    if not media_url:
        print("ERROR: MEDIA_DB_URL not set. Configure in .env")
        print("  Also ensure SSH tunnel is open: ssh -L 5433:localhost:5432 emilios@173.249.24.215")
        return

    scope = cfg.get("audio_scope", "dexter/audio/%")
    print(f"Connecting to Media DB...")
    media_engine = create_engine(media_url)

    print(f"Querying media_pipeline for scope: {scope}")
    calls = fetch_media_calls(media_engine, scope)
    print(f"Fetched {len(calls)} call records from Media DB")

    if not calls:
        print("No records found. Check MEDIA_DB_URL and SSH tunnel.")
        return

    # Collect unique phone numbers
    phones = {c["phone"] for c in calls if c.get("phone")}
    print(f"Found {len(phones)} unique phone numbers")

    # --- Connect to Dialfire DB (optional but recommended) ---
    dialfire_url = cfg.get("dialfire_db_url", "")
    contact_map = {}
    if dialfire_url:
        print(f"Connecting to Dialfire DB for contact enrichment...")
        try:
            dialfire_engine = create_engine(dialfire_url)
            contact_map = fetch_dialfire_contacts(dialfire_engine, phones)
            print(f"Enriched {len(contact_map)} contacts with PLZ/ort/firma from Dialfire")
        except Exception as e:
            print(f"Warning: Dialfire connection failed ({e}). Continuing without enrichment.")
    else:
        print("DIALFIRE_DB_URL not set. Skipping contact enrichment (no PLZ for ref matching).")

    # --- Group calls into journeys ---
    journeys_by_phone = defaultdict(list)
    for call in calls:
        phone = call.get("phone")
        if not phone:
            continue
        journeys_by_phone[phone].append(call)

    journeys = []
    for phone, phone_calls in journeys_by_phone.items():
        phone_calls.sort(key=lambda c: c["started"] or "")
        campaign = phone_calls[-1]["campaign_name"]

        # Merge contact metadata from Dialfire
        contact = contact_map.get(phone, {})

        journeys.append({
            "phone": phone,
            "campaign_name": campaign,
            "num_calls": len(phone_calls),
            "calls": phone_calls,
            # Contact metadata from Dialfire
            "firma": contact.get("firma", ""),
            "plz": contact.get("plz", ""),
            "ort": contact.get("ort", ""),
            "ap_vorname": contact.get("ap_vorname", ""),
            "ap_nachname": contact.get("ap_nachname", ""),
            "dialfire_contact_id": contact.get("dialfire_contact_id", ""),
            "dialfire_status": contact.get("dialfire_status", ""),
            "dialfire_status_detail": contact.get("dialfire_status_detail", ""),
        })

    # Sort by num_calls descending
    journeys.sort(key=lambda j: j["num_calls"], reverse=True)

    if max_journeys:
        journeys = journeys[:max_journeys]

    # --- Write output ---
    run_dir.mkdir(parents=True, exist_ok=True)
    out_path = run_dir / "journeys.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for j in journeys:
            f.write(json.dumps(j, ensure_ascii=False) + "\n")

    # Summary
    total_calls = sum(j["num_calls"] for j in journeys)
    with_transcript = sum(
        1 for j in journeys
        for c in j["calls"]
        if c["transcript_text"]
    )
    with_plz = sum(1 for j in journeys if j.get("plz"))

    report = {
        "exported_at": datetime.now().isoformat(),
        "scope": scope,
        "total_journeys": len(journeys),
        "total_calls": total_calls,
        "calls_with_transcript": with_transcript,
        "contacts_with_plz": with_plz,
        "contacts_enriched_from_dialfire": len(contact_map),
        "calls_per_journey": {
            "min": min(j["num_calls"] for j in journeys) if journeys else 0,
            "max": max(j["num_calls"] for j in journeys) if journeys else 0,
            "avg": round(total_calls / len(journeys), 1) if journeys else 0,
        },
    }
    report_path = run_dir / "export_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nExported {len(journeys)} journeys ({total_calls} calls, {with_transcript} with transcripts, {with_plz} with PLZ)")
    print(f"  -> {out_path}")
    print(f"  -> {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Export Dexter call journeys")
    parser.add_argument("--run", type=Path, required=True, help="Run output directory")
    parser.add_argument("--max-journeys", type=int, default=None, help="Limit (for testing)")
    args = parser.parse_args()

    cfg = load_config()
    run_dir = ROOT / args.run if not args.run.is_absolute() else args.run
    export_journeys(cfg, run_dir, args.max_journeys)


if __name__ == "__main__":
    main()
