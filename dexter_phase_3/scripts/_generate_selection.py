"""Generate the 2,000-contact selection CSV."""
import csv
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
engine = create_engine(os.environ["DATABASE_URL"])

ACTIVE_CIDS = [
    "H2C8QWP35CYFC8ZM", "6FLEGYS7RGQL483P",
    "2SAA6AP74RYPNDL3", "JDVTGVTLTS99ZXC3",
]
CUTOFF_CSV = "2025-07-29"   # 8-month gap for CSV contacts
CUTOFF_NEW = "2025-03-26"   # 1-year gap for wider pool

# Load CSV phones
csv_phones = set()
with open(ROOT.parent / "new_folder" / "dexter_final_numbers_appended.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        p = r.get("phone", "").strip()
        if p:
            csv_phones.add(p)


def load_exclusion_rules():
    with open(ROOT / "config" / "config.yml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    rules = cfg.get("exclusion_rules", {})
    return {
        "statuses": set(rules.get("excluded_statuses", [])),
        "tasks": set(rules.get("excluded_tasks", [])),
        "details": set(rules.get("excluded_anrufen_details", [])),
    }

EXCLUSION_RULES = load_exclusion_rules()


def is_excluded(anrufen_status_detail, anrufen_status, active_status, task=""):
    ansd = anrufen_status_detail or ""
    ans = anrufen_status or ""
    st = active_status or ""
    tsk = task or ""
    if st in EXCLUSION_RULES["statuses"] or ans in EXCLUSION_RULES["statuses"]:
        return True
    if tsk in EXCLUSION_RULES["tasks"]:
        return True
    if ansd in EXCLUSION_RULES["details"]:
        return True
    return False


with engine.connect() as conn:
    # Get best contact data per phone (from any campaign, prefer row with PLZ)
    # Plus last Dexter call date
    # Plus status in active campaigns (for closing)
    rows = conn.execute(text("""
        WITH contact_best AS (
            SELECT DISTINCT ON ("$phone")
                "$phone" AS phone,
                "$id" AS contact_id,
                "$campaign_id" AS campaign_id,
                firma, plz, ort, strasse,
                "AP_Vorname" AS ap_vorname,
                "AP_Nachname" AS ap_nachname
            FROM public.contacts
            WHERE firma IS NOT NULL AND firma != ''
            ORDER BY "$phone",
                (CASE WHEN plz IS NOT NULL AND plz != '' THEN 0 ELSE 1 END),
                "$changed" DESC NULLS LAST
        ),
        last_calls AS (
            SELECT phone, max(started) AS last_call_date, count(*) AS total_calls
            FROM media_pipeline.audio_files
            WHERE b2_object_key LIKE 'dexter/audio/%%'
            GROUP BY phone
        ),
        active_campaign AS (
            SELECT DISTINCT ON ("$phone")
                "$phone" AS phone,
                "$id" AS active_contact_id,
                "$campaign_id" AS active_campaign_id,
                "$status" AS active_status,
                "$task" AS active_task,
                "$$anrufen_status" AS anrufen_status,
                "$$anrufen_status_detail" AS anrufen_status_detail
            FROM public.contacts
            WHERE "$campaign_id" IN (:ac0, :ac1, :ac2, :ac3)
            ORDER BY "$phone", "$changed" DESC NULLS LAST
        )
        SELECT cb.phone, cb.contact_id, cb.campaign_id,
               cb.firma, cb.plz, cb.ort, cb.strasse,
               cb.ap_vorname, cb.ap_nachname,
               lc.last_call_date, lc.total_calls,
               ac.active_contact_id, ac.active_campaign_id,
               ac.active_status, ac.active_task,
               ac.anrufen_status, ac.anrufen_status_detail
        FROM contact_best cb
        JOIN last_calls lc ON lc.phone = cb.phone
        LEFT JOIN active_campaign ac ON ac.phone = cb.phone
        ORDER BY lc.last_call_date ASC
    """), {
        "ac0": ACTIVE_CIDS[0], "ac1": ACTIVE_CIDS[1],
        "ac2": ACTIVE_CIDS[2], "ac3": ACTIVE_CIDS[3],
    }).fetchall()

by_phone = {}
for r in rows:
    by_phone[r[0]] = {
        "phone": r[0],
        "contact_id": r[1], "campaign_id": r[2],
        "firma": r[3], "plz": r[4], "ort": r[5], "strasse": r[6],
        "ap_vorname": r[7] or "", "ap_nachname": r[8] or "",
        "last_call_date": str(r[9])[:10] if r[9] else "",
        "total_calls": r[10] or 0,
        "active_contact_id": r[11] or "",
        "active_campaign_id": r[12] or "",
        "active_status": r[13] or "",
        "active_task": r[14] or "",
        "anrufen_status": r[15] or "",
        "anrufen_status_detail": r[16] or "",
    }

# Part 1: from CSV, last called before July 29 2025
selection = []
for p in sorted(csv_phones):
    if p not in by_phone:
        continue
    d = by_phone[p]
    if not d["plz"] or not d["firma"]:
        continue
    if not d["last_call_date"] or d["last_call_date"] >= CUTOFF_CSV:
        continue
    if is_excluded(d["anrufen_status_detail"], d["anrufen_status"], d["active_status"], d.get("active_task", "")):
        continue
    d["source"] = "csv_selection"
    selection.append(d)

print(f"From CSV: {len(selection)}")

# Part 2: from wider pool, last called before March 26 2025 (1yr gap)
need = 2000 - len(selection)
pool = []
for phone in sorted(by_phone, key=lambda p: by_phone[p]["last_call_date"] or "9999"):
    if phone in csv_phones:
        continue
    d = by_phone[phone]
    if not d["plz"] or not d["firma"]:
        continue
    if not d["last_call_date"] or d["last_call_date"] >= CUTOFF_NEW:
        continue
    if is_excluded(d["anrufen_status_detail"], d["anrufen_status"], d["active_status"], d.get("active_task", "")):
        continue
    d["source"] = "wider_pool"
    pool.append(d)

selection.extend(pool[:need])
print(f"From wider pool: {min(need, len(pool))}")
print(f"Total selection: {len(selection)}")

# Write CSV
fieldnames = [
    "phone", "firma", "plz", "ort", "strasse",
    "ap_vorname", "ap_nachname",
    "last_call_date", "total_calls", "source",
    "active_contact_id", "active_campaign_id",
    "active_status", "active_task",
    "anrufen_status", "anrufen_status_detail",
    "action_needed",
]

outrows = []
needs_closing = 0
already_clear = 0

for d in selection:
    if d["active_contact_id"]:
        action = "close_in_old_campaign"
        needs_closing += 1
    else:
        action = "none"
        already_clear += 1

    outrows.append({
        **{k: d.get(k, "") for k in fieldnames if k != "action_needed"},
        "action_needed": action,
    })

outpath = ROOT / "runs" / "selection_2000.csv"
outpath.parent.mkdir(parents=True, exist_ok=True)
with open(outpath, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(outrows)

dates = [d["last_call_date"] for d in selection if d["last_call_date"]]
print(f"\nWritten to: {outpath}")
print(f"\nACTION SUMMARY:")
print(f"  Need closing in old campaign: {needs_closing}")
print(f"  Already clear (no action):    {already_clear}")
print(f"\n  From CSV selection:  {sum(1 for d in selection if d['source'] == 'csv_selection')}")
print(f"  From wider pool:     {sum(1 for d in selection if d['source'] == 'wider_pool')}")
print(f"\n  Last call range: {min(dates)} to {max(dates)}")
