import os, json, csv, re
from pathlib import Path

SRC = Path("data_pipelines_dexter/data/transcription_dexter_analysis/runs/2025-09-29/raw/dexter_free_extraction.jsonl")
DST = Path("data_pipelines_dexter/data/transcription_dexter_analysis/runs/2025-09-29/interim/dexter_free_extraction.csv")

fields = [
    "input_index","phone","campaign_name","num_calls_in_group","latest_started","selected_call_started","truncated_chars",
    "outcome_free_text","reason_free_text","who_reached","evidence_quote","confidence",
    "_cache_hit","_evidence_mismatch","model","run_ts"
]

DST.parent.mkdir(parents=True, exist_ok=True)
with SRC.open("r", encoding="utf-8") as f, DST.open("w", newline="", encoding="utf-8") as g:
    w = csv.DictWriter(g, fieldnames=fields)
    w.writeheader()
    for line in f:
        o = json.loads(line)
        row = {k: o.get(k, "") for k in fields}
        w.writerow(row)
print("Wrote:", DST)
