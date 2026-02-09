import argparse
import csv
import json
import os
from pathlib import Path

fields = [
    "input_index","phone","campaign_name","num_calls_in_group","latest_started","selected_call_started","truncated_chars",
    "outcome_free_text","reason_free_text","who_reached","evidence_quote","confidence",
    "_cache_hit","_evidence_mismatch","model","run_ts"
]

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Convert raw dexter_free_extraction.jsonl to an interim review CSV")
    p.add_argument(
        "--run",
        default=os.environ.get("DEXTER_RUN") or "",
        help="Run folder (contains raw/). If omitted, uses DEXTER_RUN env var.",
    )
    p.add_argument("--src", default=None, help="Optional explicit path to raw JSONL (overrides --run)")
    p.add_argument("--dst", default=None, help="Optional explicit path to output CSV (overrides --run)")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.src:
        src = Path(args.src)
    else:
        if not args.run:
            raise SystemExit("Provide --run or set DEXTER_RUN, or pass --src explicitly.")
        src = Path(args.run) / "raw" / "dexter_free_extraction.jsonl"

    if args.dst:
        dst = Path(args.dst)
    else:
        if not args.run:
            raise SystemExit("Provide --run or set DEXTER_RUN, or pass --dst explicitly.")
        dst = Path(args.run) / "interim" / "dexter_free_extraction.csv"

    if not src.exists():
        raise SystemExit(f"Raw JSONL not found: {src}")

    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open("r", encoding="utf-8") as f, dst.open("w", newline="", encoding="utf-8") as g:
        w = csv.DictWriter(g, fieldnames=fields)
        w.writeheader()
        for line in f:
            o = json.loads(line)
            row = {k: o.get(k, "") for k in fields}
            w.writerow(row)

    print("Wrote:", dst)


if __name__ == "__main__":
    main()
