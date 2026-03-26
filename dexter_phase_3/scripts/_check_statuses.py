"""Check Dialfire statuses for contacts in a run's final output."""
import csv
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
engine = create_engine(os.environ["DATABASE_URL"])

run_name = sys.argv[1] if len(sys.argv) > 1 else "runs/sample_20_v2"
run_dir = ROOT / run_name

phones = []
with open(run_dir / "final_output.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        phones.append((r["phone"], r.get("firma", "")[:35], r.get("action", ""), r.get("category_label", "")[:30]))

with engine.connect() as conn:
    for phone, firma, action, cat in phones:
        rows = conn.execute(text("""
            SELECT "$campaign_id", "$status", "$status_detail",
                   "$task", "$$anrufen_status", "$$anrufen_status_detail",
                   firma
            FROM public.contacts
            WHERE "$phone" = :phone
            ORDER BY "$changed" DESC NULLS LAST
        """), {"phone": phone}).fetchall()

        print(f"{phone:20s}  action={action:12s}  cat={cat}")
        print(f"  firma: {firma}")
        if not rows:
            print(f"  DIALFIRE: NOT FOUND")
        else:
            for i, r in enumerate(rows[:3]):
                prefix = "  DIALFIRE:" if i == 0 else "          :"
                print(f"{prefix} campaign={r[0]}  status={r[1]}  detail={r[2] or ''}")
                print(f"            task={r[3] or ''}  anrufen={r[4] or ''}  anrufen_detail={r[5] or ''}")
        print()
