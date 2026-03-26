"""Pick 20 random contacts from selection_1250.csv and export their journeys."""
import csv
import json
import os
import random
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
engine = create_engine(os.environ["DATABASE_URL"])

# Pick 20 random phones from selection
with open(ROOT / "runs" / "selection_1250.csv", encoding="utf-8") as f:
    all_rows = list(csv.DictReader(f))

random.seed(42)
sample = random.sample(all_rows, 20)
sample_phones = {r["phone"] for r in sample}

print(f"Selected {len(sample)} random contacts from selection_1250.csv")

# Now export journeys for just these 20
run_dir = ROOT / "runs" / "sample_20"
run_dir.mkdir(parents=True, exist_ok=True)

with engine.connect() as conn:
    # Get calls
    ph_pl = ", ".join(f":p{i}" for i in range(len(sample)))
    ph_params = {f"p{i}": r["phone"] for i, r in enumerate(sample)}

    rows = conn.execute(text(f"""
        SELECT af.phone, af.id, af.campaign_name, af.started, af.stopped,
               af.b2_object_key, af.recording_id,
               t.transcript_text, t.status AS t_status
        FROM media_pipeline.audio_files af
        LEFT JOIN media_pipeline.transcriptions t ON t.audio_file_id = af.id
        WHERE af.phone IN ({ph_pl})
        AND af.b2_object_key LIKE 'dexter/audio/%%'
        ORDER BY af.phone, af.started
    """), ph_params).fetchall()

    # Group by phone
    journeys = {}
    for r in rows:
        phone = r[0]
        if phone not in journeys:
            journeys[phone] = {
                "phone": phone,
                "campaign_name": r[2],
                "calls": [],
                "firma": "",
                "plz": "",
                "ort": "",
                "ap_vorname": "",
                "ap_nachname": "",
                "dialfire_contact_id": "",
                "dialfire_status": "",
            }
        journeys[phone]["calls"].append({
            "audio_id": r[1],
            "started": str(r[3]) if r[3] else "",
            "stopped": str(r[4]) if r[4] else "",
            "b2_object_key": r[5],
            "recording_id": str(r[6]) if r[6] else "",
            "transcript_text": r[7] or "",
            "transcription_status": r[8] or "",
        })

    # Enrich from selection CSV data
    for r in sample:
        phone = r["phone"]
        if phone in journeys:
            journeys[phone]["firma"] = r.get("firma", "")
            journeys[phone]["plz"] = r.get("plz", "")
            journeys[phone]["ort"] = r.get("ort", "")
            journeys[phone]["ap_vorname"] = r.get("ap_vorname", "")
            journeys[phone]["ap_nachname"] = r.get("ap_nachname", "")
            journeys[phone]["num_calls"] = len(journeys[phone]["calls"])

    # Write journeys
    out = run_dir / "journeys.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for j in journeys.values():
            f.write(json.dumps(j, ensure_ascii=False, default=str) + "\n")

    print(f"Exported {len(journeys)} journeys ({sum(len(j['calls']) for j in journeys.values())} calls) -> {out}")
