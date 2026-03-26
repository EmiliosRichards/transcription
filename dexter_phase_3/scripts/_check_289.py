"""Check the 289 contacts not in active campaigns."""
import csv
import os
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
engine = create_engine(os.environ["DATABASE_URL"])

clear = []
with open(ROOT / "runs" / "selection_1000.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        if r["action_needed"] == "none":
            clear.append(r["phone"])

print(f"289 contacts NOT in active Dexter campaigns:\n")

with engine.connect() as conn:
    found = {}
    for i in range(0, len(clear), 200):
        batch = clear[i:i+200]
        ph_pl = ", ".join(f":p{j}" for j in range(len(batch)))
        ph_params = {f"p{j}": p for j, p in enumerate(batch)}
        rows = conn.execute(text(f"""
            SELECT DISTINCT ON ("$phone")
                "$phone", "$campaign_id", "$status", "$status_detail",
                "$task", "$$anrufen_status", "$$anrufen_status_detail",
                "$id"
            FROM public.contacts
            WHERE "$phone" IN ({ph_pl})
            ORDER BY "$phone", "$changed" DESC NULLS LAST
        """), ph_params).fetchall()
        for r in rows:
            if r[0] not in found:
                found[r[0]] = {
                    "contact_id": r[7], "campaign_id": r[1],
                    "status": r[2], "status_detail": r[3],
                    "task": r[4], "anrufen_status": r[5],
                    "anrufen_status_detail": r[6],
                }

    not_found = [p for p in clear if p not in found]
    print(f"Found in other campaigns: {len(found)}")
    print(f"Not in contacts at all:   {len(not_found)}")

    if found:
        print("\ncampaign_id:")
        for k, n in Counter(v["campaign_id"] for v in found.values()).most_common():
            print(f"  {n:5d}  {k}")
        print("\nstatus:")
        for k, n in Counter(v["status"] or "(null)" for v in found.values()).most_common():
            print(f"  {n:5d}  {k}")
        print("\ntask:")
        for k, n in Counter(v["task"] or "(null)" for v in found.values()).most_common():
            print(f"  {n:5d}  {k}")
        print("\nanrufen_status:")
        for k, n in Counter(v["anrufen_status"] or "(null)" for v in found.values()).most_common():
            print(f"  {n:5d}  {k}")
        print("\nanrufen_status_detail:")
        for k, n in Counter(v["anrufen_status_detail"] or "(null)" for v in found.values()).most_common():
            print(f"  {n:5d}  {k}")

        # Are any of these callable?
        callable_count = sum(
            1 for v in found.values()
            if v["status"] == "open" and v["task"] == "anrufen_stufe"
            and (v["anrufen_status"] or "") == "open"
        )
        print(f"\nActively callable in these other campaigns: {callable_count}")
